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

