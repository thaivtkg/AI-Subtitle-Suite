import os
import pytest
from unittest.mock import MagicMock

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import AgentToolRegistry, create_timing, run_asr
from core.agent.vad_timing_service import (
    generate_vad_timing_segments,
    extract_audio_window,
    get_video_duration_ms,
)
from core.agent.models import StepStatus
from ui.SubEditor import ms_to_time_str, time_str_to_ms


def test_tc_agent_01_combined_prompt_two_steps_plan():
    """FR-01: Prompt trong ảnh 'tạo timing 3 câu tiếp theo và gen sub 3 câu đó' sinh đủ 2 bước độc lập."""
    controller = AgentCopilotController()
    # Giả lập đang có 3 câu phụ đề trong Workspace, câu 3 kết thúc ở 00:00:24,908
    controller._active_segments = [
        {"id": 1, "start": "00:00:15,350", "end": "00:00:17,540", "text": "Câu 1", "translation": "Sub 1"},
        {"id": 2, "start": "00:00:19,720", "end": "00:00:20,660", "text": "Câu 2", "translation": "Sub 2"},
        {"id": 3, "start": "00:00:21,850", "end": "00:00:24,908", "text": "Câu 3", "translation": "Sub 3"},
    ]

    prompt = "tạo timing 3 câu tiếp theo và gen sub 3 câu đó"
    plan = controller._synthesize_plan(prompt)

    # 1. Phải sinh đủ 2 bước
    assert len(plan.steps) == 2, f"Kế hoạch phải có đúng 2 bước, nhưng có {len(plan.steps)}: {[s.tool_name for s in plan.steps]}"

    # 2. Bước 1: create_timing
    step1 = plan.steps[0]
    assert step1.tool_name == "create_timing"
    assert step1.tool_args["count"] == 3
    assert step1.tool_args.get("is_continue") is True
    # Offset phải khớp với mốc kết thúc của câu 3 (24.908s)
    assert abs(step1.tool_args.get("start_offset_s", 0) - 24.908) < 0.001
    assert "24,908" in step1.title or "24.908" in step1.title

    # 3. Bước 2: run_asr (phải trỏ tới các câu mới vừa tạo, KHÔNG được biến thành limit=3 rồi đè 3 câu đầu)
    step2 = plan.steps[1]
    assert step2.tool_name == "run_asr"
    assert step2.tool_args.get("target_newly_created") is True
    assert "limit" not in step2.tool_args, "Không được dùng limit=3 vì sẽ nhận diện nhầm vào 3 câu đầu!"
    assert "vừa tạo" in step2.title or "tiếp theo" in step2.title


def test_tc_agent_02_no_existing_segments_plan_starts_from_video_beginning():
    """FR-01: Nếu chưa có câu nào, kế hoạch phải nói rõ bắt đầu từ đầu video."""
    controller = AgentCopilotController()
    controller._active_segments = []

    prompt = "tạo timing 3 câu tiếp theo và gen sub 3 câu đó"
    plan = controller._synthesize_plan(prompt)

    assert len(plan.steps) == 2
    step1 = plan.steps[0]
    assert step1.tool_name == "create_timing"
    assert step1.tool_args.get("start_offset_s", 0.0) == 0.0
    assert "từ đầu video" in step1.title


def test_tc_agent_03_non_consecutive_ids_and_unordered_segments():
    """FR-02: Phụ đề cũ có ID không liên tiếp và chưa sắp theo thời gian."""
    controller = AgentCopilotController()
    # Danh sách chưa sắp theo thời gian, ID không liên tiếp (2, 7, 1)
    controller._active_segments = [
        {"id": 2, "start": "00:00:19,000", "end": "00:00:22,000", "text": "Câu ID 2"},
        {"id": 7, "start": "00:00:30,000", "end": "00:00:35,500", "text": "Câu ID 7 (max end)"},
        {"id": 1, "start": "00:00:05,000", "end": "00:00:08,000", "text": "Câu ID 1"},
    ]

    prompt = "tạo timing 3 câu tiếp theo và gen sub 3 câu đó"
    plan = controller._synthesize_plan(prompt)

    # Max end time phải là 35.5s (từ câu ID 7)
    step1 = plan.steps[0]
    assert abs(step1.tool_args.get("start_offset_s", 0) - 35.5) < 0.001

    # Chạy create_timing
    res = create_timing(
        count=3,
        start_offset_s=35.5,
        is_continue=True,
        existing_segments=controller._active_segments,
    )

    new_segs = res["new_segments"]
    assert len(new_segs) == 3
    # ID mới phải bắt đầu từ max_id (7) + 1 = 8, 9, 10
    new_ids = [s["id"] for s in new_segs]
    assert new_ids == [8, 9, 10]

    # Kiểm tra tổng 6 câu và các câu cũ không bị thay đổi
    all_segs = res["segments"]
    assert len(all_segs) == 6
    assert all_segs[0]["id"] == 2 and all_segs[0]["text"] == "Câu ID 2"
    assert all_segs[1]["id"] == 7 and all_segs[1]["text"] == "Câu ID 7 (max end)"
    assert all_segs[2]["id"] == 1 and all_segs[2]["text"] == "Câu ID 1"


