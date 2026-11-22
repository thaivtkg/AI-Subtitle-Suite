"""
Test suite for VAD parameter flow, retry capping, and hallucination filtering.

Verifies:
- TC-VAD-FILTER-01: TimingRunRequest receives VAD parameters.
  - Default values are None.
  - Custom values are stored and accessible on TimingRunRequest and TimingCheckpoint.
  - TimingBatchService._validate_settings retains all 5 VAD parameters without dropping.
  - TimingBatchService._settings_from_checkpoint and _execute_run inject all 5 VAD parameters.
- TC-VAD-FILTER-02: VAD thresholds do not drop to 0.25 when Preset is active.
  - Explicit vad_threshold runs exactly once and does not retry with lower thresholds (call_count == 1).
  - Standard (0.5) retry is capped at 0.35 maximum and 0.25 fallback is removed.
  - vad_parameters receives min_speech_duration_ms=500 (or custom).
  - model.transcribe receives suppression flags: no_speech_threshold=0.6, log_prob_threshold=-1.0,
    compression_ratio_threshold=2.4, hallucination_silence_threshold=1.0.
- TC-VAD-FILTER-03: Segments with no_speech_prob >= 0.75 or music/hallucinations are dropped.
  - Segments with no_speech_prob >= 0.75 dropped (including when music_mode=True).
  - Segments with avg_logprob <= -1.2 and no_speech_prob >= 0.5 dropped.
  - Segments with music notes (♪, ♫, 🎵, ♩), sound tags ([music]), pure punctuation, or
    matching SubtitleGenerationValidator.HALLUCINATIONS dropped.
  - SubtitleGenerationValidator.filter_inconsistent_language called when language is set.
"""

import types
from unittest.mock import MagicMock, patch
import pytest

from core.timing.timing_run_request import TimingRunRequest
from core.timing.timing_checkpoint import TimingCheckpoint
from core.timing.timing_batch_service import TimingBatchService
from core.project.project_state import TimingState
from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
from workers.TimingBatchWorker import TimingBatchWorker


