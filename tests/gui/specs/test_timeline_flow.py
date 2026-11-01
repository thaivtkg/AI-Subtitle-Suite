# -*- coding: utf-8 -*-
"""
E2E GUI Flow Specs for Waveform Timeline using Page Object Model (POM) and QtDriver.
Verifies gap detection and creation, live tap-to-time (Mark In / Mark Out) shortcuts,
toolbar manual timing generation, and focus guard integrity.
"""
from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTextEdit
from PySide6.QtTest import QTest


def test_flow_gap_manual_timing_creation(timeline_driver):
    """
    User Flow (Workflow 2: Gap Selection & Creation):
    1. Load 2 segments with a 4000ms gap between them [3000ms -> 7000ms].
    2. Select the gap in TimelineWidget.
    3. Verify '➕ Tạo Timing thủ công' button is enabled.
    4. Click the button via Page Object.
    5. Assert new segment [3000ms -> 7000ms] is inserted chronologically.
    6. Verify TimelineTrack and SubEditor stay synchronized (3 segments).
    """
    win, driver, timeline_page, sub_page = timeline_driver

    seg1 = {
        "id": "seg1",
        "stt": "1",
        "start": "00:00:01,000",
        "end": "00:00:03,000",
        "start_ms": 1000,
        "end_ms": 3000,
        "text": "Phân đoạn đầu",
        "style_preset": "normal",
    }
    seg2 = {
        "id": "seg2",
        "stt": "2",
        "start": "00:00:07,000",
        "end": "00:00:09,000",
        "start_ms": 7000,
        "end_ms": 9000,
        "text": "Phân đoạn cuối",
        "style_preset": "normal",
    }

    timeline_page.load_segments([seg1, seg2], duration_ms=20000)

    # 1. Verify initial 2 segments and gaps exist
    assert timeline_page.get_segment_count() == 2
    gaps = timeline_page.get_gaps()
    assert len(gaps) >= 1

    # 2. Select gap [3000 -> 7000]
    timeline_page.select_gap_by_range(3000, 7000)
    assert timeline_page.btn_create_manual_gap.isEnabled() is True

    # 3. Click "➕ Tạo Timing thủ công"
    timeline_page.click_create_manual_gap()

    # 4. Assert new segment is created at index 1
    assert timeline_page.get_segment_count() == 3
    assert len(win.sub_editor.all_segments) == 3

    created_seg = win.sub_editor.all_segments[1]
    assert created_seg["start"] == "00:00:03,000"
    assert created_seg["end"] == "00:00:07,000"
    assert created_seg["start_ms"] == 3000
    assert created_seg["end_ms"] == 7000

    # 5. Gap selection should be reset
    assert win.timeline_widget.generation_range is None


def test_flow_live_tap_to_time_mark_in_and_out(timeline_driver):
    """
    User Flow (Workflow 3: Live Tap-to-Time Mark In / Mark Out):
    1. Start with empty subtitles.
    2. Park playhead at 10000ms and trigger Mark In ('[').
    3. Verify Mark In timestamp is pinned to 10000ms.
    4. Seek playhead to 12500ms and trigger Mark Out (']').
    5. Verify Mark In is cleared and new segment [10000ms -> 12500ms] is generated.
    6. Verify TimelineTrack and SubEditor reflect the new segment.
    """
    win, driver, timeline_page, sub_page = timeline_driver

    timeline_page.load_segments([], duration_ms=30000)
    win._get_current_video_duration_ms = MagicMock(return_value=30000)

    # 1. Set playhead to 10000ms and press Mark In
    win._get_current_playhead_ms = MagicMock(return_value=10000)
    timeline_page.press_mark_in(ensure_unfocused=True)

    assert timeline_page.get_manual_mark_in_ms() == 10000
    assert timeline_page.waveform._selected_range_ms == (10000, 10250)

    # 2. Move playhead to 12500ms and press Mark Out
    win._get_current_playhead_ms.return_value = 12500
    timeline_page.press_mark_out(ensure_unfocused=True)

    # 3. Assert Mark In reset and segment created
    assert timeline_page.get_manual_mark_in_ms() is None
    assert timeline_page.get_segment_count() == 1
    assert len(win.sub_editor.all_segments) == 1

    created_seg = win.sub_editor.all_segments[0]
    assert created_seg["start"] == "00:00:10,000"
    assert created_seg["end"] == "00:00:12,500"
    assert created_seg["start_ms"] == 10000
    assert created_seg["end_ms"] == 12500


