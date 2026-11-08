import pytest
from core.agent.models import (
    StepStatus,
    AgentStep,
    AgentTaskPlan,
    ChatMessage,
    AgentContextLedger
)

def test_step_status_enum():
    assert StepStatus.PENDING == "PENDING"
    assert StepStatus.RUNNING == "RUNNING"
    assert StepStatus.WAITING_APPROVAL == "WAITING_APPROVAL"
    assert StepStatus.COMPLETED == "COMPLETED"
    assert StepStatus.FAILED == "FAILED"

def test_agent_step_and_plan():
    step1 = AgentStep(
        id="step_1",
        title="ASR Gen Sub",
        tool_name="run_asr",
        tool_args={"language": "ja"},
        status=StepStatus.PENDING
    )
    step2 = AgentStep(
        id="step_2",
        title="Dịch CAT Studio",
        tool_name="translate_subtitles",
        tool_args={"target_lang": "vi"},
        status=StepStatus.PENDING
    )
    plan = AgentTaskPlan(prompt="Gen sub and translate", steps=[step1, step2])
    
    assert plan.current_step().title == "ASR Gen Sub"
    assert plan.current_step_index == 0
    assert len(plan.steps) == 2
    
    # Serialization
    data = plan.to_dict()
    restored = AgentTaskPlan.from_dict(data)
    assert restored.prompt == "Gen sub and translate"
    assert len(restored.steps) == 2
    assert restored.steps[0].tool_name == "run_asr"

def test_chat_message():
    msg = ChatMessage(role="user", content="Tạo sub giúp tôi", timestamp=1794000000.0)
    assert msg.role == "user"
    d = msg.to_dict()
    restored = ChatMessage.from_dict(d)
    assert restored.content == "Tạo sub giúp tôi"

def test_agent_context_ledger():
    ledger = AgentContextLedger(
        project_id="proj_123",
        video_path="sample.mp4",
        duration_ms=25000,
        source_lang="ja",
        target_lang="vi"
    )
    ledger.lock_rule("Giữ nguyên thuật ngữ AI")
    ledger.set_style_setting("font_name", "Arial")
    ledger.set_style_setting("primary_color", "#FFFF00")
    
    assert "Giữ nguyên thuật ngữ AI" in ledger.active_rules
    assert ledger.style_settings["font_name"] == "Arial"
    assert ledger.active_rule_count() == 1
    
    d = ledger.to_dict()
    restored = AgentContextLedger.from_dict(d)
    assert restored.project_id == "proj_123"
    assert restored.duration_ms == 25000
    assert "Giữ nguyên thuật ngữ AI" in restored.active_rules
    assert restored.style_settings["primary_color"] == "#FFFF00"
