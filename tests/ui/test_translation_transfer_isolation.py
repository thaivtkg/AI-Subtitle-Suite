# -*- coding: utf-8 -*-
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication
from ui.Gui import MainWindow


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_switch_page_does_not_auto_transfer_selected_subtitles(app, monkeypatch):
    """
    Tác vụ 3: Khi người dùng chuyển sang Tab Dịch thuật (ID 8),
    hệ thống KHÔNG được tự động chuyển các dòng đang chọn trên SubEditor sang CAT Studio
    nếu người dùng không chủ động bấm lệnh chuyển dịch.
    """
    win = MainWindow()
    win.sub_editor.all_segments = [
        {"id": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Sub 1"},
        {"id": "2", "start": "00:00:04,000", "end": "00:00:06,000", "text": "Sub 2"},
        {"id": "3", "start": "00:00:07,000", "end": "00:00:09,000", "text": "Sub 3"},
    ]
    # Giả lập người dùng bôi đen nhiều dòng trên SubEditor
    monkeypatch.setattr(win.sub_editor, "_get_selected_source_indices", lambda: [0, 1, 2])
    win._pending_translation_indices = []

    # Chuyển sang trang Dịch thuật
    win.switch_page(8)

    # Bất biến: CAT Studio phải trống (0 câu), không bị tự động ép nạp các dòng đang chọn
    assert win.page_translation.subtitle_model.rowCount() == 0, (
        f"Lỗi: CAT Studio bị tự động nạp {win.page_translation.subtitle_model.rowCount()} câu khi chuyển tab!"
    )
    assert win._pending_translation_indices == []


def test_batch_scan_does_not_arm_pending_translation_indices(app):
    """
    Tác vụ 3: Batch Scan âm thanh KHÔNG được tự ý gán _pending_translation_indices.
    """
    win = MainWindow()
    win._pending_translation_indices = []
    # Gọi batch scan với selected_indices (kể cả khi không có video)
    win._on_batch_segment_scan_requested([0, 1])

    assert win._pending_translation_indices == [], (
        "Lỗi: _on_batch_segment_scan_requested tự ý gán _pending_translation_indices!"
    )


def test_explicit_send_to_translation_works(app):
    """
    Tác vụ 3: Chỉ khi người dùng chủ động gọi _on_send_selected_to_translation,
    phụ đề mới được đưa sang CAT Studio.
    """
    win = MainWindow()
    win.sub_editor.all_segments = [
        {"id": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Sub 1"},
        {"id": "2", "start": "00:00:04,000", "end": "00:00:06,000", "text": "Sub 2"},
    ]
    win._pending_translation_indices = []

    # Người dùng chủ động kích hoạt lệnh
    win._on_send_selected_to_translation([0, 1])

    assert win.page_translation.subtitle_model.rowCount() == 2
    assert win._pending_translation_indices == []
