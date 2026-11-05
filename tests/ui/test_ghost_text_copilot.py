import pytest
import time
from core.database.tm_manager import TranslationMemoryManager
from core.translation.controllers.translation_controller import TranslationController
from unittest.mock import MagicMock

class MockSubtitleModel:
    def __init__(self):
        self.modelReset = MagicMock()
        self.dataChanged = MagicMock()

@pytest.fixture
def memory_tm():
    tm = TranslationMemoryManager(db_path=":memory:")
    tm.add_segment(
        source_text="Hello world, welcome to our AI Subtitle Suite channel.",
        target_text="Xin chào thế giới, chào mừng bạn đến với kênh AI Subtitle Suite của chúng tôi."
    )
    tm.add_segment(
        source_text="This is a fantastic tool for video editors.",
        target_text="Đây là một công cụ tuyệt vời dành cho các biên tập viên video."
    )
    return tm

def test_tm_query_copilot_prefix_exact_and_case_insensitive(memory_tm):
    # 1. Khớp chính xác tiền tố viết hoa
    res = memory_tm.query_copilot_prefix("Xin ch")
    assert res is not None
    assert res.startswith("Xin chào")

    # 2. Khớp tiền tố không phân biệt hoa thường
    res_lower = memory_tm.query_copilot_prefix("xin")
    assert res_lower is not None
    assert "Xin chào thế giới" in res_lower

    # 3. Tiền tố thứ hai
    res2 = memory_tm.query_copilot_prefix("Đây là một")
    assert res2 is not None
    assert "công cụ tuyệt vời" in res2

    # 4. Tiền tố không tồn tại -> None
    res_none = memory_tm.query_copilot_prefix("Không tồn tại")
    assert res_none is None

    # 5. Chuỗi rỗng -> None
    assert memory_tm.query_copilot_prefix("") is None

def test_tm_query_copilot_prefix_latency_under_50ms(memory_tm):
    # Ràng buộc FR-06: Độ trễ truy vấn SQLite FTS5 / index < 50ms
    start = time.perf_counter()
    for _ in range(20):
        memory_tm.query_copilot_prefix("Xin ch")
    elapsed_total = (time.perf_counter() - start) * 1000 # ms
    avg_latency = elapsed_total / 20
    assert avg_latency < 50.0 # Bắt buộc dưới 50ms

def test_translation_controller_ghost_text_lifecycle(memory_tm, qapp):
    mock_model = MockSubtitleModel()
    controller = TranslationController(subtitle_model=mock_model)
    controller.set_translation_memory(memory_tm)

    # Đặt source hiện tại
    controller._current_original = "Hello world, welcome to our AI Subtitle Suite channel."

    # 1. Khi chưa gõ gì: ghostText phải rỗng
    controller.updateCurrentTranslation("")
    assert controller.ghostText == ""

    # 2. Người dùng gõ "Xin "
    controller.updateCurrentTranslation("Xin ")
    expected_full = "Xin chào thế giới, chào mừng bạn đến với kênh AI Subtitle Suite của chúng tôi."
    expected_remainder = expected_full[len("Xin "):]
    assert controller.ghostText == expected_remainder

    # 3. Thao tác acceptNextWord() (tương đương Ctrl + Right)
    controller.acceptNextWord()
    # Từ tiếp theo là "chào"
    assert controller.currentTranslation == "Xin chào"
    assert controller.ghostText == expected_full[len("Xin chào"):]

    # 4. Thao tác acceptGhostText() (tương đương Tab)
    controller.acceptGhostText()
    assert controller.currentTranslation == expected_full
    assert controller.ghostText == ""

    # 5. Khi gõ sai lệch
    controller.updateCurrentTranslation("Xin lỗi bạn nhiều")
    assert controller.ghostText == ""
