from copy import deepcopy
from threading import Event
from unittest.mock import MagicMock

import av
import numpy as np
import pytest

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import run_asr
from core.agent.models import StepStatus
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_result import (
    SubtitleGenerationResult,
    WhisperSegmentResult,
)
from workers.SegmentScanWorker import BatchSegmentScanWorker


@pytest.fixture
def silent_video(tmp_path):
    path = tmp_path / "silent.mp4"
    with av.open(str(path), "w") as container:
        video = container.add_stream("mpeg4", rate=1)
        video.width = video.height = 16
        video.pix_fmt = "yuv420p"
        audio = container.add_stream("aac", rate=16000)
        audio.layout = "mono"
        for _ in range(8):
            frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode():
            container.mux(packet)
        frame = av.AudioFrame.from_ndarray(np.zeros((1, 128000), dtype=np.float32), format="fltp", layout="mono")
        frame.sample_rate = 16000
        for packet in audio.encode(frame):
            container.mux(packet)
        for packet in audio.encode():
            container.mux(packet)
    return str(path)


@pytest.fixture
def speech_service():
    service = MagicMock(spec=FasterWhisperService)
    service.model = object()
    service.current_compute_type = "int8"

    def transcribe(request, batch, cancelled):
        return SubtitleGenerationResult(
            batch.batch_id,
            [WhisperSegmentResult(batch.start_ms, batch.end_ms, f"Speech at {batch.start_ms}")],
        )

    service.transcribe_batch.side_effect = transcribe
    return service


def segments():
    return [
        {"start": "00:00:01,000", "end": "00:00:03,000", "text": "First old text"},
        {"start": "00:00:04,000", "end": "00:00:06,000", "text": "Second old text"},
    ]


@pytest.mark.parametrize("with_segment_ids", [False, True])
def test_missing_ids_receive_distinct_worker_results(silent_video, speech_service, with_segment_ids):
    original = segments()
    indices = [1, 2]
    if with_segment_ids:
        indices = ["segment-a", "segment-b"]
        for segment, sid in zip(original, indices):
            segment["segment_id"] = sid
    before = deepcopy(original)

    result = run_asr(indices=indices, segments=original, video_path=silent_video,
                     whisper_service=speech_service)

    assert result["status"] == "ok"
    assert result["count"] == 2
    assert [s["text"] for s in result["segments"]] == ["Speech at 1000", "Speech at 4000"]
    assert [s["original_text"] for s in result["segments"]] == ["Speech at 1000", "Speech at 4000"]
    assert original == before
    assert all("id" not in s for s in result["segments"])


def test_prompt_cannot_replace_plan_until_async_result_is_consumed(qtbot, silent_video, speech_service):
    controller = AgentCopilotController()
    controller.async_mode = True
    controller.context_ledger.video_path = silent_video
    controller.whisper_service = speech_service
    controller._active_segments = segments()
    entered, release = Event(), Event()
    transcribe = speech_service.transcribe_batch.side_effect

    def blocked_transcribe(*args):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Test did not release ASR")
        return transcribe(*args)

    speech_service.transcribe_batch.side_effect = blocked_transcribe
    notifications = []
    controller.notification_requested.connect(notifications.append)
    plan = controller.submit_prompt("gen sub câu 2")
    controller.approve_plan()
    worker = controller._active_worker
    try:
        qtbot.waitUntil(entered.is_set)
        returned = controller.submit_prompt("đổi style sub chữ đỏ")
        assert returned is plan
        assert controller.active_plan is plan
        assert not controller.is_waiting_plan_approval()
        assert not controller.is_waiting_task_approval()
        assert notifications
        controller.request_task_revision()
        controller.approve_plan()
        assert controller._active_worker is worker
        assert plan.steps[0].status == StepStatus.RUNNING
        release.set()
        assert worker.wait(5000)
        assert controller.submit_prompt("đổi style sub chữ đỏ") is plan
        qtbot.waitUntil(lambda: plan.steps[0].status == StepStatus.COMPLETED)
        assert controller._active_segments[1]["text"] == "Speech at 4000"
        next_plan = controller.submit_prompt("đổi style sub chữ đỏ")
        assert next_plan is not plan
        assert controller.is_waiting_plan_approval()
        assert not controller.is_waiting_task_approval()
    finally:
        release.set()
        worker.wait(5000)


@pytest.mark.parametrize("ids", [
    ("76e9729e-df90-49d1-aa10-63adf025d48b", "8f009b2c-c7e8-47dc-8d23-147809e3b6cc"),
    (2, 42),
])
def test_sentence_number_selects_position_before_asr(silent_video, speech_service, ids):
    controller = AgentCopilotController()
    controller.context_ledger.video_path = silent_video
    controller.whisper_service = speech_service
    original = segments()
    for segment, sid in zip(original, ids):
        segment["id"] = sid
    controller._active_segments = deepcopy(original)
    plan = controller.submit_prompt("gen sub câu 2")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.COMPLETED
    assert controller._active_segments[0] == original[0]
    assert controller._active_segments[1]["text"] == "Speech at 4000"
    assert controller._last_step_result["indices"] == [ids[1]]


