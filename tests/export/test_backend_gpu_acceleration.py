# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
from core.Backend import detect_video_encoder, burn_hardsub
import core.Backend as backend_module


def test_detect_video_encoder_prefers_nvenc_when_supported():
    with patch.object(backend_module, "_CACHED_VIDEO_ENCODER", None):
        with patch("subprocess.run") as mock_run:
            mock_res = MagicMock(returncode=0)
            mock_run.return_value = mock_res
            enc, desc = detect_video_encoder("ffmpeg")
            assert enc == "h264_nvenc"
            assert "NVIDIA" in desc


def test_detect_video_encoder_falls_back_to_libx264_on_failure():
    with patch.object(backend_module, "_CACHED_VIDEO_ENCODER", None):
        with patch("subprocess.run") as mock_run:
            mock_res = MagicMock(returncode=1)
            mock_run.return_value = mock_res
            enc, desc = detect_video_encoder("ffmpeg")
            assert enc == "libx264"
            assert "CPU" in desc


def test_burn_hardsub_applies_video_encoder_in_ffmpeg_command():
    class _FakeStdout:
        def __iter__(self):
            return iter(())
        def close(self):
            return None

    class _FakeProcess:
        def __init__(self, returncode=0):
            self.stdout = _FakeStdout()
            self.returncode = returncode
        def poll(self):
            return self.returncode
        def wait(self):
            return self.returncode

    with patch.object(backend_module, "_CACHED_VIDEO_ENCODER", ("h264_nvenc", "NVIDIA NVENC (GPU)")):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "video.mp4"
            srt = Path(temp_dir) / "sub.srt"
            output = Path(temp_dir) / "out.mp4"
            video.write_bytes(b"vid")
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

            with patch("core.runtime.runtime_paths.RuntimePaths.get_ffmpeg_exe", return_value="ffmpeg"), \
                 patch("subprocess.Popen", return_value=_FakeProcess(0)) as mock_popen:
                burn_hardsub(str(video), str(srt), str(output), video_resolution=(1280, 720))

            cmd = mock_popen.call_args.args[0]
            assert "-c:v" in cmd
            c_v_idx = cmd.index("-c:v")
            assert cmd[c_v_idx + 1] == "h264_nvenc"


def test_burn_hardsub_falls_back_to_cpu_when_gpu_fails():
    class _FakeStdout:
        def __iter__(self):
            return iter(())
        def close(self):
            return None

    calls = []
    class _FakeProcess:
        def __init__(self, codec, returncode):
            self.codec = codec
            self.returncode = returncode
            self.stdout = _FakeStdout()
        def poll(self):
            return self.returncode
        def wait(self):
            return self.returncode

    def fake_popen(cmd, **kwargs):
        c_v = cmd[cmd.index("-c:v") + 1]
        calls.append(c_v)
        if c_v == "h264_nvenc":
            return _FakeProcess("h264_nvenc", returncode=1)
        return _FakeProcess("libx264", returncode=0)

    with patch.object(backend_module, "_CACHED_VIDEO_ENCODER", ("h264_nvenc", "NVIDIA NVENC (GPU)")):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "video.mp4"
            srt = Path(temp_dir) / "sub.srt"
            output = Path(temp_dir) / "out.mp4"
            video.write_bytes(b"vid")
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

            with patch("core.runtime.runtime_paths.RuntimePaths.get_ffmpeg_exe", return_value="ffmpeg"), \
                 patch("subprocess.Popen", side_effect=fake_popen):
                burn_hardsub(str(video), str(srt), str(output), video_resolution=(1280, 720))

            assert calls == ["h264_nvenc", "libx264"], f"Expected fallback from GPU to CPU, got {calls}"
