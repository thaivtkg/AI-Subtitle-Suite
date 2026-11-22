# -*- coding: utf-8 -*-
"""
E2E GUI Flow Specs for Subtitle Editor using Page Object Model (POM) and QtDriver.
Verifies element discovery, typing simulation, row navigation, table synchronization,
and cursor stability.
"""
import pytest
from PySide6.QtCore import Qt


def test_flow_edit_text_syncs_to_table_and_model(sub_editor_driver):
    """
    User Flow:
    1. Select first segment via Page Object.
    2. Enter new text into CurrentSubtitleEditor.
    3. Verify text reflects in editor, table cell, and data model.
    """
    editor, page, driver = sub_editor_driver

    # 1. Verify initial state
    assert page.get_current_text() == "Câu thứ nhất ban đầu"
    assert page.get_table_cell_text(0, 4) == "Câu thứ nhất ban đầu"
    driver.assert_visible(page.txt_content, True)

    # 2. Enter new text
    new_text = "Nội dung biên tập tự động qua GUI Driver"
    page.type_current_text(new_text, clear_first=True, wait_debounce=True)

    # 3. Assert synchronization
    assert page.get_current_text() == new_text
    assert page.get_table_cell_text(0, 4) == new_text
    assert editor.all_segments[0]["text"] == new_text


def test_flow_navigation_between_segments(sub_editor_driver):
    """
    User Flow:
    1. Select Row 0 -> verify title #1.
    2. Click '>' (Next Segment) -> verify advances to Row 1 and title #2.
    3. Click '<' (Previous Segment) -> verify returns to Row 0.
    """
    editor, page, driver = sub_editor_driver

    assert "#1" in page.get_current_title()
    assert page.get_current_text() == "Câu thứ nhất ban đầu"

    # Click next
    page.click_next_segment()
    assert "#2" in page.get_current_title()
    assert page.get_current_text() == "Câu thứ hai ban đầu"

    # Click previous
    page.click_prev_segment()
    assert "#1" in page.get_current_title()
    assert page.get_current_text() == "Câu thứ nhất ban đầu"


def test_flow_undo_redo_via_page_object(sub_editor_driver):
    """
    User Flow:
    1. Edit text on Row 0.
    2. Trigger Undo -> verify text and table restore to original.
    3. Trigger Redo -> verify new text is restored.
    """
    editor, page, driver = sub_editor_driver

    original_text = "Câu thứ nhất ban đầu"
    modified_text = "Phiên bản chỉnh sửa"

    page.type_current_text(modified_text, clear_first=True, wait_debounce=True)
    assert page.get_current_text() == modified_text
    assert page.get_table_cell_text(0, 4) == modified_text

    # Undo
    editor.undo_manager.undo()
    driver.wait_ms(50)
    assert page.get_current_text() == original_text
    assert page.get_table_cell_text(0, 4) == original_text
    assert editor.all_segments[0]["text"] == original_text

    # Redo
    editor.undo_manager.redo()
    driver.wait_ms(50)
    assert page.get_current_text() == modified_text
    assert page.get_table_cell_text(0, 4) == modified_text
    assert editor.all_segments[0]["text"] == modified_text


def test_flow_cursor_preservation_under_live_qtbot(sub_editor_driver):
    """
    User Flow (BUG-SUB-001 regression gate under POM):
    Simulates real user typing key by key and verifies cursor position is NOT reset to 0
    after debounce execution.
    """
    editor, page, driver = sub_editor_driver

    txt_widget = page.txt_content
    txt_widget.setFocus()
    txt_widget.setPlainText("Gõ kiểm tra con trỏ")

    # Set cursor at index 18 (end of text)
    cursor = txt_widget.textCursor()
    cursor.setPosition(len("Gõ kiểm tra con trỏ"))
    txt_widget.setTextCursor(cursor)

    # Let debounce run
    driver.wait_ms(350)

    # Cursor must remain at end of text, not reset to 0
    actual_pos = txt_widget.textCursor().position()
    assert actual_pos == len("Gõ kiểm tra con trỏ"), f"Cursor jumped to {actual_pos} instead of {len('Gõ kiểm tra con trỏ')}"