# ==============================================================================
# TC-VAD-FILTER-01: Data Contracts & Service Pipeline (VAD Parameters)
# ==============================================================================
class TestTCVadFilter01DataContractsAndPipeline:
    """Verifies that all 5 VAD parameters travel intact through data contracts and service pipeline."""

    def test_timing_run_request_default_values(self):
        """Default values of the 5 VAD parameters on TimingRunRequest must be None."""
        request = TimingRunRequest(
            video_path="sample.mp4",
            start_ms=0,
            target_segment_count=10,
        )
        assert request.vad_preset is None
        assert request.vad_threshold is None
        assert request.vad_speech_pad_ms is None
        assert request.vad_max_speech_duration_s is None
        assert request.min_speech_duration_ms is None

    def test_timing_run_request_and_checkpoint_custom_values(self):
        """Custom values are stored and accessible on TimingRunRequest and TimingCheckpoint."""
        request = TimingRunRequest(
            video_path="sample.mp4",
            start_ms=1000,
            target_segment_count=15,
            vad_preset="speech_heavy",
            vad_threshold=0.45,
            vad_speech_pad_ms=300,
            vad_max_speech_duration_s=25.0,
            min_speech_duration_ms=600,
        )
        assert request.vad_preset == "speech_heavy"
        assert request.vad_threshold == 0.45
        assert request.vad_speech_pad_ms == 300
        assert request.vad_max_speech_duration_s == 25.0
        assert request.min_speech_duration_ms == 600

        checkpoint = TimingCheckpoint(
            project_id="proj_101",
            source_fingerprint="fp_101",
            timing_artifact_id="art_101",
            timing_revision=2,
            batch_size=10,
            vad_preset="speech_heavy",
            vad_threshold=0.45,
            vad_speech_pad_ms=300,
            vad_max_speech_duration_s=25.0,
            min_speech_duration_ms=600,
        )
        assert checkpoint.vad_preset == "speech_heavy"
        assert checkpoint.vad_threshold == 0.45
        assert checkpoint.vad_speech_pad_ms == 300
        assert checkpoint.vad_max_speech_duration_s == 25.0
        assert checkpoint.min_speech_duration_ms == 600

    def test_validate_settings_retains_all_5_vad_parameters(self):
        """TimingBatchService._validate_settings(settings) retains all 5 VAD parameters without dropping."""
        raw_settings = {
            "model_size": "base",
            "compute_type": "float16",
            "use_vad": True,
            "min_silence_ms": 500,
            "fix_overlap": True,
            "overlap_gap_ms": 50,
            "overlap_ms": 800,
            "max_window_ms": 120000,
            "vad_preset": "podcast",
            "vad_threshold": 0.42,
            "vad_speech_pad_ms": 350,
            "vad_max_speech_duration_s": 20.0,
            "min_speech_duration_ms": 550,
        }
        validated = TimingBatchService._validate_settings(raw_settings)
        assert validated["vad_preset"] == "podcast"
        assert validated["vad_threshold"] == 0.42
        assert validated["vad_speech_pad_ms"] == 350
        assert validated["vad_max_speech_duration_s"] == 20.0
        assert validated["min_speech_duration_ms"] == 550

    def test_validate_settings_type_casting(self):
        """TimingBatchService._validate_settings casts numeric string inputs appropriately."""
        raw_settings = {
            "model_size": "base",
            "compute_type": "float16",
            "use_vad": True,
            "min_silence_ms": "500",
            "fix_overlap": True,
            "overlap_gap_ms": "50",
            "overlap_ms": "800",
            "max_window_ms": "120000",
            "vad_preset": "custom",
            "vad_threshold": "0.38",
            "vad_speech_pad_ms": "400",
            "vad_max_speech_duration_s": "30.0",
            "min_speech_duration_ms": "500",
        }
        validated = TimingBatchService._validate_settings(raw_settings)
        assert isinstance(validated["vad_preset"], str)
        assert isinstance(validated["vad_threshold"], float)
        assert isinstance(validated["vad_speech_pad_ms"], int)
        assert isinstance(validated["vad_max_speech_duration_s"], float)
        assert isinstance(validated["min_speech_duration_ms"], int)
        assert validated["vad_threshold"] == 0.38
        assert validated["vad_speech_pad_ms"] == 400
        assert validated["vad_max_speech_duration_s"] == 30.0
        assert validated["min_speech_duration_ms"] == 500

    def test_settings_from_checkpoint_injects_all_5_vad_parameters(self):
        """TimingBatchService._settings_from_checkpoint extracts and retains all 5 VAD parameters."""
        checkpoint = TimingCheckpoint(
            project_id="proj_102",
            source_fingerprint="fp_102",
            timing_artifact_id="art_102",
            timing_revision=1,
            batch_size=10,
            model_size="small",
            compute_type="int8",
            use_vad=True,
            min_silence_ms=500,
            fix_overlap=True,
            overlap_gap_ms=50,
            overlap_ms=800,
            max_window_ms=120000,
            vad_preset="cfg9",
            vad_threshold=0.35,
            vad_speech_pad_ms=250,
            vad_max_speech_duration_s=15.0,
            min_speech_duration_ms=500,
        )
        settings = TimingBatchService._settings_from_checkpoint(checkpoint)
        assert settings["vad_preset"] == "cfg9"
        assert settings["vad_threshold"] == 0.35
        assert settings["vad_speech_pad_ms"] == 250
        assert settings["vad_max_speech_duration_s"] == 15.0
        assert settings["min_speech_duration_ms"] == 500

    def test_execute_run_injects_all_5_vad_parameters_into_timing_run_request(self):
        """TimingBatchService._execute_run constructs TimingRunRequest with all 5 VAD parameters."""
        mock_project_service = MagicMock()
        mock_project = MagicMock()
        mock_project.source.path = "video_source.mp4"
        mock_project.state.timing = TimingState()
        mock_project_service.current_project = mock_project

        service = TimingBatchService(mock_project_service)

        settings = {
            "model_size": "base",
            "compute_type": "float16",
            "use_vad": True,
            "min_silence_ms": 500,
            "fix_overlap": True,
            "overlap_gap_ms": 50,
            "overlap_ms": 800,
            "max_window_ms": 120000,
            "vad_preset": "podcast",
            "vad_threshold": 0.42,
            "vad_speech_pad_ms": 320,
            "vad_max_speech_duration_s": 22.5,
            "min_speech_duration_ms": 550,
        }

        with patch("core.timing.timing_batch_service.TimingBatchWorker") as MockWorkerClass:
            mock_worker_instance = MagicMock()
            MockWorkerClass.return_value = mock_worker_instance

            service._execute_run(start_ms=0, target_count=5, settings=settings)

            assert MockWorkerClass.call_count == 1
            constructed_request: TimingRunRequest = MockWorkerClass.call_args[0][0]
            assert isinstance(constructed_request, TimingRunRequest)
            assert constructed_request.vad_preset == "podcast"
            assert constructed_request.vad_threshold == 0.42
            assert constructed_request.vad_speech_pad_ms == 320
            assert constructed_request.vad_max_speech_duration_s == 22.5
            assert constructed_request.min_speech_duration_ms == 550
            assert mock_worker_instance.start.call_count == 1


