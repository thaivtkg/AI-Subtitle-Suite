import types
from unittest.mock import MagicMock, patch
import pytest

from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.timing.timing_run_request import TimingRunRequest
from workers.TimingBatchWorker import TimingBatchWorker


class TestValidatorHallucinationEnhancements:
    def test_music_symbols_detected_as_hallucinations(self):
        assert SubtitleGenerationValidator.is_hallucination("♪")
        assert SubtitleGenerationValidator.is_hallucination("♫")
        assert SubtitleGenerationValidator.is_hallucination("🎵")
        assert SubtitleGenerationValidator.is_hallucination("♩")
        assert SubtitleGenerationValidator.is_hallucination("♬")
        assert SubtitleGenerationValidator.is_hallucination("♪ ♫ 🎵 ♩ ♬")
        assert SubtitleGenerationValidator.is_hallucination("   ♪   ")

    def test_sound_tags_detected_as_hallucinations(self):
        assert SubtitleGenerationValidator.is_hallucination("[music]")
        assert SubtitleGenerationValidator.is_hallucination("(music)")
        assert SubtitleGenerationValidator.is_hallucination("[applause]")
        assert SubtitleGenerationValidator.is_hallucination("(applause)")
        assert SubtitleGenerationValidator.is_hallucination("[laughter]")
        assert SubtitleGenerationValidator.is_hallucination("(laughter)")
        assert SubtitleGenerationValidator.is_hallucination("[cheering]")
        assert SubtitleGenerationValidator.is_hallucination("(cheering)")
        assert SubtitleGenerationValidator.is_hallucination("[sound]")
        assert SubtitleGenerationValidator.is_hallucination("[MUSIC]")
        assert SubtitleGenerationValidator.is_hallucination("(Applause)")

    def test_pure_punctuation_detected_as_hallucinations(self):
        assert SubtitleGenerationValidator.is_hallucination("...")
        assert SubtitleGenerationValidator.is_hallucination(".")
        assert SubtitleGenerationValidator.is_hallucination("—")
        assert SubtitleGenerationValidator.is_hallucination("!??")
        assert SubtitleGenerationValidator.is_hallucination("   ...   ")
        assert SubtitleGenerationValidator.is_hallucination("")
        assert SubtitleGenerationValidator.is_hallucination("   ")

    def test_known_phrases_detected_as_hallucinations(self):
        assert SubtitleGenerationValidator.is_hallucination("Thank you for watching!")
        assert SubtitleGenerationValidator.is_hallucination("ご視聴ありがとうございました")
        assert SubtitleGenerationValidator.is_hallucination("Diyorlar.")
        assert SubtitleGenerationValidator.is_hallucination("đăng ký kênh")

    def test_valid_speech_not_hallucinations(self):
        assert not SubtitleGenerationValidator.is_hallucination("Xin chào các bạn")
        assert not SubtitleGenerationValidator.is_hallucination("This is a valid sentence.")
        assert not SubtitleGenerationValidator.is_hallucination("こんにちは、元気ですか？")


