# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtCore import QTimer
from core.translation.core.prompt_builder import PromptBuilder, format_chat
from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel


def test_prompt_builder_deepseek_closes_think_tag():
    """Tác vụ 2: Đóng thẻ think ngay trong prompt DeepSeek-R1 để kích hoạt zero-think instant generation."""
    prompt = PromptBuilder.build(
        story_summary="Summary",
        current_sub="こんにちは",
        model_family="deepseek",
    )
    assert "<｜Assistant｜><think>\n</think>\n" in prompt
    assert not prompt.rstrip().endswith("<think>")


def test_thinking_progress_dynamic_crawls_to_98():
    """Tác vụ 3: Tiến độ không bị dừng chết ở 95%, tiếp tục tiệm cận lên 98%."""
    model = SubtitleModel()
    ctrl = TranslationController(model)
    ctrl._status = "TRANSLATING"
    ctrl._translation_progress = 95
    ctrl._progress_tick_count = 0

    # Chạy 12 ticks
    for _ in range(12):
        ctrl._on_thinking_progress_tick()

    assert ctrl.translationProgress == 96

    # Tiếp tục chạy thêm 24 ticks -> lên 98
    for _ in range(24):
        ctrl._on_thinking_progress_tick()

    assert ctrl.translationProgress == 98

    # Chạy thêm nữa không vượt quá 98%
    for _ in range(20):
        ctrl._on_thinking_progress_tick()

    assert ctrl.translationProgress == 98
    ctrl.shutdown()


def test_translation_watchdog_timeout_triggers_error():
    """Tác vụ 3: Watchdog Timeout tự động hủy và đưa về trạng thái ERROR khi worker đơ."""
    model = SubtitleModel()
    model.load_data([{"id": 1, "original": "Test line", "translation": "", "status": "PENDING"}])
    ctrl = TranslationController(model)
    ctrl._status = "TRANSLATING"
    ctrl._active_translation_index = 0
    ctrl._current_index = 0

    failed_signals = []
    ctrl.translationFailed.connect(lambda idx, err: failed_signals.append((idx, err)))

    ctrl._on_translation_timeout()

    assert ctrl.status == "ERROR"
    assert "vượt quá 90s" in ctrl.currentTranslation
    assert len(failed_signals) == 1
    assert failed_signals[0][0] == 0
    ctrl.shutdown()


def test_gui_startup_clears_stale_pytest_or_temp_output_dir(qapp):
    """Tác vụ 1: Khởi động GUI tự động dọn sạch thư mục tạm của pytest hoặc Temp trong settings."""
    from ui.Gui import MainWindow
    
    stale_settings = {
        "output_dir": r"C:\Users\Kuroberus\AppData\Local\Temp\pytest-of-Kuroberus\pytest-273\test_dir"
    }
    
    with patch("ui.Gui.load_settings", return_value=stale_settings):
        win = MainWindow()
        # Xác nhận đường dẫn rác từ pytest bị reset sạch sẽ về rỗng
        assert win.out_input.text() == ""
        assert win.page_export.out_edit.text() == ""
        assert win.output_dir == ""
        win.close()


def test_persist_canonical_setting_ignores_temp_paths(qapp):
    """Tác vụ 1: Không bao giờ cho phép ghi đè đường dẫn rác pytest/temp vào settings.json thật."""
    from ui.Gui import MainWindow

    win = MainWindow()
    with patch("ui.Gui.save_settings") as mock_save:
        win._persist_canonical_setting("output_dir", r"C:\Users\Kuroberus\AppData\Local\Temp\pytest-273\abc")
        assert not mock_save.called

        # Đường dẫn bình thường của người dùng vẫn được lưu
        win._persist_canonical_setting("output_dir", r"D:\MyVideos\Subtitles")
        assert mock_save.called
    win.close()
