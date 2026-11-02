# -*- coding: utf-8 -*-
import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_tc_stab_01_continuous_progress_beyond_85(qapp):
    """
    Tác vụ 1.1: Tiến trình suy luận không bị kẹt ở mốc 85%.
    Khi mô hình suy luận lâu (<think>), tiến trình tiếp tục tăng mượt từ 85% -> 95%.
    """
    model = SubtitleModel()
    controller = TranslationController(subtitle_model=model)

    controller._status = "TRANSLATING"
    controller._translation_progress = 85
    controller._progress_tick_count = 0

    # Chạy tick 24 lần (tương đương 6 giây nếu tick = 250ms)
    for _ in range(24):
        controller._on_thinking_progress_tick()

    assert controller.translationProgress > 85, (
        f"Lỗi: Tiến trình dịch bị kẹt cứng ở mốc {controller.translationProgress}%! "
        "Kỳ vọng tiến trình tiếp tục tiệm cận lên vùng 86% - 95%."
    )
    assert controller.translationProgress <= 95, (
        f"Lỗi: Tiến trình suy luận vượt quá 95% ({controller.translationProgress}%) trước khi nhận token!"
    )


def test_tc_stab_01_selection_preserves_translating_progress(qapp):
    """
    Tác vụ 1.1: Bảo toàn mốc tiến trình khi người dùng chọn lại câu đang dịch.
    loadSubtitle(index) không được reset cứng về 0% nếu câu đó đang trong quá trình dịch.
    """
    model = SubtitleModel()
    model.load_data([
        {"id": "s1", "original": "Hello", "translation": "", "status": "PENDING"},
        {"id": "s2", "original": "World", "translation": "", "status": "PENDING"},
    ])
    controller = TranslationController(subtitle_model=model)

    controller._active_translation_index = 0
    controller._status = "TRANSLATING"
    controller._translation_progress = 65

    # Người dùng bấm chọn lại câu 0 trong danh sách
    controller.loadSubtitle(0)

    assert controller.translationProgress == 65, (
        f"Lỗi: Tiến trình dịch bị reset về {controller.translationProgress}% khi chọn lại câu đang dịch!"
    )
    assert controller.status == "TRANSLATING"


def test_tc_stab_02_cancel_translation_resets_state(qapp):
    """
    Tác vụ 2.1: Slot cancelTranslation() ngắt worker, reset trạng thái về PENDING và progress về 0.
    """
    model = SubtitleModel()
    model.load_data([
        {"id": "s1", "original": "Hello", "translation": "", "status": "PENDING"},
    ])
    controller = TranslationController(subtitle_model=model)

    assert hasattr(controller, "cancelTranslation"), "TranslationController phải có slot cancelTranslation"

    controller._current_index = 0
    controller._active_translation_index = 0
    controller._status = "TRANSLATING"
    controller._translation_progress = 50
    model.update_translation(0, "partial...", "TRANSLATING")

    # Bấm hủy dịch
    controller.cancelTranslation()

    assert controller.status == "PENDING"
    assert controller.translationProgress == 0
    assert controller._active_translation_index == -1
    sub = model.get_all_data()[0]
    assert sub["status"] == "PENDING"


def test_tc_stab_03_empty_queue_guard_blocks_stale_worker(qapp):
    """
    Tác vụ 3.1: Khi hàng đợi rỗng (_current_index == -1), tín hiệu từ worker cũ không được phép
    làm sống lại giao diện (không được set status thành TRANSLATING/TRANSLATED).
    """
    model = SubtitleModel()
    model.load_data([])
    controller = TranslationController(subtitle_model=model)

    controller.loadSubtitle(-1)
    assert controller.status == "IDLE"
    assert controller.currentTranslation == ""

    # Mô phỏng worker rác phát tín hiệu progress và finished
    controller._active_translation_index = 0
    controller.on_progress(0, "Stale text from dead worker")

    assert controller.status == "IDLE", (
        f"Lỗi bảo vệ hàng đợi: on_progress làm sống lại status={controller.status} khi queue rỗng!"
    )
    assert controller.currentTranslation == ""

    controller.on_finished(0, "Stale finished translation")
    assert controller.status == "IDLE", (
        f"Lỗi bảo vệ hàng đợi: on_finished làm sống lại status={controller.status} khi queue rỗng!"
    )
    assert controller.currentTranslation == ""


def test_tc_stab_04_hallucination_validator():
    """
    Tác vụ 4.1: SubtitleGenerationValidator loại bỏ các từ ảo giác Whisper ngoại lai
    (như 'Diyorlar.', 'thank you.', 'watching!').
    """
    from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
    from core.subtitle_generation.subtitle_generation_result import WhisperSegmentResult

    segments = [
        WhisperSegmentResult(1000, 2000, "Diyorlar."),
        WhisperSegmentResult(2500, 3500, "diyorlar"),
        WhisperSegmentResult(4000, 5000, "Thank you."),
        WhisperSegmentResult(5500, 6500, "Thanks for watching!"),
        WhisperSegmentResult(7000, 8000, "俺に忠誠を誓うというか"),
    ]

    valid = SubtitleGenerationValidator.validate(segments, batch_start_ms=0, batch_end_ms=10000)
    assert len(valid) == 1, f"Kỳ vọng lọc bỏ 4 câu ảo giác, nhưng còn lại {len(valid)} câu: {[s.text for s in valid]}"
    assert valid[0].text == "俺に忠誠を誓うというか"