def test_flow_focus_guard_on_mark_in_out(timeline_driver):
    """
    User Flow (Focus Guard Integrity):
    When focus is inside an editor (QTextEdit or QLineEdit), pressing '[' or ']'
    must NOT trigger Mark In / Mark Out, preventing accidental timing triggers while typing.
    """
    win, driver, timeline_page, sub_page = timeline_driver

    seg1 = {
        "id": "seg1",
        "stt": "1",
        "start": "00:00:01,000",
        "end": "00:00:03,000",
        "start_ms": 1000,
        "end_ms": 3000,
        "text": "Nội dung đang gõ",
        "style_preset": "normal",
    }
    timeline_page.load_segments([seg1], duration_ms=20000)
    win.sub_editor.select_segment(0)
    driver.wait_ms(50)

    # 1. Focus into CurrentSubtitleEditor text edit
    txt_widget = sub_page.txt_content
    txt_widget.setFocus()
    driver.wait_ms(30)
    assert QApplication.focusWidget() == txt_widget

    win._get_current_playhead_ms = MagicMock(return_value=5000)
    win._manual_mark_in_ms = None

    # 2. Trigger Mark In with ensure_unfocused=False (maintains focus inside txt_widget)
    timeline_page.press_mark_in(ensure_unfocused=False)

    # Focus guard must prevent Mark In from activating
    assert timeline_page.get_manual_mark_in_ms() is None

    # 3. Test Mark Out guard when focus is inside editor
    win._manual_mark_in_ms = 5000
    timeline_page.press_mark_out(ensure_unfocused=False)

    # Still 5000 because Mark Out was guarded
    assert timeline_page.get_manual_mark_in_ms() == 5000

    # 4. Clean up mark in state
    win._manual_mark_in_ms = None


def test_flow_add_manual_timing_toolbar_at_playhead(timeline_driver):
    """
    User Flow (Workflow 1: Toolbar '➕ Thêm Timing' Button):
    1. Load 1 segment [1000ms -> 4000ms].
    2. Park playhead at 2000ms (inside existing segment).
    3. Click '➕ Thêm Timing' on the toolbar via Page Object.
    4. Assert new 2000ms segment is appended right after the active segment [4000ms -> 6000ms].
    5. Verify TimelineTrack and SubEditor are synced with 2 segments.
    """
    win, driver, timeline_page, sub_page = timeline_driver

    seg1 = {
        "id": "seg1",
        "stt": "1",
        "start": "00:00:01,000",
        "end": "00:00:04,000",
        "start_ms": 1000,
        "end_ms": 4000,
        "text": "Câu một",
        "style_preset": "normal",
    }
    timeline_page.load_segments([seg1], duration_ms=20000)
    win._get_current_video_duration_ms = MagicMock(return_value=20000)
    win._get_current_playhead_ms = MagicMock(return_value=2000)

    # Click "+ Thêm Timing" toolbar button
    timeline_page.click_add_manual_timing_toolbar()

    assert timeline_page.get_segment_count() == 2
    assert len(win.sub_editor.all_segments) == 2

    new_seg = win.sub_editor.all_segments[1]
    assert new_seg["start"] == "00:00:04,000"
    assert new_seg["end"] == "00:00:06,000"
    assert new_seg["start_ms"] == 4000
    assert new_seg["end_ms"] == 6000
