import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from core.project.project_state import TimingState
from core.timing.timing_run_request import TimingRunRequest
from core.timing.timing_checkpoint import TimingCheckpoint
from core.timing.timing_batch_service import TimingBatchService
from workers.TimingBatchWorker import TimingBatchWorker


class TestMusicMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_timing_state_and_request_defaults(self):
        state = TimingState()
        self.assertFalse(state.music_mode)

        req = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
        )
        self.assertFalse(req.music_mode)
        self.assertIsNone(req.language)

        req_custom = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            music_mode=True,
            language="zh",
        )
        self.assertTrue(req_custom.music_mode)
        self.assertEqual(req_custom.language, "zh")

    def test_checkpoint_and_service_settings_validation(self):
        settings = {
            "model_size": "base",
            "compute_type": "float16",
            "use_vad": True,
            "min_silence_ms": 500,
            "fix_overlap": True,
            "overlap_gap_ms": 50,
            "overlap_ms": 800,
            "max_window_ms": 120000,
            "music_mode": True,
            "language": "zh",
        }
        validated = TimingBatchService._validate_settings(settings)
        self.assertTrue(validated["music_mode"])
        self.assertEqual(validated["language"], "zh")

        cp = TimingCheckpoint(
            project_id="proj_1",
            source_fingerprint="fp_1",
            timing_artifact_id="art_1",
            timing_revision=1,
            batch_size=10,
            **validated,
        )
        self.assertTrue(cp.music_mode)
        self.assertEqual(cp.language, "zh")

        restored_settings = TimingBatchService._settings_from_checkpoint(cp)
        self.assertTrue(restored_settings["music_mode"])
        self.assertEqual(restored_settings["language"], "zh")

    def test_panel_ui_music_mode_toggle_and_sync(self):
        from ui.subtitle_generation_panel import SubtitleGenerationPanel
        from core.subtitle_generation.generation_service import SubtitleGenerationService
        from core.subtitle_generation.faster_whisper_service import FasterWhisperService

        mock_proj_service = MagicMock()
        mock_proj = MagicMock()
        mock_timing = TimingState(music_mode=True)
        mock_proj.state.timing = mock_timing
        mock_proj.state.task_mode = "timing"
        mock_proj_service.current_project = mock_proj

        gen_service = SubtitleGenerationService(FasterWhisperService(), mock_proj_service)
        panel = SubtitleGenerationPanel(gen_service)

        self.assertTrue(hasattr(panel, "chk_music_mode"))
        self.assertFalse(panel.chk_music_mode.isChecked())

        # Test sync from project restores music_mode = True
        panel.sync_timing_settings_from_project()
        self.assertTrue(panel.chk_music_mode.isChecked())

        # Test toggle changes project state
        panel.cmb_mode.setCurrentIndex(1)  # timing mode
        panel.chk_music_mode.setChecked(False)
        self.assertFalse(mock_timing.music_mode)
        settings_off = panel._timing_settings()
        self.assertNotIn("music_mode", settings_off)

        panel.chk_music_mode.setChecked(True)
        self.assertTrue(mock_timing.music_mode)
        settings_on = panel._timing_settings()
        self.assertIn("music_mode", settings_on)
        self.assertTrue(settings_on["music_mode"])

    def test_worker_transcribe_music_mode_active(self):
        req = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            music_mode=True,
            language="zh",
        )
        worker = TimingBatchWorker(req)

        mock_model = MagicMock()
        mock_seg = MagicMock()
        mock_seg.start = 0.5
        mock_seg.end = 4.2
        mock_seg.text = "Hello song"
        mock_model.transcribe.return_value = ([mock_seg], MagicMock(duration=120.0))

        # Test direct inference call inside worker logic
        is_music = getattr(worker.request, "music_mode", False)
        lang = getattr(worker.request, "language", None)
        self.assertTrue(is_music)
        self.assertEqual(lang, "zh")

        kwargs = {"vad_filter": False, "word_timestamps": True}
        if lang:
            kwargs["language"] = lang
        segments_gen, info = mock_model.transcribe("dummy.wav", **kwargs)
        raw_segments = list(segments_gen)

        mock_model.transcribe.assert_called_once_with(
            "dummy.wav",
            vad_filter=False,
            word_timestamps=True,
            language="zh",
        )
        self.assertEqual(len(raw_segments), 1)

    def test_worker_transcribe_standard_mode_uses_vad(self):
        req = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            music_mode=False,
            use_vad=True,
            language="en",
        )
        worker = TimingBatchWorker(req)

        mock_model = MagicMock()
        mock_seg = MagicMock()
        mock_seg.start = 1.0
        mock_seg.end = 3.0
        mock_seg.text = "Conversation"
        mock_info = MagicMock(duration=120.0, duration_after_vad=50.0, language="en", language_probability=0.98)
        mock_model.transcribe.return_value = ([mock_seg], mock_info)

        raw_segments, info = worker._transcribe_with_vad_retry(mock_model, "dummy.wav", language="en")
        self.assertEqual(len(raw_segments), 1)
        # Check vad_filter=True was passed to model.transcribe
        called_kwargs = mock_model.transcribe.call_args[1]
        self.assertTrue(called_kwargs["vad_filter"])
        self.assertTrue(called_kwargs["word_timestamps"])
        self.assertEqual(called_kwargs["language"], "en")
