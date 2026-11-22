import shutil
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.subtitle_generation.faster_whisper_service import FasterWhisperService


@pytest.mark.parametrize("fast_frames", [0, 1600, 32000])
def test_short_fast_seek_retries_accurate_seek(monkeypatch, fast_frames):
    commands = []

    def extract(command, **kwargs):
        commands.append(command.copy())
        frames = fast_frames if command.index("-ss") < command.index("-i") else 32000
        with wave.open(command[-1], "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x01\x00" * frames)

    monkeypatch.setattr("core.subtitle_generation.faster_whisper_service.subprocess.run", extract)
    path, directory = FasterWhisperService._extract_batch_audio(
        SimpleNamespace(video_path="video.wmv", audio_boost=True),
        SimpleNamespace(start_ms=16000, end_ms=18000),
    )
    try:
        with wave.open(path) as audio:
            assert audio.getnframes() == 32000
        assert len(commands) == (1 if fast_frames == 32000 else 2)
        assert all("volume=2.0" in command for command in commands)
    finally:
        shutil.rmtree(directory)


def test_empty_audio_after_retry_is_error_and_temp_is_cleaned(monkeypatch):
    outputs = []

    def extract(command, **kwargs):
        outputs.append(Path(command[-1]))
        with wave.open(str(outputs[-1]), "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))

    monkeypatch.setattr("core.subtitle_generation.faster_whisper_service.subprocess.run", extract)
    with pytest.raises(RuntimeError, match="empty audio"):
        FasterWhisperService._extract_batch_audio(
            SimpleNamespace(video_path="video.wmv"),
            SimpleNamespace(start_ms=16000, end_ms=18000),
        )
    assert len(outputs) == 2
    assert not outputs[-1].parent.exists()
