from copy import deepcopy

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import run_asr
from core.agent.models import AgentStep, StepStatus
from ui.components.agent_report_inspector_widget import AgentReportInspectorWidget


def test_asr_range_25_to_27_updates_only_target_segments(qtbot):
    controller = AgentCopilotController()
    original = [
        {"id": f"uuid-{i}", "text": f"Original {i}", "start": i * 1000, "end": i * 1000 + 500}
        for i in range(1, 25)
    ] + [
        {"id": i, "text": f"Dòng phụ đề #{i}", "start": i * 1000, "end": i * 1000 + 500}
        for i in range(25, 28)
    ]
    controller._active_segments = deepcopy(original)
    observed = {}

    def fake_asr(**kwargs):
        observed["indices"] = kwargs["indices"]
        segments = deepcopy(kwargs["segments"])
        for i in range(24, 27):
            segments[i]["text"] = f"Recognized {i + 1}"
        return {"status": "ok", "segments": segments, "indices": kwargs["indices"], "count": 3}

    controller.tool_registry._tools["run_asr"] = fake_asr
    plan = controller.submit_prompt("gen sub từ câu 25 đến câu 27")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.COMPLETED
    assert observed["indices"] == [25, 26, 27]
    assert controller._active_segments[:24] == original[:24]
    assert [s["text"] for s in controller._active_segments[24:]] == [
        "Recognized 25", "Recognized 26", "Recognized 27"]


def test_asr_report_shows_target_rows_and_keeps_full_workspace(qtbot):
    inspector = AgentReportInspectorWidget()
    qtbot.addWidget(inspector)
    card = inspector.inspection_card
    segments = [
        {"id": f"uuid-{i}" if i < 25 else i, "text": f"Line {i}",
         "start": i * 1000, "end": i * 1000 + 500}
        for i in range(1, 28)
    ]

    inspector.update_report(0, AgentStep(id="1", title="ASR", tool_name="run_asr"),
                            {"segments": segments, "indices": [25, 26, 27], "count": 3})

    assert [row.index for row in card._rows] == [25, 26, 27]
    assert "00:00:25,000" in card._rows[0].lbl_info.text()
    assert len(card.get_current_segments()) == 27
    card._rows[0].editor.setText("Corrected 25")
    assert card.get_current_segments()[24]["text"] == "Corrected 25"
    assert card.get_current_segments()[0]["text"] == "Line 1"


def test_missing_requested_rows_fail_without_running_asr():
    controller = AgentCopilotController()
    controller._active_segments = [
        {"id": f"uuid-{i}", "text": f"Original {i}", "start": i * 1000, "end": i * 1000 + 500}
        for i in range(1, 25)
    ]
    original = deepcopy(controller._active_segments)
    called = []
    controller.tool_registry._tools["run_asr"] = lambda **kwargs: called.append(kwargs)

    plan = controller.submit_prompt("gen sub từ câu 25 đến câu 27")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.FAILED
    assert "25" in plan.steps[0].error_message
    assert controller._active_segments == original
    assert not called


def test_separate_prompt_for_newly_created_segments_does_not_scan_first_three():
    controller = AgentCopilotController()
    controller._active_segments = [
        {"id": f"uuid-{i}", "text": f"Original {i}", "start": i * 1000, "end": i * 1000 + 500}
        for i in range(1, 25)
    ] + [
        {"id": i, "text": f"Dòng phụ đề #{i}", "start": i * 1000, "end": i * 1000 + 500}
        for i in range(25, 28)
    ]
    controller._last_created_indices = [25, 26, 27]
    observed = {}

    def fake_asr(**kwargs):
        observed["indices"] = kwargs["indices"]
        return {"status": "ok", "segments": kwargs["segments"], "indices": kwargs["indices"], "count": 3}

    controller.tool_registry._tools["run_asr"] = fake_asr
    plan = controller.submit_prompt("gen sub 3 câu vừa tạo")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.COMPLETED
    assert observed["indices"] == [25, 26, 27]


def test_newly_created_prompt_without_history_fails_instead_of_scanning_all():
    controller = AgentCopilotController()
    controller._active_segments = [{"id": i, "text": f"Original {i}"} for i in range(1, 4)]
    called = []
    controller.tool_registry._tools["run_asr"] = lambda **kwargs: called.append(kwargs)

    plan = controller.submit_prompt("gen sub 3 câu vừa tạo")
    controller.approve_plan()

    assert plan.steps[0].status == StepStatus.FAILED
    assert "vừa tạo" in plan.steps[0].error_message
    assert not called


def test_unknown_explicit_ids_are_not_successful_zero_count(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"test")
    original = [{"id": "uuid-1", "text": "Original", "start": 1000, "end": 1500}]

    result = run_asr(indices=[25], segments=original, video_path=str(video))

    assert result["status"] == "error"
    assert result["count"] == 0
    assert result["segments"] == original
