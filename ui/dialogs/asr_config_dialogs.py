from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
from ui.core.icons import get_icon


class _ObsidianSectionDialog(QDialog):
    """Reusable Obsidian Dark frameless modal hosting a detached configuration widget."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        icon_name: str,
        content_widget,
        *,
        width: int = 620,
        min_height: int = 360,
        parent=None,
    ):
        super().__init__(parent)
        self._content_widget = content_widget
        self._drag_pos = None
        self.setWindowTitle(title)
        self.setFixedWidth(width)
        self.setMinimumHeight(min_height)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(Qt.NonModal)

        if isinstance(content_widget, QGroupBox):
            content_widget.setTitle("")
            content_widget.setStyleSheet("QGroupBox { border: none; margin-top: 0px; padding-top: 0px; }")

        self._setup_ui(title, subtitle, icon_name, content_widget)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.accept)

    def showEvent(self, event):
        parent = self.parentWidget()
        if parent is not None:
            for sibling in parent.findChildren(_ObsidianSectionDialog):
                if sibling is not self and sibling.isVisible():
                    sibling.hide()
        super().showEvent(event)
        self.adjustSize()
        if parent is not None and parent.isVisible():
            center = parent.frameGeometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        else:
            screen = QApplication.primaryScreen()
            if screen is not None:
                center = screen.availableGeometry().center()
                self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 48:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _setup_ui(self, title: str, subtitle: str, icon_name: str, content_widget):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("AsrConfigDialogCard")
        card.setStyleSheet("""
            QFrame#AsrConfigDialogCard {
                background-color: #131824;
                border: 1.5px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("AsrConfigDialogHeader")
        header.setFixedHeight(48)
        header.setStyleSheet("""
            QFrame#AsrConfigDialogHeader {
                background-color: #1B2232;
                border-top-left-radius: 15px;
                border-top-right-radius: 15px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)
        header_layout.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(icon_name, "#38BDF8", 16).pixmap(16, 16))
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #F8FAFC; letter-spacing: 0.4px;"
        )

        btn_close = QPushButton("✕")
        btn_close.setObjectName("btn_dialog_close")
        btn_close.setFixedSize(32, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setToolTip("Đóng (Esc)")
        # Đặt rõ min-width/min-height khớp setFixedSize và padding: 0px để không bị global stylesheet bóp hẹp nút ✕
        btn_close.setStyleSheet("""
            QPushButton#btn_dialog_close {
                background-color: rgba(255, 255, 255, 0.06);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                padding: 0px;
                min-width: 32px;
                max-width: 32px;
                min-height: 28px;
                max-height: 28px;
            }
            QPushButton#btn_dialog_close:hover {
                background-color: #EF4444;
                color: #FFFFFF;
                border-color: #EF4444;
            }
        """)
        btn_close.clicked.connect(self.accept)

        header_layout.addWidget(icon_lbl)
        header_layout.addWidget(title_lbl, 1)
        header_layout.addWidget(btn_close)
        card_layout.addWidget(header)

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(20, 14, 20, 12)
        body_layout.setSpacing(10)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setWordWrap(True)
            sub_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; background: transparent;")
            body_layout.addWidget(sub_lbl)

        if content_widget is not None:
            content_widget.setParent(card)
            content_widget.show()
            body_layout.addWidget(content_widget)

        body_layout.addStretch()
        card_layout.addLayout(body_layout, 1)

        footer = QFrame()
        footer.setObjectName("AsrConfigDialogFooter")
        footer.setStyleSheet(
            "QFrame#AsrConfigDialogFooter { border-top: 1px solid rgba(255, 255, 255, 0.07); }"
        )
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 10, 20, 12)
        footer_layout.addStretch()

        btn_done = QPushButton("Đóng")
        btn_done.setFixedHeight(30)
        btn_done.setFixedWidth(96)
        btn_done.setProperty("variant", "primary")
        btn_done.setCursor(Qt.PointingHandCursor)
        btn_done.clicked.connect(self.accept)
        footer_layout.addWidget(btn_done)
        card_layout.addWidget(footer)

        root_layout.addWidget(card)


class ModelConfigDialog(_ObsidianSectionDialog):
    """Dialog cấu hình Model Whisper / Model Chuyên Ngữ / Compute Type / Language."""

    def __init__(self, model_widget, parent=None):
        super().__init__(
            title="CẤU HÌNH MODEL ASR (MODEL CONFIGURATION)",
            subtitle="Chọn model Whisper chuẩn hoặc model chuyên ngôn ngữ (Kotoba JA), loại tính toán VRAM và ngôn ngữ nguồn.",
            icon_name="box",
            content_widget=model_widget,
            width=540,
            min_height=390,
            parent=parent,
        )
        self.setObjectName("ModelConfigDialog")


class AsrVadConfigDialog(_ObsidianSectionDialog):
    """Dialog cấu hình ASR / VAD Preset & thông số tách câu chi tiết."""

    def __init__(self, vad_widget, parent=None):
        super().__init__(
            title="ASR / VAD PRESET & THÔNG SỐ TÁCH CÂU",
            subtitle="Tinh chỉnh ngưỡng im lặng, độ nhạy VAD, khoảng đệm đầu/cuối câu và độ dài tối đa theo model đang chọn.",
            icon_name="sliders",
            content_widget=vad_widget,
            width=680,
            min_height=420,
            parent=parent,
        )
        self.setObjectName("AsrVadConfigDialog")