# ==============================================================================
# TC-VAD-FILTER-02: Core Worker VAD Threshold Guard & Retry Capping
# ==============================================================================
class TestTCVadFilter02VADThresholdsAndRetryCapping:
    """Verifies that VAD thresholds do not drop to 0.25 and preset configs execute once."""

    def test_preset_threshold_runs_once_without_retry(self):
        """When request.vad_threshold is explicitly set, transcription runs exactly once (call_count == 1)."""
        call_records = []

        class MockModel:
            def transcribe(self, _path, **kwargs):
                call_records.append(kwargs)
                info = types.SimpleNamespace(
                    duration=30.0,
                    duration_after_vad=0.0,
                    language="en",
                    language_probability=0.9,
                )
                # Return 0 segments to trigger retry if bug existed
                return [], info

        request = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            vad_preset="cfg9",
            vad_threshold=0.35,
        )
        worker = TimingBatchWorker(request)
        model = MockModel()

        segments, info = worker._transcribe_with_vad_retry(model, "chunk.wav")

        assert len(call_records) == 1
        assert call_records[0]["vad_parameters"]["threshold"] == 0.35
        assert segments == []

    def test_custom_preset_runs_once_even_with_empty_result(self):
        """Custom preset threshold (e.g. 0.40) must run only 1 attempt and never fall back to lower threshold."""
        call_records = []

        class MockModel:
            def transcribe(self, _path, **kwargs):
                call_records.append(kwargs)
                info = types.SimpleNamespace(
                    duration=30.0,
                    duration_after_vad=0.0,
                    language="vi",
                    language_probability=0.95,
                )
                return [], info

        request = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            vad_preset="custom",
            vad_threshold=0.40,
        )
        worker = TimingBatchWorker(request)
        model = MockModel()

        segments, _ = worker._transcribe_with_vad_retry(model, "chunk.wav")

        assert len(call_records) == 1
        assert call_records[0]["vad_parameters"]["threshold"] == 0.40
        assert 0.25 not in [c["vad_parameters"]["threshold"] for c in call_records]
        assert segments == []

    def test_standard_threshold_caps_retry_at_035_and_removes_025(self):
        """Standard mode (0.50): attempt 1 uses 0.50, attempt 2 is capped at 0.35, and 0.25 is completely removed."""
        attempt_thresholds = []

        class MockModel:
            def transcribe(self, _path, **kwargs):
                thresh = kwargs["vad_parameters"]["threshold"]
                attempt_thresholds.append(thresh)
                info = types.SimpleNamespace(
                    duration=60.0,
                    duration_after_vad=20.0,
                    language="en",
                    language_probability=0.98,
                )
                if len(attempt_thresholds) == 1:
                    return [], info  # Attempt 1 returns 0 segments
                # Attempt 2 returns valid segment
                return [types.SimpleNamespace(start=0.5, end=2.0, text="valid speech", words=None)], info

        request = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            vad_preset="standard",
            vad_threshold=0.50,
        )
        worker = TimingBatchWorker(request)
        model = MockModel()

        segments, info = worker._transcribe_with_vad_retry(model, "chunk.wav")

        assert attempt_thresholds == [0.50, 0.35]
        assert 0.25 not in attempt_thresholds
        assert len(segments) == 1
        assert segments[0].text == "valid speech"

    def test_standard_threshold_max_two_attempts_no_025_when_empty(self):
        """Standard mode stops after attempt 2 (threshold 0.35) even if both attempts return 0 segments."""
        attempt_thresholds = []

        class MockModel:
            def transcribe(self, _path, **kwargs):
                thresh = kwargs["vad_parameters"]["threshold"]
                attempt_thresholds.append(thresh)
                info = types.SimpleNamespace(
                    duration=60.0,
                    duration_after_vad=0.0,
                    language="en",
                    language_probability=0.9,
                )
                return [], info

        request = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            vad_preset=None,
            vad_threshold=None,
        )
        worker = TimingBatchWorker(request)
        model = MockModel()

        segments, info = worker._transcribe_with_vad_retry(model, "chunk.wav")

        assert attempt_thresholds == [0.50, 0.35]
        assert 0.25 not in attempt_thresholds
        assert segments == []

    def test_vad_parameters_receive_min_speech_duration_ms(self):
        """vad_parameters receives min_speech_duration_ms=500 by default and custom value when specified."""
        captured_kwargs = []

        class MockModel:
            def transcribe(self, _path, **kwargs):
                captured_kwargs.append(kwargs)
                info = types.SimpleNamespace(
                    duration=20.0,
                    duration_after_vad=10.0,
                    language="en",
                    language_probability=0.95,
                )
                return [types.SimpleNamespace(start=0.0, end=1.5, text="ok", words=None)], info

        # 1. Default when min_speech_duration_ms is None -> 500
        req_default = TimingRunRequest(video_path="test.mp4", start_ms=0, target_segment_count=5)
        worker_default = TimingBatchWorker(req_default)
        worker_default._transcribe_with_vad_retry(MockModel(), "chunk.wav")
        assert captured_kwargs[-1]["vad_parameters"]["min_speech_duration_ms"] == 500

        # 2. Custom value -> 650
        req_custom = TimingRunRequest(
            video_path="test.mp4",
            start_ms=0,
            target_segment_count=5,
            min_speech_duration_ms=650,
            vad_speech_pad_ms=300,
            vad_max_speech_duration_s=18.0,
        )
        worker_custom = TimingBatchWorker(req_custom)
        worker_custom._transcribe_with_vad_retry(MockModel(), "chunk.wav")
        params = captured_kwargs[-1]["vad_parameters"]
        assert params["min_speech_duration_ms"] == 650
        assert params["speech_pad_ms"] == 300
        assert params["max_speech_duration_s"] == 18.0

    def test_model_transcribe_receives_hallucination_suppression_flags(self):
        """model.transcribe receives all 4 hallucination suppression flags and VAD settings."""
        captured_kwargs = {}

        class MockModel:
            def transcribe(self, _path, **kwargs):
                captured_kwargs.update(kwargs)
                info = types.SimpleNamespace(
                    duration=15.0,
                    duration_after_vad=5.0,
                    language="vi",
                    language_probability=0.99,
                )
                return [types.SimpleNamespace(start=0.0, end=1.0, text="alo", words=None)], info

        request = TimingRunRequest(video_path="test.mp4", start_ms=0, target_segment_count=5)
        worker = TimingBatchWorker(request)
        worker._transcribe_with_vad_retry(MockModel(), "chunk.wav")

        assert captured_kwargs["vad_filter"] is True
        assert captured_kwargs["word_timestamps"] is True
        assert captured_kwargs["no_speech_threshold"] == 0.6
        assert captured_kwargs["log_prob_threshold"] == -1.0
        assert captured_kwargs["compression_ratio_threshold"] == 2.4
        assert captured_kwargs["hallucination_silence_threshold"] == 1.0


