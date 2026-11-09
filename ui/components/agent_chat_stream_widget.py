import time
from typing import Optional, List
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QFrame,
    QSizePolicy,
)

from core.agent.models import ChatMessage, AgentContextLedger


class ProjectMemoryBar(QWidget):
    """Persistent project memory bar at the top of the chat column."""

    def __init__(self, ledger: Optional[AgentContextLedger] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("memory_bar")
        self._ledger = ledger or AgentContextLedger()
        self._init_ui()
        self.update_ledger(self._ledger)

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget#memory_bar {
                background: #1e293b;
                border-bottom: 1px solid #334155;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # Title
        self.lbl_title = QLabel("🧠 BỘ NHỚ DỰ ÁN", self)
        self.lbl_title.setStyleSheet("font-weight: bold; color: #cbd5e1; font-size: 10px;")
        layout.addWidget(self.lbl_title)

        # Pills container
        self.pill_video = QLabel("🎬 Video: N/A", self)
        self.pill_video.setStyleSheet("""
            background: rgba(168, 85, 247, 0.2);
            color: #c084fc;
            border: 1px solid #a855f7;
            padding: 2px 6px;
            border-radius: 10px;
            font-weight: 600;
            font-size: 9px;
        """)
        layout.addWidget(self.pill_video)

        self.pill_lang = QLabel("🌐 Gốc: -- → Đích: --", self)
        self.pill_lang.setStyleSheet("""
            background: rgba(168, 85, 247, 0.2);
            color: #c084fc;
            border: 1px solid #a855f7;
            padding: 2px 6px;
            border-radius: 10px;
            font-weight: 600;
            font-size: 9px;
        """)
        layout.addWidget(self.pill_lang)

        layout.addStretch()

        # Rules count
        self.lbl_rules = QLabel("Đã khóa 0 quy tắc", self)
        self.lbl_rules.setStyleSheet("color: #64748b; font-size: 9px;")
        layout.addWidget(self.lbl_rules)

    def update_ledger(self, ledger: AgentContextLedger):
        self._ledger = ledger
        dur_s = (ledger.duration_ms or 0) / 1000.0
        self.pill_video.setText(f"🎬 Video: {dur_s:.1f}s" if dur_s > 0 else "🎬 Chưa nạp video")
        lang_map = {"ja": "JP", "en": "EN", "vi": "VI", "ko": "KO", "zh": "ZH"}
        src = lang_map.get((ledger.source_lang or "").lower(), (ledger.source_lang or "AUTO").upper())
        tgt = lang_map.get((ledger.target_lang or "").lower(), (ledger.target_lang or "VI").upper())
        self.pill_lang.setText(f"🌐 Gốc: {src} → Đích: {tgt}")
        rules_cnt = len(ledger.active_rules)
        self.lbl_rules.setText(f"Đã khóa {rules_cnt} quy tắc")

    def get_summary_text(self) -> str:
        return f"{self.pill_video.text()} | {self.pill_lang.text()} | {self.lbl_rules.text()}"


class ChatBubble(QWidget):
    """Individual chat bubble widget for User or Assistant with dynamic height & zero truncation."""

    def __init__(self, message: ChatMessage, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._message = message
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        h_layout = QHBoxLayout(self)
        h_layout.setContentsMargins(0, 2, 0, 2)
        h_layout.setSpacing(0)

        self.lbl = QLabel(self)
        self.lbl.setTextFormat(Qt.TextFormat.MarkdownText)
        self.lbl.setText(message.content)
        self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        is_user = message.role == "user"
        if is_user:
            self.lbl.setStyleSheet("""
                background: #0284c7;
                color: #ffffff;
                padding: 8px 12px;
                border-radius: 8px 8px 0 8px;
                font-size: 11px;
            """)
            h_layout.addStretch(1)
            h_layout.addWidget(self.lbl, 4)
        else:
            self.lbl.setStyleSheet("""
                background: #1e293b;
                color: #e2e8f0;
                padding: 8px 12px;
                border-radius: 8px 8px 8px 0;
                border: 1px solid #334155;
                font-size: 11px;
            """)
            h_layout.addWidget(self.lbl, 4)
            h_layout.addStretch(1)


class AgentChatStreamWidget(QWidget):
    """Left column component: Memory Bar + Chat Stream + Prompt Input."""

    prompt_submitted = Signal(str)

    def __init__(self, ledger: Optional[AgentContextLedger] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("mc_col_chat")
        self._ledger = ledger or AgentContextLedger()
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget#mc_col_chat {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Memory Bar
        self.memory_bar = ProjectMemoryBar(self._ledger, self)
        main_layout.addWidget(self.memory_bar)

        # 2. Chat Stream Scroll Area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("chat_stream")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea#chat_stream {
                background: transparent;
                border: none;
            }
            QScrollArea#chat_stream QWidget {
                background: transparent;
            }
        """)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(10, 8, 10, 8)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.chat_container)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)
        main_layout.addWidget(self.scroll_area, 1)

        # 3. Input Box
        input_container = QWidget(self)
        input_container.setObjectName("chat_input_box")
        input_container.setStyleSheet("""
            QWidget#chat_input_box {
                background: #090d16;
                border-top: 1px solid #334155;
            }
        """)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(6)

        self.prompt_input = QLineEdit(input_container)
        self.prompt_input.setObjectName("prompt_input")
        self.prompt_input.setPlaceholderText("Gõ lệnh hoặc yêu cầu chỉnh sửa...")
        self.prompt_input.setStyleSheet("""
            QLineEdit#prompt_input {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 6px 8px;
                color: #e2e8f0;
                font-size: 11px;
            }
            QLineEdit#prompt_input:focus {
                border: 1px solid #0284c7;
            }
        """)
        self.prompt_input.returnPressed.connect(self._on_send_clicked)
        input_layout.addWidget(self.prompt_input, 1)

        self.btn_send_prompt = QPushButton("Gửi", input_container)
        self.btn_send_prompt.setObjectName("btn_send_prompt")
        self.btn_send_prompt.setStyleSheet("""
            QPushButton#btn_send_prompt {
                background: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#btn_send_prompt:hover {
                background: #0369a1;
            }
            QPushButton#btn_send_prompt:pressed {
                background: #075985;
            }
        """)
        self.btn_send_prompt.clicked.connect(self._on_send_clicked)
        input_layout.addWidget(self.btn_send_prompt)

        main_layout.addWidget(input_container)

    def _on_scroll_range_changed(self, min_val: int, max_val: int):
        try:
            if hasattr(self, "scroll_area") and self.scroll_area:
                vsb = self.scroll_area.verticalScrollBar()
                if vsb:
                    vsb.setValue(max_val)
        except RuntimeError:
            pass

    def add_message(self, message: ChatMessage):
        """Append a new bubble message and auto-scroll to the bottom."""
        bubble = ChatBubble(message, self.chat_container)
        # Insert before stretch
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        try:
            if hasattr(self, "scroll_area") and self.scroll_area:
                vsb = self.scroll_area.verticalScrollBar()
                if vsb:
                    vsb.setValue(vsb.maximum())
        except RuntimeError:
            pass

    def set_messages(self, messages: List[ChatMessage]):
        """Clear and load full chat message history."""
        # Remove old widgets
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for msg in messages:
            self.add_message(msg)

    def update_ledger(self, ledger: AgentContextLedger):
        self.memory_bar.update_ledger(ledger)

    def _on_send_clicked(self):
        text = self.prompt_input.text().strip()
        if text:
            self.prompt_input.clear()
            self.prompt_submitted.emit(text)
