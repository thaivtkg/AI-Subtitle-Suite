import pytest
from unittest.mock import MagicMock
from core.agent.agent_tool_registry import AgentToolRegistry

def test_tool_registry_registration_and_execution():
    registry = AgentToolRegistry()
    mock_asr = MagicMock(return_value={"status": "success", "segments_count": 142})
    registry.register_tool("run_asr", mock_asr, description="Run ASR")
    
    tools = registry.get_tools_schema()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "run_asr"
    
    res = registry.execute_tool("run_asr", {"language": "ja", "model": "base"})
    mock_asr.assert_called_once_with(language="ja", model="base")
    assert res["status"] == "success"
    assert res["segments_count"] == 142

def test_tool_registry_execution_nonexistent_tool():
    registry = AgentToolRegistry()
    with pytest.raises(ValueError, match="Tool 'unknown' is not registered"):
        registry.execute_tool("unknown", {})

def test_tool_registry_handles_tool_exception_cleanly():
    registry = AgentToolRegistry()
    mock_bad_tool = MagicMock(side_effect=RuntimeError("Video file missing"))
    registry.register_tool("bad_tool", mock_bad_tool)
    
    res = registry.safe_execute_tool("bad_tool", {})
    assert res["success"] is False
    assert "Video file missing" in res["error"]
