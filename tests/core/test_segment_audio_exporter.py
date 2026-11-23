import array
import os
import subprocess
import wave

import pytest

from core.audio.segment_audio_exporter import (
    build_export_ffmpeg_cmd,
    export_merged_segments_audio,
    export_segment_audio,
    format_merged_audio_filename,
    format_segment_audio_filename,
)
from core.runtime.runtime_paths import RuntimePaths


def _make_synthetic_stereo_48k_mp4(tmp_path) -> str:
    video_path = str(tmp_path / "sample_48k_stereo.mp4")
    ffmpeg_exe = RuntimePaths.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=5",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=64x64:d=5",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:v",
        "libx264",
        "-t",
        "5",
        "-c:a",
        "aac",
        video_path,
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=creationflags, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return video_path


def test_format_segment_audio_filename():
    assert format_segment_audio_filename(64, 776900, 780300, "wav") == "0064_00-12-56-900_00-13-00-300.wav"
    assert format_segment_audio_filename(3, 1000, 2500, "MP3") == "0003_00-00-01-000_00-00-02-500.mp3"


def test_build_export_ffmpeg_cmd_preserves_original_audio_properties():
    wav_cmd = build_export_ffmpeg_cmd("ffmpeg", "in.mp4", 1000, 2500, "out.wav", "wav")
    assert "-ar" not in wav_cmd
    assert "-ac" not in wav_cmd
    assert "pcm_s16le" in wav_cmd
    assert "-vn" in wav_cmd

    mp3_cmd = build_export_ffmpeg_cmd("ffmpeg", "in.mp4", 10500, 12000, "out.mp3", "mp3")
    assert "-ar" not in mp3_cmd
    assert "-ac" not in mp3_cmd
    assert "-af" not in mp3_cmd
    assert "libmp3lame" in mp3_cmd
    # Hybrid fast seek before -i for start > 2s
    assert mp3_cmd.index("-ss") < mp3_cmd.index("-i")


def test_build_export_ffmpeg_cmd_rejects_invalid_range_and_format():
    with pytest.raises(ValueError):
        build_export_ffmpeg_cmd("ffmpeg", "in.mp4", 3000, 3000, "out.wav", "wav")
    with pytest.raises(ValueError):
        build_export_ffmpeg_cmd("ffmpeg", "in.mp4", 1000, 2000, "out.ogg", "ogg")


def test_export_segment_audio_real_wav_and_mp3_preserves_stereo_48k(tmp_path):
    video_path = _make_synthetic_stereo_48k_mp4(tmp_path)

    wav_out = str(tmp_path / "clip.wav")
    export_segment_audio(video_path, 1200, 2700, wav_out, audio_format="wav")
    assert os.path.isfile(wav_out)
    with wave.open(wav_out, "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 48000
        dur_s = wf.getnframes() / float(wf.getframerate())
        assert 1.40 <= dur_s <= 1.60

    mp3_out = str(tmp_path / "clip.mp3")
    export_segment_audio(video_path, 2500, 4000, mp3_out, audio_format="mp3")
    assert os.path.isfile(mp3_out)
    assert os.path.getsize(mp3_out) > 1000


def test_export_segment_audio_missing_video_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        export_segment_audio(str(tmp_path / "missing.mp4"), 0, 1000, str(tmp_path / "out.wav"))


def test_format_merged_audio_filename_orders_by_stt():
    assert format_merged_audio_filename([12, 3, 7], "wav") == "merged_0003-0012_3segs.wav"
    assert format_merged_audio_filename([5, 2], "MP3") == "merged_0002-0005_2segs.mp3"


def test_export_merged_segments_audio_sorts_by_stt_and_preserves_stereo_48k(tmp_path):
    video_path = _make_synthetic_stereo_48k_mp4(tmp_path)
    # Use segments with start > 2.0s and duration < 2.0s (hybrid-seek path) + out-of-order STT
    progress_labels = []
    merged_wav = str(tmp_path / "merged_out.wav")
    export_merged_segments_audio(
        video_path,
        [(5, 3200, 4400), (2, 2100, 3100)],
        merged_wav,
        audio_format="wav",
        progress_cb=lambda done, total, label: progress_labels.append((done, total, label)),
    )
    assert os.path.isfile(merged_wav)
    # First sliced segment must be STT #2 before STT #5
    stt_steps = [label for _, _, label in progress_labels if label.startswith("STT #")]
    assert stt_steps[0] == "STT #2"
    assert stt_steps[-1] == "STT #5"

    with wave.open(merged_wav, "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
        assert ch == 2
        assert sr == 48000
        dur_s = nframes / float(sr)
        # Default gap_ms=300: 1.0s + 0.3s silence + 1.2s = 2.5s
        assert 2.38 <= dur_s <= 2.62

    samples = array.array("h")
    samples.frombytes(raw)
    # Both segments must contain real non-zero audio (regression guard against silent afade/seek bug)
    seg1_mid = samples[int(0.2 * sr * ch):int(0.8 * sr * ch)]
    gap_mid = samples[int(1.05 * sr * ch):int(1.25 * sr * ch)]
    seg2_mid = samples[int(1.5 * sr * ch):int(2.3 * sr * ch)]
    assert max(abs(v) for v in seg1_mid) > 1000
    assert max(abs(v) for v in gap_mid) == 0
    assert max(abs(v) for v in seg2_mid) > 1000
    assert samples[0] == 0 and samples[-1] == 0

    # Back-to-back merge with gap_ms=0
    merged_zero_gap = str(tmp_path / "merged_no_gap.wav")
    export_merged_segments_audio(
        video_path,
        [(5, 3200, 4400), (2, 2100, 3100)],
        merged_zero_gap,
        audio_format="wav",
        gap_ms=0,
        edge_fade_ms=15,
    )
    with wave.open(merged_zero_gap, "rb") as wf:
        dur_zero = wf.getnframes() / float(wf.getframerate())
        assert 2.08 <= dur_zero <= 2.32

    merged_mp3 = str(tmp_path / "merged_out.mp3")
    export_merged_segments_audio(
        video_path,
        [(5, 3200, 4400), (2, 2100, 3100)],
        merged_mp3,
        audio_format="mp3",
    )
    assert os.path.isfile(merged_mp3)
    assert os.path.getsize(merged_mp3) > 1500