# ==============================================================================
# TC-VAD-FILTER-03: Result Mapping Hallucination & Music Filtering
# ==============================================================================
class TestTCVadFilter03SegmentFilteringAndHallucinations:
    """Verifies that non-speech, music notes, sound tags, and foreign hallucinations are dropped."""

    def test_segments_with_high_no_speech_prob_dropped_including_music_mode(self):
        """Segments with no_speech_prob >= 0.75 are dropped even when music_mode=True."""
        seg_high_1 = types.SimpleNamespace(
            start=0.0, end=2.0, text="Drum thump", no_speech_prob=0.75, avg_logprob=-0.4, words=None
        )
        seg_high_2 = types.SimpleNamespace(
            start=2.5, end=4.0, text="Bass beat", no_speech_prob=0.88, avg_logprob=-0.3, words=None
        )
        seg_valid = types.SimpleNamespace(
            start=4.5, end=6.5, text="Lời bài hát rõ ràng", no_speech_prob=0.20, avg_logprob=-0.2, words=None
        )

        request = TimingRunRequest(
            video_path="song.mp4",
            start_ms=0,
            target_segment_count=5,
            music_mode=True,  # music_mode must NOT bypass no_speech_prob >= 0.75 check
        )
        worker = TimingBatchWorker(request)

        with patch("faster_whisper.WhisperModel") as MockWhisper, \
             patch("subprocess.run") as mock_subproc, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=50000), \
             patch("wave.open") as mock_wave:

            mock_subproc.return_value = types.SimpleNamespace(returncode=0, stderr="")
            mock_wav = MagicMock()
            mock_wav.getnframes.return_value = 16000 * 10
            mock_wav.getframerate.return_value = 16000
            mock_wave.return_value.__enter__.return_value = mock_wav

            model_mock = MagicMock()
            MockWhisper.return_value = model_mock
            info = types.SimpleNamespace(duration=10.0, duration_after_vad=10.0, language="vi", language_probability=0.99)
            model_mock.transcribe.return_value = ([seg_high_1, seg_high_2, seg_valid], info)

            emitted = []
            worker.finished_signal.connect(lambda segs, is_end: emitted.extend(segs))
            worker.run()

            assert len(emitted) == 1
            assert emitted[0]["start_ms"] == 4500
            assert emitted[0]["end_ms"] == 6500

    def test_segments_with_low_logprob_and_moderate_no_speech_dropped(self):
        """Segments with avg_logprob <= -1.2 and no_speech_prob >= 0.5 are dropped."""
        seg_low_dual = types.SimpleNamespace(
            start=0.0, end=2.0, text="Inaudible mumbling", no_speech_prob=0.55, avg_logprob=-1.35, words=None
        )
        seg_boundary_dual = types.SimpleNamespace(
            start=2.5, end=4.0, text="Exact boundary condition", no_speech_prob=0.50, avg_logprob=-1.20, words=None
        )
        seg_low_logprob_only = types.SimpleNamespace(
            start=4.5, end=6.0, text="Low logprob but speech clear", no_speech_prob=0.30, avg_logprob=-1.40, words=None
        )
        seg_mod_no_speech_only = types.SimpleNamespace(
            start=6.5, end=8.0, text="Moderate no speech but high confidence", no_speech_prob=0.60, avg_logprob=-0.50, words=None
        )

        request = TimingRunRequest(video_path="video.mp4", start_ms=0, target_segment_count=5)
        worker = TimingBatchWorker(request)

        with patch("faster_whisper.WhisperModel") as MockWhisper, \
             patch("subprocess.run") as mock_subproc, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=50000), \
             patch("wave.open") as mock_wave:

            mock_subproc.return_value = types.SimpleNamespace(returncode=0, stderr="")
            mock_wav = MagicMock()
            mock_wav.getnframes.return_value = 16000 * 10
            mock_wav.getframerate.return_value = 16000
            mock_wave.return_value.__enter__.return_value = mock_wav

            model_mock = MagicMock()
            MockWhisper.return_value = model_mock
            info = types.SimpleNamespace(duration=10.0, duration_after_vad=10.0, language="en", language_probability=0.99)
            raw = [seg_low_dual, seg_boundary_dual, seg_low_logprob_only, seg_mod_no_speech_only]
            model_mock.transcribe.return_value = (raw, info)

            emitted = []
            worker.finished_signal.connect(lambda segs, is_end: emitted.extend(segs))
            worker.run()

            # seg_low_dual and seg_boundary_dual dropped; seg_low_logprob_only and seg_mod_no_speech_only kept
            assert len(emitted) == 2
            assert emitted[0]["start_ms"] == 4500
            assert emitted[1]["start_ms"] == 6500

    def test_segments_with_music_notes_and_sound_tags_dropped(self):
        """Segments containing only music notes, sound tags, pure punctuation, or known hallucinations are dropped."""
        notes = ["♪", "♫", "🎵", "♩", "♬", "♪ ♫ 🎵", "  ♪  "]
        sound_tags = ["[music]", "(music)", "[applause]", "(applause)", "[laughter]", "(laughter)", "[cheering]", "(cheering)", "[sound]"]
        punctuations = ["...", "---", "!?", ".", "   ...   ", ""]
        hallucinations = ["Thank you for watching!", "ご視聴ありがとうございました", "Diyorlar.", "đăng ký kênh", "amara.org", "subtitles by"]

        for text in notes + sound_tags + punctuations + hallucinations:
            assert SubtitleGenerationValidator.is_hallucination(text) is True, f"Failed for text: '{text}'"

        # Legitimate speech must not be detected as hallucination
        legit = ["Xin chào mọi người", "Good morning Vietnam", "こんにちは世界", "Today we discuss technology"]
        for text in legit:
            assert SubtitleGenerationValidator.is_hallucination(text) is False, f"False positive for: '{text}'"

    def test_filter_inconsistent_language_called_when_language_set(self):
        """When language is set (e.g. 'ja'), Latin-only segments without Japanese characters are dropped."""
        seg_japanese = types.SimpleNamespace(
            start=0.0, end=2.0, text="ありがとうございます", no_speech_prob=0.1, avg_logprob=-0.2, words=None
        )
        seg_latin_hallu = types.SimpleNamespace(
            start=2.5, end=4.5, text="Subtitles by someone else and foreign speech", no_speech_prob=0.1, avg_logprob=-0.2, words=None
        )

        request = TimingRunRequest(
            video_path="anime.mp4",
            start_ms=0,
            target_segment_count=5,
            language="ja",
        )
        worker = TimingBatchWorker(request)

        with patch("faster_whisper.WhisperModel") as MockWhisper, \
             patch("subprocess.run") as mock_subproc, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=50000), \
             patch("wave.open") as mock_wave:

            mock_subproc.return_value = types.SimpleNamespace(returncode=0, stderr="")
            mock_wav = MagicMock()
            mock_wav.getnframes.return_value = 16000 * 10
            mock_wav.getframerate.return_value = 16000
            mock_wave.return_value.__enter__.return_value = mock_wav

            model_mock = MagicMock()
            MockWhisper.return_value = model_mock
            info = types.SimpleNamespace(duration=10.0, duration_after_vad=10.0, language="ja", language_probability=0.99)
            model_mock.transcribe.return_value = ([seg_japanese, seg_latin_hallu], info)

            emitted = []
            worker.finished_signal.connect(lambda segs, is_end: emitted.extend(segs))
            worker.run()

            # Only Japanese segment kept, Latin hallucination dropped
            assert len(emitted) == 1
            assert emitted[0]["start_ms"] == 0
            assert emitted[0]["end_ms"] == 2000

    def test_auto_detect_language_bypasses_language_filter(self):
        """When language is 'Auto Detect' or None, language consistency filter does not drop foreign segments."""
        seg_english = types.SimpleNamespace(
            start=0.0, end=2.0, text="Hello and welcome", no_speech_prob=0.1, avg_logprob=-0.2, words=None
        )

        request = TimingRunRequest(
            video_path="multilingual.mp4",
            start_ms=0,
            target_segment_count=5,
            language="Auto Detect",
        )
        worker = TimingBatchWorker(request)

        with patch("faster_whisper.WhisperModel") as MockWhisper, \
             patch("subprocess.run") as mock_subproc, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=50000), \
             patch("wave.open") as mock_wave:

            mock_subproc.return_value = types.SimpleNamespace(returncode=0, stderr="")
            mock_wav = MagicMock()
            mock_wav.getnframes.return_value = 16000 * 10
            mock_wav.getframerate.return_value = 16000
            mock_wave.return_value.__enter__.return_value = mock_wav

            model_mock = MagicMock()
            MockWhisper.return_value = model_mock
            info = types.SimpleNamespace(duration=10.0, duration_after_vad=10.0, language="en", language_probability=0.99)
            model_mock.transcribe.return_value = ([seg_english], info)

            emitted = []
            worker.finished_signal.connect(lambda segs, is_end: emitted.extend(segs))
            worker.run()

            assert len(emitted) == 1
            assert emitted[0]["start_ms"] == 0
            assert emitted[0]["end_ms"] == 2000

    def test_comprehensive_result_mapping_drops_all_hallucination_types(self):
        """Comprehensive verification: mixes valid segments with high no_speech_prob, low logprob,
        notes, tags, hallucinations, and pure punctuation, ensuring ONLY valid segments survive."""
        raw_segs = [
            # 1. Valid speech (Kept)
            types.SimpleNamespace(start=0.0, end=2.0, text="Chào mừng đến với hội thảo", no_speech_prob=0.05, avg_logprob=-0.2, words=None),
            # 2. High no_speech_prob >= 0.75 (Dropped)
            types.SimpleNamespace(start=2.5, end=4.0, text="Drum solo", no_speech_prob=0.82, avg_logprob=-0.3, words=None),
            # 3. Low logprob <= -1.2 & no_speech_prob >= 0.5 (Dropped)
            types.SimpleNamespace(start=4.5, end=6.0, text="Muffled sound", no_speech_prob=0.52, avg_logprob=-1.25, words=None),
            # 4. Music note ♪ (Dropped)
            types.SimpleNamespace(start=6.5, end=8.0, text="♪ ♫", no_speech_prob=0.1, avg_logprob=-0.3, words=None),
            # 5. Sound tag [applause] (Dropped)
            types.SimpleNamespace(start=8.5, end=10.0, text="[applause]", no_speech_prob=0.1, avg_logprob=-0.3, words=None),
            # 6. Punctuation only (Dropped)
            types.SimpleNamespace(start=10.5, end=11.5, text="...", no_speech_prob=0.1, avg_logprob=-0.3, words=None),
            # 7. Hallucination phrase (Dropped)
            types.SimpleNamespace(start=12.0, end=14.0, text="ご視聴ありがとうございました", no_speech_prob=0.1, avg_logprob=-0.3, words=None),
            # 8. Valid speech (Kept)
            types.SimpleNamespace(start=14.5, end=17.0, text="Phần thuyết trình tiếp theo", no_speech_prob=0.10, avg_logprob=-0.25, words=None),
        ]

        request = TimingRunRequest(video_path="lecture.mp4", start_ms=0, target_segment_count=5)
        worker = TimingBatchWorker(request)

        with patch("faster_whisper.WhisperModel") as MockWhisper, \
             patch("subprocess.run") as mock_subproc, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=100000), \
             patch("wave.open") as mock_wave:

            mock_subproc.return_value = types.SimpleNamespace(returncode=0, stderr="")
            mock_wav = MagicMock()
            mock_wav.getnframes.return_value = 16000 * 20
            mock_wav.getframerate.return_value = 16000
            mock_wave.return_value.__enter__.return_value = mock_wav

            model_mock = MagicMock()
            MockWhisper.return_value = model_mock
            info = types.SimpleNamespace(duration=20.0, duration_after_vad=20.0, language="vi", language_probability=0.99)
            model_mock.transcribe.return_value = (raw_segs, info)

            emitted = []
            worker.finished_signal.connect(lambda segs, is_end: emitted.extend(segs))
            worker.run()

            # Exactly segments #1 and #8 must survive
            assert len(emitted) == 2
            assert emitted[0]["start_ms"] == 0
            assert emitted[0]["end_ms"] == 2000
            assert emitted[1]["start_ms"] == 14500
            assert emitted[1]["end_ms"] == 17000


