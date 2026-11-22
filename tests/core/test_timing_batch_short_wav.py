import wave
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.timing.timing_run_request import TimingRunRequest
from workers.TimingBatchWorker import TimingBatchWorker


@pytest.mark.parametrize("fast_duration", [None, 0, 113])
def test_short_fast_seek_retries_accurately_and_fills_requested_batch(tmp_path, qapp, fast_duration):
    request = TimingRunRequest(
        video_path=str(tmp_path / "source.wmv"),
        start_ms=382_200,
        target_segment_count=5,
        max_window_ms=120_000,
        use_vad=False,
    )
    worker = TimingBatchWorker(request)
    results = []
    worker.finished_signal.connect(lambda segments, eof: results.append((segments, eof)))
    ffmpeg_commands = []
    transcriptions = []

    def fake_ffmpeg(cmd, **_kwargs):
        ffmpeg_commands.append(cmd)
        accurate = cmd.index("-ss") > cmd.index("-i")
        duration = 120 if accurate else fast_duration
        if duration is None:
            open(cmd[-1], "wb").close()
        else:
            with wave.open(cmd[-1], "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\0" * duration * 32000)
        return SimpleNamespace(returncode=0, stderr="")

    class FakeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, wav_path, **_kwargs):
            with wave.open(wav_path, "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
            transcriptions.append(duration)
            offsets = (10, 20, 30) if len(transcriptions) == 1 else (5, 15)
            segments = [SimpleNamespace(start=s, end=s + 0.5, words=None) for s in offsets]
            return segments, SimpleNamespace(duration=duration)

    with patch("torch.cuda.is_available", return_value=False), \
         patch("faster_whisper.WhisperModel", FakeModel), \
         patch("core.services.model_manager.ModelManager.get_model_path_for_inference", return_value="base"), \
         patch("workers.TimingBatchWorker.subprocess.run", side_effect=fake_ffmpeg):
        worker.run()

    assert len(results) == 1
    assert len(results[0][0]) == 5
    assert results[0][1] is False
    assert transcriptions == [120, 120]
    assert any(cmd.index("-ss") > cmd.index("-i") for cmd in ffmpeg_commands)


def test_empty_audio_after_accurate_seek_reports_end_of_source(tmp_path, qapp):
    worker = TimingBatchWorker(TimingRunRequest(
        video_path=str(tmp_path / "source.wmv"), start_ms=120_000,
        target_segment_count=5,
    ))
    results = []
    worker.finished_signal.connect(lambda segments, eof: results.append((segments, eof)))
    commands = []

    def fake_ffmpeg(cmd, **_kwargs):
        commands.append(cmd)
        with wave.open(cmd[-1], "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
        return SimpleNamespace(returncode=0, stderr="")

    with patch("torch.cuda.is_available", return_value=False), \
         patch("faster_whisper.WhisperModel"), \
         patch("core.services.model_manager.ModelManager.get_model_path_for_inference", return_value="base"), \
         patch("workers.TimingBatchWorker.subprocess.run", side_effect=fake_ffmpeg):
        worker.run()

    assert results == [([], True)]
    assert len(commands) == 2
