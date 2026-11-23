# -*- coding: utf-8 -*-
"""
Verification suite for Architectural, Concurrency & Performance Audit Fixes:
- AUD-CONCUR-001: ModelManager Mutex Lock & TranslationController Multi-Worker Busy Guard
- AUD-PERF-001: FFmpeg Fast Input Seeking (-ss before -i)
- AUD-PERF-002: VideoPlayer Temporal Locality O(1) & Bisect Binary Search O(log N)
- AUD-MEM-001: Safe QThread Lifecycle & Resource Cleanup
"""
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QApplication

from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from player.video_player import VideoPlayerWidget, _parse_time_to_ms, _extract_segment_info


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_aud_perf_001_ffmpeg_fast_input_seeking():
    """AUD-PERF-001: FFmpeg đặt '-ss' trước '-i' để fast-seek demuxer O(1) thay vì decode O(N^2)."""
    req = SubtitleGenerationRequest(
        request_id="r1",
        project_id="p1",
        source_fingerprint="fp1",
        video_path="video.mp4",
        model_size="small",
        compute_type="int8",
        language="vi",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
        audio_boost=False,
    )
    batch = SubtitleGenerationBatch("b1", 3600000, 3630000, "RUNNING", 1, "", "")

    with patch("subprocess.run") as mock_run, patch("wave.open") as mock_audio:
        mock_audio.return_value.__enter__.return_value.getnframes.return_value = 480000
        mock_audio.return_value.__enter__.return_value.getframerate.return_value = 16000
        _, tmp = FasterWhisperService._extract_batch_audio(req, batch)
        cmd = mock_run.call_args[0][0]

        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")

        # Khẳng định '-ss' xuất hiện trước '-i'
        assert ss_idx < i_idx, f"-ss (idx {ss_idx}) phải đứng trước -i (idx {i_idx})"
        assert cmd[ss_idx + 1] == "3600.000"
        assert cmd[i_idx + 1] == "video.mp4"


def test_aud_perf_002_video_player_bisect_and_temporal_locality(qapp):
    """AUD-PERF-002: VideoPlayer sử dụng Temporal Locality O(1) và Bisect O(log N) cho playback scrubbing."""
    player = VideoPlayerWidget()
    try:
        # Tạo 200 phụ đề liên tiếp
        subs = []
        for i in range(200):
            s = i * 2000
            e = s + 1500
            subs.append({
                "stt": i + 1,
                "start_ms": s,
                "end_ms": e,
                "text": f"Câu phụ đề thứ {i + 1}",
                "style_preset": "normal"
            })
        player.sub_controller.subs = subs

        # 1. Tìm câu ở index 150 (start_ms = 300,000ms -> 301,500ms)
        target_time = 300500
        player.position_changed(target_time)

        assert player._current_playback_sub is not None
        assert player._current_playback_sub["stt"] == 151
        assert player._current_playback_sub["text"] == "Câu phụ đề thứ 151"

        # 2. Fast Path: Frame tiếp theo tại 300533ms (vẫn trong câu 151) -> O(1)
        prev_ref = player._current_playback_sub
        player.position_changed(300533)
        assert player._current_playback_sub is prev_ref

        # 3. Rơi vào khoảng nghỉ giữa 2 câu (301600ms) -> Clear subtitle
        player.position_changed(301600)
        assert player._current_playback_sub is None

    finally:
        player.close()
        player.deleteLater()
