from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from ui.theme import Theme


class KeyCap(QLabel):
    """Widget viên phím (KeyCap) mô phỏng nút bấm bàn phím trên Dark Theme."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"""
            background-color: {Theme.SURFACE_ELEVATED};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
            min-height: 18px;
        """)


class HotkeysCheatsheetDialog(QDialog):
    """Bảng Tra Cứu Phím Tắt Nhanh (Pro CAT Hotkeys) chuẩn Dark Liquid Theme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bảng Tra Cứu Phím Tắt Nhanh")
        self.setFixedSize(580, 610)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag_pos = None

        self._setup_ui()
        self._setup_shortcuts()

    def mousePressEvent(self, event):
        """Cho phép kéo di chuyển cửa sổ khi nhấp giữ chuột trên thanh Header (48px trên cùng)."""
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

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Container Card chính
        card = QFrame()
        card.setObjectName("HotkeysCard")
        card.setStyleSheet("""
            QFrame#HotkeysCard {
                background-color: #131824;
                border: 1.5px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # 1. HEADER BAR
        header = QFrame()
        header.setObjectName("HotkeysHeader")
        header.setFixedHeight(48)
        header.setStyleSheet("""
            QFrame#HotkeysHeader {
                background-color: transparent;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 16, 0)
        header_layout.setSpacing(10)

        lbl_icon = QLabel("⌨")
        lbl_icon.setStyleSheet(f"background: transparent; border: none; border-radius: 0px; font-size: 16px; color: {Theme.CYAN};")
        header_layout.addWidget(lbl_icon)

        lbl_title = QLabel("BẢNG TRA CỨU PHÍM TẮT NHANH (PRO CAT HOTKEYS)")
        lbl_title.setStyleSheet(f"background: transparent; border: none; border-radius: 0px; font-size: 13px; font-weight: bold; color: {Theme.TEXT_PRIMARY};")
        header_layout.addWidget(lbl_title, stretch=1)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(30, 26)
        btn_close.setCursor(Qt.PointingHandCursor)
        # padding: 0px loại bỏ triệt để xung đột với stylesheet toàn cục
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                padding: 0px;
                min-height: 0px;
            }
            QPushButton:hover {
                background-color: #EF4444;
                color: #FFFFFF;
                border-color: #EF4444;
            }
        """)
        btn_close.clicked.connect(self.close)
        header_layout.addWidget(btn_close)
        card_layout.addWidget(header)

        # 2. SCROLLABLE CONTENT
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 2px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.22); border-radius: 3px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent; border: none;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(22, 10, 22, 12)
        content_layout.setSpacing(7)

        # --- NHÓM 1: BIÊN TẬP & PHỤ ĐỀ ---
        content_layout.addWidget(self._create_group_header("✦ BIÊN TẬP & PHỤ ĐỀ (TIMELINE & SUBTITLE)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "M"], "Gộp các phân đoạn đã chọn (Merge)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "Shift", "S"], "Tách phân đoạn tại vị trí hiện tại (Split)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "K"], "Cắt phân đoạn tại con trỏ phát (Split at Playhead)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "Z"], "Hoàn tác thao tác trước đó (Undo)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "Y"], "Làm lại thao tác vừa hoàn tác (Redo)"))

        content_layout.addWidget(self._create_divider())

        # --- NHÓM 2: ĐIỀU HƯỚNG & PHÁT ---
        content_layout.addWidget(self._create_group_header("✦ ĐIỀU HƯỚNG & PHÁT (NAVIGATION & PLAYBACK)"))
        content_layout.addWidget(self._create_hotkey_row(["Space"], "Phát / Tạm dừng video (Play / Pause)"))
        content_layout.addWidget(self._create_hotkey_row(["Alt", "▲ / ▼"], "Di chuyển lên / xuống giữa các câu"))
        content_layout.addWidget(self._create_hotkey_row(["Nhấp đơn"], "Chọn câu & Focus ô soạn thảo văn bản"))
        content_layout.addWidget(self._create_hotkey_row(["Nhấp đúp"], "Nghe thử âm thanh đoạn phụ đề"))

        content_layout.addWidget(self._create_divider())

        # --- NHÓM 3: QUẢN LÝ TỆP & DỰ ÁN ---
        content_layout.addWidget(self._create_group_header("✦ QUẢN LÝ TỆP & DỰ ÁN (FILE & PROJECT)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "N"], "Tạo dự án mới (New Project)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "O"], "Mở thư mục dự án (.ai-subtitle)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "S"], "Lưu dự án hiện tại (Save Project)"))
        content_layout.addWidget(self._create_hotkey_row(["Ctrl", "Shift", "E"], "Xuất file phụ đề SRT (Export)"))
        content_layout.addWidget(self._create_hotkey_row(["F1"], "Bật / Tắt Bảng tra cứu phím tắt này"))

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        card_layout.addWidget(scroll)

        root_layout.addWidget(card)

    def _setup_shortcuts(self):
        shortcut_esc = QShortcut(QKeySequence("Esc"), self)
        shortcut_esc.activated.connect(self.close)
        shortcut_f1 = QShortcut(QKeySequence("F1"), self)
        shortcut_f1.activated.connect(self.close)

    def _create_group_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            background: transparent;
            color: {Theme.CYAN};
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 0.5px;
            border: none;
            margin-top: 4px;
        """)
        return lbl

    def _create_divider(self) -> QFrame:
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); border: none;")
        return div

    def _create_hotkey_row(self, keys: list[str], description: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent; border: none;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 1, 4, 1)
        row_layout.setSpacing(12)

        keys_container = QWidget()
        keys_container.setFixedWidth(190)
        keys_layout = QHBoxLayout(keys_container)
        keys_layout.setContentsMargins(0, 0, 0, 0)
        keys_layout.setSpacing(4)

        for idx, key in enumerate(keys):
            if idx > 0:
                plus = QLabel("+")
                plus.setStyleSheet(f"background: transparent; color: {Theme.TEXT_MUTED}; font-weight: bold; font-size: 11px; border: none;")
                keys_layout.addWidget(plus)
            keys_layout.addWidget(KeyCap(key))
        keys_layout.addStretch()
        row_layout.addWidget(keys_container)

        lbl_desc = QLabel(description)
        lbl_desc.setStyleSheet(f"background: transparent; color: {Theme.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none;")
        row_layout.addWidget(lbl_desc, stretch=1)

        return row
