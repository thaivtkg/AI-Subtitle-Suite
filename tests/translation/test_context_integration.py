import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from core.translation.core.prompt_builder import PromptBuilder
from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel
from core.translation.core.translation_memory import TranslationMemory, TMEntry
from core.translation.core.glossary import Glossary, GlossaryHit
from core.translation.core.entity_dictionary import EntityDictionary, EntityHit
from core.translation.services.translation_pipeline_adapter import TranslationPipelineAdapter
from tests.translation.e2e.deterministic_worker import DeterministicWorkerFactory


# --- TIỆN ÍCH CAPTURE SIGNAL VÀ CHỜ EVENT LOOP ---

class SignalSpy:
    """Giả lập QSignalSpy linh hoạt cho PySide6, hỗ trợ len, chỉ mục và chờ event loop."""
    def __init__(self, signal):
        self._emissions = []
        self._signal = signal
        signal.connect(self._slot)

    def _slot(self, *args):
        self._emissions.append(list(args))

    def wait(self, timeout_ms=500):
        app = QCoreApplication.instance()
        elapsed = 0
        while elapsed < timeout_ms and not self._emissions:
            if app:
                app.processEvents()
            QTest.qWait(10)
            elapsed += 10
        return len(self._emissions) > 0

    def __len__(self):
        return len(self._emissions)

    def __getitem__(self, index):
        return self._emissions[index]

    def count(self):
        return len(self._emissions)


# Alias tương thích với tên gọi QSignalSpy
QSignalSpy = SignalSpy


@pytest.fixture
def qtbot():
    """Khởi tạo QApplication nếu chưa có cho các test case Qt."""
    return QGuiApplication.instance() or QGuiApplication([])


# --- PROMPT BUILDER TESTS (TC-P3B4-01, TC-P3B4-02, TC-P3B4-03, TC-P3B4-06..12) ---

def test_tc_p3b4_01_no_hits_no_injection():
    """TC-P3B4-01 & TC-P3B4-11: Khi không có hit nào, không chèn PROJECT-SPECIFIC TRANSLATION RULES."""
    prompt = PromptBuilder.build("Story", "English", "Vietnamese", [], "Hello", [])
    assert "PROJECT-SPECIFIC TRANSLATION RULES" not in prompt
    assert "[GLOSSARY]" not in prompt
    assert "[ENTITIES]" not in prompt


def test_tc_p3b4_02_glossary_injection_with_forbidden():
    """TC-P3B4-02 & TC-P3B4-07: Glossary hit kèm forbidden alternatives được chèn mệnh lệnh cấm."""
    hit = GlossaryHit("King", "Vua", 0, 4)
    forbidden = ("Quốc vương", "Chúa")
    prompt = PromptBuilder.build("Story", "Eng", "Vie", [], "King", [], glossary_hits=[(hit, forbidden)])
    assert "[GLOSSARY]" in prompt
    assert '- "King" MUST be translated as "Vua". (ABSOLUTELY FORBIDDEN: "Quốc vương", "Chúa")' in prompt


def test_tc_p3b4_03_entity_injection():
    """TC-P3B4-03 & TC-P3B4-08: Entity hit được format đầy đủ matched_form, entity_type, canonical_name."""
    hit = EntityHit("Tony Stark", "Iron Man", "Tony Stark", "CHARACTER", 0, 8)
    prompt = PromptBuilder.build("Story", "Eng", "Vie", [], "Iron Man", [], entity_hits=[hit])
    assert "[ENTITIES]" in prompt
    assert '- "Iron Man" (CHARACTER, canonical name: "Tony Stark") MUST be translated as "Tony Stark".' in prompt


def test_tc_p3b4_06_glossary_prompt_injection():
    """TC-P3B4-06: Matched glossary hits được format chuẩn dưới mục [GLOSSARY]."""
    hit = GlossaryHit("potion", "thuốc lắc", 0, 6)
    prompt = PromptBuilder.build("Story", "English", "Vietnamese", [], "potion", [], glossary_hits=[(hit, ())])
    assert "[GLOSSARY]" in prompt
    assert '- "potion" MUST be translated as "thuốc lắc".' in prompt
    assert "ABSOLUTELY FORBIDDEN" not in prompt