class TestTimingBatchWorkerVADLogic:
    def test_preset_threshold_runs_once_without_retry(self):
        """TC-VAD-FILTER-02: Preset thresholds run exactly once and never drop to 0.25."""
        class MockTranscribeModel:
            def __init__(self):
                self.calls = []

            def transcribe(self, _path, **kwargs):
                self.calls.append(kwargs)
                info = types.SimpleNamespace(
                    duration=60.0,
                    duration_after_vad=0.0,
                    language="en",
                    language_probability=0.9,
                )
                return [], info

        req = TimingRunRequest(
            video_path="dummy.mp4",
            start_ms=0,
            target_segment_count=5,
            vad_preset="cfg9",
            vad_threshold=0.35,
        )
        worker = TimingBatchWorker(req)
        model = MockTranscribeModel()
        segments, _info = worker._transcribe_with_vad_retry(model, "dummy.wav")

        assert len(model.calls) == 1
        assert model.calls[0]["vad_parameters"]["threshold"] == 0.35
        assert segments == []

    def test_standard_threshold_caps_retry_at_035_and_removes_025(self):
        """Standard mode retries with 0.35 max; 0.25 fallback is completely removed."""
        class MockTranscribeModel:
            def __init__(self):
                self.thresholds = []

            def transcribe(self, _path, **kwargs):
                self.thresholds.append(kwargs["vad_parameters"]["threshold"])
                info = types.SimpleNamespace(
                    duration=60.0,
                    duration_after_vad=30.0,
                    language="en",
                    language_probability=0.95,
                )
                if len(self.thresholds) == 1:
                    return [], info
                return [types.SimpleNamespace(start=1.0, end=2.0, text="valid speech", words=None)], info

        req = TimingRunRequest(
            video_path="dummy.mp4",
            start_ms=0,
            target_segment_count=5,
            vad_preset="standard",
            vad_threshold=0.5,
        )
        worker = TimingBatchWorker(req)
        model = MockTranscribeModel()
        segments, _info = worker._transcribe_with_vad_retry(model, "dummy.wav")

        assert model.thresholds == [0.5, 0.35]
        assert 0.25 not in model.thresholds
        assert len(segments) == 1

    def test_vad_parameters_and_suppression_flags_injected(self):
        """Verify min_speech_duration_ms=500, speech_pad_ms, max_speech_duration_s, and suppression flags."""
        class MockTranscribeModel:
            def __init__(self):
                self.last_kwargs = None

            def transcribe(self, _path, **kwargs):
                self.last_kwargs = kwargs
                info = types.SimpleNamespace(
                    duration=60.0,
                    duration_after_vad=30.0,
                    language="en",
                    language_probability=0.9,
                )
                return [types.SimpleNamespace(start=1.0, end=2.0, text="hello", words=None)], info

        req = TimingRunRequest(
            video_path="dummy.mp4",
            start_ms=0,
            target_segment_count=5,
            vad_preset="custom",
            vad_threshold=0.4,
            min_speech_duration_ms=600,
            vad_speech_pad_ms=300,
            vad_max_speech_duration_s=15.0,
        )
        worker = TimingBatchWorker(req)
        model = MockTranscribeModel()
        worker._transcribe_with_vad_retry(model, "dummy.wav")

        opts = model.last_kwargs
        vad_params = opts["vad_parameters"]
        assert vad_params["threshold"] == 0.4
        assert vad_params["min_speech_duration_ms"] == 600
        assert vad_params["speech_pad_ms"] == 300
        assert vad_params["max_speech_duration_s"] == 15.0

        assert opts["no_speech_threshold"] == 0.6
        assert opts["log_prob_threshold"] == -1.0
        assert opts["compression_ratio_threshold"] == 2.4
        assert opts["hallucination_silence_threshold"] == 1.0


class TestTimingBatchWorkerResultFiltering:
    def test_filtering_drops_high_no_speech_and_hallucinations(self):
        """TC-VAD-FILTER-03: Segments with no_speech_prob >= 0.75, avg_logprob <= -1.2 & no_speech_prob >= 0.5,
        music notes, sound tags, or inconsistent language are dropped."""
        seg_normal = types.SimpleNamespace(start=0.0, end=2.0, text="Xin chào", no_speech_prob=0.1, avg_logprob=-0.3, words=None)
        seg_high_no_speech = types.SimpleNamespace(start=2.5, end=4.0, text="Drum beat", no_speech_prob=0.85, avg_logprob=-0.5, words=None)
        seg_low_logprob = types.SimpleNamespace(start=4.5, end=6.0, text="Mumble", no_speech_prob=0.55, avg_logprob=-1.3, words=None)
        seg_music_note = types.SimpleNamespace(start=6.5, end=8.0, text="♪", no_speech_prob=0.2, avg_logprob=-0.4, words=None)
        seg_sound_tag = types.SimpleNamespace(start=8.5, end=10.0, text="[music]", no_speech_prob=0.1, avg_logprob=-0.3, words=None)
        seg_hallucination = types.SimpleNamespace(start=10.5, end=12.0, text="Thank you for watching", no_speech_prob=0.1, avg_logprob=-0.3, words=None)

        req = TimingRunRequest(
            video_path="dummy.mp4",
            start_ms=0,
            target_segment_count=10,
            music_mode=True,  # Even in music mode, no_speech_prob >= 0.75 must be dropped
        )
        worker = TimingBatchWorker(req)

        # Mock wave.open and os.path.getsize, os.path.exists
        with patch("faster_whisper.WhisperModel") as MockWhisperModel, \
             patch("subprocess.run") as mock_subproc, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=100000), \
             patch("wave.open") as mock_wave_open:

            mock_subproc.return_value = types.SimpleNamespace(returncode=0, stderr="")
            mock_wav = MagicMock()
            mock_wav.getnframes.return_value = 16000 * 10
            mock_wav.getframerate.return_value = 16000
            mock_wave_open.return_value.__enter__.return_value = mock_wav

            mock_instance = MagicMock()
            MockWhisperModel.return_value = mock_instance
            info = types.SimpleNamespace(duration=10.0, duration_after_vad=10.0, language="vi", language_probability=0.99)
            raw_segs = [seg_normal, seg_high_no_speech, seg_low_logprob, seg_music_note, seg_sound_tag, seg_hallucination]
            mock_instance.transcribe.return_value = (raw_segs, info)

            finished_segments = []
            worker.finished_signal.connect(lambda segs, is_end: finished_segments.extend(segs))
            worker.run()

            # Only seg_normal should have been accepted
            assert len(finished_segments) == 1
            assert finished_segments[0]["start_ms"] == 0
            assert finished_segments[0]["end_ms"] == 2000

    def test_inconsistent_language_dropped(self):
        """When language='ja', Latin-only segment without Japanese characters is dropped."""
        seg_japanese = types.SimpleNamespace(start=0.0, end=2.0, text="はい、わかりました", no_speech_prob=0.1, avg_logprob=-0.2, words=None)
        seg_latin_hallucination = types.SimpleNamespace(start=2.5, end=4.0, text="Foreign hallucination", no_speech_prob=0.1, avg_logprob=-0.2, words=None)

        req = TimingRunRequest(
            video_path="dummy.mp4",
            start_ms=0,
            target_segment_count=5,
            language="ja",
        )
        worker = TimingBatchWorker(req)

        with patch("faster_whisper.WhisperModel") as MockWhisperModel, \
             patch("subprocess.run") as mock_subproc, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=100000), \
             patch("wave.open") as mock_wave_open:

            mock_subproc.return_value = types.SimpleNamespace(returncode=0, stderr="")
            mock_wav = MagicMock()
            mock_wav.getnframes.return_value = 16000 * 10
            mock_wav.getframerate.return_value = 16000
            mock_wave_open.return_value.__enter__.return_value = mock_wav

            mock_instance = MagicMock()
            MockWhisperModel.return_value = mock_instance
            info = types.SimpleNamespace(duration=10.0, duration_after_vad=10.0, language="ja", language_probability=0.99)
            mock_instance.transcribe.return_value = ([seg_japanese, seg_latin_hallucination], info)

            finished_segments = []
            worker.finished_signal.connect(lambda segs, is_end: finished_segments.extend(segs))
            worker.run()

            assert len(finished_segments) == 1
            assert finished_segments[0]["start_ms"] == 0
            assert finished_segments[0]["end_ms"] == 2000