def test_flow_sub_editor_vertical_alignment_and_newline_sanitization(sub_editor_driver):
    """
    PLAN-SUBEDITOR-ALIGNMENT-AND-SANITIZATION-001 & PLAN-UI-DRIVER-E2E-VERIFICATION-001:
    Verify via QtDriver that leading/trailing newlines are stripped in both table_subtitles
    and CurrentSubtitleEditor, and table cells are vertically centered (Qt.AlignVCenter).
    """
    editor, page, driver = sub_editor_driver

    editor.all_segments = [
        {"stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "\n\nEm cảm ơn ngài\n"},
    ]
    editor.render_page()
    page.select_row(0)
    driver.wait_ms(50)

    assert page.get_table_cell_text(0, 4) == "Em cảm ơn ngài"
    assert page.get_current_text() == "Em cảm ơn ngài"
    assert bool(page.get_table_cell_alignment(0, 4) & int(Qt.AlignVCenter)) is True


def test_flow_rescan_button_click_via_qt_driver_triggers_large_v3_and_vram_guard(main_window_driver, monkeypatch):
    """
    BUG-SCAN-ID-001 & PLAN-RESCAN-LARGEV3-VRAM-GUARD-AND-LOG-COMPRESSION-001:
    Click real btn_current_sub_scan via QtDriver on a segment without explicit 'id' (only 'stt').
    Verify scan_mode=='asr', model_size=='large-v3', compute_type=='float16', and callback updates table.
    """
    from unittest.mock import MagicMock
    from core.services.model_manager import ModelManager
    from workers.SegmentScanWorker import SegmentScanWorker

    win, driver, sub_page, _cat_page, _timeline_page = main_window_driver

    win.project_service.current_project = MagicMock(project_id="p_e2e", video_path="dummy.mp4")
    win.current_vid = "dummy.mp4"
    win.subtitle_whisper_service.device = "cuda"

    win.sub_editor.all_segments = [
        {"stt": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu cũ"},
    ]
    win.sub_editor.render_page()
    sub_page.select_row(0)
    driver.wait_ms(50)

    monkeypatch.setattr(ModelManager, "is_installed", staticmethod(lambda m: True))
    monkeypatch.setattr(SegmentScanWorker, "start", lambda self: None)

    # Real QtDriver click on btn_current_sub_scan
    sub_page.click_scan()
    driver.wait_ms(50)

    assert hasattr(win, "scan_worker") and win.scan_worker is not None
    assert win.scan_worker.scan_mode == "asr"
    assert win.scan_worker.request.model_size == "large-v3"
    # On <=4.5GB VRAM (e.g. RTX 3050 4GB) or VRAM > 65%, guard automatically selects int8_float16; otherwise float16
    assert win.scan_worker.request.compute_type in ("float16", "int8_float16")
    assert win.scan_worker.request.use_vad is True

    # Simulate worker completion callback and verify UI table updates
    win._on_segment_scan_finished(win.scan_worker.segment_id, "Câu mới từ large-v3")
    driver.wait_ms(50)

    assert sub_page.get_table_cell_text(0, 4) == "Câu mới từ large-v3"
    assert sub_page.get_current_text() == "Câu mới từ large-v3"
    win.project_service.current_project = None


def test_flow_activity_log_view_filters_and_noise_suppression_via_qt_driver(main_window_driver):
    """
    BUG-LOG-PREFIX-002 & GAP-UI-DRIVER-003:
    Verify ActivityLogView objectName locators, noise suppression, single prefix on _on_timing_log,
    and source filter switching ('CAT' vs 'ASR') via QtDriver.
    """
    from PySide6.QtWidgets import QComboBox, QPushButton, QTextEdit

    win, driver, _sub_page, _cat_page, _timeline_page = main_window_driver

    source_filter = driver.find_widget("activity_source_filter", root=win.log_box, widget_type=QComboBox)
    clear_btn = driver.find_widget("activity_clear_button", root=win.log_box, widget_type=QPushButton)
    log_text = driver.find_widget("activity_log_text", root=win.log_box, widget_type=QTextEdit)

    driver.click(clear_btn)
    driver.wait_ms(50)

    win.append_log("llama_kv_cache_iswa: using full-size SWA cache")
    win.append_log("[MODEL_COMMIT] target=0")
    win.append_log("[CAT] Câu #1: Ngươi tìm ta đây rốt cuộc có chuyện gì?")
    win._on_timing_log("[ASR] VRAM đạt 75% (>65%) ➔ Tự động chuyển sang int8_float16.")
    driver.wait_ms(50)

    plain = log_text.toPlainText()
    assert "llama_kv_cache_iswa" not in plain
    assert "[MODEL_COMMIT]" not in plain
    assert "[TIMING] [ASR]" not in plain
    assert "Ngươi tìm ta đây rốt cuộc có chuyện gì?" in plain
    assert "Tự động chuyển sang int8_float16" in plain

    source_filter.setCurrentText("CAT")
    driver.wait_ms(50)
    assert "Ngươi tìm ta đây rốt cuộc có chuyện gì?" in log_text.toPlainText()
    assert "Tự động chuyển sang int8_float16" not in log_text.toPlainText()

    source_filter.setCurrentText("ASR")
    driver.wait_ms(50)
    assert "Tự động chuyển sang int8_float16" in log_text.toPlainText()
    assert "Ngươi tìm ta đây rốt cuộc có chuyện gì?" not in log_text.toPlainText()


def test_flow_workspace_model_banner_visibility_and_sync(main_window_driver):
    """
    Verify top-bar Model & ASR/VAD banners and two separate config dialogs:
    - Both banners hidden outside Studio Workspace (Dashboard / Queue / Translation).
    - Visible inside Studio Workspace (tab 1) and sync immediately when switching models or VAD preset.
    - ModelConfigDialog and AsrVadConfigDialog are separate dialogs hosting detached panel sections cleanly.
    """
    from PySide6.QtWidgets import QDialog

    win, driver, _sub_page, _cat_page, _timeline_page = main_window_driver
    model_banner = getattr(win, "btn_workspace_model_banner", None)
    vad_banner = getattr(win, "btn_workspace_vad_banner", None)
    assert model_banner is not None
    assert vad_banner is not None

    model_dlg = getattr(win, "model_config_dialog", None)
    vad_dlg = getattr(win, "asr_vad_config_dialog", None)
    assert isinstance(model_dlg, QDialog)
    assert isinstance(vad_dlg, QDialog)
    assert model_dlg is not vad_dlg
    assert model_dlg.isAncestorOf(win.generation_panel.model_group)
    assert vad_dlg.isAncestorOf(win.generation_panel.asr_vad_group)
    assert not model_dlg.isAncestorOf(win.generation_panel.asr_vad_group)
    assert not vad_dlg.isAncestorOf(win.generation_panel.model_group)

    win.switch_page(0, animate=False)
    driver.wait_ms(30)
    assert model_banner.isVisible() is False
    assert vad_banner.isVisible() is False

    win.switch_page(1, animate=False)
    driver.wait_ms(30)
    assert model_banner.isVisible() is True
    assert vad_banner.isVisible() is True
    active_model = win.generation_panel._get_effective_model_size()
    assert active_model in model_banner.text()
    assert "VAD:" in vad_banner.text()

    idx_k20 = win.generation_panel.cmb_specialized_model.findData("kotoba-whisper-v2.0")
    assert idx_k20 > 0
    win.generation_panel.cmb_specialized_model.setCurrentIndex(idx_k20)
    driver.wait_ms(30)
    assert "kotoba-whisper-v2.0" in model_banner.text()
    assert "Chuyên ngữ" in model_banner.text()
    assert "350ms / 0.25" in vad_banner.text()

    idx_cfg9 = win.generation_panel.cmb_vad_preset.findData("cfg9")
    assert idx_cfg9 >= 0
    win.generation_panel.cmb_vad_preset.setCurrentIndex(idx_cfg9)
    driver.wait_ms(30)
    assert "CFG-9 · 300ms / 0.35" in vad_banner.text()

    # Single floating dialog rule: opening one automatically closes any previously open dialog
    from PySide6.QtWidgets import QApplication, QPushButton
    driver.click(win.btn_workspace_model_banner)
    driver.wait_ms(30)
    assert model_dlg.isVisible() is True
    assert vad_dlg.isVisible() is False

    driver.click(win.btn_workspace_vad_banner)
    driver.wait_ms(40)
    assert vad_dlg.isVisible() is True
    assert model_dlg.isVisible() is False
    assert not model_dlg.isModal() and not vad_dlg.isModal()
    assert QApplication.activeModalWidget() not in (model_dlg, vad_dlg)

    for dlg in (model_dlg, vad_dlg):
        close_btn = dlg.findChild(QPushButton, "btn_dialog_close")
        assert close_btn is not None
        assert close_btn.text() == "✕"
        assert close_btn.width() >= 30
        assert close_btn.height() >= 26
        assert close_btn.fontMetrics().horizontalAdvance("✕") <= close_btn.width()

    _, _, pad_hint_lbl = win.generation_panel._vad_row_widgets["speech_pad"]
    assert pad_hint_lbl.width() >= pad_hint_lbl.sizeHint().width()

    # Opening Hotkeys cheatsheet closes currently open VAD/Model config dialog first
    from unittest.mock import patch
    from ui.dialogs.hotkeys_cheatsheet_dialog import HotkeysCheatsheetDialog
    with patch.object(HotkeysCheatsheetDialog, "exec", return_value=0):
        win.action_show_hotkeys()
    driver.wait_ms(20)
    assert vad_dlg.isVisible() is False
    assert model_dlg.isVisible() is False

    # Re-open model_dlg, close via its ✕ button, confirm both hidden
    driver.click(win.btn_workspace_model_banner)
    driver.wait_ms(30)
    assert model_dlg.isVisible() is True
    assert vad_dlg.isVisible() is False
    driver.click(model_dlg.findChild(QPushButton, "btn_dialog_close"))
    driver.wait_ms(30)
    assert model_dlg.isVisible() is False
    assert vad_dlg.isVisible() is False

    # Also test opening from drawer quick buttons doesn't lock mouse/app
    p = win.generation_panel
    win.overlay_host.show()
    win.overlay_host.resize(900, 650)
    win.generation_drawer.resize(620, 620)
    driver.wait_ms(40)
    assert p.btn_open_model_config_dialog.height() == 34
    assert p.btn_open_asr_vad_dialog.height() == 34
    assert abs(p.btn_open_model_config_dialog.width() - p.btn_open_asr_vad_dialog.width()) <= 2
    assert abs(p.btn_range_timeline.width() - p.btn_range_preview.width()) <= 2
    assert p.btn_range_timeline.height() == p.btn_range_preview.height() == 34
    assert abs(p.txt_start.width() - p.btn_range_timeline.width()) <= 2
    assert abs(p.txt_end.width() - p.btn_range_preview.width()) <= 2
    assert abs(p.txt_start.width() - p.txt_end.width()) <= 2
    assert p.txt_start.height() == p.txt_end.height() == 32
    unit_left = p.cmb_range_unit.mapTo(p.range_group, p.cmb_range_unit.rect().topLeft()).x()
    unit_right = p.cmb_range_unit.mapTo(p.range_group, p.cmb_range_unit.rect().topRight()).x()
    start_left = p.txt_start.mapTo(p.range_group, p.txt_start.rect().topLeft()).x()
    timeline_left = p.btn_range_timeline.mapTo(p.range_group, p.btn_range_timeline.rect().topLeft()).x()
    end_left = p.txt_end.mapTo(p.range_group, p.txt_end.rect().topLeft()).x()
    preview_left = p.btn_range_preview.mapTo(p.range_group, p.btn_range_preview.rect().topLeft()).x()
    start_right = p.txt_start.mapTo(p.range_group, p.txt_start.rect().topRight()).x()
    timeline_right = p.btn_range_timeline.mapTo(p.range_group, p.btn_range_timeline.rect().topRight()).x()
    end_right = p.txt_end.mapTo(p.range_group, p.txt_end.rect().topRight()).x()
    preview_right = p.btn_range_preview.mapTo(p.range_group, p.btn_range_preview.rect().topRight()).x()
    assert abs(unit_left - start_left) <= 2
    assert abs(start_left - timeline_left) <= 2
    assert abs(start_right - timeline_right) <= 2
    assert abs(end_left - preview_left) <= 2
    assert abs(unit_right - end_right) <= 2
    assert abs(unit_right - preview_right) <= 2
    assert p.cmb_range_unit.width() > 210
    assert p.cmb_mode.width() > 210
    assert p.cmb_batch_mode.width() > 210
    assert p.cmb_range_unit.height() == p.cmb_mode.height() == p.cmb_batch_mode.height() == 32
    win.overlay_host.hide()

    driver.click(win.generation_panel.btn_open_model_config_dialog)
    driver.wait_ms(30)
    assert model_dlg.isVisible() is True
    assert not model_dlg.isModal()
    assert QApplication.activeModalWidget() is not model_dlg
    model_dlg.accept()
    driver.wait_ms(20)

    win.switch_page(8, animate=False)
    driver.wait_ms(30)
    assert model_banner.isVisible() is False
    assert vad_banner.isVisible() is False

    win.switch_page(2, animate=False)
    driver.wait_ms(30)
    assert model_banner.isVisible() is False
    assert vad_banner.isVisible() is False

    win.generation_panel.cmb_specialized_model.setCurrentIndex(0)
    win.switch_page(1, animate=False)
    driver.wait_ms(30)
    assert model_banner.isVisible() is True
    assert vad_banner.isVisible() is True
    assert "Model:" in model_banner.text()


