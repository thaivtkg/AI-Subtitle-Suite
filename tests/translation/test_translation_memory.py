from dataclasses import FrozenInstanceError
import pytest

from core.translation.core.translation_memory import TranslationMemory, TMEntry


# ---------------------------------------------------------------------------
# TC-P3B3-01  Valid entry preserves literal strings
# ---------------------------------------------------------------------------
def test_tc_p3b3_01_valid_entry_preserves_literal_values():
    entry = TMEntry("  Good morning, Captain.  ", "  Chào buổi sáng, Đại úy.  ")
    tm = TranslationMemory.from_entries([entry])
    assert tm.to_payload() == {
        "  Good morning, Captain.  ": {
            "target_text": "  Chào buổi sáng, Đại úy.  ",
        }
    }
    retrieved = tm.get("  Good morning, Captain.  ")
    assert retrieved is not None
    assert retrieved.source_text == "  Good morning, Captain.  "
    assert retrieved.target_text == "  Chào buổi sáng, Đại úy.  "


# ---------------------------------------------------------------------------
# TC-P3B3-02  Entry validity (rejects empty or whitespace-only)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "source_text,target_text",
    [
        ("", "Bản dịch"),
        ("   ", "Bản dịch"),
        ("Câu gốc", ""),
        ("Câu gốc", "   "),
    ],
)
def test_tc_p3b3_02_rejects_empty_or_whitespace_fields(source_text, target_text):
    with pytest.raises(ValueError):
        TranslationMemory.from_entries([(source_text, target_text)])


# ---------------------------------------------------------------------------
# TC-P3B3-03  Last-write-wins overwrite
# ---------------------------------------------------------------------------
def test_tc_p3b3_03_last_write_wins_overwrite():
    tm = TranslationMemory.from_entries([
        ("Hello world", "Chào thế giới"),
        ("Hello world", "Xin chào thế giới"),
    ])
    assert len(tm) == 1
    assert tm.lookup("Hello world").target_text == "Xin chào thế giới"

    # Dynamic overwrite via add()
    tm.add("Hello world", "Chào toàn thể nhân loại")
    assert len(tm) == 1
    assert tm.lookup("Hello world").target_text == "Chào toàn thể nhân loại"


# ---------------------------------------------------------------------------
# TC-P3B3-04  Update and remove
# ---------------------------------------------------------------------------
def test_tc_p3b3_04_update_and_remove():
    tm = TranslationMemory.from_entries([("Hello", "Chào")])
    tm.update("Hello", "Xin chào")
    assert tm.lookup("Hello").target_text == "Xin chào"

    with pytest.raises(KeyError):
        tm.update("NonExistent", "Bản dịch")

    tm.remove("Hello")
    assert len(tm) == 0
    assert tm.lookup("Hello") is None

    with pytest.raises(KeyError):
        tm.remove("NonExistent")


# ---------------------------------------------------------------------------
# TC-P3B3-05  Exact match 100%
# ---------------------------------------------------------------------------
def test_tc_p3b3_05_exact_match_100():
    tm = TranslationMemory.from_entries([
        ("All systems are operational.", "Tất cả hệ thống đã sẵn sàng."),
        ("Stand by.", "Chờ lệnh."),
    ])
    match = tm.lookup("All systems are operational.")
    assert match is not None
    assert match.source_text == "All systems are operational."
    assert match.target_text == "Tất cả hệ thống đã sẵn sàng."


# ---------------------------------------------------------------------------
# TC-P3B3-06  Case-sensitive lookup
# ---------------------------------------------------------------------------
def test_tc_p3b3_06_case_sensitive_lookup():
    tm = TranslationMemory.from_entries([
        ("Hello World", "Chào thế giới"),
    ])
    assert tm.lookup("hello world") is None
    assert tm.lookup("HELLO WORLD") is None
    assert tm.lookup("Hello World") is not None