def test_tc_agent_04_merge_timing_and_snapshot_rollback():
    """FR-02: Nối timing mới, bảo toàn phụ đề cũ và khôi phục snapshot khi Redo."""
    controller = AgentCopilotController()
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:04,000", "text": "Gốc 1", "translation": "Trans 1"},
        {"id": 2, "start": "00:00:05,000", "end": "00:00:08,000", "text": "Gốc 2", "translation": "Trans 2"},
    ]
    controller._active_segments = list(initial_segs)

    plan = controller._synthesize_plan("tạo timing 2 câu tiếp theo và gen sub 2 câu đó")
    controller.active_plan = plan
    controller._waiting_plan_approval = True

    # Duyệt plan và chạy bước 1 (create_timing)
    controller.approve_plan()
    assert controller.is_waiting_task_approval() is True

    # Danh sách lúc này phải có 4 câu (2 cũ + 2 mới)
    assert len(controller._active_segments) == 4
    assert controller._active_segments[0]["text"] == "Gốc 1"
    assert controller._active_segments[1]["text"] == "Gốc 2"
    assert controller._active_segments[2]["id"] == 3
    assert controller._active_segments[3]["id"] == 4

    # Bấm Redo (làm lại) -> phải khôi phục đúng 2 câu ban đầu
    controller.request_task_revision("Không ưng timing này, làm lại")
    assert len(controller._active_segments) == 2, "Rollback phải khôi phục đúng 2 câu ban đầu!"
    assert controller._active_segments[0]["text"] == "Gốc 1"
    assert controller._active_segments[1]["text"] == "Gốc 2"

    # Chạy lại bước 1 -> vẫn chỉ là 4 câu, tuyệt đối không bị trùng lặp thành 6 câu!
    controller.approve_plan()
    assert len(controller._active_segments) == 4
    assert [s["id"] for s in controller._active_segments] == [1, 2, 3, 4]


def test_tc_agent_05_gate2_user_timing_edit_preserved_in_asr():
    """FR-05: Người dùng sửa timing ở Cổng 2 trước khi duyệt, bước ASR phải dùng timing mới nhất."""
    controller = AgentCopilotController()
    controller._active_segments = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:04,000", "text": "Câu 1"},
    ]

    plan = controller._synthesize_plan("tạo timing 1 câu tiếp theo và gen sub 1 câu đó")
    controller.active_plan = plan
    controller._waiting_plan_approval = True
    controller.approve_plan()

    assert len(controller._active_segments) == 2
    new_seg = controller._active_segments[1]
    assert new_seg["id"] == 2

    # Người dùng sửa mốc thời gian của câu 2 ở Cổng 2 thành 00:00:10,000 -> 00:00:14,000
    controller._active_segments[1]["start"] = "00:00:10,000"
    controller._active_segments[1]["end"] = "00:00:14,000"

    # Duyệt bước 1 để chạy bước 2 (run_asr)
    controller.approve_next_step()

    # Kiểm tra bước 2 đã chạy xong
    assert len(controller._active_segments) == 2
    # Mốc thời gian đã sửa phải được giữ nguyên 100% sau khi ASR hoàn tất
    assert controller._active_segments[1]["start"] == "00:00:10,000"
    assert controller._active_segments[1]["end"] == "00:00:14,000"
    # Câu cũ 1 giữ nguyên
    assert controller._active_segments[0]["text"] == "Câu 1"