class TestSileroVadAntiSaturationAndResumeSync:
    """Regression coverage for Silero VAD LSTM saturation reset and continue_timing settings sync."""

    def test_silero_vad_anti_saturation_resets_state_on_bgm_and_preserves_on_speech(self):
        """Anti-saturation patch resets (h, c) after non-speech/saturated windows and preserves it across speech."""
        import numpy as np
        from faster_whisper.vad import SileroVADModel
        from core.subtitle_generation.faster_whisper_service import ensure_silero_vad_anti_saturation_patch

        ensure_silero_vad_anti_saturation_patch()
        ensure_silero_vad_anti_saturation_patch()
        assert getattr(SileroVADModel, "_anti_saturation_patched", False) is True

        seen_states = []
        mock_session = MagicMock()

        def fake_run(_output_names, feeds):
            idx = len(seen_states)
            h_in = feeds["h"].copy()
            c_in = feeds["c"].copy()
            seen_states.append((h_in, c_in, feeds["input"].shape[0]))
            if idx == 0:
                # Non-speech/BGM window (max prob 0.10 < 0.25) winds up c -> must reset before window 1
                out = np.full((feeds["input"].shape[0], 1), 0.10, dtype=np.float32)
                c_next = np.full((1, 1, 128), 6.0, dtype=np.float32)
            elif idx == 1:
                # Speech window (max prob 0.80 >= 0.25, |c| <= 20) -> must preserve state into window 2
                out = np.full((feeds["input"].shape[0], 1), 0.80, dtype=np.float32)
                c_next = np.full((1, 1, 128), 5.0, dtype=np.float32)
            elif idx == 2:
                # Speech window whose cell state saturates (|c| = 25.0 > 20.0) -> must reset before window 3
                out = np.full((feeds["input"].shape[0], 1), 0.70, dtype=np.float32)
                c_next = np.full((1, 1, 128), 25.0, dtype=np.float32)
            else:
                out = np.full((feeds["input"].shape[0], 1), 0.90, dtype=np.float32)
                c_next = np.full((1, 1, 128), 2.0, dtype=np.float32)
            h_next = np.full((1, 1, 128), float(idx + 1), dtype=np.float32)
            return out, h_next, c_next

        mock_session.run.side_effect = fake_run

        vad = SileroVADModel.__new__(SileroVADModel)
        vad.session = mock_session

        audio = np.ones(512 * 256, dtype=np.float32)
        audio_snapshot = audio.copy()
        probs = vad(audio)

        assert probs.shape == (256, 1)
        assert np.array_equal(audio, audio_snapshot)
        assert len(seen_states) == 4
        assert all(frame_count == 64 for _h, _c, frame_count in seen_states)
        # Window 1 got reset after non-speech window 0
        assert np.all(seen_states[1][0] == 0.0) and np.all(seen_states[1][1] == 0.0)
        # Window 2 preserved window 1's active speech state (h=2.0, c=5.0)
        assert np.all(seen_states[2][0] == 2.0) and np.all(seen_states[2][1] == 5.0)
        # Window 3 got reset after window 2's |c|=25.0 exceeded 20.0
        assert np.all(seen_states[3][0] == 0.0) and np.all(seen_states[3][1] == 0.0)

    def test_continue_timing_applies_updated_language_and_vad_preset_from_ui(self, tmp_path):
        """continue_timing applies UI/project language and cfg9 VAD preset over stale checkpoint values."""
        from core.artifacts.artifact import Artifact
        from core.artifacts.artifact_store import ArtifactStore
        from core.artifacts.artifact_types import ArtifactStatus, ArtifactType
        from core.services.project_service import ProjectService

        video_path = tmp_path / "GIRO-11.mp4"
        video_path.write_bytes(b"video-data")
        project_dir = tmp_path / "GIRO-11.ai-subtitle"

        project_service = ProjectService(ArtifactStore())
        project = project_service.create_project(str(project_dir), "GIRO-11", str(video_path))

        srt_path = project_dir / "artifacts" / "timing" / "GIRO_11_timing.srt"
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nLine 1\n\n", encoding="utf-8")

        artifact = Artifact(
            artifact_id="art_timing_1",
            artifact_type=ArtifactType.TIMING,
            path=str(srt_path),
            created_at="2026-11-14T00:00:00",
            updated_at="2026-11-14T00:00:00",
            source_project_id=project.project_id,
            status=ArtifactStatus.READY,
            revision=1,
            metadata={},
        )
        project_service.artifact_store.register(artifact)
        project.state.timing.timing_artifact_id = "art_timing_1"

        stale_checkpoint = TimingCheckpoint(
            project_id=project.project_id,
            source_fingerprint=project.source.fingerprint,
            timing_artifact_id="art_timing_1",
            timing_revision=1,
            batch_size=5,
            model_size="large-v3",
            compute_type="float16",
            use_vad=True,
            min_silence_ms=500,
            fix_overlap=True,
            overlap_gap_ms=50,
            overlap_ms=800,
            max_window_ms=120000,
            language="zh",
            vad_preset=None,
            vad_threshold=None,
            vad_speech_pad_ms=None,
            vad_max_speech_duration_s=None,
            min_speech_duration_ms=None,
        )
        project_service.save_timing_checkpoint(stale_checkpoint)

        timing_service = TimingBatchService(project_service)
        captured = []
        timing_service._execute_run = lambda **kwargs: captured.append(kwargs)

        ui_settings = {
            "model_size": "large-v3",
            "compute_type": "float16",
            "use_vad": True,
            "min_silence_ms": 300,
            "fix_overlap": True,
            "overlap_gap_ms": 50,
            "overlap_ms": 800,
            "max_window_ms": 120000,
            "language": "ja",
            "vad_preset": "cfg9",
            "vad_threshold": 0.35,
            "vad_speech_pad_ms": 300,
            "vad_max_speech_duration_s": 6.0,
        }
        timing_service.continue_timing(5, ui_settings)

        assert len(captured) == 1
        effective = captured[0]["settings"]
        assert effective["language"] == "ja"
        assert effective["vad_preset"] == "cfg9"
        assert effective["vad_threshold"] == 0.35
        assert effective["vad_speech_pad_ms"] == 300
        assert effective["vad_max_speech_duration_s"] == 6.0
        assert effective["min_silence_ms"] == 300

        updated_cp = project_service.load_timing_checkpoint()
        assert updated_cp.language == "ja"
        assert updated_cp.vad_preset == "cfg9"
        assert updated_cp.vad_threshold == 0.35
        assert updated_cp.vad_speech_pad_ms == 300
        assert updated_cp.vad_max_speech_duration_s == 6.0
        assert updated_cp.min_silence_ms == 300

        # Also verify fallback to project.state.timing when caller passes empty settings
        project_service.save_timing_checkpoint(stale_checkpoint)
        project.state.timing.language = "ja"
        project.state.timing.vad_preset = "cfg9"
        project.state.timing.vad_threshold = 0.35
        project.state.timing.vad_speech_pad_ms = 300
        project.state.timing.vad_max_speech_duration_s = 6.0
        project.state.timing.min_silence_ms = 300
        captured.clear()
        timing_service.continue_timing(5, {})
        assert len(captured) == 1
        assert captured[0]["settings"]["language"] == "ja"
        assert captured[0]["settings"]["vad_preset"] == "cfg9"
        assert captured[0]["settings"]["vad_threshold"] == 0.35
        assert captured[0]["settings"]["min_silence_ms"] == 300
