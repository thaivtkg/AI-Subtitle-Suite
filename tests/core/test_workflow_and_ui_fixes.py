# -*- coding: utf-8 -*-
"""
Kiểm thử tự động xác minh các bản vá cho Phase 2 & Phase 3:
- BUG-DRAFT-001: SubEditor.save_draft() với đường dẫn tường minh không mở QFileDialog
- BUG-STYLE-CONFLICT-001: Hardsub lấy đúng style từ SubtitleInspectorPanel
- BUG-DRAFT-002: DraftCenterPage.scan_drafts() dọn dẹp widget cũ sạch sẽ, không đè EmptyState
- BUG-DRAWER-001: Drawer panel tự đóng khi rời Studio Workspace và khôi phục khi quay lại
- BUG-DUP-WIDGET-001: SubtitleGenerationPanel chỉ có duy nhất 1 khung Generation History
- BUG-NAV-001: lbl_page_title đồng bộ chính xác khi chuyển tab (ví dụ "Draft Center")
- BUG-QML-TEARDOWN-001: cancelTranslation() và callback an toàn khi SubtitleModel bị hủy
"""
import os
import json
import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QGroupBox, QWidget


def test_bug_draft_001_save_draft_with_explicit_path_does_not_open_dialog(qapp, tmp_path):
    from ui.SubEditor import SubtitleEditorWidget
    
    editor = SubtitleEditorWidget()
    editor.project_service = MagicMock()
    editor.all_segments = [{"stt": 1, "text": "Draft Line 1"}]
    
    target_file = str(tmp_path / "custom_draft.ai-subtitle-draft")
    
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName") as mock_dialog:
        # Gọi với filepath rõ ràng và silent=False
        result_path = editor.save_draft(filepath=target_file, silent=False)
        
        # Đảm bảo QFileDialog KHÔNG BAO GIỜ bị gọi
        mock_dialog.assert_not_called()
        
        # Đảm bảo trả về đúng đường dẫn và project_service.save_draft được gọi
        assert result_path == target_file
        editor.project_service.save_draft.assert_called_once_with(target_file, editor.all_segments)


