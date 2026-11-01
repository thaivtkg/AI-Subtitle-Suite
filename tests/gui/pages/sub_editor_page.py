# -*- coding: utf-8 -*-
"""
Page Object for Subtitle Editor (SubtitleEditorWidget & CurrentSubtitleEditor).
Encapsulates UI interaction with table rows, editor input fields, timing controls,
and manual timing buttons.
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTextEdit, QLineEdit, QLabel, QPushButton
from tests.gui.pages.base_page import BasePage
from tests.gui.drivers.qt_driver import QtDriver


class SubEditorPage(BasePage):
    """Page Object for Subtitle Editor in Subtitle Studio."""

    # Locators (objectName identifiers)
    LOC_TXT_CONTENT = "txt_current_sub_content"
    LOC_INP_START = "inp_current_sub_start"
    LOC_INP_END = "inp_current_sub_end"
    LOC_LBL_DURATION = "lbl_current_sub_duration"
    LOC_LBL_TITLE = "lbl_current_sub_title"
    LOC_BTN_SCAN = "btn_current_sub_scan"
    LOC_TABLE = "table_subtitles"
    LOC_BTN_PREV = "btn_prev_segment"
    LOC_BTN_NEXT = "btn_next_segment"
    LOC_BTN_ADD_TIMING = "btn_add_manual_timing"

    def __init__(self, driver: QtDriver, sub_editor_widget=None):
        super().__init__(driver)
        self.sub_editor = sub_editor_widget or self.window.findChild(sub_editor_widget.__class__ if sub_editor_widget else object, "sub_editor") or getattr(self.window, "sub_editor", None)

    # -------------------------------------------------------------------------
    # Element Getters
    # -------------------------------------------------------------------------

    @property
    def txt_content(self) -> QTextEdit:
        return self.driver.find_widget(self.LOC_TXT_CONTENT, widget_type=QTextEdit)

    @property
    def inp_start(self) -> QLineEdit:
        return self.driver.find_widget(self.LOC_INP_START, widget_type=QLineEdit)

    @property
    def inp_end(self) -> QLineEdit:
        return self.driver.find_widget(self.LOC_INP_END, widget_type=QLineEdit)

    @property
    def lbl_duration(self) -> QLabel:
        return self.driver.find_widget(self.LOC_LBL_DURATION, widget_type=QLabel)

    @property
    def lbl_title(self) -> QLabel:
        return self.driver.find_widget(self.LOC_LBL_TITLE, widget_type=QLabel)

    @property
    def btn_scan(self) -> QPushButton:
        return self.driver.find_widget(self.LOC_BTN_SCAN, widget_type=QPushButton)

    @property
    def table(self) -> QTableWidget:
        return self.driver.find_widget(self.LOC_TABLE, widget_type=QTableWidget)

    @property
    def btn_prev(self) -> QPushButton:
        return self.driver.find_widget(self.LOC_BTN_PREV, widget_type=QPushButton)

    @property
    def btn_next(self) -> QPushButton:
        return self.driver.find_widget(self.LOC_BTN_NEXT, widget_type=QPushButton)

    @property
    def btn_add_timing(self) -> Optional[QPushButton]:
        try:
            return self.driver.find_widget(self.LOC_BTN_ADD_TIMING, widget_type=QPushButton)
        except LookupError:
            return None

    # -------------------------------------------------------------------------
    # User Actions
    # -------------------------------------------------------------------------

    def select_row(self, row_index: int) -> SubEditorPage:
        """Selects a subtitle row in the table."""
        tbl = self.table
        assert 0 <= row_index < tbl.rowCount(), f"Row index {row_index} out of range [0, {tbl.rowCount()})"
        item = tbl.item(row_index, 0)
        if item is not None:
            rect = tbl.visualItemRect(item)
            if self.driver.qtbot:
                self.driver.qtbot.mouseClick(tbl.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
            else:
                tbl.selectRow(row_index)
        else:
            tbl.selectRow(row_index)
        self.wait_ms(50)
        return self

    def type_current_text(self, text: str, clear_first: bool = True, wait_debounce: bool = True) -> SubEditorPage:
        """Types new subtitle text into CurrentSubtitleEditor."""
        self.driver.type_text(self.txt_content, text, clear_first=clear_first)
        if wait_debounce:
            # Wait for 250ms debounce timer + 50ms buffer
            self.wait_ms(300)
        return self

    def get_current_text(self) -> str:
        """Returns the text currently displayed in CurrentSubtitleEditor."""
        return self.driver.get_text(self.txt_content)

    def get_current_start_time(self) -> str:
        return self.driver.get_text(self.inp_start)

    def get_current_end_time(self) -> str:
        return self.driver.get_text(self.inp_end)

    def get_current_duration(self) -> str:
        return self.driver.get_text(self.lbl_duration)

    def get_current_title(self) -> str:
        return self.driver.get_text(self.lbl_title)

    def get_table_row_count(self) -> int:
        return self.table.rowCount()

    def get_table_cell_text(self, row: int, col: int = 4) -> str:
        """Returns text of specified cell in table (col 4 = COL_TEXT)."""
        item = self.table.item(row, col)
        return item.text() if item is not None else ""

    def click_prev_segment(self) -> SubEditorPage:
        self.driver.click(self.btn_prev)
        return self

    def click_next_segment(self) -> SubEditorPage:
        self.driver.click(self.btn_next)
        return self

    def click_scan(self) -> SubEditorPage:
        self.driver.click(self.btn_scan)
        return self

    def click_add_manual_timing(self) -> SubEditorPage:
        btn = self.btn_add_timing
        assert btn is not None, "btn_add_manual_timing must exist on toolbar"
        self.driver.click(btn)
        return self
