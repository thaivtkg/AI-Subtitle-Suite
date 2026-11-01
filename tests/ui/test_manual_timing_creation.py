import pytest
from unittest.mock import MagicMock
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit
from ui.Gui import MainWindow
from core.subtitle_generation.generation_range import GenerationRangeStatus


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def app_window(qapp):
    win = MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    try:
        if hasattr(win, "video_player") and hasattr(win.video_player, "cleanup"):
            win.video_player.cleanup()
    except Exception:
        pass
    try:
        qapp.removeEventFilter(win)
    except Exception:
        pass
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_manual_timing_at_playhead_advances_and_supports_undo_redo(app_window, qapp):
    """Workflow 1: Clicking btn_add_manual_timing adds segment at playhead,
    advances after an existing segment if parked inside one, updates SubEditor & TimelineTrack,
    and supports undo/redo."""
    win = app_window
    win.timeline_widget.duration_ms = 20000

    # Initial single segment 1000ms -> 4000ms
    seg1 = {
        "id": "seg1",
        "stt": "1",
        "start": "00:00:01,000",
        "end": "00:00:04,000",
        "start_ms": 1000,
        "end_ms": 4000,
        "text": "Hello world",
        "style_preset": "normal",
    }
    win.sub_editor.all_segments = [seg1]
    win.timeline_controller.sync_from_editor_segments(win.sub_editor.all_segments)
    win.sub_editor.render_page()

    # 1. Park playhead at 2000ms (inside seg1)
    win._get_current_playhead_ms = MagicMock(return_value=2000)
    win._get_current_video_duration_ms = MagicMock(return_value=20000)

    # Click "+ Thêm Timing" button
    win.btn_add_manual_timing.click()
    qapp.processEvents()

    # Segment should advance past seg1 (to 4000ms), duration 2000ms -> 6000ms
    assert len(win.sub_editor.all_segments) == 2
    added = win.sub_editor.all_segments[1]
    assert added["start"] == "00:00:04,000"
    assert added["end"] == "00:00:06,000"
    assert added["start_ms"] == 4000
    assert added["end_ms"] == 6000

    # Verify TimelineTrack is synced
    track_segs = win.timeline_widget.container.track.segments
    assert len(track_segs) == 2
    assert track_segs[1].start_ms == 4000
    assert track_segs[1].end_ms == 6000

    # 2. Undo
    win.undo_manager.undo()
    qapp.processEvents()
    assert len(win.sub_editor.all_segments) == 1

    # 3. Redo
    win.undo_manager.redo()
    qapp.processEvents()
    assert len(win.sub_editor.all_segments) == 2
    assert win.sub_editor.all_segments[1]["start"] == "00:00:04,000"
    assert win.sub_editor.all_segments[1]["end"] == "00:00:06,000"


def test_manual_timing_gap_range_creation(app_window, qapp):
    """Workflow 2: Selecting a Gap / range enables create_manual_gap_button,
    and clicking it creates the exact segment [start_ms, end_ms] in chronological order."""
    win = app_window
    win.timeline_widget.duration_ms = 20000

    # Two segments: [1000 -> 3000] and [7000 -> 9000] with a gap between 3000 and 7000
    seg1 = {
        "id": "seg1",
        "stt": "1",
        "start": "00:00:01,000",
        "end": "00:00:03,000",
        "start_ms": 1000,
        "end_ms": 3000,
        "text": "Start",
        "style_preset": "normal",
    }
    seg2 = {
        "id": "seg2",
        "stt": "2",
        "start": "00:00:07,000",
        "end": "00:00:09,000",
        "start_ms": 7000,
        "end_ms": 9000,
        "text": "End",
        "style_preset": "normal",
    }
    win.sub_editor.all_segments = [seg1, seg2]
    win.timeline_data_provider.load_runtime_data(win.sub_editor.all_segments, 20000)
    win.timeline_widget.load_project_data(20000, win.timeline_data_provider.get_all_segments())
    win.timeline_controller.sync_from_editor_segments(win.sub_editor.all_segments)
    win.sub_editor.render_page()

    # Select the gap between 3000 and 7000
    gaps = win.timeline_widget.container.track.gaps
    target_gap = next((g for g in gaps if g.start_ms == 3000 and g.end_ms == 7000), None)
    assert target_gap is not None
    win.timeline_widget.select_gap(target_gap)
    qapp.processEvents()

    assert win.timeline_widget.range_validation.status == GenerationRangeStatus.VALID
    assert win.timeline_widget.container.create_manual_gap_button.isEnabled() is True

    # Click "➕ Tạo Timing thủ công" button
    win.timeline_widget.container.create_manual_gap_button.click()
    qapp.processEvents()

    # Should insert at chronological index 1 between seg1 and seg2
    assert len(win.sub_editor.all_segments) == 3
    new_seg = win.sub_editor.all_segments[1]
    assert new_seg["start"] == "00:00:03,000"
    assert new_seg["end"] == "00:00:07,000"
    assert new_seg["start_ms"] == 3000
    assert new_seg["end_ms"] == 7000

    # Gap selection should be cleared
    assert win.timeline_widget.generation_range is None

    # Track should be synced
    assert len(win.timeline_widget.container.track.segments) == 3