class TestFasterWhisperServiceVADSettings:
    def test_transcribe_batch_vad_defaults_and_language_filter(self, tmp_path):
        dummy_video = tmp_path / "dummy.mp4"
        dummy_video.write_bytes(b"dummy")

        req = SubtitleGenerationRequest(
            request_id="req_001",
            project_id="proj_001",
            source_fingerprint="fp_001",
            video_path=str(dummy_video),
            model_size="base",
            compute_type="int8",
            language="ja",
            use_vad=True,
            min_silence_ms=500,
            word_timestamps=False,
        )
        batch = SubtitleGenerationBatch(
            batch_id="batch_001",
            start_ms=0,
            end_ms=10000,
            status="PENDING",
            revision=1,
            created_at="2026-11-14T00:00:00",
            updated_at="2026-11-14T00:00:00",
        )

        mock_model = MagicMock()
        captured_options = {}

        def mock_transcribe(_path, **options):
            captured_options.update(options)
            seg1 = MagicMock(start=0.0, end=2.0, text="こんにちは", words=[])
            seg2 = MagicMock(start=2.5, end=4.0, text="Foreign hallu", words=[])
            return [seg1, seg2], None

        mock_model.transcribe.side_effect = mock_transcribe

        service = FasterWhisperService()
        service.model = mock_model
        service.current_model_size = "base"
        service.current_compute_type = "int8"

        with patch.object(service, "_extract_batch_audio", return_value=(str(dummy_video), None)):
            result = service.transcribe_batch(req, batch, is_cancelled=lambda: False)

        assert captured_options["vad_filter"] is True
        assert captured_options["hallucination_silence_threshold"] == 1.0
        assert captured_options["vad_parameters"]["min_speech_duration_ms"] == 500

        # Only Japanese segment retained; Latin hallucination dropped
        assert len(result.segments) == 1
        assert result.segments[0].text == "こんにちは"

    def test_run_defaults_to_vad_filter_true(self, tmp_path):
        dummy_video = tmp_path / "test_run.mp4"
        dummy_video.write_bytes(b"content")

        mock_model = MagicMock()
        captured_kwargs = {}

        def mock_transcribe(_path, **kwargs):
            captured_kwargs.update(kwargs)
            seg = MagicMock(start=0.0, end=1.0, text="test")
            return [seg], None

        mock_model.transcribe.side_effect = mock_transcribe

        service = FasterWhisperService()
        service.model = mock_model
        service.current_model_size = "tiny"
        service.current_compute_type = "int8"

        with patch.object(service, "is_loaded", return_value=True), \
             patch("core.utils.file_utils.atomic_save_text"):
            service.run(str(dummy_video), model_size="tiny", language="en")

        assert captured_kwargs.get("vad_filter") is True
