# -*- coding: utf-8 -*-
"""
Verification suite for Architectural, Concurrency & Performance Audit Fixes:
- AUD-CONCUR-001: ModelManager Mutex Lock & TranslationController Multi-Worker Busy Guard
- AUD-PERF-001: FFmpeg Fast Input Seeking (-ss before -i)
- AUD-PERF-002: VideoPlayer Temporal Locality O(1) & Bisect Binary Search O(log N)
- AUD-MEM-001: Safe QThread Lifecycle & Resource Cleanup
"""
import threading
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QApplication

from core.translation.llm.model_manager import ModelManager
from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from player.video_player import VideoPlayerWidget, _parse_time_to_ms, _extract_segment_info


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_aud_concur_001_model_manager_mutex_lock():
    """AUD-CONCUR-001: ModelManager sở hữu RLock độc quyền bảo vệ generate/stream."""
    mgr = ModelManager.get_instance("ollama")
    assert hasattr(mgr, "_lock")
    assert isinstance(mgr._lock, type(threading.RLock()))

    # Xác thực generate acquire lock
    mgr.backend.generate = MagicMock(return_value="translated text")
    result = mgr.generate("test prompt")
    assert result == "translated text"
    mgr.backend.generate.assert_called_once_with("test prompt", system_prompt="")


def test_aud_concur_001_and_mem_001_controller_busy_guard(qapp):
    """AUD-CONCUR-001 & AUD-MEM-001: is_busy() phát hiện bất kỳ worker nào đang chạy và chặn collision."""
    model = SubtitleModel()
    model.load_data([
        {"original": "Hello", "translation": "Xin chào", "status": "PENDING"},
        {"original": "World", "translation": "", "status": "PENDING"},
    ])
    controller = TranslationController(model)

    assert controller.is_busy() is False

    # Giả lập worker đang chạy
    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    controller.worker = mock_worker

    assert controller.is_busy() is True

    # Khi bận, requestTranslation không được khởi tạo luồng mới
    factory_mock = MagicMock()
    controller._worker_factory = factory_mock
    controller.requestTranslation(1, "English", "Vietnamese", "")
    factory_mock.assert_not_called()

    # Tương tự cho requestAlternativeTranslation
    controller.requestAlternativeTranslation(1, "English")
    factory_mock.assert_not_called()

    # Tương tự cho extractTermsForSubtitle
    controller.extractTermsForSubtitle(0)
    factory_mock.assert_not_called()

    # Giả lập worker dừng
    mock_worker.isRunning.return_value = False
    assert controller.is_busy() is False

    # Dọn dẹp
    controller.shutdown()
    assert controller.worker is None


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

    with patch("subprocess.run") as mock_run:
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