def test_partial_timing_can_continue_to_asr(monkeypatch, silent_video, speech_service):
    monkeypatch.setattr("core.agent.vad_timing_service.extract_audio_window", lambda *a, **k: np.zeros(16000))
    monkeypatch.setattr("core.agent.vad_timing_service.detect_speech_intervals_vad", lambda *a, **k: [
        {"start_ms": 1000, "end_ms": 3000}, {"start_ms": 4000, "end_ms": 6000},
    ])
    controller = AgentCopilotController()
    controller.context_ledger.video_path = silent_video
    controller.whisper_service = speech_service
    plan = controller.submit_prompt("tạo timing 3 câu và gen sub 3 câu đó")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.COMPLETED
    assert controller._last_step_result["status"] == "partial"
    assert controller.is_waiting_task_approval()
    assert "2/3" in controller.chat_history[-1].content
    controller.approve_next_step()
    assert plan.steps[1].status == StepStatus.COMPLETED
    assert [s["text"] for s in controller._active_segments] == ["Speech at 1000", "Speech at 4000"]
    assert controller._last_step_result["count"] == 2


def test_partial_asr_still_blocks_approval(silent_video, speech_service):
    speech_service.transcribe_batch.side_effect = [
        SubtitleGenerationResult("first", [WhisperSegmentResult(1000, 3000, "Recognized first")]),
        SubtitleGenerationResult("second", [], "ASR failure"),
    ]
    controller = AgentCopilotController()
    controller.context_ledger.video_path = silent_video
    controller.whisper_service = speech_service
    controller._active_segments = segments()
    plan = controller.submit_prompt("gen sub")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.FAILED
    assert not controller.is_waiting_task_approval()
    assert [s["text"] for s in controller._active_segments] == ["Recognized first", "Second old text"]
    controller.approve_next_step()
    assert not controller.is_plan_completed()


@pytest.mark.parametrize("recognized", [[], [WhisperSegmentResult(1000, 3000, "Diyorlar.")],
                                         [WhisperSegmentResult(1000, 3000, "English speech")]])
def test_empty_or_filtered_asr_preserves_text_and_blocks_approval(silent_video, speech_service, recognized):
    speech_service.transcribe_batch.side_effect = None
    speech_service.transcribe_batch.return_value = SubtitleGenerationResult("empty", recognized)
    controller = AgentCopilotController()
    controller.context_ledger.video_path = silent_video
    controller.context_ledger.source_lang = "ja"
    controller.whisper_service = speech_service
    original = segments()
    controller._active_segments = deepcopy(original)
    plan = controller.submit_prompt("gen sub")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.FAILED
    assert controller._active_segments == original
    assert not controller.is_waiting_task_approval()
    assert "Không nhận diện" in plan.steps[0].error_message
    controller.approve_next_step()
    assert not controller.is_plan_completed()


def test_empty_asr_among_successful_segments_is_partial(silent_video, speech_service):
    speech_service.transcribe_batch.side_effect = [
        SubtitleGenerationResult("first", [WhisperSegmentResult(1000, 3000, "Recognized first")]),
        SubtitleGenerationResult("second", []),
    ]
    result = run_asr(segments=segments(), video_path=silent_video, whisper_service=speech_service)
    assert result["status"] == "partial"
    assert result["count"] == 1
    assert [s["text"] for s in result["segments"]] == ["Recognized first", "Second old text"]


def test_empty_workspace_and_silent_video_stay_empty(silent_video, speech_service):
    controller = AgentCopilotController()
    controller.context_ledger.video_path = silent_video
    controller.whisper_service = speech_service
    plan = controller.submit_prompt("tạo timing 3 câu và gen sub 3 câu đó")
    controller.approve_plan()

    assert controller._last_step_result["status"] == "no_speech"
    assert controller._active_segments == []
    assert "0 phân đoạn" in controller.chat_history[-1].content or "0 câu" in controller.chat_history[-1].content
    controller.approve_next_step()
    assert plan.steps[1].status == StepStatus.COMPLETED
    assert controller._active_segments == []
    assert controller._last_step_result["count"] == 0
    speech_service.transcribe_batch.assert_not_called()
    speech_service.load_model.assert_not_called()
    controller.request_task_revision()
    controller.approve_next_step()
    assert controller._active_segments == []
    speech_service.transcribe_batch.assert_not_called()


@pytest.mark.parametrize("loaded_size", ["tiny", "large-v3"])
def test_batch_scan_uses_requested_model_and_reuses_matching_model(monkeypatch, loaded_size):
    service = FasterWhisperService(device="cpu")
    old_model = object()
    new_model = object()
    service.model = old_model
    service.current_model_size = loaded_size
    service.current_compute_type = "int8"
    model_factory = MagicMock(return_value=new_model)
    monkeypatch.setattr("faster_whisper.WhisperModel", model_factory)
    monkeypatch.setattr("core.services.model_manager.ModelManager.get_model_path_for_inference", lambda size: f"local/{size}")
    observed_models = []

    def transcribe(request, batch, cancelled):
        observed_models.append(service.model)
        return SubtitleGenerationResult(batch.batch_id, [WhisperSegmentResult(1000, 3000, "Recognized")])

    monkeypatch.setattr(service, "transcribe_batch", transcribe)
    request = SubtitleGenerationRequest(
        request_id="test", project_id="test", source_fingerprint="test", video_path="unused.mp4",
        model_size="large-v3", compute_type="int8", language=None, use_vad=False,
        min_silence_ms=300, word_timestamps=False,
    )
    worker = BatchSegmentScanWorker([{"id": "uuid-a", "start_ms": 1000, "end_ms": 3000}], request, service)
    worker.run()

    assert service.current_model_size == "large-v3"
    assert observed_models == [new_model if loaded_size == "tiny" else old_model]
    assert model_factory.call_count == (1 if loaded_size == "tiny" else 0)
