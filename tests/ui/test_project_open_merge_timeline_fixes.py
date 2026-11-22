# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.subtitle_controller import SubtitleController
from core.subtitle_editing.commands.merge_command import MergeCommand
from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_editing.selection_controller import SubtitleSelectionController
from ui.SubEditor import SubtitleEditorWidget
from ui.components.animated_stack import AnimatedStack


class TestProjectOpenMergeAndTimelineFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_subtitle_controller_loads_non_utf8_byte_0xf3_without_error(self):
        ctrl = SubtitleController()
        with tempfile.TemporaryDirectory() as tmp:
            srt_path = os.path.join(tmp, "legacy_cp1252.srt")
            # Byte 0xf3 at offset ~41 (e.g. Spanish/Vietnamese cp1252 character)
            payload = (
                "1\n"
                "00:00:01,000 --> 00:00:03,000\n"
                "Adi\xf3s amigo mio " + ("x" * 20) + "\xf3\n\n"
            ).encode("cp1252")
            with open(srt_path, "wb") as f:
                f.write(payload)

            ctrl.load_srt(srt_path)
            self.assertEqual(len(ctrl.subtitles), 1)
            self.assertIn("Adiós", ctrl.subtitles[0][2])

    def test_merge_selected_rows_1_and_2_even_when_row_2_focused(self):
        undo_mgr = GlobalUndoManager()
        sel_ctrl = SubtitleSelectionController()
        editor = SubtitleEditorWidget()
        editor.undo_manager = undo_mgr
        editor.selection_controller = sel_ctrl
        undo_mgr.state_changed.connect(editor.render_page)

        editor.all_segments = [
            {"id": "s1", "stt": "1", "start": "00:00:01,000", "end": "00:00:02,000", "start_ms": 1000, "end_ms": 2000, "text": "Mot"},
            {"id": "s2", "stt": "2", "start": "00:00:02,200", "end": "00:00:03,000", "start_ms": 2200, "end_ms": 3000, "text": "Hai"},
            {"id": "s3", "stt": "3", "start": "00:00:03,500", "end": "00:00:05,000", "start_ms": 3500, "end_ms": 5000, "text": "Ba"},
        ]
        editor.render_page()

        # Simulate clicking row 1 then Ctrl+clicking row 2 -> current_index becomes 1 (row 2)!
        sel_model = editor.table.selectionModel()
        sel_model.select(editor.table.model().index(0, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        sel_model.select(editor.table.model().index(1, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        editor.current_index = 1

        editor.trigger_merge()

        # Must merge rows 1 and 2 ("Mot Hai"), leaving row 3 ("Ba") untouched
        self.assertEqual(len(editor.all_segments), 2)
        self.assertEqual(editor.all_segments[0]["text"], "Mot Hai")
        self.assertEqual(editor.all_segments[0]["end"], "00:00:03,000")
        self.assertEqual(editor.all_segments[1]["text"], "Ba")

        # Undo restores all 3 segments cleanly
        undo_mgr.undo()
        self.assertEqual(len(editor.all_segments), 3)
        self.assertEqual([s["text"] for s in editor.all_segments], ["Mot", "Hai", "Ba"])
        editor.deleteLater()

    def test_merge_three_contiguous_rows_and_reject_non_contiguous(self):
        undo_mgr = GlobalUndoManager()
        editor = SubtitleEditorWidget()
        editor.undo_manager = undo_mgr
        undo_mgr.state_changed.connect(editor.render_page)

        editor.all_segments = [
            {"id": "s1", "stt": "1", "start": "00:00:01,000", "end": "00:00:02,000", "text": "A"},
            {"id": "s2", "stt": "2", "start": "00:00:02,100", "end": "00:00:03,000", "text": "B"},
            {"id": "s3", "stt": "3", "start": "00:00:03,100", "end": "00:00:04,000", "text": "C"},
        ]
        editor.render_page()

        # Non-contiguous [0, 2] must NOT merge
        sel_model = editor.table.selectionModel()
        sel_model.select(editor.table.model().index(0, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        sel_model.select(editor.table.model().index(2, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        editor.trigger_merge()
        self.assertEqual(len(editor.all_segments), 3)

        # Contiguous [0, 1, 2] merges all 3
        sel_model.select(editor.table.model().index(1, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        editor.trigger_merge()
        self.assertEqual(len(editor.all_segments), 1)
        self.assertEqual(editor.all_segments[0]["text"], "A B C")
        self.assertEqual(editor.all_segments[0]["end"], "00:00:04,000")

        undo_mgr.undo()
        self.assertEqual([s["text"] for s in editor.all_segments], ["A", "B", "C"])
        editor.deleteLater()

    def test_animated_stack_disables_opacity_effect_when_idle(self):
        stack = AnimatedStack()
        p0 = QWidget()
        p1 = QWidget()
        stack.addWidget(p0)
        stack.addWidget(p1)
        stack.resize(300, 200)
        stack.show()
        self.app.processEvents()

        self.assertFalse(p0.graphicsEffect().isEnabled())
        self.assertFalse(p1.graphicsEffect().isEnabled())

        # Instant switch hides old immediately without leaving effects enabled
        stack.setCurrentIndex(1, duration=0)
        self.assertIs(stack.currentWidget(), p1)
        self.assertTrue(p1.isVisible())
        self.assertFalse(p0.isVisible())
        self.assertFalse(p1.graphicsEffect().isEnabled())
        self.assertFalse(p0.graphicsEffect().isEnabled())
        stack.close()

    def test_mainwindow_timeline_multi_select_shift_ctrl_marquee_and_draft_load(self):
        from ui.Gui import MainWindow

        win = MainWindow()
        try:
            segs = [
                {"id": "seg-1", "stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "start_ms": 1000, "end_ms": 3000, "text": "One"},
                {"id": "seg-2", "stt": "2", "start": "00:00:04,000", "end": "00:00:06,000", "start_ms": 4000, "end_ms": 6000, "text": "Two"},
                {"id": "seg-3", "stt": "3", "start": "00:00:07,000", "end": "00:00:09,000", "start_ms": 7000, "end_ms": 9000, "text": "Three"},
            ]
            win.sub_editor.all_segments = segs
            win.sub_editor.render_page()
            win.timeline_data_provider.load_runtime_data(segs, 12000)
            win.timeline_widget.load_project_data(12000, win.timeline_data_provider.get_all_segments())
            win.timeline_widget.resize(1200, 220)
            win.show()
            self.app.processEvents()

            track = win.timeline_widget.container.track
            x1 = track._ms_to_x(2000)
            x2 = track._ms_to_x(5000)
            x3 = track._ms_to_x(8000)

            # 1. Click seg-1 then Ctrl+Click seg-2 -> must stay multi-selected even with VideoPlayer wired
            QTest.mouseClick(track, Qt.LeftButton, Qt.NoModifier, QPoint(x1, 20))
            self.assertEqual(track.selected_ids, {"seg-1"})
            QTest.mouseClick(track, Qt.LeftButton, Qt.ControlModifier, QPoint(x2, 20))
            self.assertEqual(track.selected_ids, {"seg-1", "seg-2"})
            self.assertEqual(win.sub_editor._get_selected_source_indices(), [0, 1])

            # 2. Click seg-1 then Shift+Click seg-3 -> contiguous range {seg-1, seg-2, seg-3}
            QTest.mouseClick(track, Qt.LeftButton, Qt.NoModifier, QPoint(x1, 20))
            QTest.mouseClick(track, Qt.LeftButton, Qt.ShiftModifier, QPoint(x3, 20))
            self.assertEqual(track.selected_ids, {"seg-1", "seg-2", "seg-3"})
            self.assertEqual(win.sub_editor._get_selected_source_indices(), [0, 1, 2])

            # 3. Marquee drag on empty space across seg-1 and seg-2 -> {seg-1, seg-2}
            x_empty_start = track._ms_to_x(200)
            x_drag_end = track._ms_to_x(5500)
            QTest.mousePress(track, Qt.LeftButton, Qt.NoModifier, QPoint(x_empty_start, 20))
            QTest.mouseMove(track, QPoint(x_drag_end, 20))
            QTest.mouseRelease(track, Qt.LeftButton, Qt.NoModifier, QPoint(x_drag_end, 20))
            self.assertEqual(track.selected_ids, {"seg-1", "seg-2"})
            self.assertEqual(win.sub_editor._get_selected_source_indices(), [0, 1])

            # 4. _load_draft_from_center must NOT raise AttributeError on bottom_tabs
            with tempfile.TemporaryDirectory() as tmp:
                vid_path = os.path.join(tmp, "demo_video.mp4")
                draft_path = os.path.join(tmp, "demo_video.ai-subtitle-draft")
                with open(vid_path, "wb") as vf:
                    vf.write(b"fake")
                with open(draft_path, "w", encoding="utf-8") as df:
                    df.write('{"segments": [{"id": "d1", "stt": "1", "start": "00:00:00,000", "end": "00:00:01,000", "start_ms": 0, "end_ms": 1000, "text": "Hi"}]}')
                win.queue_mgr.add_video(vid_path)
                with patch("ui.toast.Toast.show_info"):
                    ok = win._load_draft_from_center(draft_path, silent=True)
                self.assertTrue(ok)
                self.assertEqual(win.stack.currentIndex(), 1)
                self.assertEqual(win.lbl_page_title.text(), "Studio Workspace")
        finally:
            win.close()
            win.deleteLater()

    def test_media_file_rejected_by_subtitle_loaders(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp4_path = os.path.join(tmp, "rendered_hardsub.mp4")
            with open(mp4_path, "wb") as f:
                f.write(b"\x00\x00\x00\x18ftypmp42\xf3\xff\xfe" * 100)

            ctrl = SubtitleController()
            ctrl.load_srt(mp4_path)
            self.assertEqual(ctrl.subtitles, [])

            editor = SubtitleEditorWidget()
            editor.all_segments = [{"id": "1", "stt": "1", "start": "00:00:00,000", "end": "00:00:01,000", "text": "Keep"}]
            editor.load_srt_file(mp4_path)
            self.assertEqual(len(editor.all_segments), 1)
            editor.deleteLater()

    def test_hardsub_artifact_does_not_overwrite_active_artifact_and_workspace_recovers_draft(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from core.artifacts.artifact import Artifact
        from core.artifacts.artifact_store import ArtifactStore
        from core.artifacts.artifact_types import ArtifactStatus, ArtifactType
        from core.services.workspace_service import WorkspaceService
        from ui.Gui import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            draft_path = os.path.join(tmp, "demo.ai-subtitle-draft")
            hardsub_path = os.path.join(tmp, "demo_hardsub.mp4")
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write('{"segments": [{"id": "s1", "start_ms": 0, "end_ms": 1000, "text": "OK"}]}')
            with open(hardsub_path, "wb") as f:
                f.write(b"\x00\x00\x00\x18ftypisom\xf3")

            store = ArtifactStore()
            draft_art = Artifact(
                artifact_id="draft-1",
                artifact_type=ArtifactType.DRAFT,
                path=draft_path,
                created_at="2026-11-19T00:00:00+00:00",
                updated_at="2026-11-19T00:00:00+00:00",
                source_project_id="proj-1",
                status=ArtifactStatus.READY,
            )
            hardsub_art = Artifact(
                artifact_id="hardsub-1",
                artifact_type=ArtifactType.HARDSUB,
                path=hardsub_path,
                created_at="2026-11-19T00:01:00+00:00",
                updated_at="2026-11-19T00:01:00+00:00",
                source_project_id="proj-1",
                status=ArtifactStatus.READY,
            )
            store.register(draft_art)
            store.register(hardsub_art)

            # Simulate corrupted state from older bug where active_artifact_id pointed to HARDSUB .mp4
            proj = SimpleNamespace(
                project_id="proj-1",
                state=SimpleNamespace(
                    active_artifact_id="hardsub-1",
                    subtitle_artifact_id=None,
                    timing=None,
                ),
            )
            ps = SimpleNamespace(current_project=proj, artifact_store=store)
            ws = WorkspaceService(MagicMock(), ps)
            resolved = ws._resolve_subtitle_artifact_path(proj)
            self.assertEqual(resolved, os.path.normpath(draft_path))

            # Also verify _register_artifact with HARDSUB preserves existing active_artifact_id
            win = MainWindow()
            try:
                win.project_service = MagicMock()
                win.project_service.current_project = SimpleNamespace(
                    project_id="proj-1",
                    state=SimpleNamespace(
                        active_artifact_id="draft-1",
                        timing_status="READY",
                        text_status="DRAFT",
                        timing=None,
                    ),
                )
                win.artifact_store = ArtifactStore()
                win._register_artifact(hardsub_path, ArtifactType.HARDSUB, mark_dirty=False)
                self.assertEqual(win.project_service.current_project.state.active_artifact_id, "draft-1")
                self.assertEqual(win.project_service.current_project.state.text_status, "DRAFT")
            finally:
                win.close()
                win.deleteLater()

    def test_tm_manager_recovers_corrupt_database_file(self):
        """A corrupt non-SQLite tm.db file should be backed up to .corrupt and rebuilt cleanly."""
        from core.database.tm_manager import TranslationMemoryManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "tm.db")
            with open(db_path, "wb") as f:
                f.write(b"[mov,mp4,m4a] moov atom not found\n" + b"\x00" * 512)

            tm = TranslationMemoryManager(db_path=db_path)
            try:
                tm.add_segment("Hello", "Xin chao")
                matches = tm.find_matches("Hello")
                self.assertTrue(matches)
                self.assertTrue(os.path.exists(f"{db_path}.corrupt"))
            finally:
                tm.close()