def test_bug_style_conflict_001_hardsub_uses_inspector_style(qapp, tmp_path):
    from ui.Gui import MainWindow
    from tests.uat.conftest import MockProjectService

    win = MainWindow(project_service=MockProjectService(str(tmp_path)))
    
    # Thiết lập style trong inspector_panel
    win.inspector_panel.cmb_font.setCurrentFont("Courier New")
    win.inspector_panel.spin_size.setValue(48)
    win.inspector_panel.spin_outline.setValue(5.0)
    
    # Chuẩn bị môi trường hardsub
    video_file = str(tmp_path / "test.mp4")
    srt_file = str(tmp_path / "test.srt")
    with open(video_file, "w") as f: f.write("video")
    with open(srt_file, "w") as f: f.write("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    
    win.queue_mgr.active_vid = video_file
    win.queue_mgr.active_item_key = video_file
    win.queue_mgr.get_srt_for_video = lambda v: srt_file
    win.sub_editor.all_segments = [{"start": "00:00:01,000", "end": "00:00:02,000", "text": "Hello"}]
    
    with patch("ui.Gui.HardsubWorker") as mock_worker_cls:
        mock_worker_instance = MagicMock()
        mock_worker_cls.return_value = mock_worker_instance
        
        win._trigger_export_hardsub()
        
        assert mock_worker_cls.called
        kwargs = mock_worker_cls.call_args[1]
        
        # Xác minh font_size và outline_width được lấy từ inspector_panel thay vì page_settings mặc định
        assert kwargs["font_size"] == 48
        assert kwargs["font_name"] == "Courier New"
        assert kwargs["outline_width"] == 5.0
    win.close()


def test_bug_draft_002_draft_center_clears_old_widgets_cleanly(qapp, tmp_path):
    from ui.pages.draft_center_page import DraftCenterPage
    
    page = DraftCenterPage()
    # Ban đầu không có draft -> tạo empty_state
    page.set_directory(str(tmp_path))
    assert page.empty_state is not None
    assert page.cards_layout.count() == 1
    
    old_empty_state = page.empty_state
    
    # Tạo 1 file draft trong thư mục
    draft_path = str(tmp_path / "test1.ai-subtitle-draft")
    with open(draft_path, "w", encoding="utf-8") as f:
        json.dump({"segments": [{"text": "Sample"}]}, f)
        
    # Nạp lại
    page.scan_drafts()
    
    # Xác minh: old_empty_state đã bị ẩn và tách khỏi parent, cards_layout chỉ chứa thẻ draft mới
    assert old_empty_state.isHidden()
    assert old_empty_state.parent() is None
    assert page.empty_state is None
    assert page.cards_layout.count() == 1


def test_bug_drawer_001_switching_page_hides_overlay_host(qapp, tmp_path):
    from ui.Gui import MainWindow
    from tests.uat.conftest import MockProjectService

    win = MainWindow(project_service=MockProjectService(str(tmp_path)))
    win.resize(1000, 700)
    win.show()
    
    # Ở Studio Workspace, mở drawer
    win.switch_page(1)
    win._toggle_ai_drawer()
    assert win.overlay_host.isVisible()
    assert win.btn_drawer_toggle.isVisible()
    
    # Chuyển sang Draft Center (tab 4)
    win.switch_page(4)
    assert not win.overlay_host.isVisible()
    assert not win.btn_drawer_toggle.isVisible()
    
    # Chuyển sang Dịch thuật AI (tab 8)
    win.switch_page(8)
    assert not win.overlay_host.isVisible()
    assert not win.btn_drawer_toggle.isVisible()
    
    # Quay lại Studio Workspace (tab 1) -> Tự động khôi phục trạng thái mở của drawer
    win.switch_page(1)
    assert win.overlay_host.isVisible()
    assert win.btn_drawer_toggle.isVisible()
    win.close()


def test_bug_dup_widget_001_single_history_group_in_generation_panel(qapp):
    from ui.subtitle_generation_panel import SubtitleGenerationPanel
    
    panel = SubtitleGenerationPanel(MagicMock())
    
    # Tìm tất cả QGroupBox có tiêu đề Generation History
    groups = [
        w for w in panel.findChildren(QGroupBox)
        if "Generation History" in w.title()
    ]
    
    # Xác minh chỉ có đúng 1 group duy nhất
    assert len(groups) == 1
    # Group duy nhất chứa cả history_list và các nút quick rollback
    assert hasattr(panel, "history_list")
    assert hasattr(panel, "btn_rollback")
    assert hasattr(panel, "btn_rb_10")
    assert hasattr(panel, "btn_rb_initial")


def test_bug_nav_001_page_title_updates_to_draft_center(qapp, tmp_path):
    from ui.Gui import MainWindow
    from tests.uat.conftest import MockProjectService

    win = MainWindow(project_service=MockProjectService(str(tmp_path)))
    
    win.switch_page(0)
    assert win.lbl_page_title.text() == "Dashboard"
    
    win.switch_page(1)
    assert win.lbl_page_title.text() == "Studio Workspace"
    
    win.switch_page(4)
    assert win.lbl_page_title.text() == "Draft Center"
    
    win.switch_page(5)
    assert win.lbl_page_title.text() == "Export Center"
    
    win.switch_page(8)
    assert win.lbl_page_title.text() == "Dịch thuật AI"
    win.close()


def test_bug_qml_teardown_001_cancel_translation_safe_when_model_deleted():
    from core.translation.controllers.translation_controller import TranslationController
    
    mock_model = MagicMock()
    controller = TranslationController(subtitle_model=mock_model)
    
    # Giả lập khi SubtitleModel đã bị QML/C++ xóa (shiboken6.isValid trả về False hoặc ném RuntimeError)
    controller._is_model_valid = lambda: False
    controller._active_translation_index = 0
    controller._status = "TRANSLATING"
    
    # Hủy dịch trong trạng thái C++ model đã chết
    controller.cancelTranslation()
    
    # Đảm bảo không ném ngoại lệ và trạng thái được reset về PENDING
    assert controller._status == "PENDING"
    mock_model.update_translation.assert_not_called()
    
    # Kiểm tra các callback worker cũng an toàn tuyệt đối
    controller.on_progress(0, "text")
    controller.on_finished(0, "text")
    controller.on_error(0, "err")
    mock_model.update_translation.assert_not_called()
