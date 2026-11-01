# -*- coding: utf-8 -*-
"""
Page Object for Waveform Timeline (TimelineWidget, SubtitleTrack, WaveformView, TimeRuler).
Encapsulates UI interactions with playhead seeking, gap detection & creation,
and live tap-to-time (Mark In / Mark Out) shortcuts.
"""
from __future__ import annotations
from typing import Optional, List, Any
from unittest.mock import MagicMock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QLineEdit, QLabel, QApplication, QTextEdit
from PySide6.QtTest import QTest
from tests.gui.pages.base_page import BasePage
from tests.gui.drivers.qt_driver import QtDriver


class TimelineWidgetPage(BasePage):
    """Page Object for Timeline and Waveform in Subtitle Studio."""

    # Locators (objectName identifiers)
    LOC_TIMELINE_WIDGET = "timeline_widget"
    LOC_TIMELINE_CONTAINER = "timeline_container"
    LOC_TIMELINE_RULER = "timeline_ruler"
    LOC_TIMELINE_WAVEFORM = "timeline_waveform"
    LOC_TIMELINE_TRACK = "timeline_track"
    LOC_TIMELINE_GAP_ROW = "timeline_gap_row"
    LOC_BTN_CREATE_MANUAL_GAP = "btn_create_manual_gap"
    LOC_BTN_ADD_MANUAL_TIMING = "btn_add_manual_timing"

    def __init__(self, driver: QtDriver, timeline_widget=None):
        super().__init__(driver)
        self._timeline_widget = timeline_widget or getattr(self.window, "timeline_widget", None)

    # -------------------------------------------------------------------------
    # Element Getters
    # -------------------------------------------------------------------------

    @property
    def timeline_widget(self):
        if self._timeline_widget is not None:
            return self._timeline_widget
        return self.driver.find_widget(self.LOC_TIMELINE_WIDGET)

    @property
    def container(self):
        return self.timeline_widget.container

    @property
    def track(self):
        return self.container.track

    @property
    def waveform(self):
        return self.container.waveform

    @property
    def ruler(self):
        return self.container.ruler

    @property
    def btn_create_manual_gap(self) -> QPushButton:
        return self.container.create_manual_gap_button

    @property
    def btn_add_manual_timing(self) -> Optional[QPushButton]:
        try:
            return self.driver.find_widget(self.LOC_BTN_ADD_MANUAL_TIMING, widget_type=QPushButton)
        except LookupError:
            return None

    # -------------------------------------------------------------------------
    # Timeline Actions & State Inspection
    # -------------------------------------------------------------------------

    def load_segments(self, segments: list, duration_ms: int = 20000) -> TimelineWidgetPage:
        """Loads segments into SubEditor and synchronizes TimelineTrack and DataProvider."""
        self.timeline_widget.duration_ms = duration_ms
        if hasattr(self.window, "sub_editor"):
            self.window.sub_editor.all_segments = list(segments)
        if hasattr(self.window, "timeline_data_provider"):
            self.window.timeline_data_provider.load_runtime_data(segments, duration_ms)
        if hasattr(self.timeline_widget, "load_project_data"):
            dp_segs = self.window.timeline_data_provider.get_all_segments() if hasattr(self.window, "timeline_data_provider") else segments
            self.timeline_widget.load_project_data(duration_ms, dp_segs)
        if hasattr(self.window, "timeline_controller"):
            self.window.timeline_controller.sync_from_editor_segments(segments)
        if hasattr(self.window, "sub_editor") and hasattr(self.window.sub_editor, "render_page"):
            self.window.sub_editor.render_page()
        self.wait_ms(30)
        return self

    def get_playhead_position_ms(self) -> int:
        """Returns the current playhead position in milliseconds."""
        if hasattr(self.window, "_get_current_playhead_ms"):
            fn = self.window._get_current_playhead_ms
            val = fn() if callable(fn) else fn
            return int(val)
        if hasattr(self.waveform, "playhead_ms"):
            return int(self.waveform.playhead_ms)
        return 0

    def seek_to_ms(self, target_ms: int) -> TimelineWidgetPage:
        """Positions playhead at the given millisecond mark."""
        if hasattr(self.window, "_get_current_playhead_ms"):
            if isinstance(self.window._get_current_playhead_ms, MagicMock):
                self.window._get_current_playhead_ms.return_value = target_ms
            elif hasattr(self.window, "video_player"):
                self.window.video_player.seek_position(target_ms)
        if hasattr(self.timeline_widget, "seek_requested"):
            self.timeline_widget.seek_requested.emit(target_ms)
        if hasattr(self.waveform, "set_playhead_position"):
            self.waveform.set_playhead_position(target_ms)
        self.wait_ms(20)
        return self

    def get_segment_count(self) -> int:
        """Returns the number of subtitle blocks rendered on the timeline track."""
        return len(self.track.segments)

    def get_gaps(self) -> List[Any]:
        """Returns list of gap objects currently detected between segments."""
        return list(getattr(self.track, "gaps", []))

    def select_gap_by_index(self, gap_index: int) -> TimelineWidgetPage:
        """Selects a gap by its index in track.gaps."""
        gaps = self.get_gaps()
        assert 0 <= gap_index < len(gaps), f"Gap index {gap_index} out of range [0, {len(gaps)})"
        target_gap = gaps[gap_index]
        self.timeline_widget.select_gap(target_gap)
        self.wait_ms(30)
        return self

    def select_gap_by_range(self, start_ms: int, end_ms: int) -> TimelineWidgetPage:
        """Finds and selects the gap matching [start_ms, end_ms]."""
        gaps = self.get_gaps()
        target = next((g for g in gaps if g.start_ms == start_ms and g.end_ms == end_ms), None)
        assert target is not None, f"No gap found with range [{start_ms}, {end_ms}]. Available: {[(g.start_ms, g.end_ms) for g in gaps]}"
        self.timeline_widget.select_gap(target)
        self.wait_ms(30)
        return self

    def click_create_manual_gap(self) -> TimelineWidgetPage:
        """Clicks the '➕ Tạo Timing thủ công' button in the gap row."""
        assert self.btn_create_manual_gap.isEnabled() is True, "btn_create_manual_gap must be enabled to click"
        self.driver.click(self.btn_create_manual_gap)
        self.wait_ms(50)
        return self

    def create_timing_from_gap(self, gap_index: int) -> TimelineWidgetPage:
        """High-level flow: Selects gap and clicks manual gap timing button."""
        self.select_gap_by_index(gap_index)
        self.click_create_manual_gap()
        return self

    def click_add_manual_timing_toolbar(self) -> TimelineWidgetPage:
        """Clicks '➕ Thêm Timing' on the timeline toolbar."""
        btn = self.btn_add_manual_timing
        assert btn is not None, "btn_add_manual_timing not found on window"
        self.driver.click(btn)
        self.wait_ms(50)
        return self

    # -------------------------------------------------------------------------
    # Live Tap-to-Time (Mark In / Mark Out)
    # -------------------------------------------------------------------------

    def press_mark_in(self, ensure_unfocused: bool = True) -> TimelineWidgetPage:
        """
        Triggers '[' (Mark In).
        If ensure_unfocused is True, clears focus from text inputs first to satisfy the focus guard.
        """
        if ensure_unfocused:
            focus_w = QApplication.focusWidget()
            if isinstance(focus_w, (QLineEdit, QTextEdit)):
                focus_w.clearFocus()
                self.timeline_widget.setFocus()

        if hasattr(self.window, "_on_manual_mark_in"):
            self.window._on_manual_mark_in()
        else:
            QTest.keyClick(self.timeline_widget, Qt.Key_BracketLeft)
        self.wait_ms(30)
        return self

    def press_mark_out(self, ensure_unfocused: bool = True) -> TimelineWidgetPage:
        """
        Triggers ']' (Mark Out).
        If ensure_unfocused is True, clears focus from text inputs first.
        """
        if ensure_unfocused:
            focus_w = QApplication.focusWidget()
            if isinstance(focus_w, (QLineEdit, QTextEdit)):
                focus_w.clearFocus()
                self.timeline_widget.setFocus()

        if hasattr(self.window, "_on_manual_mark_out"):
            self.window._on_manual_mark_out()
        else:
            QTest.keyClick(self.timeline_widget, Qt.Key_BracketRight)
        self.wait_ms(30)
        return self

    def get_manual_mark_in_ms(self) -> Optional[int]:
        """Returns the pinned mark in timestamp if active, else None."""
        return getattr(self.window, "_manual_mark_in_ms", None)
