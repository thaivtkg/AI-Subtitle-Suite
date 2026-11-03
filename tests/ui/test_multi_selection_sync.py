# -*- coding: utf-8 -*-
import os
import unittest
from PySide6.QtCore import Qt, QPoint, QItemSelectionModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from core.subtitle_editing.selection_controller import (
    SelectionSource,
    SubtitleSelectionController,
)
from core.timeline.timeline_controller import TimelineController
from core.timeline.timeline_data_provider import TimelineDataProvider
from ui.SubEditor import SubtitleEditorWidget
from ui.timeline.timeline_widget import TimelineWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestMultiSelectionSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.selection_controller = SubtitleSelectionController()
        self.provider = TimelineDataProvider()
        self.timeline = TimelineWidget()
        self.editor = SubtitleEditorWidget()
        self.editor.selection_controller = self.selection_controller
        self.controller = TimelineController(
            None,
            self.timeline,
            self.provider,
            selection_controller=self.selection_controller,
        )
        self.selection_controller.selection_changed.connect(self.editor.sync_selection)
        self.selection_controller.multi_selection_changed.connect(self.editor.sync_multi_selection)
        self.segments = [
            {"id": "seg-1", "stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "start_ms": 1000, "end_ms": 3000, "text": "Sub 1"},
            {"id": "seg-2", "stt": "2", "start": "00:00:04,000", "end": "00:00:06,000", "start_ms": 4000, "end_ms": 6000, "text": "Sub 2"},
            {"id": "seg-3", "stt": "3", "start": "00:00:07,000", "end": "00:00:09,000", "start_ms": 7000, "end_ms": 9000, "text": "Sub 3"},
        ]
        self.editor.all_segments = self.segments
        self.editor.render_page()
        self.provider.load_runtime_data(self.segments, 10000)
        self.timeline.load_project_data(10000, self.provider.get_all_segments())

    def tearDown(self):
        self.timeline.deleteLater()
        self.editor.deleteLater()

    def test_table_multi_selection_syncs_to_timeline_track(self):
        """Khi bôi đen 2 dòng trên bảng, Timeline Track phải lưu đúng 2 ID và cùng sáng."""
        sel_model = self.editor.table.selectionModel()
        sel_model.select(self.editor.table.model().index(0, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        sel_model.select(self.editor.table.model().index(1, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.assertEqual(self.editor._get_selected_source_indices(), [0, 1])
        track = self.timeline.container.track
        self.assertEqual(track.selected_ids, {"seg-1", "seg-2"})

    def test_timeline_track_ctrl_click_syncs_to_table(self):
        """Khi Ctrl+Click 2 khối trên Track, Bảng phụ đề phải bôi đen chính xác 2 hàng."""
        track = self.timeline.container.track
        # Sub 1 spans 1000ms..3000ms -> at default zoom (e.g. 100px/s), x=200px is inside Sub 1
        # Sub 2 spans 4000ms..6000ms -> x=500px is inside Sub 2
        seg1 = track.segments[0]
        seg2 = track.segments[1]
        x_seg1 = track._ms_to_x((seg1.start_ms + seg1.end_ms) // 2)
        x_seg2 = track._ms_to_x((seg2.start_ms + seg2.end_ms) // 2)

        QTest.mouseClick(track, Qt.LeftButton, Qt.NoModifier, QPoint(x_seg1, 20))
        self.assertEqual(track.selected_ids, {"seg-1"})

        QTest.mouseClick(track, Qt.LeftButton, Qt.ControlModifier, QPoint(x_seg2, 20))
        self.assertEqual(track.selected_ids, {"seg-1", "seg-2"})
        selected_table_indices = self.editor._get_selected_source_indices()
        self.assertEqual(selected_table_indices, [0, 1])
        self.assertIn("(2 câu)", self.editor.current_editor.lbl_title.text())

    def test_timeline_track_shift_click_also_multi_selects(self):
        """Shift+Click trên Track cũng phải cho phép đa chọn và đồng bộ ngược lên Bảng."""
        track = self.timeline.container.track
        seg1 = track.segments[0]
        seg2 = track.segments[1]
        x_seg1 = track._ms_to_x((seg1.start_ms + seg1.end_ms) // 2)
        x_seg2 = track._ms_to_x((seg2.start_ms + seg2.end_ms) // 2)

        QTest.mouseClick(track, Qt.LeftButton, Qt.NoModifier, QPoint(x_seg1, 20))
        QTest.mouseClick(track, Qt.LeftButton, Qt.ShiftModifier, QPoint(x_seg2, 20))
        self.assertEqual(track.selected_ids, {"seg-1", "seg-2"})
        self.assertEqual(self.editor._get_selected_source_indices(), [0, 1])
