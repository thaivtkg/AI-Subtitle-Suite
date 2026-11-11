import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import create_timing, run_asr
from core.agent.vad_timing_service import generate_vad_timing_segments
from core.agent.models import AgentTaskPlan, AgentStep, StepStatus
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from ui.SubEditor import ms_to_time_str, time_str_to_ms


def test_tc_01_real_asr_service_init_and_validator_params():
    """Lỗi 1 [P1]: FasterWhisperService có current_compute_type=None vẫn áp dụng float16,
    SubtitleGenerationValidator import đúng, SubtitleGenerationRequest đủ project_id và source_fingerprint."""
    mock_svc = MagicMock()
    mock_svc.current_compute_type = None  # Giả lập FasterWhisperService khởi tạo current_compute_type=None
    mock_svc.model = None  # Cần nạp model

    loaded_args = []
    def fake_load(size, c_type):
        loaded_args.append((size, c_type))
        mock_svc.model = MagicMock()
    mock_svc.load_model.side_effect = fake_load

    mock_result = MagicMock(error=None)
    mock_result.segments = [MagicMock(text="Thử nghiệm ASR thật", start_ms=1000, end_ms=3000)]
    mock_svc.transcribe_batch.return_value = mock_result

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_vid:
        segs = [{"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Cũ"}]
        res = run_asr(
            segments=segs,
            indices=[1],
            model_size="tiny",
            video_path=tmp_vid.name,
            whisper_service=mock_svc,
        )
        assert res["status"] == "ok"
        # Đã áp dụng fallback float16 khi current_compute_type=None
        assert loaded_args == [("tiny", "float16")]
        # Kiểm tra transcribe_batch được gọi với SubtitleGenerationRequest hợp lệ
        assert mock_svc.transcribe_batch.call_count == 1
        call_req = mock_svc.transcribe_batch.call_args[0][0]
        assert isinstance(call_req, SubtitleGenerationRequest)
        assert call_req.project_id is not None and call_req.project_id != ""
        assert call_req.source_fingerprint is not None and call_req.source_fingerprint != ""


def test_tc_02_vad_empty_indices_does_not_wipe_existing_subtitles_and_redo_preserves():
    """Lỗi 2 [P1]: Khi VAD trả về 0 câu mới (new_indices=[]), ASR không được xử lý toàn bộ câu cũ.
    Redo không bị mất target_newly_created."""
    controller = AgentCopilotController()
    existing_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1 giữ nguyên"},
        {"id": 2, "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2 giữ nguyên"},
    ]
    controller._active_segments = list(existing_segs)

    # 1. Giả lập create_timing trả về 0 câu mới
    timing_res = {"status": "ok", "new_indices": [], "new_segments": [], "segments": existing_segs}
    step_timing = AgentStep(id="1", title="Tạo timing", tool_name="create_timing")
    step_asr = AgentStep(
        id="2",
        title="ASR câu mới",
        tool_name="run_asr",
        tool_args={"target_newly_created": True},
    )
    plan = AgentTaskPlan(prompt="tạo timing 3 câu và gen sub", steps=[step_timing, step_asr])
    controller.active_plan = plan

    # Xử lý kết quả bước 1
    controller._handle_step_result(0, step_timing, {"success": True, "result": timing_res})
    assert controller._last_created_indices == []
    # Bước 2 đã được gán indices=[]
    assert step_asr.tool_args.get("indices") == []

    # Chạy bước 2 (run_asr)
    mock_svc = MagicMock()
    mock_svc.model = MagicMock()
    controller.whisper_service = mock_svc
    controller.context_ledger.video_path = "dummy_video.mp4"

    controller.approve_next_step()
    # ASR hoàn thành với 0 câu quét, toàn bộ phụ đề cũ giữ nguyên 100%
    assert len(controller._active_segments) == 2
    assert controller._active_segments[0]["text"] == "Câu 1 giữ nguyên"
    assert controller._active_segments[1]["text"] == "Câu 2 giữ nguyên"
    assert mock_svc.transcribe_batch.call_count == 0

    # Kiểm tra Redo: User bấm làm lại bước 2
    controller.request_task_revision()
    assert step_asr.status == StepStatus.PENDING
    assert step_asr.tool_args.get("indices") == []