def test_tc_agent_06_asr_honest_error_when_model_missing():
    """FR-04: Thiếu model hoặc lỗi ASR phải được báo cáo trung thực, không điền chuỗi mẫu giả lập."""
    mock_service_no_model = MagicMock()
    mock_service_no_model.model = None
    mock_service_no_model.load_model.side_effect = RuntimeError("CUDA Out of Memory: No model files found")

    segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu cũ"},
        {"id": 2, "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu mới"},
    ]

    # Giả lập file video tồn tại để kích hoạt nhánh ASR thật
    res = run_asr(
        language="ja",
        indices=[2],
        segments=segs,
        video_path="D:\\Projects\\Video\\JMSZ38_02.wmv",
        whisper_service=mock_service_no_model,
    )

    # Phải trả về trạng thái error rõ ràng
    assert res["status"] == "error"
    assert "Chưa nạp mô hình" in res["error"] or "model" in res["error"].lower()
    # Không được điền chuỗi mẫu "Nội dung nhận diện câu #2 (Whisper)"
    assert segs[1]["text"] == "Câu mới"


def test_tc_agent_07_reasoning_engine_no_hardcoded_intro():
    """FR-05: Loại bỏ hoàn toàn văn bản viết sẵn '17.5s nhạc intro', báo cáo trung thực số liệu."""
    from core.agent.reasoning_engine import DynamicReasoningEngine
    from core.agent.models import AgentStep

    engine = DynamicReasoningEngine()

    step = AgentStep(
        id="step_1",
        title="Khởi tạo Timing 3 câu tiếp theo",
        tool_name="create_timing",
        tool_args={"count": 3, "is_continue": True, "start_offset_s": 24.908},
    )

    result = {
        "segments": [
            {"id": 1, "start": "00:00:15,350", "end": "00:00:17,540"},
            {"id": 2, "start": "00:00:19,720", "end": "00:00:20,660"},
            {"id": 3, "start": "00:00:21,850", "end": "00:00:24,908"},
            {"id": 4, "start": "00:00:26,100", "end": "00:00:29,500"},
            {"id": 5, "start": "00:00:32,240", "end": "00:00:33,960"},
            {"id": 6, "start": "00:00:33,960", "end": "00:00:36,610"},
        ],
        "new_segments": [
            {"id": 4, "start": "00:00:26,100", "end": "00:00:29,500"},
            {"id": 5, "start": "00:00:32,240", "end": "00:00:33,960"},
            {"id": 6, "start": "00:00:33,960", "end": "00:00:36,610"},
        ],
        "start_offset_s": 24.908,
        "status": "ok",
    }

    report = engine.synthesize_completion(step=step, result=result)

    # Tuyệt đối không chứa chuỗi văn bản bịa đặt "17.5s nhạc intro"
    assert "17.5s" not in report, "Báo cáo không được chứa số liệu 17.5s bịa đặt!"
    assert "intro không lời" not in report
    # Phải nêu đúng số câu thêm (3 câu tiếp theo) và khoảng thời gian thực tế
    assert "3 phân đoạn" in report or "3 câu" in report
    assert "00:00:26,100" in report
    assert "00:00:36,610" in report


def test_tc_agent_08_real_video_jmsz_continuation():
    """FR-03 & FR-06: Chạy kiểm định thực tế trên video thật JMSZ38_02.wmv từ mốc 24.908s."""
    real_video = r"D:\Projects\Video\JMSZ38_02.wmv"
    if not os.path.exists(real_video):
        pytest.skip("Bỏ qua test video thật nếu không tìm thấy JMSZ38_02.wmv")

    # Quét 3 đoạn thoại tiếp theo sau mốc 24.908s
    segs = generate_vad_timing_segments(
        count=3,
        video_path=real_video,
        start_offset_s=24.908,
    )

    assert len(segs) >= 1, "VAD phải tìm thấy ít nhất 1 đoạn thoại sau mốc 24.908s"

    # Mọi phân đoạn tìm được phải có mốc bắt đầu >= 24.908s (sau khi trừ dung sai nhỏ của seek frame trimming)
    first_st = time_str_to_ms(segs[0]["start"])
    assert first_st >= 24000, f"Đoạn đầu tiên ({segs[0]['start']}) phải nằm sau mốc tiếp tục!"
