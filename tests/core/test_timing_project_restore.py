import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from core.artifacts.artifact_store import ArtifactStore
from core.artifacts.artifact import Artifact
from core.artifacts.artifact_types import ArtifactStatus, ArtifactType
from core.project.project_state import TimingState
from core.services.project_service import ProjectService
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.generation_service import SubtitleGenerationService
from core.subtitle_placement import SubtitlePlacementState
from core.timing.timing_batch_service import TimingBatchService
from core.timing.timing_checkpoint import TimingCheckpoint
from ui.subtitle_generation_panel import SubtitleGenerationPanel


class TestTimingProjectRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _project(self):
        root = tempfile.mkdtemp()
        video_path = os.path.join(root, "video.mp4")
        with open(video_path, "wb") as handle:
            handle.write(b"video")
        project_dir = os.path.join(root, "project.ai-subtitle")
        service = ProjectService(ArtifactStore())
        service.create_project(project_dir, "video.mp4", video_path)
        return root, project_dir, service

    def test_resume_uses_33_editor_segments_when_artifact_id_collides(self):
        root, project_dir, service = self._project()
        try:
            timing_service = self._commit_finished_batch(service)
            timing_id = service.current_project.state.timing.timing_artifact_id
            timing_path = service.artifact_store.get(timing_id).path
            segments = [
                {"start_ms": i * 10000, "end_ms": i * 10000 + 3060, "text": f"Old {i}"}
                for i in range(1, 34)
            ]
            with open(timing_path, "w", encoding="utf-8") as handle:
                for i, segment in enumerate(segments, 1):
                    handle.write(
                        f"{i}\n{timing_service._ms_to_time_str(segment['start_ms'])} --> "
                        f"{timing_service._ms_to_time_str(segment['end_ms'])}\nOld {i}\n\n"
                    )
            checkpoint = service.load_timing_checkpoint()
            checkpoint.next_segment_index = 26
            checkpoint.last_completed_end_ms = 253060
            service.save_timing_checkpoint(checkpoint)
            service.current_project.state.timing.next_segment_index = 26
            subtitle_path = os.path.join(project_dir, "subtitle.json")
            with open(subtitle_path, "w", encoding="utf-8") as handle:
                handle.write('{"segments": []}')
            service.artifact_store.register(Artifact(
                artifact_id=timing_id, artifact_type=ArtifactType.SUBTITLE,
                path=subtitle_path, created_at="now", updated_at="now",
                source_project_id=service.current_project.project_id,
                status=ArtifactStatus.READY, revision=1, metadata={},
            ))

            captured = []
            timing_service._execute_run = lambda **kwargs: captured.append(kwargs)
            with self.assertRaisesRegex(ValueError, "Editor có nhiều câu"):
                timing_service.continue_timing(1, {}, existing_segments=segments + [
                    {"start_ms": 340000, "end_ms": 341000}
                ])
            self.assertEqual(service.current_project.state.timing.timing_artifact_id, timing_id)
            # Unknown editor coverage must use the complete artifact.
            timing_service.continue_timing(1, {}, existing_segments=None)
            self.assertEqual(service.load_timing_checkpoint().next_segment_index, 34)
            timing_service.continue_timing(1, {}, existing_segments=[
                {"start": row["start_ms"], "end": row["end_ms"], "text": row["text"]}
                for row in segments
            ])

            self.assertEqual(service.current_project.state.timing.next_segment_index, 34)
            self.assertEqual(service.load_timing_checkpoint().next_segment_index, 34)
            self.assertEqual(captured[0]["start_ms"], segments[-1]["end_ms"])
            self.assertEqual(
                service.artifact_store.get(service.current_project.state.timing.timing_artifact_id).path,
                timing_path,
            )
            self.assertEqual(service.artifact_store.get(timing_id).path, subtitle_path)
            timing_service._on_worker_finished(
                [{"start_ms": 335000, "end_ms": 336000}], True
            )
            with open(timing_path, encoding="utf-8") as handle:
                timing_text = handle.read()
            self.assertEqual(timing_text.count("-->"), 34)
            self.assertIn("Old 33", timing_text)
            self.assertIn("\n34\n", timing_text)
            with open(subtitle_path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), {"segments": []})
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            self.assertEqual(
                reopened.artifact_store.get(
                    reopened.current_project.state.timing.timing_artifact_id
                ).path, timing_path,
            )
            self.assertEqual(reopened.artifact_store.get(timing_id).path, subtitle_path)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resume_button_passes_editor_segments_to_timing_service(self):
        from ui.Gui import MainWindow

        window = MainWindow.__new__(MainWindow)
        segments = [{"start_ms": 379060, "end_ms": 383060}]
        window.sub_editor = SimpleNamespace(all_segments=segments)
        window._current_range_segments = lambda: segments
        window.project_service = MagicMock()
        window.project_service.load_timing_checkpoint.return_value = SimpleNamespace(
            timing_artifact_id="timing"
        )
        window.timing_service = MagicMock()

        MainWindow._resume_timing_draft(window, 5, {"use_vad": True})

        window.timing_service.continue_timing.assert_called_once_with(
            5, {"use_vad": True}, existing_segments=segments
        )

    def test_completed_timing_checkpoint_does_not_offer_resume_after_editor_edits(self):
        from unittest.mock import patch

        root, project_dir, service = self._project()
        try:
            self._commit_finished_batch(service)
            service.current_project.state.timing.status = "IDLE"
            with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
                panel = self._panel(service)

            self.assertFalse(panel._has_resumable_timing_checkpoint())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generate_next_timing_batch_appends_without_recovery_prompt(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        from ui.Gui import MainWindow

        root, project_dir, service = self._project()
        try:
            timing_service = self._commit_finished_batch(service)
            service.current_project.state.timing.status = "IDLE"
            artifact_id = service.current_project.state.timing.timing_artifact_id
            window = MainWindow.__new__(MainWindow)
            window.project_service = service
            window.timing_service = timing_service
            window._current_range_segments = lambda: None
            window._on_timing_error = lambda error: self.fail(error)
            runs = []
            timing_service._execute_run = lambda **kwargs: runs.append(kwargs)
            with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
                panel = self._panel(service)
            panel.cmb_mode.setCurrentIndex(1)
            panel.video_duration_ms = 600000
            panel.spin_batch_val.setValue(3)
            panel.timing_start_requested.connect(
                lambda count, settings: MainWindow._start_timing_draft(window, count, settings)
            )
            panel.timing_resume_requested.connect(
                lambda count, settings: MainWindow._resume_timing_draft(window, count, settings)
            )
            with patch.object(QMessageBox, "question") as prompt:
                panel._on_generate_clicked()
            prompt.assert_not_called()
            self.assertEqual(runs[0]["start_ms"], 4000)
            self.assertEqual(runs[0]["target_count"], 3)
            self.assertEqual(service.current_project.state.timing.timing_artifact_id, artifact_id)
            timing_service._on_worker_finished([
                {"start_ms": 5000, "end_ms": 6000},
                {"start_ms": 7000, "end_ms": 8000},
                {"start_ms": 9000, "end_ms": 10000},
            ], False)
            artifact = service.artifact_store.get(artifact_id)
            with open(artifact.path, encoding="utf-8") as handle:
                self.assertEqual(handle.read().count("-->"), 5)
            self.assertEqual(service.load_timing_checkpoint().next_segment_index, 6)
            service.current_project.state.timing.status = "COMPLETED"
            panel._reset_ui_state()
            with patch.object(QMessageBox, "question") as prompt:
                panel._on_generate_clicked()
            prompt.assert_not_called()
            self.assertEqual(runs[1]["start_ms"], 10000)
            self.assertEqual(service.current_project.state.timing.timing_artifact_id, artifact_id)
            timing_service._on_worker_finished([], True)
            with open(artifact.path, encoding="utf-8") as handle:
                self.assertEqual(handle.read().count("-->"), 5)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_continue_timing_keeps_editor_edits_and_deleted_rows(self):
        root, project_dir, service = self._project()
        try:
            timing_service = self._commit_finished_batch(service)
            artifact_id = service.current_project.state.timing.timing_artifact_id
            runs = []
            timing_service._execute_run = lambda **kwargs: runs.append(kwargs)
            edited = [{"start": "00:00:01,200", "end": "00:00:02,500", "text": "Edited\nsubtitle"}]
            with open(service.artifact_store.get(artifact_id).path, encoding="utf-8") as handle:
                original_draft = handle.read()
            timing_service.continue_timing(1, {}, existing_segments=edited)
            self.assertEqual(runs[0]["start_ms"], 2500)
            with open(service.artifact_store.get(artifact_id).path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), original_draft)
            timing_service._on_worker_finished([{"start_ms": 5000, "end_ms": 6000}], False)
            with open(service.artifact_store.get(artifact_id).path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertEqual(content.count("-->"), 2)
            self.assertIn("00:00:01,200 --> 00:00:02,500\nEdited\nsubtitle", content)
            self.assertNotIn("00:00:03,000", content)
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            self.assertEqual(reopened.load_timing_checkpoint().next_segment_index, 3)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_continue_timing_after_deleting_all_rows_keeps_empty_editor_authoritative(self):
        root, project_dir, service = self._project()
        try:
            timing_service = self._commit_finished_batch(service)
            runs = []
            timing_service._execute_run = lambda **kwargs: runs.append(kwargs)
            timing_service.continue_timing(1, {}, existing_segments=[])
            self.assertEqual(runs[0]["start_ms"], 0)
            timing_service._on_worker_finished([{"start_ms": 5000, "end_ms": 6000}], False)
            artifact_id = service.current_project.state.timing.timing_artifact_id
            with open(service.artifact_store.get(artifact_id).path, encoding="utf-8") as handle:
                content = handle.read()
            self.assertEqual(content.count("-->"), 1)
            self.assertTrue(content.startswith("1\n"))
            self.assertEqual(service.load_timing_checkpoint().next_segment_index, 2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def _panel(service):
        return SubtitleGenerationPanel(
            SubtitleGenerationService(FasterWhisperService(), service)
        )

    @staticmethod
    def _configure_timing(panel):
        panel.cmb_mode.setCurrentIndex(1)
        for i in range(panel.cmb_model.count()):
            if panel.cmb_model.itemData(i) == "large-v3-turbo":
                panel.cmb_model.setCurrentIndex(i)
                break
        else:
            panel.cmb_model.setCurrentText("large-v3-turbo")
        panel.cmb_compute.setCurrentText("float16")
        panel.chk_fix_overlap.setChecked(True)
        panel.spin_overlap_gap.setValue(80)

    @staticmethod
    def _commit_finished_batch(service, task_mode="timing"):
        state = service.current_project.state
        state.task_mode = task_mode
        state.timing = TimingState(
            model_size="small",
            compute_type="int8",
            use_vad=True,
            min_silence_ms=731,
            fix_overlap=True,
            overlap_gap_ms=137,
            overlap_ms=913,
            max_window_ms=98765,
            batch_size=2,
            next_segment_index=1,
        )
        service.save_project()

        timing_service = TimingBatchService(service)
        timing_service._current_settings = {
            "model_size": "small",
            "compute_type": "int8",
            "use_vad": True,
            "min_silence_ms": 731,
            "fix_overlap": True,
            "overlap_gap_ms": 137,
            "overlap_ms": 913,
            "max_window_ms": 98765,
        }
        timing_service._on_worker_finished(
            [
                {"start_ms": 1000, "end_ms": 2000, "text": "A"},
                {"start_ms": 3000, "end_ms": 4000, "text": "B"},
            ],
            True,
        )
        return timing_service

    def test_r1_timing_transaction_preserves_task_mode(self):
        root, project_dir, service = self._project()
        try:
            self._commit_finished_batch(service)
            with open(os.path.join(project_dir, "state.json"), encoding="utf-8") as handle:
                disk_state = json.load(handle)
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            self.assertEqual(disk_state["task_mode"], "timing")
            self.assertEqual(reopened.current_project.state.task_mode, "timing")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_r2_timing_transaction_preserves_unrelated_project_state(self):
        root, project_dir, service = self._project()
        try:
            state = service.current_project.state
            state.task_mode = "timing"
            state.text_status = "READY"
            state.export_status = "DONE"
            state.subtitle_artifact_id = "subtitle-artifact"
            state.selected_segment_id = "segment-7"
            state.subtitle_placement = SubtitlePlacementState(mode="top", x=0.2, y=0.3)
            self._commit_finished_batch(service)

            with open(os.path.join(project_dir, "state.json"), encoding="utf-8") as handle:
                disk_state = json.load(handle)
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            restored = reopened.current_project.state
            self.assertEqual(disk_state["text_status"], "READY")
            self.assertEqual(disk_state["export_status"], "DONE")
            self.assertEqual(
                disk_state["active_artifact_id"],
                restored.timing.timing_artifact_id,
            )
            self.assertEqual(disk_state["subtitle_artifact_id"], "subtitle-artifact")
            self.assertEqual(disk_state["selected_segment_id"], "segment-7")
            self.assertEqual(disk_state["subtitle_placement"], {"mode": "top", "x": 0.2, "y": 0.3})
            self.assertEqual(restored.text_status, "READY")
            self.assertEqual(restored.export_status, "DONE")
            self.assertEqual(restored.subtitle_artifact_id, "subtitle-artifact")
            self.assertEqual(restored.selected_segment_id, "segment-7")
            self.assertEqual(restored.subtitle_placement, SubtitlePlacementState(mode="top", x=0.2, y=0.3))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_r3_worker_finished_commit_round_trips_timing_artifact(self):
        root, project_dir, service = self._project()
        try:
            self._commit_finished_batch(service)
            expected = service.current_project.state
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            restored = reopened.current_project.state
            self.assertEqual(restored.task_mode, "timing")
            self.assertEqual(restored.timing.model_size, "small")
            self.assertEqual(restored.timing.compute_type, "int8")
            self.assertEqual(restored.timing.overlap_gap_ms, 137)
            self.assertEqual(restored.timing.timing_artifact_id, expected.timing.timing_artifact_id)
            self.assertEqual(restored.timing_status, "READY")
            self.assertTrue(os.path.exists(
                reopened.artifact_store.get(restored.timing.timing_artifact_id).path
            ))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_r4_timing_transaction_preserves_asr_task_mode(self):
        root, project_dir, service = self._project()
        try:
            self._commit_finished_batch(service, task_mode="asr")
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            self.assertEqual(reopened.current_project.state.task_mode, "asr")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_r5_retry_uses_checkpoint_owned_settings(self):
        root, _project_dir, service = self._project()
        try:
            project = service.current_project
            checkpoint_settings = {
                "model_size": "large-v3-turbo",
                "compute_type": "float16",
                "use_vad": True,
                "min_silence_ms": 500,
                "fix_overlap": True,
                "overlap_gap_ms": 80,
                "overlap_ms": 800,
                "max_window_ms": 120000,
            }
            caller_settings = {
                "model_size": "small",
                "compute_type": "int8",
                "use_vad": True,
                "min_silence_ms": 900,
                "fix_overlap": False,
                "overlap_gap_ms": 137,
                "overlap_ms": 1200,
                "max_window_ms": 60000,
            }
            service.save_timing_checkpoint(TimingCheckpoint(
                project_id=project.project_id,
                source_fingerprint=project.source.fingerprint,
                timing_artifact_id="",
                timing_revision=1,
                batch_size=1,
                active_batch={
                    "start_segment": 1,
                    "start_ms": 250,
                    "status": "FAILED",
                },
                **checkpoint_settings,
            ))
            timing_service = TimingBatchService(service)
            captured = []
            timing_service._execute_run = lambda **kwargs: captured.append(kwargs)

            timing_service.retry_timing(3, caller_settings)

            self.assertEqual(captured[0]["target_count"], 3)
            self.assertEqual(captured[0]["settings"], checkpoint_settings)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_r6_resume_transaction_preserves_current_project_preference(self):
        root, project_dir, service = self._project()
        try:
            checkpoint_settings = {
                "model_size": "large-v3-turbo",
                "compute_type": "float16",
                "use_vad": True,
                "min_silence_ms": 500,
                "fix_overlap": True,
                "overlap_gap_ms": 80,
                "overlap_ms": 800,
                "max_window_ms": 120000,
            }
            current_settings = {
                "model_size": "small",
                "compute_type": "int8",
                "use_vad": True,
                "min_silence_ms": 500,
                "fix_overlap": False,
                "overlap_gap_ms": 137,
                "overlap_ms": 800,
                "max_window_ms": 120000,
            }
            state = service.current_project.state
            state.task_mode = "timing"
            for name, value in checkpoint_settings.items():
                setattr(state.timing, name, value)
            state.timing.batch_size = 1
            state.timing.next_segment_index = 1
            service.save_project()

            timing_service = TimingBatchService(service)
            timing_service._current_settings = checkpoint_settings.copy()
            timing_service._on_worker_finished(
                [{"start_ms": 1000, "end_ms": 2000}], True
            )

            for name, value in current_settings.items():
                setattr(state.timing, name, value)
            captured = []
            timing_service._execute_run = lambda **kwargs: captured.append(kwargs)
            timing_service.continue_timing(1, current_settings)
            self.assertEqual(captured[0]["settings"], checkpoint_settings)

            timing_service._current_settings = checkpoint_settings.copy()
            timing_service._on_worker_finished(
                [{"start_ms": 3000, "end_ms": 4000}], True
            )

            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            restored_timing = reopened.current_project.state.timing
            checkpoint = reopened.load_timing_checkpoint()
            self.assertEqual(restored_timing.model_size, "small")
            self.assertEqual(restored_timing.compute_type, "int8")
            self.assertFalse(restored_timing.fix_overlap)
            self.assertEqual(restored_timing.overlap_gap_ms, 137)
            self.assertEqual(checkpoint.model_size, "large-v3-turbo")
            self.assertEqual(checkpoint.compute_type, "float16")
            self.assertTrue(checkpoint.fix_overlap)
            self.assertEqual(checkpoint.overlap_gap_ms, 80)
            self.assertEqual(reopened.current_project.state.task_mode, "timing")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p1_real_ui_mutation_save_and_reload(self):
        root, project_dir, service = self._project()
        try:
            panel = self._panel(service)
            self._configure_timing(panel)
            service.save_project()

            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            timing = reopened.current_project.state.timing
            self.assertEqual(timing.model_size, "large-v3-turbo")
            self.assertEqual(timing.compute_type, "float16")
            self.assertTrue(timing.fix_overlap)
            self.assertEqual(timing.overlap_gap_ms, 80)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p2_loaded_timing_project_restores_panel_mode_and_values(self):
        root, project_dir, service = self._project()
        try:
            panel = self._panel(service)
            self._configure_timing(panel)
            service.save_project()

            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            restored_panel = self._panel(reopened)
            restored_panel.sync_timing_settings_from_project()

            self.assertEqual(restored_panel.cmb_mode.currentData(), "timing")
            self.assertEqual(restored_panel.cmb_model.currentData(), "large-v3-turbo")
            self.assertEqual(restored_panel.cmb_compute.currentText(), "float16")
            self.assertTrue(restored_panel.chk_fix_overlap.isChecked())
            self.assertEqual(restored_panel.spin_overlap_gap.value(), 80)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p3_round_trip_preserves_all_timing_values(self):
        root, project_dir, service = self._project()
        try:
            service.current_project.state.timing = TimingState(
                model_size="small",
                compute_type="int8",
                use_vad=True,
                min_silence_ms=731,
                fix_overlap=True,
                overlap_gap_ms=137,
                overlap_ms=913,
                max_window_ms=98765,
            )
            service.save_project()
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            self.assertEqual(reopened.current_project.state.timing, service.current_project.state.timing)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p4_round_trip_preserves_false_overlap_and_custom_gap(self):
        root, project_dir, service = self._project()
        try:
            service.current_project.state.timing.fix_overlap = False
            service.current_project.state.timing.overlap_gap_ms = 137
            service.save_project()
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            timing = reopened.current_project.state.timing
            self.assertFalse(timing.fix_overlap)
            self.assertEqual(timing.overlap_gap_ms, 137)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p5_programmatic_panel_restore_does_not_dirty(self):
        root, project_dir, service = self._project()
        try:
            service.current_project.state.task_mode = "timing"
            service.current_project.state.timing.overlap_gap_ms = 80
            service.save_project()
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            reopened.revision_tracker = MagicMock(is_transitioning=False)
            panel = self._panel(reopened)
            panel.sync_timing_settings_from_project()
            self.assertFalse(reopened.current_project.state.dirty)
            reopened.revision_tracker.record_external_change.assert_not_called()
            panel.spin_overlap_gap.setValue(81)
            reopened.revision_tracker.record_external_change.assert_called_once_with()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p6_mode_switch_keeps_timing_preferences(self):
        root, _project_dir, service = self._project()
        try:
            panel = self._panel(service)
            self._configure_timing(panel)
            panel.cmb_mode.setCurrentIndex(0)
            panel.cmb_mode.setCurrentIndex(1)
            self.assertEqual(panel.cmb_model.currentData(), "large-v3-turbo")
            self.assertEqual(panel.cmb_compute.currentText(), "float16")
            self.assertEqual(panel.spin_overlap_gap.value(), 80)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p7_project_switch_keeps_timing_settings_isolated(self):
        root, project_a, service = self._project()
        video_b = os.path.join(root, "video-b.mp4")
        with open(video_b, "wb") as handle:
            handle.write(b"video-b")
        project_b = os.path.join(root, "project-b.ai-subtitle")
        try:
            service.current_project.state.timing.overlap_gap_ms = 80
            service.save_project()
            service.create_project(project_b, "video-b.mp4", video_b)
            service.current_project.state.timing.overlap_gap_ms = 137
            service.save_project()
            service.open_project(project_a)
            self.assertEqual(service.current_project.state.timing.overlap_gap_ms, 80)
            service.open_project(project_b)
            self.assertEqual(service.current_project.state.timing.overlap_gap_ms, 137)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p8_legacy_project_without_timing_loads_cleanly(self):
        root, project_dir, service = self._project()
        try:
            service.save_project()
            state_path = os.path.join(project_dir, "state.json")
            with open(state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            data.pop("timing", None)
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            self.assertEqual(reopened.current_project.state.timing, TimingState())
            self.assertFalse(reopened.current_project.state.dirty)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p9_legacy_project_without_task_mode_defaults_without_mutation(self):
        root, project_dir, service = self._project()
        try:
            service.save_project()
            state_path = os.path.join(project_dir, "state.json")
            with open(state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            data.pop("task_mode", None)
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)

            reopened = ProjectService(ArtifactStore())
            reopened.revision_tracker = MagicMock(is_transitioning=False)
            reopened.open_project(project_dir)

            self.assertEqual(reopened.current_project.state.task_mode, "asr")
            self.assertFalse(reopened.current_project.state.dirty)
            reopened.revision_tracker.record_external_change.assert_not_called()
            with open(state_path, "r", encoding="utf-8") as handle:
                self.assertNotIn("task_mode", json.load(handle))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _corrupt_timing_vad_fixture(self):
        root, project_dir, service = self._project()
        service.current_project.state.task_mode = "timing"
        service.current_project.state.timing.use_vad = False
        service.save_project()
        reopened = ProjectService(ArtifactStore())
        reopened.open_project(project_dir)
        return root, reopened

    def test_p10_timing_restore_forces_vad_in_ui_and_effective_settings(self):
        root, service = self._corrupt_timing_vad_fixture()
        try:
            panel = self._panel(service)
            panel.sync_timing_settings_from_project()
            self.assertTrue(panel.chk_vad.isChecked())
            self.assertTrue(panel._timing_settings()["use_vad"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p10_timing_generate_forces_vad_true(self):
        root, service = self._corrupt_timing_vad_fixture()
        try:
            panel = self._panel(service)
            panel.sync_timing_settings_from_project()
            panel.video_duration_ms = 1
            panel._set_ui_state_running = lambda: None
            panel._has_resumable_timing_checkpoint = lambda: False
            calls = []
            panel.timing_start_requested.connect(lambda _batch, settings: calls.append(settings))
            panel._on_generate_clicked()
            self.assertTrue(calls[0]["use_vad"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_p10_timing_resume_forces_vad_true(self):
        root, service = self._corrupt_timing_vad_fixture()
        try:
            panel = self._panel(service)
            panel.sync_timing_settings_from_project()
            panel._set_ui_state_running = lambda: None
            calls = []
            panel.timing_resume_requested.connect(lambda _batch, settings: calls.append(settings))
            panel._on_resume_clicked()
            self.assertTrue(calls[0]["use_vad"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


    def test_timing_project_restore_preserves_language(self):
        """Xác thực khôi phục đúng ngôn ngữ đã lưu trong dự án khi mở lại."""
        root, project_dir, service = self._project()
        try:
            state = service.current_project.state
            state.task_mode = "timing"
            state.timing = TimingState(language="ja")
            service.save_project()

            reopened = ProjectService(ArtifactStore())
            reopened.open_project(project_dir)
            panel = self._panel(reopened)
            panel.sync_timing_settings_from_project()
            self.assertEqual(panel.cmb_language.currentText(), "ja")
            self.assertEqual(panel._timing_settings().get("language"), "ja")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_tc_timing_resume_self_heals_when_artifact_revision_ahead(self):
        """Kiểm tra TimingBatchService tự đồng bộ khi artifact.revision > checkpoint.timing_revision"""
        root, project_dir, service = self._project()
        try:
            self._commit_finished_batch(service)
            timing_service = TimingBatchService(service)
            checkpoint = service.load_timing_checkpoint()
            artifact = service.artifact_store.get(checkpoint.timing_artifact_id)

            # Giả lập người dùng edit phụ đề: revision tăng lên 5 trong khi checkpoint vẫn là 2
            checkpoint.timing_revision = 2
            service.save_timing_checkpoint(checkpoint)
            artifact.revision = 5

            captured = []
            timing_service._execute_run = lambda **kwargs: captured.append(kwargs)

            # Không được quăng ValueError('Dữ liệu Checkpoint bị cũ')
            timing_service.continue_timing(1, {})

            updated_checkpoint = service.load_timing_checkpoint()
            self.assertEqual(updated_checkpoint.timing_revision, 5)
            self.assertEqual(len(captured), 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_tc_timing_generate_prompt_choice_start_fresh(self):
        """Khi có checkpoint, chọn No sẽ bắt đầu lại từ đầu thay vì resume."""
        from PySide6.QtWidgets import QMessageBox
        from unittest.mock import patch

        root, project_dir, service = self._project()
        try:
            self._commit_finished_batch(service)
            # A completed batch is not resumable unless an unfinished batch remains.
            service.current_project.state.timing.status = "IDLE"
            checkpoint = service.load_timing_checkpoint()
            checkpoint.active_batch = {"status": "CANCELLED"}
            service.save_timing_checkpoint(checkpoint)
            with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
                panel = self._panel(service)
            panel.cmb_mode.setCurrentIndex(1)  # timing mode
            panel.video_duration_ms = 600000
            panel._set_ui_state_running = lambda: None
            self.assertTrue(panel._has_resumable_timing_checkpoint())

            start_calls = []
            resume_calls = []
            panel.timing_start_requested.connect(lambda b, s: start_calls.append((b, s)))
            panel.timing_resume_requested.connect(lambda b, s: resume_calls.append((b, s)))

            # Chọn No -> start fresh
            with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
                panel._on_generate_clicked()

            self.assertEqual(len(start_calls), 1)
            self.assertEqual(len(resume_calls), 0)

            # Chọn Yes -> resume
            start_calls.clear()
            resume_calls.clear()
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                panel._on_generate_clicked()

            self.assertEqual(len(start_calls), 0)
            self.assertEqual(len(resume_calls), 1)

            # Chọn Cancel -> không làm gì
            start_calls.clear()
            resume_calls.clear()
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel):
                panel._on_generate_clicked()

            self.assertEqual(len(start_calls), 0)
            self.assertEqual(len(resume_calls), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_start_timing_with_external_srt_continues_from_last_subtitle(self):
        """start_timing(existing_segments=...) must continue after last external SRT end time."""
        root, _project_dir, service = self._project()
        try:
            timing_service = TimingBatchService(service)
            captured = []
            timing_service._execute_run = lambda **kwargs: captured.append(kwargs)

            external_segments = [
                {"start": 1000, "end": 4000, "text": "Ext line 1"},
                {"start": 5000, "end": 12500, "text": "Ext line 2"},
            ]
            timing_service.start_timing(2, {}, existing_segments=external_segments)

            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["start_ms"], 12500)
            cp = service.load_timing_checkpoint()
            self.assertEqual(cp.next_segment_index, 3)
            self.assertEqual(cp.last_completed_end_ms, 12500)

            timing_service._on_worker_finished(
                [{"start_ms": 14000, "end_ms": 16500, "text": ""}],
                is_end_of_source=True,
            )
            from core.srt_parser import SrtParser
            art = service.artifact_store.get(service.current_project.state.timing.timing_artifact_id)
            self.assertIsNotNone(art)
            parsed = SrtParser.parse(art.path)
            self.assertEqual(len(parsed), 3)
            self.assertEqual(parsed[0]["text"], "Ext line 1")
            self.assertEqual(parsed[1]["text"], "Ext line 2")
            self.assertEqual(parsed[1]["end"], 12500)
            self.assertEqual(parsed[2]["start"], 14000)

            # Empty trailing VAD result at EOF must still commit preserved external segments.
            timing_service2 = TimingBatchService(service)
            timing_service2._execute_run = lambda **kwargs: None
            timing_service2.start_timing(2, {}, existing_segments=external_segments)
            timing_service2._on_worker_finished([], is_end_of_source=True)
            art2 = service.artifact_store.get(service.current_project.state.timing.timing_artifact_id)
            parsed2 = SrtParser.parse(art2.path)
            self.assertEqual(len(parsed2), 2)
            self.assertEqual(parsed2[1]["end"], 12500)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_add_external_srt_then_generate_timing_continues_from_last_segment(self):
        """Adding external SRT via panel (even over a stale timing checkpoint) continues from its end."""
        from PySide6.QtWidgets import QFileDialog, QMainWindow
        from unittest.mock import patch
        from ui.Gui import MainWindow

        root, project_dir, service = self._project()
        try:
            # Seed a stale earlier timing checkpoint to verify external SRT import clears it.
            self._commit_finished_batch(service)
            cp = service.load_timing_checkpoint()
            cp.active_batch = {"status": "CANCELLED"}
            service.save_timing_checkpoint(cp)

            srt_path = os.path.join(root, "external.srt")
            with open(srt_path, "w", encoding="utf-8") as handle:
                handle.write(
                    "1\n00:00:02,000 --> 00:00:05,000\nFirst line\n\n"
                    "2\n00:06:30,000 --> 00:06:32,450\nLast line\n\n"
                )

            with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
                panel = self._panel(service)

            win = QMainWindow()
            win.setCentralWidget(panel)

            class FakeEditor:
                def __init__(self, project_svc):
                    self.project_service = project_svc
                    self.all_segments = []
                    self.srt_path = None
                    self.undo_manager = None

                def render_page(self):
                    pass

                def save_draft(self, filepath=None, silent=False):
                    target = filepath or self.srt_path or os.path.join(project_dir, "Project.ai-subtitle-draft")
                    self.project_service.save_draft(target, self.all_segments)
                    self.srt_path = target
                    return target

            video_path = os.path.join(root, "video.mp4")
            item_key = "item_ext_1"

            class FakeQueue:
                def __init__(self):
                    self.active_item_key = item_key
                    self.active_vid = video_path
                    self.srt_for_item = None

                def get_item(self, key):
                    if key == item_key:
                        return {
                            "project_id": service.current_project.project_id,
                            "project_root": project_dir,
                        }
                    return {}

                def set_srt_for_video(self, key, path):
                    if key == item_key:
                        self.srt_for_item = path

                def get_active_data(self):
                    return video_path, self.srt_for_item

            win.sub_editor = FakeEditor(service)
            win.queue_mgr = FakeQueue()
            win.project_service = service
            win.generation_panel = panel
            win._queue_project_identity_matches = lambda pid, proot: MainWindow._queue_project_identity_matches(win, pid, proot)
            win._current_range_segments = lambda: MainWindow._current_range_segments(win)
            win._on_timing_error = lambda msg: self.fail(f"Unexpected timing error: {msg}")

            timing_service = TimingBatchService(service)
            captured = []
            timing_service._execute_run = lambda **kwargs: captured.append(kwargs)
            win.timing_service = timing_service

            with patch.object(QFileDialog, "getOpenFileName", return_value=(srt_path, "")):
                panel._on_add_external_srt()

            # Draft saved inside project dir and bound to queue so _current_range_segments succeeds
            self.assertIsNotNone(win.queue_mgr.srt_for_item)
            self.assertTrue(win.queue_mgr.srt_for_item.startswith(project_dir))
            self.assertIsNone(service.load_timing_checkpoint())

            panel.cmb_mode.setCurrentIndex(1)  # Timing Draft (VAD Only)
            panel.video_duration_ms = 600000
            panel._set_ui_state_running = lambda: None
            panel.timing_start_requested.connect(
                lambda b, s: MainWindow._start_timing_draft(win, b, s)
            )
            panel.timing_resume_requested.connect(
                lambda b, s: self.fail("Should start timing from external SRT end instead of resuming stale checkpoint")
            )

            panel._on_generate_clicked()

            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["start_ms"], 392450)
            self.assertEqual(service.load_timing_checkpoint().next_segment_index, 3)

            # Selecting No (Start Fresh) on a resumable prompt must start at 0ms and ignore editor segments.
            panel._set_ui_state_running = lambda: None
            panel.timing_start_requested.disconnect()
            captured.clear()
            panel._timing_start_fresh = True
            MainWindow._start_timing_draft(win, 2, {})
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["start_ms"], 0)
            self.assertFalse(panel._timing_start_fresh)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