def test_tc_03_non_integer_uuid_or_missing_id_stability():
    """Lỗi 3 [P1]: Câu cũ có ID dạng UUID hoặc thiếu id -> create_timing cấp ID mới không đè vị trí cũ,
    run_asr chỉ nhận diện đúng câu mới."""
    existing_segs = [
        {"id": "uuid-aaa-111", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu UUID 1"},
        {"id": "uuid-bbb-222", "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu UUID 2"},
        {"start": "00:00:07,000", "end": "00:00:09,000", "text": "Câu thiếu id 3"},
    ]

    # create_timing thêm 2 câu mới
    timing_res = create_timing(count=2, existing_segments=existing_segs, is_continue=True)
    new_segs = timing_res["new_segments"]
    # ID mới phải > len(existing_segs) = 3 (tức là 4 và 5)
    assert new_segs[0]["id"] == 4
    assert new_segs[1]["id"] == 5

    # run_asr với indices=[4, 5]
    mock_svc = MagicMock()
    mock_svc.model = MagicMock()
    mock_svc.transcribe_batch.side_effect = (
        lambda req, batch, cancel: MagicMock(
            error=None,
            segments=[MagicMock(text="Nhận diện mới", start_ms=batch.start_ms, end_ms=batch.end_ms)]
        )
    )

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_vid:
        asr_res = run_asr(
            indices=[4, 5],
            segments=timing_res["segments"],
            video_path=tmp_vid.name,
            whisper_service=mock_svc,
        )
        assert asr_res["status"] == "ok"
        all_res_segs = asr_res["segments"]
        # 3 câu cũ giữ nguyên
        assert all_res_segs[0]["text"] == "Câu UUID 1"
        assert all_res_segs[1]["text"] == "Câu UUID 2"
        assert all_res_segs[2]["text"] == "Câu thiếu id 3"
        # 2 câu mới được nhận diện
        assert all_res_segs[3]["text"] == "Nhận diện mới"
        assert all_res_segs[4]["text"] == "Nhận diện mới"


def test_tc_04_async_step_execution_worker(qtbot):
    """Lỗi 4 [P1]: ASR thật chạy qua StepExecutionWorker trong controller không làm khóa GUI."""
    controller = AgentCopilotController()
    controller.async_mode = True

    mock_svc = MagicMock()
    mock_svc.model = MagicMock()
    mock_result = MagicMock(error=None)
    mock_result.segments = [MagicMock(text="Async ASR Done", start_ms=1000, end_ms=3000)]
    mock_svc.transcribe_batch.return_value = mock_result
    controller.whisper_service = mock_svc

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_vid:
        controller.context_ledger.video_path = tmp_vid.name
        controller._active_segments = [{"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Old"}]

        step = AgentStep(id="1", title="ASR Async", tool_name="run_asr", tool_args={"indices": [1]})
        plan = AgentTaskPlan(prompt="Test async", steps=[step])
        controller.active_plan = plan
        controller._waiting_plan_approval = True

        with qtbot.waitSignal(controller.step_completed, timeout=3000):
            controller.approve_plan()

        assert step.status == StepStatus.COMPLETED
        assert controller._active_segments[0]["text"] == "Async ASR Done"


def test_tc_05_asr_failure_marks_step_failed_and_does_not_complete_plan():
    """Lỗi 5 [P1]: Khi ASR thất bại, controller đánh dấu step FAILED, giữ text cũ,
    và approve_next_step không thể cho qua hoặc kết thúc kế hoạch."""
    controller = AgentCopilotController()
    segs = [{"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Văn bản gốc cần bảo toàn"}]
    controller._active_segments = list(segs)

    # Mock service không có model và load_model gặp lỗi
    mock_svc = MagicMock()
    mock_svc.model = None
    mock_svc.load_model.side_effect = RuntimeError("VRAM OOM")
    controller.whisper_service = mock_svc

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_vid:
        controller.context_ledger.video_path = tmp_vid.name
        step1 = AgentStep(id="1", title="ASR lỗi", tool_name="run_asr", tool_args={"indices": [1]})
        step2 = AgentStep(id="2", title="Dịch thuật", tool_name="translate_subtitles")
        plan = AgentTaskPlan(prompt="Lỗi ASR", steps=[step1, step2])
        controller.active_plan = plan

        failed_signals = []
        controller.step_failed.connect(lambda idx, s, err: failed_signals.append((idx, s, err)))

        controller._run_current_step()

        # Step 1 phải FAILED
        assert step1.status == StepStatus.FAILED
        assert len(failed_signals) == 1
        # Văn bản cũ không bị đè lỗi
        assert controller._active_segments[0]["text"] == "Văn bản gốc cần bảo toàn"
        # Không được cho phép approve
        assert not controller.is_waiting_task_approval()
        controller.approve_next_step()
        assert plan.status != StepStatus.COMPLETED
        assert controller.current_step_index == 0


def test_tc_06_missing_video_returns_error_without_synthetic_text():
    """Lỗi 6 [P1]: Khi không có file video, run_asr báo lỗi rõ ràng và giữ nguyên dữ liệu,
    không điền chuỗi giả '(Whisper)'."""
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1 thật sự"},
        {"id": 2, "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2 thật sự"},
    ]

    res = run_asr(
        segments=initial_segs,
        indices=[1, 2],
        video_path="non_existent_video_path_12345.mp4",
    )

    assert res["status"] == "error"
    assert "Không tìm thấy file video" in res["error"]
    # Dữ liệu giữ nguyên 100%
    assert res["segments"][0]["text"] == "Câu 1 thật sự"
    assert res["segments"][1]["text"] == "Câu 2 thật sự"
    assert "Whisper" not in res["segments"][0]["text"]


