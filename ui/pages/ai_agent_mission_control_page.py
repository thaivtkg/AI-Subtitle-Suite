import logging
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QSplitter,
    QSizePolicy,
)

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.models import AgentTaskPlan, AgentStep, ChatMessage
from ui.components.agent_chat_stream_widget import AgentChatStreamWidget
from ui.components.agent_report_inspector_widget import AgentReportInspectorWidget
from ui.notifications.task_alert_service import TaskAlertService

logger = logging.getLogger(__name__)


class AIAgentMissionControlPage(QWidget):
    """
    Dedicated Tab C: AI Agent Mission Control Page.
    2-Column Parallel Layout matching 100% approved mockup (layout1-memory-chat.html).
    Left Col: Persistent Project Memory Bar + Chat Stream + Prompt Input.
    Right Col: Task Stepper + Inspection/Edit Sheet + Action Approval Bar.
    """

    def __init__(
        self,
        controller: Optional[AgentCopilotController] = None,
        alert_service: Optional[TaskAlertService] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("ai_agent_mission_control_page")
        self.controller = controller or AgentCopilotController()
        self.alert_service = alert_service or TaskAlertService(self)

        self._init_ui()
        self._wire_signals()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget#ai_agent_mission_control_page {
                background: #090d16;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 2-Column Splitter (Ratio 1 : 1.2)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background: transparent;
                width: 6px;
            }
        """)

        # Left Column: Chat & Memory
        self.col_chat = AgentChatStreamWidget(self.controller.context_ledger, self)
        self.splitter.addWidget(self.col_chat)

        # Right Column: Stepper & Inspection & Action
        self.col_inspect = AgentReportInspectorWidget(self)
        self.splitter.addWidget(self.col_inspect)

        # Set ratio 1 : 1.2
        self.splitter.setStretchFactor(0, 10)
        self.splitter.setStretchFactor(1, 12)

        layout.addWidget(self.splitter)

    def _wire_signals(self):
        # UI -> Controller
        self.col_chat.prompt_submitted.connect(self._on_prompt_submitted)
        self.col_inspect.approve_clicked.connect(self._on_approve_clicked)
        self.col_inspect.redo_clicked.connect(self._on_redo_clicked)

        # Controller -> UI
        self.controller.chat_message_added.connect(self._on_chat_message_added)
        self.controller.plan_ready.connect(self._on_plan_ready)
        self.controller.step_started.connect(self._on_step_started)
        self.controller.step_completed.connect(self._on_step_completed)
        self.controller.step_failed.connect(self._on_step_failed)
        self.controller.plan_completed.connect(self._on_plan_completed)

        # Controller -> Notification
        if self.alert_service:
            self.controller.notification_requested.connect(
                self.alert_service.on_notification_requested
            )

    @Slot(str)
    def _on_prompt_submitted(self, prompt: str):
        import copy
        if hasattr(self, "col_inspect") and self.col_inspect:
            edited = self.col_inspect.get_current_segments()
            if edited:
                self.controller._active_segments = copy.deepcopy(edited)
                win_getter = getattr(self, "window", None)
                parent_win = win_getter() if callable(win_getter) else None
                if parent_win and hasattr(parent_win, "_sync_from_ai_agent_page"):
                    parent_win._sync_from_ai_agent_page()
        self.controller.submit_prompt(prompt)

    @Slot(object)
    def _on_chat_message_added(self, message: ChatMessage):
        self.col_chat.add_message(message)

    @Slot(object)
    def _on_plan_ready(self, plan: AgentTaskPlan):
        self.col_inspect.step_stepper.set_plan(plan)
        # CỔNG 1: Render PlanBriefingCardWidget (Strict Gate Isolation - KHÔNG rò rỉ dữ liệu kết quả)
        self.col_inspect.render_plan_briefing(plan)

    @Slot(int, object)
    def _on_step_started(self, step_idx: int, step: AgentStep):
        self.col_inspect.step_stepper.set_plan(self.controller.active_plan)
        self.col_inspect.set_badge_status("running")
        self.col_inspect.btn_approve_next.setEnabled(False)

    @Slot(int, object, dict)
    def _on_step_completed(self, step_idx: int, step: AgentStep, result: dict):
        self.col_inspect.step_stepper.set_plan(self.controller.active_plan)
        self.col_inspect.update_report(step_idx, step, result)
        self.col_inspect.btn_approve_next.setText("✔ Duyệt & Chạy bước tiếp")
        self.col_inspect.btn_approve_next.setEnabled(True)

    @Slot(int, object, str)
    def _on_step_failed(self, step_idx: int, step: AgentStep, error: str):
        self.col_inspect.step_stepper.set_plan(self.controller.active_plan)
        self.col_inspect.show_error(step_idx, step, error)

    @Slot(object)
    def _on_plan_completed(self, plan: AgentTaskPlan):
        self.col_inspect.step_stepper.set_plan(plan)
        self.col_inspect.set_badge_status("done")
        self.col_inspect.lbl_report_title.setText("🎉 TOÀN BỘ KẾ HOẠCH ĐÃ HOÀN TẤT")
        self.col_inspect.btn_approve_next.setEnabled(False)

    @Slot()
    def _on_approve_clicked(self):
        from core.agent.models import StepStatus
        if self.controller.is_waiting_plan_approval():
            preserved = self.col_inspect.get_current_segments()
            self.controller.approve_plan(preserved_segments=preserved if preserved else None)
            return

        curr_step = self.controller.active_plan.current_step() if self.controller.active_plan else None
        if curr_step and curr_step.status == StepStatus.PENDING:
            if hasattr(self.col_inspect.inspection_card, "_rows") and self.col_inspect.inspection_card._rows:
                preserved = self.col_inspect.get_current_segments()
                if preserved:
                    self.controller._active_segments = preserved
            self.controller.approve_next_step()
            return

        if self.controller.is_waiting_task_approval():
            preserved = self.col_inspect.get_current_segments()
            if preserved:
                self.controller._active_segments = preserved
            self.controller.approve_next_step()

    @Slot()
    def _on_redo_clicked(self):
        import copy
        self.controller.request_task_revision("Yêu cầu làm lại task này")
        self.col_inspect.step_stepper.set_plan(self.controller.active_plan)
        curr_step = self.controller.active_plan.current_step() if self.controller.active_plan else None
        reverted_segs = copy.deepcopy(self.controller._active_segments)
        self.col_inspect.inspection_card.current_segments = reverted_segs
        if curr_step:
            self.col_inspect.update_report(
                self.controller.current_step_index,
                curr_step,
                {"segments": reverted_segs, "status": "reverted"},
            )
        self.col_inspect.btn_approve_next.setText("✔ Chạy lại Task này")
        self.col_inspect.btn_approve_next.setEnabled(True)

    def get_current_segments(self):
        segs = self.col_inspect.get_current_segments()
        if not segs and hasattr(self.controller, "_active_segments") and self.controller._active_segments:
            return self.controller._active_segments
        return segs
