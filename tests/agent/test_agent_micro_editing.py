import pytest
from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import AgentToolRegistry, create_timing, adjust_subtitle_bounds, shift_subtitles
from core.agent.models import StepStatus


def test_synthesize_plan_gen_sub_n_segments():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("gen sub 5 câu đầu")
    
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "run_asr"
    assert "5 câu đầu" in step.title
    assert step.tool_args.get("limit") == 5


def test_synthesize_plan_create_timing():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("tạo timing 5 câu đầu")
    
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "create_timing"
    assert "5 câu đầu" in step.title
    assert step.tool_args.get("count") == 5


def test_synthesize_plan_adjust_duration_bounds():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("điều chỉnh thời lượng mỗi câu sub tăng 100ms ở mốc cuối và giảm 100ms ở mốc đầu")
    
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "adjust_subtitle_bounds"
    assert step.tool_args.get("delta_start_ms") == -100
    assert step.tool_args.get("delta_end_ms") == 100


def test_synthesize_plan_shift_subtitles():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("đưa cả đoạn sub ... lên 1s")
    
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "shift_subtitles"
    assert step.tool_args.get("offset_ms") == 1000

    plan_back = controller._synthesize_plan("lùi cả đoạn sub 500ms")
    assert len(plan_back.steps) == 1
    assert plan_back.steps[0].tool_args.get("offset_ms") == -500


def test_tool_create_timing_execution():
    res = create_timing(count=5, duration_per_block_ms=2500, gap_ms=500)
    assert res["status"] == "ok"
    assert res["count"] == 5
    segments = res["segments"]
    assert len(segments) == 5
    assert segments[0]["start"] == "00:00:00,500"
    assert segments[0]["end"] == "00:00:03,000"
    assert segments[1]["start"] == "00:00:03,500"


def test_tool_adjust_subtitle_bounds_execution():
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Segment 1"},
        {"id": 2, "start": "00:00:04,000", "end": "00:00:06,000", "text": "Segment 2"},
    ]
    res = adjust_subtitle_bounds(delta_start_ms=-100, delta_end_ms=100, segments=initial_segs)
    assert res["status"] == "ok"
    adj = res["segments"]
    # 1000 - 100 = 900ms -> 00:00:00,900
    assert adj[0]["start"] == "00:00:00,900"
    # 3000 + 100 = 3100ms -> 00:00:03,100
    assert adj[0]["end"] == "00:00:03,100"


def test_tool_shift_subtitles_execution():
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Segment 1"},
    ]
    res = shift_subtitles(offset_ms=1000, segments=initial_segs)
    assert res["status"] == "ok"
    shifted = res["segments"]
    # 1000 + 1000 = 2000ms -> 00:00:02,000
    assert shifted[0]["start"] == "00:00:02,000"
    # 3000 + 1000 = 4000ms -> 00:00:04,000
    assert shifted[0]["end"] == "00:00:04,000"


def test_controller_hitl_lifecycle_with_micro_editing():
    controller = AgentCopilotController()
    
    # 1. Tạo timing 5 câu
    controller.submit_prompt("tạo timing 5 câu đầu")
    assert controller.is_waiting_plan_approval()
    controller.approve_plan()
    assert controller.is_waiting_task_approval()
    assert len(controller._active_segments) == 5
    assert controller._last_step_result["count"] == 5

    # 2. Điều chỉnh thời lượng mỗi câu tăng 100ms ở mốc cuối và giảm 100ms ở mốc đầu
    controller.submit_prompt("điều chỉnh thời lượng mỗi câu sub tăng 100ms ở mốc cuối và giảm 100ms ở mốc đầu")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()
    assert len(controller._active_segments) == 5
    # Verify bounds adjusted
    assert controller._active_segments[0]["start"] == "00:00:00,400"
    assert controller._active_segments[0]["end"] == "00:00:03,600"

    # 3. Đưa cả đoạn sub lên 1s
    controller.submit_prompt("đưa cả đoạn sub ... lên 1s")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()
    # 400 + 1000 = 1400ms -> 00:00:01,400
    assert controller._active_segments[0]["start"] == "00:00:01,400"
    # 3600 + 1000 = 4600ms -> 00:00:04,600
    assert controller._active_segments[0]["end"] == "00:00:04,600"


def test_tool_adjust_subtitle_bounds_overlap_auto_resolve():
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Segment 1"},
        {"id": 2, "start": "00:00:03,200", "end": "00:00:05,000", "text": "Segment 2"},
    ]
    # Extending end by 500ms (3000 -> 3500) will overlap with Seg 2 (start 3200)
    res = adjust_subtitle_bounds(delta_start_ms=0, delta_end_ms=500, segments=initial_segs)
    assert res["status"] == "ok"
    adj = res["segments"]
    # Seg 1 end trimmed to next_start 3200ms -> 00:00:03,200
    assert adj[0]["end"] == "00:00:03,200"
    assert adj[1]["start"] == "00:00:03,200"


def test_tool_shift_subtitles_non_negative_clamp_and_independent_subsequent_segments():
    initial_segs = [
        {"id": 1, "start": "00:00:00,300", "end": "00:00:02,000", "text": "Segment 1"},
        {"id": 2, "start": "00:00:03,000", "end": "00:00:05,000", "text": "Segment 2"},
    ]
    # Shift backwards -500ms (Rigid Translation Invariant):
    # Seg 1: start 300 - 500 clamped to 0ms; dur = 1700ms -> end = 0 + 1700 = 1700ms
    # Seg 2: start 3000 - 500 = 2500ms; end 5000 - 500 = 4500ms
    res = shift_subtitles(offset_ms=-500, segments=initial_segs)
    assert res["status"] == "ok"
    shifted = res["segments"]
    assert shifted[0]["start"] == "00:00:00,000"
    assert shifted[0]["end"] == "00:00:01,700"
    assert shifted[1]["start"] == "00:00:02,500"
    assert shifted[1]["end"] == "00:00:04,500"