def test_tc_07_start_from_beginning_is_not_forced_to_continue():
    """Lỗi 7 [P2]: Prompt 'tạo timing 3 câu đầu' (is_continue=False) khi đã có phụ đề
    phải bắt đầu từ 0.0s, không bị đẩy ra sau câu cuối."""
    existing_segs = [
        {"id": 1, "start": "00:00:10,000", "end": "00:00:15,000", "text": "Đã có ở 15s"},
    ]

    res = create_timing(
        count=3,
        existing_segments=existing_segs,
        is_continue=False,  # Yêu cầu từ đầu
        start_offset_s=0.0,
    )

    new_segs = res["new_segments"]
    assert len(new_segs) == 3
    # Phải bắt đầu từ 00:00:00,500 chứ không phải 15.5s
    assert time_str_to_ms(new_segs[0]["start"]) < 10000


def test_tc_08_vad_timing_multi_window_loop_traverses_silence():
    """Lỗi 8 [P2]: Khi video có khoảng im lặng dài > 5 phút (300s), generate_vad_timing_segments
    lặp qua các cửa sổ tiếp theo cho đến khi đủ câu hoặc hết video."""
    video_path = "mock_long_video.mp4"
    # Giả lập:
    # Cửa sổ 0s - 300s: hoàn toàn im lặng (detect_speech_intervals_vad trả [])
    # Cửa sổ 300s - 600s: có 2 đoạn thoại
    def mock_extract(v_path, start_offset_s, max_duration_s):
        return [0.0] * 16000  # Fake audio

    call_offsets = []
    def mock_detect(audio, start_offset_s, **kwargs):
        call_offsets.append(start_offset_s)
        if start_offset_s < 300.0:
            return []  # Im lặng 5 phút đầu
        else:
            return [
                {"start_ms": 310000, "end_ms": 315000},
                {"start_ms": 320000, "end_ms": 325000},
            ]

    with patch("core.agent.vad_timing_service.os.path.exists", return_value=True), \
         patch("core.agent.vad_timing_service.get_video_duration_ms", return_value=1000000), \
         patch("core.agent.vad_timing_service.extract_audio_window", side_effect=mock_extract), \
         patch("core.agent.vad_timing_service.detect_speech_intervals_vad", side_effect=mock_detect):

        segs = generate_vad_timing_segments(
            count=2,
            video_path=video_path,
            start_offset_s=0.0,
        )

        assert len(segs) == 2
        assert segs[0]["start"] == ms_to_time_str(310000)
        assert segs[1]["start"] == ms_to_time_str(320000)
        # Đã quét qua ít nhất 2 cửa sổ
        assert len(call_offsets) >= 2
        assert 0.0 in call_offsets
        assert any(off >= 300.0 for off in call_offsets)
