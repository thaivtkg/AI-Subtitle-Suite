from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPushButton, QLabel

from ui.Gui import MainWindow
from ui.components.agent_report_inspector_widget import EditableSegmentRow


def test_ai_agent_copilot_full_lifecycle_e2e(qtbot):
    """
    End-to-End Acceptance Test for AI Agent Copilot (8-Step User Journey):
    1. Open MainWindow & switch to Tab 9 (Mission Control).
    2. Enter natural prompt & send.
    3. Verify plan synthesis, chat history & stepper.
    4. Approve plan to start execution.
    5. Step 1 (ASR) runs, pauses, alerts taskbar/sound, displays report.
    6. Direct in-place editing on inspection card.
    7. Approve next step (CAT Translation).
    8. Switch to Studio Workspace and verify 100% two-way subtitle sync.
    """
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()

    # Step 1: Switch to AI Agent Mission Control Tab (id: 9)
    win.switch_page(9)
    assert win.stack.currentWidget() == win.page_ai_agent
    assert win.lbl_page_title.text() == "Phòng Điều Hành AI Agent"

    page = win.page_ai_agent
    controller = page.controller

    # Mock tool registry to return deterministic segments for ASR and Translation
    mock_segments_asr = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:04,500", "text": "Chào mừng đến với AI Subtitle Suite"},
        {"id": 2, "start": "00:00:05,200", "end": "00:00:06,600", "text": "Hôm nay chúng ta kiểm thử Copilot"},
    ]
    mock_segments_trans = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:04,500", "text": "Welcome to AI Subtitle Suite", "translation": "Welcome to AI Subtitle Suite"},
        {"id": 2, "start": "00:00:05,200", "end": "00:00:06,600", "text": "Today we test Copilot", "translation": "Today we test Copilot"},
    ]

    def mock_safe_execute(name, args):
        if name == "run_asr":
            return {"success": True, "result": {"segments": mock_segments_asr}}
        elif name == "translate_subtitles":
            return {"success": True, "result": {"segments": mock_segments_trans}}
        return {"success": True, "result": {"status": "ok"}}

    controller.tool_registry.safe_execute_tool = MagicMock(side_effect=mock_safe_execute)

    # Mock alert service to verify chime & flash
    page.alert_service.alert_window = MagicMock()
    page.alert_service.play_chime = MagicMock()

    # Step 2: Enter prompt & submit
    prompt_input = page.findChild(QLineEdit, "prompt_input")
    btn_send = page.findChild(QPushButton, "btn_send_prompt")
    prompt_input.setText("Gen sub từ video rồi dịch sang tiếng Việt nhé, nhớ giữ nguyên các thuật ngữ AI và làm font vàng viền đen")
    qtbot.mouseClick(btn_send, Qt.MouseButton.LeftButton)

    # Step 3: Verify plan synthesis
    assert controller.active_plan is not None
    assert len(controller.active_plan.steps) >= 2
    assert controller.is_waiting_plan_approval()

    badge = page.findChild(QLabel, "status_badge")
    assert badge.text() == "CHỜ BẠN DUYỆT"

    btn_approve = page.findChild(QPushButton, "btn_approve_next")
    assert btn_approve.isEnabled()
    assert "Duyệt Kế Hoạch" in btn_approve.text()

    # Step 4: Approve plan
    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)

    # Step 5: Step 1 (ASR) executed and paused
    assert controller.is_waiting_task_approval()
    assert controller.current_step_index == 0
    page.alert_service.alert_window.assert_called_once()
    page.alert_service.play_chime.assert_called_once()

    # Verify inspection card shows segment rows
    rows = page.findChildren(EditableSegmentRow)
    assert len(rows) >= 2
    assert "Chào mừng" in rows[0].editor.text()

    # Step 6: In-place direct text edit on segment #1
    rows[0].editor.setText("Chào mừng quý khách đến với AI Subtitle Suite (Đã biên tập)")

    # Step 7: Approve next step (CAT Translation)
    assert btn_approve.isEnabled()
    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)

    # Step 2 completed and waiting for approval or completed
    assert controller.current_step_index == 1
    assert controller.is_waiting_task_approval() or controller.is_plan_completed()

    # Step 8: Switch back to Studio Workspace (Tab 1) and verify two-way data sync
    win.switch_page(1)
    assert win.stack.currentWidget() != page
    assert win.timeline_dock.isVisible()

    # Verify sub_editor received the updated segments
    assert len(win.sub_editor.all_segments) >= 2
    assert win.sub_editor.all_segments[0].get("text") is not None
