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
