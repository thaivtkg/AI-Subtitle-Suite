import pytest
from unittest.mock import MagicMock
from core.agent.models import AgentStep, AgentTaskPlan, StepStatus, AgentContextLedger
from core.agent.agent_copilot_controller import AgentCopilotController

def test_copilot_controller_requires_approval_between_steps():
    mock_tools = MagicMock()
    mock_tools.safe_execute_tool = MagicMock(return_value={"success": True, "result": {"count": 100}})
    
    mock_llm = MagicMock()
    mock_llm.generate_with_fallback = MagicMock(return_value={
        "role": "assistant",
        "content": "Kế hoạch đã lập.",
        "tool_calls": []
    })
    
    mock_snapshot = MagicMock()
    mock_snapshot.take_snapshot = MagicMock(return_value="snap_123")
    
    ledger = AgentContextLedger(project_id="test_p")
    
    ctrl = AgentCopilotController(
        tool_registry=mock_tools,
        llm_client=mock_llm,
        snapshot_manager=mock_snapshot,
        context_ledger=ledger
    )
    
    # 1. Custom mock plan builder
    step1 = AgentStep(id="s1", title="ASR", tool_name="run_asr", tool_args={"lang": "ja"})
    step2 = AgentStep(id="s2", title="Translate", tool_name="translate_subtitles", tool_args={"target": "vi"})
    custom_plan = AgentTaskPlan(prompt="Gen and translate", steps=[step1, step2])
    ctrl._synthesize_plan = MagicMock(return_value=custom_plan)
    
    # 2. Submit prompt
    ctrl.submit_prompt("Tạo phụ đề video này")
    assert ctrl.is_waiting_plan_approval() is True
    assert ctrl.current_step_index == 0
    assert mock_tools.safe_execute_tool.call_count == 0
    
    # 3. Approve plan -> Runs Step 0 and PAUSES
    ctrl.approve_plan()
    assert mock_snapshot.take_snapshot.call_count == 1
    assert mock_tools.safe_execute_tool.call_count == 1
    assert ctrl.is_waiting_task_approval() is True
    assert ctrl.current_step_index == 0
    
    # Verify Step 1 did NOT run automatically
    assert mock_tools.safe_execute_tool.call_count == 1
    
    # 4. Approve next step -> Runs Step 1 and PAUSES for Step 1 review
    ctrl.approve_next_step()
    assert mock_snapshot.take_snapshot.call_count == 2
    assert mock_tools.safe_execute_tool.call_count == 2
    assert ctrl.current_step_index == 1
    assert ctrl.is_waiting_task_approval() is True

    # 5. Approve Step 1 completion -> Plan finishes
    ctrl.approve_next_step()
    assert ctrl.is_plan_completed() is True

def test_copilot_controller_redo_task_rolls_back():
    mock_tools = MagicMock()
    mock_tools.safe_execute_tool = MagicMock(return_value={"success": True, "result": {"count": 100}})
    mock_snapshot = MagicMock()
    mock_snapshot.take_snapshot = MagicMock(return_value="snap_pre_task")
    mock_snapshot.restore_snapshot = MagicMock(return_value=True)
    
    ctrl = AgentCopilotController(
        tool_registry=mock_tools,
        llm_client=MagicMock(),
        snapshot_manager=mock_snapshot
    )
    
    step1 = AgentStep(id="s1", title="ASR", tool_name="run_asr")
    ctrl.active_plan = AgentTaskPlan(prompt="Test", steps=[step1])
    ctrl.approve_plan()
    
    # Now in waiting approval
    assert ctrl.is_waiting_task_approval() is True
    
    # Redo task
    ctrl.request_task_revision("Dịch lại")
    mock_snapshot.restore_snapshot.assert_called_with("snap_pre_task")