# ---------------------------------------------------------------------------
# TC-P3B3-07  Whole-string boundary (substring does NOT match)
# ---------------------------------------------------------------------------
def test_tc_p3b3_07_whole_string_boundary():
    tm = TranslationMemory.from_entries([
        ("I like apples", "Tôi thích táo"),
    ])
    assert tm.lookup("apples") is None
    assert tm.lookup("like") is None
    assert tm.lookup("I like") is None
    assert tm.lookup("I like apples and oranges") is None
    assert tm.lookup("I like apples") is not None


# ---------------------------------------------------------------------------
# TC-P3B3-08  Whitespace sensitivity
# ---------------------------------------------------------------------------
def test_tc_p3b3_08_whitespace_sensitivity():
    tm = TranslationMemory.from_entries([
        ("Hello world", "Chào thế giới"),
    ])
    assert tm.lookup("Hello  world") is None
    assert tm.lookup(" Hello world") is None
    assert tm.lookup("Hello world ") is None
    assert tm.lookup("Hello\nworld") is None
    assert tm.lookup("Hello world") is not None


# ---------------------------------------------------------------------------
# TC-P3B3-09  Miss lookup returns None
# ---------------------------------------------------------------------------
def test_tc_p3b3_09_miss_lookup_returns_none():
    tm = TranslationMemory.from_entries([("A", "B")])
    assert tm.lookup("Unknown sentence") is None

    # Invalid query type raises ValueError
    with pytest.raises(ValueError):
        tm.lookup(123)


# ---------------------------------------------------------------------------
# TC-P3B3-10  Lookup immutability & frozen dataclass
# ---------------------------------------------------------------------------
def test_tc_p3b3_10_lookup_immutability():
    tm = TranslationMemory.from_entries([("Original", "Bản dịch")])
    before_payload = tm.to_payload()
    result = tm.lookup("Original")
    assert result is not None
    assert tm.to_payload() == before_payload

    # Frozen dataclass mutation attempt must fail
    with pytest.raises(FrozenInstanceError):
        result.target_text = "Hacked"


def test_logic_02_accept_translation_saves_to_tm_and_close_clears():
    """Kiểm tra LOGIC-02: Duyệt câu tự động lưu vào TM và đóng dự án dọn sạch _entries."""
    from unittest.mock import MagicMock
    from core.translation.controllers.translation_controller import TranslationController
    from core.translation.controllers.project_controller import ProjectController
    from core.translation.models.subtitle import SubtitleModel

    model = SubtitleModel()
    model.load_data([
        {"id": 1, "start_time": "00:00:01,000", "end_time": "00:00:02,000", "original": "How are you?", "translation": "", "status": "PENDING"}
    ])
    pc = ProjectController(subtitle_model=model)
    tc = TranslationController(subtitle_model=model)
    tc.bind_intelligence(
        glossary=pc.glossary,
        entities=pc.entity_dictionary,
        translation_memory=pc.translation_memory,
        project_controller=pc,
    )
    pc.bind_translation_controller(tc)

    # Ban đầu TM chưa có câu này
    assert pc.translation_memory.lookup("How are you?") is None

    # Kiểm tra index ngoài biên không gây crash hay UnboundLocalError
    assert tc.acceptTranslation(-1, "Lỗi index âm") is False
    assert tc.acceptTranslation(999, "Lỗi index quá lớn") is False

    # Người dùng duyệt bản dịch câu #0
    success = tc.acceptTranslation(0, "Bạn khỏe không?")
    assert success is True

    # Khẳng định câu đã được lưu vào Translation Memory!
    match = pc.translation_memory.lookup("How are you?")
    assert match is not None
    assert match.target_text == "Bạn khỏe không?"

    # Đóng dự án -> _entries trong TM phải được dọn sạch hoàn toàn
    pc.closeProject()
    assert len(pc.translation_memory._entries) == 0
    assert pc.translation_memory.lookup("How are you?") is None


