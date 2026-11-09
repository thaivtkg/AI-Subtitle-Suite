from typing import Optional, List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame

from core.agent.models import AgentTaskPlan, AgentStep, StepStatus


class StepChip(QLabel):
    """Visual chip for a single step in the stepper."""

    def __init__(self, step_num: int, step: AgentStep, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("step_chip")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_status(step_num, step)

    def update_status(self, step_num: int, step: AgentStep):
        if step.status == StepStatus.COMPLETED:
            self.setText(f"✔ {step_num}. {step.title}")
            self.setStyleSheet("""
                QLabel#step_chip {
                    background: rgba(34, 197, 94, 0.2);
                    color: #4ade80;
                    padding: 4px 8px;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: 600;
                }
            """)
        elif step.status == StepStatus.RUNNING:
            self.setText(f"⏳ {step_num}. {step.title}")
            self.setStyleSheet("""
                QLabel#step_chip {
                    background: rgba(245, 158, 11, 0.2);
                    color: #fbbf24;
                    padding: 4px 8px;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
        else:
            self.setText(f"{step_num}. {step.title}")
            self.setStyleSheet("""
                QLabel#step_chip {
                    background: transparent;
                    color: #94a3b8;
                    padding: 4px 8px;
                    border-radius: 3px;
                    font-size: 10px;
                    opacity: 0.5;
                }
            """)


class AgentTaskStepperWidget(QWidget):
    """Horizontal Stepper showing the pipeline of steps with state chips."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("step_stepper")
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget#step_stepper {
                background: #1e293b;
                border-radius: 4px;
            }
        """)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)
        self._show_empty_state()

    def _show_empty_state(self):
        self.clear()
        lbl = QLabel("Chưa có kế hoạch nào được tạo", self)
        lbl.setStyleSheet("color: #64748b; font-size: 10px; padding: 4px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl)

    def clear(self):
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def set_plan(self, plan: Optional[AgentTaskPlan]):
        self.clear()
        if not plan or not plan.steps:
            self._show_empty_state()
            return

        for idx, step in enumerate(plan.steps):
            chip = StepChip(idx + 1, step, self)
            self.layout.addWidget(chip)
