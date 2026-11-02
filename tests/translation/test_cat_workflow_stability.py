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
