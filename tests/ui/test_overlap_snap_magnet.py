# -*- coding: utf-8 -*-
"""
Tests for FR-02: Overlap Snap Magnet & Eco-Timer 1Hz (DEV-SPEC-PHASE1-HUD-001).
Validates:
1. Overlap detection between consecutive subtitle segments.
2. Eco-Timer: 1Hz (500ms cycle) starts ONLY when overlap > 0 and widget is visible, stops when overlap == 0 or widget is hidden.
3. Snap Overlap: Resizes previous segment's end_ms to (next_seg.start_ms - 20ms) via ResizeEndCommand.
4. Undo: Ctrl+Z restores original overlapping duration cleanly.
5. Soft/Non-blocking: Overlap warning does not prevent workspace operations.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_editing.selection_controller import SubtitleSelectionController, SelectionSource
from core.timeline.timeline_controller import TimelineController
from core.timeline.timeline_data_provider import TimelineDataProvider
from ui.timeline.subtitle_track import SubtitleTrack
from ui.timeline.timeline_widget import TimelineWidget


app = QApplication.instance() or QApplication([])


class TestOverlapSnapMagnet(unittest.TestCase):
    def setUp(self):
        self.dirty_calls = []
        self.artifact = SimpleNamespace(revision=0)
        self.project = SimpleNamespace(
            current_project=SimpleNamespace(state=SimpleNamespace(active_artifact_id="sub")),
            artifact_store=SimpleNamespace(get=lambda _id: self.artifact),
            mark_dirty=lambda: self.dirty_calls.append("dirty"),
        )
        # Create 2 overlapping segments: seg1 ends at 2500ms, seg2 starts at 2000ms (500ms overlap)
        self.rows = [
            {"id": "seg_1", "stt": "1", "start_ms": 1000, "end_ms": 2500, "text": "Segment one", "status": "generated"},
            {"id": "seg_2", "stt": "2", "start_ms": 2000, "end_ms": 4000, "text": "Segment two", "status": "generated"},
        ]
        self.provider = TimelineDataProvider()
        self.provider.load_runtime_data(self.rows, 10000)

        self.timeline = TimelineWidget()
        self.timeline.load_project_data(10000, self.provider.get_all_segments())
        self.timeline.show()
        self.selection = SubtitleSelectionController()
        self.undo = GlobalUndoManager()
        self.controller = TimelineController(
            self.project, self.timeline, self.provider, self.undo, self.selection
        )
        self.undo.state_changed.connect(self.controller._refresh_ui)

    def tearDown(self):
        self.undo.undo_stack.cleanChanged.disconnect()
        self.timeline.close()
        self.timeline.deleteLater()

    def test_count_overlaps_detects_collision(self):
        track = self.timeline.container.track
        self.assertEqual(track.count_overlaps(), 1)

        # Non-overlapping segments
        non_overlap_rows = [
            {"id": "s1", "stt": "1", "start_ms": 1000, "end_ms": 2000, "text": "s1", "status": "generated"},
            {"id": "s2", "stt": "2", "start_ms": 2500, "end_ms": 4000, "text": "s2", "status": "generated"},
        ]
        provider = TimelineDataProvider()
        provider.load_runtime_data(non_overlap_rows, 10000)
        self.timeline.load_project_data(10000, provider.get_all_segments())
        self.assertEqual(track.count_overlaps(), 0)

    def test_eco_timer_lifecycle_starts_on_overlap_stops_when_cleared(self):
        track = self.timeline.container.track
        track.show()
        track.check_overlap_timer()
        # Has 1 overlap and is visible -> timer must be active
        self.assertTrue(hasattr(track, "_overlap_timer"))
        self.assertTrue(track._overlap_timer.isActive())
        self.assertEqual(track._overlap_timer.interval(), 500)

        # Clear overlaps -> timer must stop
        non_overlap_rows = [
            {"id": "s1", "stt": "1", "start_ms": 1000, "end_ms": 1900, "text": "s1", "status": "generated"},
            {"id": "s2", "stt": "2", "start_ms": 2000, "end_ms": 3000, "text": "s2", "status": "generated"},
        ]
        provider = TimelineDataProvider()
        provider.load_runtime_data(non_overlap_rows, 10000)
        self.timeline.load_project_data(10000, provider.get_all_segments())
        track.check_overlap_timer()
        self.assertFalse(track._overlap_timer.isActive())

    def test_eco_timer_stops_on_hide_and_resumes_on_show(self):
        track = self.timeline.container.track
        track.show()
        track.check_overlap_timer()
        self.assertTrue(track._overlap_timer.isActive())

        # Widget hide stops timer to conserve battery/CPU
        track.hide()
        self.assertFalse(track._overlap_timer.isActive())

        # Widget show resumes timer
        track.show()
        self.assertTrue(track._overlap_timer.isActive())

    def test_overlap_blink_toggles_flag(self):
        track = self.timeline.container.track
        initial_flag = track._overlap_blink_on
        track._toggle_overlap_blink()
        self.assertNotEqual(track._overlap_blink_on, initial_flag)
        track._toggle_overlap_blink()
        self.assertEqual(track._overlap_blink_on, initial_flag)

    def test_snap_overlap_resizes_end_with_20ms_gap(self):
        # Initial: seg_1 end = 2500ms, seg_2 start = 2000ms (overlap 500ms)
        success = self.controller.snap_overlap("seg_1")
        self.assertTrue(success)

        seg1 = self.provider.get_segment("seg_1")
        seg2 = self.provider.get_segment("seg_2")

        # seg1.end_ms must be snapped to seg2.start_ms - 20ms = 1980ms
        self.assertEqual(seg1.end_ms, 1980)
        self.assertEqual(seg2.start_ms, 2000)
        self.assertEqual(seg2.start_ms - seg1.end_ms, 20)
        self.assertEqual(self.timeline.container.track.count_overlaps(), 0)

    def test_snap_overlap_undo_restores_original_end_time(self):
        # Perform snap
        self.controller.snap_overlap("seg_1")
        self.assertEqual(self.provider.get_segment("seg_1").end_ms, 1980)

        # Undo via timeline controller
        self.controller.handle_undo()
        self.assertEqual(self.provider.get_segment("seg_1").end_ms, 2500)
        self.assertEqual(self.timeline.container.track.count_overlaps(), 1)

    def test_snap_overlap_without_argument_finds_first_collision(self):
        # Auto-detects first collision when no segment_id is given
        success = self.controller.snap_overlap()
        self.assertTrue(success)
        self.assertEqual(self.provider.get_segment("seg_1").end_ms, 1980)

    def test_btn_snap_overlap_widget_exists(self):
        self.assertTrue(hasattr(self.timeline, "btn_snap_overlap") or hasattr(self.timeline.container, "btn_snap_overlap"))
        btn = getattr(self.timeline, "btn_snap_overlap", None) or getattr(self.timeline.container, "btn_snap_overlap", None)
        self.assertIsNotNone(btn)
        self.assertEqual(btn.objectName(), "btn_snap_overlap")


if __name__ == "__main__":
    unittest.main()
