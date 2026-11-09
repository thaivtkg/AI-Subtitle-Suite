import copy
from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QLineEdit,
    QTextEdit,
)

from core.agent.models import AgentTaskPlan, AgentStep, StepStatus
from ui.components.agent_task_stepper_widget import AgentTaskStepperWidget


class EditableSegmentRow(QWidget):
    """Row displaying a segment with editable text."""

    text_changed = Signal(int, str)
    focused = Signal(int)

    def __init__(self, index: int, time_str: str, text: str, is_active: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.set_active(is_active)

        # Label index & time
        self.lbl_info = QLabel(f"<strong>#{index:02d}</strong> [{time_str}]", self)
        self.lbl_info.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")
        layout.addWidget(self.lbl_info)

        # Editable text edit
        self.editor = QLineEdit(text, self)
        self.editor.setStyleSheet("""
            QLineEdit {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 2px;
                color: #e2e8f0;
                padding: 2px 6px;
                font-size: 10px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        self.editor.textChanged.connect(lambda t: self.text_changed.emit(self.index, t))
        self.editor.installEventFilter(self)
        layout.addWidget(self.editor, 1)

    def set_active(self, is_active: bool):
        border_style = "border-left: 2px solid #38bdf8;" if is_active else "border-left: 2px solid transparent;"
        self.setStyleSheet(f"""
            QWidget {{
                background: #1e293b;
                border-radius: 3px;
                {border_style}
            }}
        """)

    def eventFilter(self, obj, event):
        if obj == self.editor and event.type() == QEvent.Type.FocusIn:
            self.focused.emit(self.index)
        return super().eventFilter(obj, event)


class EditableResultReportWidget(QScrollArea):
    """Interactive preview and editable inspection report."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("inspection_card")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("""
            QScrollArea#inspection_card {
                background: #090d16;
                border: 1px solid #1e293b;
                border-radius: 4px;
            }
            QScrollArea#inspection_card QWidget {
                background: #090d16;
            }
        """)

        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        self.setWidget(self.container)
        self.current_segments = []
        self._rows: List[EditableSegmentRow] = []
        self.show_placeholder()

    def show_placeholder(self):
        self.clear()
        lbl = QLabel("Chưa có kết quả task nào để báo cáo.\nHãy gửi câu lệnh hoặc duyệt kế hoạch để bắt đầu.", self.container)
        lbl.setStyleSheet("color: #64748b; font-size: 10px; padding: 12px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl)
        self.layout.addStretch()

    def show_error_report(self, step_title: str, error_message: str):
        self.clear()
        box = QWidget(self.container)
        box.setStyleSheet("""
            QWidget {
                background: rgba(239, 68, 68, 0.1);
                border: 1px solid #ef4444;
                border-radius: 4px;
            }
        """)
        box_l = QVBoxLayout(box)
        box_l.setContentsMargins(10, 10, 10, 10)
        box_l.setSpacing(6)

        lbl_err_title = QLabel(f"❌ <strong>Lỗi thực thi:</strong> {step_title}", box)
        lbl_err_title.setStyleSheet("color: #ef4444; font-size: 11px; background: transparent; border: none;")
        box_l.addWidget(lbl_err_title)

        lbl_err_desc = QLabel(f"Chi tiết: {error_message}", box)
        lbl_err_desc.setStyleSheet("color: #fca5a5; font-size: 10px; background: transparent; border: none;")
        lbl_err_desc.setWordWrap(True)
        box_l.addWidget(lbl_err_desc)

        hint = QLabel("💡 Gợi ý: Bạn có thể bấm nút 'Yêu cầu làm lại task này' bên dưới hoặc gửi yêu cầu mới trong khung chat.", box)
        hint.setStyleSheet("color: #94a3b8; font-size: 9px; background: transparent; border: none;")
        hint.setWordWrap(True)
        box_l.addWidget(hint)

        self.layout.addWidget(box)
        self.layout.addStretch()

    def clear(self):
        self._rows.clear()
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def render_result(self, step_title: str, result_dict: Dict[str, Any]):
        self.clear()

        hint = QLabel("Dữ liệu kết quả (bạn có thể click sửa trực tiếp text trước khi duyệt):", self.container)
        hint.setStyleSheet("color: #64748b; font-size: 9px; margin-bottom: 2px;")
        self.layout.addWidget(hint)

        segments = result_dict.get("segments", [])
        self.current_segments = copy.deepcopy(segments)
        if segments:
            for i, seg in enumerate(segments[:30]):
                t_in = seg.get("start", "00:00.000")
                t_out = seg.get("end", "00:00.000")
                if isinstance(t_in, (int, float)):
                    t_in = f"{int(t_in)//60:02d}:{int(t_in)%60:02d}.{int((t_in*1000)%1000):03d}"
                if isinstance(t_out, (int, float)):
                    t_out = f"{int(t_out)//60:02d}:{int(t_out)%60:02d}.{int((t_out*1000)%1000):03d}"
                time_str = f"{t_in} → {t_out}"
                text = seg.get("text", "")
                row = EditableSegmentRow(i + 1, time_str, text, is_active=False, parent=self.container)
                row.text_changed.connect(self._on_segment_text_changed)
                row.focused.connect(self._on_row_focused)
                self._rows.append(row)
                self.layout.addWidget(row)
        else:
            # Render general report fields
            text_view = QTextEdit(self.container)
            text_view.setReadOnly(False)
            text_view.setStyleSheet("""
                QTextEdit {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 3px;
                    color: #cbd5e1;
                    font-size: 10px;
                    padding: 6px;
                }
            """)
            lines = [f"{k}: {v}" for k, v in result_dict.items()]
            text_view.setPlainText("\n".join(lines) if lines else f"Hoàn thành: {step_title}")
            self.layout.addWidget(text_view)

        self.layout.addStretch()

    def _on_row_focused(self, index: int):
        for r in self._rows:
            r.set_active(r.index == index)

    def _on_segment_text_changed(self, idx: int, new_text: str):
        if 0 <= idx - 1 < len(self.current_segments):
            self.current_segments[idx - 1]["text"] = new_text
            self.current_segments[idx - 1]["translation"] = new_text

    def get_current_segments(self) -> List[Dict[str, Any]]:
        return self.current_segments


class AgentReportInspectorWidget(QWidget):
    """Right column component: Stepper + Inspection Card + Approval Bar."""

    approve_clicked = Signal()
    redo_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("mc_col_inspect")
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget#mc_col_inspect {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 1. Stepper
        self.step_stepper = AgentTaskStepperWidget(self)
        layout.addWidget(self.step_stepper)

        # 2. Header Bar: Title + Badge
        header_bar = QWidget(self)
        h_layout = QHBoxLayout(header_bar)
        h_layout.setContentsMargins(0, 2, 0, 2)

        self.lbl_report_title = QLabel("🔍 BÁO CÁO KẾT QUẢ TASK", header_bar)
        self.lbl_report_title.setStyleSheet("font-weight: 700; color: #cbd5e1; font-size: 11px;")
        h_layout.addWidget(self.lbl_report_title)

        h_layout.addStretch()

        self.status_badge = QLabel("CHỜ BẠN DUYỆT", header_bar)
        self.status_badge.setObjectName("status_badge")
        self.set_badge_status("waiting")
        h_layout.addWidget(self.status_badge)

        layout.addWidget(header_bar)

        # 3. Interactive / Editable Result Report Area
        self.inspection_card = EditableResultReportWidget(self)
        layout.addWidget(self.inspection_card, 1)

        # 4. Action Control Bar
        action_bar = QWidget(self)
        action_bar.setStyleSheet("border-top: 1px solid #1e293b;")
        ab_layout = QHBoxLayout(action_bar)
        ab_layout.setContentsMargins(0, 6, 0, 0)
        ab_layout.setSpacing(6)

        self.lbl_hint = QLabel("Sau khi bấm duyệt, Agent sẽ chuyển sang bước tiếp.", action_bar)
        self.lbl_hint.setStyleSheet("color: #94a3b8; font-size: 9px; border: none;")
        ab_layout.addWidget(self.lbl_hint, 1)

        self.btn_redo_task = QPushButton("Yêu cầu làm lại task này", action_bar)
        self.btn_redo_task.setObjectName("btn_redo_task")
        self.btn_redo_task.setStyleSheet("""
            QPushButton#btn_redo_task {
                background: #334155;
                color: #cbd5e1;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton#btn_redo_task:hover {
                background: #475569;
            }
        """)
        self.btn_redo_task.clicked.connect(self._on_redo_clicked)
        ab_layout.addWidget(self.btn_redo_task)

        self.btn_approve_next = QPushButton("✔ Duyệt & Chạy bước tiếp", action_bar)
        self.btn_approve_next.setObjectName("btn_approve_next")
        self.btn_approve_next.setStyleSheet("""
            QPushButton#btn_approve_next {
                background: #16a34a;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton#btn_approve_next:hover {
                background: #15803d;
            }
            QPushButton#btn_approve_next:disabled {
                background: #1e293b;
                color: #64748b;
            }
        """)
        self.btn_approve_next.clicked.connect(self._on_approve_clicked)
        ab_layout.addWidget(self.btn_approve_next)

        layout.addWidget(action_bar)

    def set_badge_status(self, mode: str):
        if mode == "waiting":
            self.status_badge.setText("CHỜ BẠN DUYỆT")
            self.status_badge.setStyleSheet("""
                QLabel#status_badge {
                    background: rgba(245, 158, 11, 0.15);
                    color: #fbbf24;
                    border: 1px solid #d97706;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
            """)
        elif mode in ("failed", "error"):
            self.status_badge.setText("THẤT BẠI")
            self.status_badge.setStyleSheet("""
                QLabel#status_badge {
                    background: rgba(239, 68, 68, 0.15);
                    color: #ef4444;
                    border: 1px solid #dc2626;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
            """)
        elif mode == "done":
            self.status_badge.setText("HOÀN TẤT")
            self.status_badge.setStyleSheet("""
                QLabel#status_badge {
                    background: rgba(34, 197, 94, 0.15);
                    color: #4ade80;
                    border: 1px solid #16a34a;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
            """)
        else:
            self.status_badge.setText("SẴN SÀNG")
            self.status_badge.setStyleSheet("""
                QLabel#status_badge {
                    background: rgba(148, 163, 184, 0.15);
                    color: #94a3b8;
                    border: 1px solid #475569;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
            """)

    def update_report(self, step_idx: int, step: AgentStep, result: Dict[str, Any]):
        self.lbl_report_title.setText(f"🔍 BÁO CÁO KẾT QUẢ TASK #{step_idx + 1}")
        self.set_badge_status("waiting")
        self.inspection_card.render_result(step.title, result)
        self.btn_approve_next.setEnabled(True)

    def show_error(self, step_idx: int, step: AgentStep, error: str):
        self.lbl_report_title.setText(f"❌ TASK #{step_idx + 1} THẤT BẠI")
        self.set_badge_status("failed")
        self.inspection_card.show_error_report(step.title, error)
        self.btn_approve_next.setEnabled(False)
        self.btn_redo_task.setEnabled(True)

    def _on_approve_clicked(self):
        # Anti-rapid double click protection
        self.btn_approve_next.setEnabled(False)
        self.approve_clicked.emit()

    def _on_redo_clicked(self):
        self.redo_clicked.emit()

    def get_current_segments(self) -> List[Dict[str, Any]]:
        return self.inspection_card.get_current_segments()