def test_live_tap_to_time_mark_in_and_mark_out(app_window, qapp):
    """Workflow 3: Calling _on_manual_mark_in() at 10000ms and _on_manual_mark_out()
    at 12500ms creates a manual segment [00:00:10,000 -> 00:00:12,500]."""
    win = app_window
    win.timeline_widget.duration_ms = 30000
    win.sub_editor.all_segments = []
    win.timeline_controller.sync_from_editor_segments([])

    # Mark in at 10000ms
    win._get_current_playhead_ms = MagicMock(return_value=10000)
    win._on_manual_mark_in()

    assert win._manual_mark_in_ms == 10000
    assert win.timeline_widget.container.waveform._selected_range_ms == (10000, 10250)

    # Mark out at 12500ms
    win._get_current_playhead_ms = MagicMock(return_value=12500)
    win._on_manual_mark_out()
    qapp.processEvents()

    assert win._manual_mark_in_ms is None
    # Waveform highlights the newly created segment
    assert win.timeline_widget.container.waveform._selected_range_ms == (10000, 12500)
    assert len(win.sub_editor.all_segments) == 1
    created = win.sub_editor.all_segments[0]
    assert created["start"] == "00:00:10,000"
    assert created["end"] == "00:00:12,500"
    assert created["start_ms"] == 10000
    assert created["end_ms"] == 12500


def test_focus_guard_on_mark_in_out(app_window, qapp):
    """Focus guard: When focus is inside a QLineEdit or QTextEdit,
    mark in and mark out do not intercept characters."""
    win = app_window
    line_edit = QLineEdit(win)
    win.setCentralWidget(line_edit)
    line_edit.setFocus()
    qapp.processEvents()
    assert isinstance(QApplication.focusWidget(), QLineEdit)

    win._manual_mark_in_ms = None
    win._get_current_playhead_ms = MagicMock(return_value=5000)

    win._on_manual_mark_in()
    assert win._manual_mark_in_ms is None

    win._manual_mark_in_ms = 5000
    win._on_manual_mark_out()
    # Still 5000 because mark out was guarded
    assert win._manual_mark_in_ms == 5000


def test_empty_sub_editor_add_timing_creates_canonical_srt_strings(app_window, qapp):
    """Adding timing when editor is empty produces valid SRT formatted strings."""
    win = app_window
    win.sub_editor.all_segments = []
    win._get_current_playhead_ms = MagicMock(return_value=500)
    win._get_current_video_duration_ms = MagicMock(return_value=30000)

    idx = win.sub_editor.trigger_add(500, 30000)
    assert idx == 0
    assert len(win.sub_editor.all_segments) == 1
    seg = win.sub_editor.all_segments[0]
    assert seg["start"] == "00:00:00,500"
    assert seg["end"] == "00:00:02,500"
    assert isinstance(seg["start"], str)
    assert isinstance(seg["end"], str)