def test_tc_p3b4_07_forbidden_alternatives_clause():
    """TC-P3B4-07: Từ cấm xuất hiện chính xác khi có forbidden_alternatives."""
    hit = GlossaryHit("magic", "phép thuật", 5, 10)
    prompt = PromptBuilder.build("Story", "English", "Vietnamese", [], "some magic", [], glossary_hits=[(hit, ("ma thuật",))])
    assert '- "magic" MUST be translated as "phép thuật". (ABSOLUTELY FORBIDDEN: "ma thuật")' in prompt


def test_tc_p3b4_08_entity_prompt_injection():
    """TC-P3B4-08: Entity location injection hiển thị đúng thuộc tính."""
    hit = EntityHit("Wakanda", "Wakanda", "Wakanda", "LOCATION", 0, 7)
    prompt = PromptBuilder.build("Story", "English", "Vietnamese", [], "Wakanda", [], entity_hits=[hit])
    assert '[ENTITIES]' in prompt
    assert '- "Wakanda" (LOCATION, canonical name: "Wakanda") MUST be translated as "Wakanda".' in prompt


def test_tc_p3b4_09_selective_injection_only(qtbot):
    """TC-P3B4-09: Chỉ inject những terms/entities thực sự xuất hiện trong câu subtitle."""
    glossary = Glossary([
        ("King", "Vua", ()),
        ("Queen", "Hoàng hậu", ()),
    ])
    entities = EntityDictionary([
        ("Stark", "LOCATION", "Nhà Stark", ()),
        ("Lannister", "ORGANIZATION", "Nhà Lannister", ()),
    ])
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "The King visits Stark castle", "translation": "", "status": "PENDING"}])
    
    captured_prompts = []
    class InterceptFactory:
        def create_worker(self, target_index, prompt, profile):
            captured_prompts.append(prompt)
            return DeterministicWorkerFactory("fast").create_worker(target_index, prompt, profile)

    controller = TranslationController(model, worker_factory=InterceptFactory())
    controller.bind_intelligence(glossary=glossary, entities=entities)
    controller.requestTranslation(0, "English", "Vietnamese", "Story")

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "King" in prompt
    assert "Stark" in prompt
    assert "Queen" not in prompt
    assert "Lannister" not in prompt
    controller.worker.wait(1000)


def test_tc_p3b4_10_deterministic_hit_ordering():
    """TC-P3B4-10: Injected glossary và entity xuất hiện theo thứ tự tăng dần của start position."""
    hit1 = GlossaryHit("first", "thứ nhất", 0, 5)
    hit2 = GlossaryHit("second", "thứ hai", 10, 16)
    # Truyền ngược thứ tự hit2 trước, hit1 sau
    prompt = PromptBuilder.build("Story", "Eng", "Vie", [], "first and second", [], glossary_hits=[(hit2, ()), (hit1, ())])
    idx_first = prompt.find('"first"')
    idx_second = prompt.find('"second"')
    assert idx_first < idx_second


def test_tc_p3b4_12_coexistence_in_prompt():
    """TC-P3B4-12: Khi có cả glossary và entities, cả hai khối cùng hiển thị chuẩn xác."""
    ghit = GlossaryHit("sword", "thanh kiếm", 0, 5)
    ehit = EntityHit("Excalibur", "Excalibur", "Thánh kiếm", "ITEM", 10, 19)
    prompt = PromptBuilder.build("Story", "Eng", "Vie", [], "sword and Excalibur", [], glossary_hits=[(ghit, ())], entity_hits=[ehit])
    assert "[GLOSSARY]" in prompt
    assert "[ENTITIES]" in prompt
    assert prompt.find("[GLOSSARY]") < prompt.find("[ENTITIES]")


# --- TRANSLATION CONTROLLER & SHORT-CIRCUIT TESTS (TC-P3B4-04..05, 13..14) ---

