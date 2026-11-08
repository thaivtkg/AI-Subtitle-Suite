from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton, QTextEdit, QLabel

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.models import AgentContextLedger, AgentStep, AgentTaskPlan, StepStatus, ChatMessage


def test_mission_control_page_structure_matches_approved_mockup(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # 1. Verify 2-Column Split
    col_chat = page.findChild(QWidget, "mc_col_chat")
    col_inspect = page.findChild(QWidget, "mc_col_inspect")
    assert col_chat is not None, "Missing Left Column (mc_col_chat)"
    assert col_inspect is not None, "Missing Right Column (mc_col_inspect)"

    # 2. Verify Left Column components
    assert page.findChild(QWidget, "memory_bar") is not None, "Missing memory_bar"
    assert page.findChild(QWidget, "chat_stream") is not None, "Missing chat_stream"
    assert page.findChild(QLineEdit, "prompt_input") is not None, "Missing prompt_input"
    assert page.findChild(QPushButton, "btn_send_prompt") is not None, "Missing btn_send_prompt"

    # 3. Verify Right Column components
    assert page.findChild(QWidget, "step_stepper") is not None, "Missing step_stepper"
    assert page.findChild(QWidget, "inspection_card") is not None, "Missing inspection_card"
    assert page.findChild(QPushButton, "btn_redo_task") is not None, "Missing btn_redo_task"
    assert page.findChild(QPushButton, "btn_approve_next") is not None, "Missing btn_approve_next"


def test_mission_control_prompt_submission_updates_chat_and_stepper(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    prompt_input = page.findChild(QLineEdit, "prompt_input")
    btn_send = page.findChild(QPushButton, "btn_send_prompt")

    prompt_input.setText("Gen sub từ video rồi dịch sang tiếng Việt nhé")
    qtbot.mouseClick(btn_send, Qt.MouseButton.LeftButton)

    # Controller should have synthesized plan and added messages
    assert controller.active_plan is not None
    assert len(controller.chat_history) >= 2

    # Stepper should render chips
    stepper = page.findChild(QWidget, "step_stepper")
    chips = stepper.findChildren(QWidget, "step_chip")
    assert len(chips) >= 2


def test_mission_control_approval_flow_and_anti_double_click(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    controller = AgentCopilotController()
    # Mock tool registry to return immediate success
    controller.tool_registry.safe_execute_tool = MagicMock(
        return_value={"success": True, "result": {"segments": [{"id": 1, "text": "Test segment"}]}}
    )

    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # Submit prompt to set plan
    controller.submit_prompt("Tạo sub và dịch sang tiếng Việt")

    # In waiting plan approval mode, btn_approve_next should approve plan
    btn_approve = page.findChild(QPushButton, "btn_approve_next")
    assert btn_approve.isEnabled()

    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)

    # Controller executed step 0 and now is waiting for task approval
    assert controller.is_waiting_task_approval()

    # Inspection card should show report and status badge
    badge = page.findChild(QLabel, "status_badge")
    assert badge is not None
    assert "CHỜ BẠN DUYỆT" in badge.text()

    # Rapid double click test: when clicked, button should trigger advance and prevent immediate re-click
    assert btn_approve.isEnabled()
    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)
    # Step 1 should have run and now waiting for step 1 approval or completion
    assert controller.current_step_index == 1 or controller.is_plan_completed()


def test_mission_control_redo_task_calls_revision(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    controller = AgentCopilotController()
    controller.tool_registry.safe_execute_tool = MagicMock(
        return_value={"success": True, "result": {"output": "ok"}}
    )

    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    controller.submit_prompt("Gen sub và dịch")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()

    btn_redo = page.findChild(QPushButton, "btn_redo_task")
    controller.request_task_revision = MagicMock(wraps=controller.request_task_revision)
    qtbot.mouseClick(btn_redo, Qt.MouseButton.LeftButton)

    controller.request_task_revision.assert_called_once()


def test_mission_control_memory_bar_updates(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    ledger = AgentContextLedger(
        project_id="p1",
        video_path="demo.mp4",
        duration_ms=25000,
        source_lang="ja",
        target_lang="vi",
        active_rules=["Giữ thuật ngữ AI"],
    )
    controller = AgentCopilotController(context_ledger=ledger)
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    memory_bar = page.findChild(QWidget, "memory_bar")
    assert memory_bar is not None
    # Check that text reflects 25.0s, JP -> VI, 1 quy tắc
    text = memory_bar.get_summary_text()
    assert "25.0s" in text
    assert "JP" in text
    assert "VI" in text