def test_tc_p3b4_tm_short_circuit(qtbot):
    """TC-P3B4-01 & 02: TM hit không tạo worker, cập nhật TRANSLATED và phát tín hiệu an toàn."""
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "Hello", "translation": "", "status": "PENDING"}])
    controller = TranslationController(model)
    
    tm = TranslationMemory.from_entries([("Hello", "Xin chào")])
    controller.bind_intelligence(translation_memory=tm)
    
    spy_completed = QSignalSpy(controller.translationCompleted)
    spy_updated = QSignalSpy(controller.translationUpdated)
    
    # Kích hoạt dịch thuật
    controller.requestTranslation(0, "English", "Vietnamese", "Story")
    
    # Kiểm tra trạng thái đã cập nhật ngay lập tức
    assert model.get_all_data()[0]["status"] == "TRANSLATED"
    assert model.get_all_data()[0]["translation"] == "Xin chào"
    assert controller.status == "TRANSLATED"
    assert controller.currentTranslation == "Xin chào"
    assert controller.worker is None
    
    # Đợi Event Loop xử lý QTimer.singleShot(0, ...)
    spy_completed.wait(100)
    assert len(spy_completed) == 1
    assert spy_completed[0][0] == 0  # Trả về đúng index
    assert len(spy_updated) >= 1
    assert spy_updated[-1][0] == "Xin chào"


def test_tc_p3b4_03_status_invariant_never_accepted(qtbot):
    """TC-P3B4-03: TM short-circuit đánh dấu TRANSLATED, tuyệt đối không tự ý đánh ACCEPTED."""
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "Repeat", "translation": "", "status": "PENDING"}])
    controller = TranslationController(model)
    controller.bind_intelligence(translation_memory=TranslationMemory.from_entries([("Repeat", "Lặp lại")]))
    
    controller.requestTranslation(0, "English", "Vietnamese", "Story")
    status = model.get_all_data()[0]["status"]
    assert status == "TRANSLATED"
    assert status != "ACCEPTED"


def test_tc_p3b4_04_zero_worker_overhead(qtbot):
    """TC-P3B4-04: Tuyệt đối không tạo hay khởi chạy TranslationWorker khi TM hit."""
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "Hit", "translation": "", "status": "PENDING"}])
    controller = TranslationController(model)
    controller.bind_intelligence(translation_memory=TranslationMemory.from_entries([("Hit", "Đánh trúng")]))
    
    controller.requestTranslation(0, "English", "Vietnamese", "Story")
    assert controller.worker is None
    assert controller._worker is None


def test_tc_p3b4_05_tm_miss_proceeds_to_worker(qtbot):
    """TC-P3B4-05: Khi TM miss, tiếp tục luồng tạo Worker thông thường."""
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "Miss", "translation": "", "status": "PENDING"}])
    controller = TranslationController(model, worker_factory=DeterministicWorkerFactory("fast"))
    controller.bind_intelligence(translation_memory=TranslationMemory.from_entries([("Other", "Khác")]))
    
    controller.requestTranslation(0, "English", "Vietnamese", "Story")
    assert controller.worker is not None
    assert controller.worker.isRunning()
    controller.worker.wait(1000)


def test_tc_p3b4_13_batch_pipeline_integration(qtbot):
    """TC-P3B4-13: Batch pipeline phối hợp mượt mà với TM short-circuit qua TranslationPipelineAdapter."""
    model = SubtitleModel()
    model.load_data([
        {"index": 0, "original": "Line 0 TM Hit", "translation": "", "status": "PENDING"},
    ])
    controller = TranslationController(model, worker_factory=DeterministicWorkerFactory("fast"))
    controller.bind_intelligence(translation_memory=TranslationMemory.from_entries([("Line 0 TM Hit", "Dòng 0 Đã Dịch")]))
    adapter = TranslationPipelineAdapter(controller)

    successes = []
    errors = []
    adapter.translate(0, lambda idx: successes.append(idx), lambda idx, err: errors.append((idx, err)))

    spy = SignalSpy(controller.translationCompleted)
    spy.wait(200)

    assert 0 in successes
    assert len(errors) == 0
    assert model.get_all_data()[0]["status"] == "TRANSLATED"
    assert model.get_all_data()[0]["translation"] == "Dòng 0 Đã Dịch"


def test_tc_p3b4_unbound_controller_fallback(qtbot):
    """TC-P3B4-14: Kiểm tra tương thích ngược khi không bind intelligence."""
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "Hello", "translation": "", "status": "PENDING"}])
    controller = TranslationController(model)
    # Không gọi bind_intelligence()
    
    # Gọi không crash và xử lý như bình thường (ví dụ: tạo worker vì TM miss)
    controller.requestTranslation(0, "English", "Vietnamese", "Story")
    assert controller._worker is not None  # Khởi tạo luồng bình thường
    controller._worker.wait(1000)


