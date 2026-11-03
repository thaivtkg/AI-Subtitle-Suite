# -*- coding: utf-8 -*-
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QFileDialog,
)


class MissingMediaDialog(QDialog):
    """Hộp thoại Khôi phục Liên kết Video (Relink Missing Media)

    Cho phép người dùng:
    1. Chọn lại đường dẫn video mới (Relink / Browse)
    2. Dùng video đã tự động phát hiện ở thư mục lân cận (Use Suggested)
    3. Mở dự án ở chế độ không có video (Subtitle / CAT Studio Only)
    4. Hủy bỏ (Cancel)
    """

    def __init__(
        self,
        project_name: str = "",
        missing_path: str = "",
        suggested_path: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.project_name = project_name
        self.missing_path = missing_path
        self.suggested_path = suggested_path
        self.result_action = "CANCEL"  # "RELINK", "OPEN_WITHOUT_VIDEO", "CANCEL"
        self.selected_video_path: str | None = None

        self.setWindowTitle("🎬 Khôi phục Liên kết Video - AI Subtitle Suite")
        self.setMinimumWidth(560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QLabel {
                color: #F8FAFC;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QFrame.card {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 12px;
            }
            QPushButton {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
                font-weight: 500;
                padding: 8px 16px;
                border-radius: 6px;
            }
            QPushButton#btn_primary {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#btn_primary:hover {
                background-color: #0369A1;
            }
            QPushButton#btn_suggested {
                background-color: #065F46;
                color: #A7F3D0;
                border: 1px solid #10B981;
            }
            QPushButton#btn_suggested:hover {
                background-color: #047857;
            }
            QPushButton#btn_secondary {
                background-color: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
            }
            QPushButton#btn_secondary:hover {
                background-color: #475569;
            }
            QPushButton#btn_ghost {
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid #334155;
            }
            QPushButton#btn_ghost:hover {
                background-color: #1E293B;
                color: #F1F5F9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 32px;")
        header_layout.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        title_lbl = QLabel("Không tìm thấy Video gốc của Dự án")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #F8FAFC;")
        title_layout.addWidget(title_lbl)

        proj_desc = f"Dự án: <b style='color: #38BDF8;'>{self.project_name or 'Dự án'}</b>"
        proj_lbl = QLabel(proj_desc)
        proj_lbl.setStyleSheet("font-size: 13px; color: #94A3B8;")
        title_layout.addWidget(proj_lbl)
        header_layout.addLayout(title_layout, stretch=1)
        layout.addLayout(header_layout)

        # Missing path card
        missing_card = QFrame()
        missing_card.setProperty("class", "card")
        missing_card.setStyleSheet(
            "background-color: #1E293B; border: 1px solid #EF4444; border-radius: 6px; padding: 10px;"
        )
        missing_card_layout = QVBoxLayout(missing_card)
        missing_card_layout.setContentsMargins(10, 8, 10, 8)
        missing_card_layout.setSpacing(4)

        missing_title = QLabel("Đường dẫn ban đầu (Không tìm thấy):")
        missing_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #F87171;")
        missing_card_layout.addWidget(missing_title)

        path_lbl = QLabel(self.missing_path)
        path_lbl.setWordWrap(True)
        path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_lbl.setStyleSheet("font-size: 12px; color: #CBD5E1; font-family: monospace;")
        missing_card_layout.addWidget(path_lbl)
        layout.addWidget(missing_card)

        # Suggested Candidate Card (if available)
        if self.suggested_path:
            suggested_card = QFrame()
            suggested_card.setStyleSheet(
                "background-color: #064E3B; border: 1px solid #10B981; border-radius: 6px; padding: 10px;"
            )
            sugg_layout = QVBoxLayout(suggested_card)
            sugg_layout.setContentsMargins(10, 8, 10, 8)
            sugg_layout.setSpacing(6)

            sugg_title = QLabel("⚡ Tự động tìm thấy tệp video cùng tên ở thư mục lân cận:")
            sugg_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #6EE7B7;")
            sugg_layout.addWidget(sugg_title)

            sugg_path_lbl = QLabel(self.suggested_path)
            sugg_path_lbl.setWordWrap(True)
            sugg_path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            sugg_path_lbl.setStyleSheet("font-size: 12px; color: #A7F3D0; font-family: monospace;")
            sugg_layout.addWidget(sugg_path_lbl)

            self.btn_use_suggested = QPushButton("⚡ Sử dụng Video này và Mở Dự Án")
            self.btn_use_suggested.setObjectName("btn_suggested")
            self.btn_use_suggested.setCursor(Qt.PointingHandCursor)
            self.btn_use_suggested.clicked.connect(self._on_use_suggested_clicked)
            sugg_layout.addWidget(self.btn_use_suggested)

            layout.addWidget(suggested_card)

        # Description / Options
        opt_lbl = QLabel(
            "Tệp video có thể đã bị di chuyển hoặc đổi tên. Hãy chọn cách xử lý bên dưới:"
        )
        opt_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        layout.addWidget(opt_lbl)

        # Action Buttons Layout
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        # Primary browse
        self.btn_browse = QPushButton("🔍  Chọn Lại Đường Dẫn Video Mới (Relink Media)...")
        self.btn_browse.setObjectName("btn_primary")
        self.btn_browse.setFixedHeight(36)
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        btn_layout.addWidget(self.btn_browse)

        # Secondary open without video
        self.btn_open_no_video = QPushButton("📄  Mở Không Cần Video (Chỉ Sửa Phụ Đề & Dịch Thuật)")
        self.btn_open_no_video.setObjectName("btn_secondary")
        self.btn_open_no_video.setFixedHeight(34)
        self.btn_open_no_video.setCursor(Qt.PointingHandCursor)
        self.btn_open_no_video.clicked.connect(self._on_open_no_video_clicked)
        btn_layout.addWidget(self.btn_open_no_video)

        # Cancel
        self.btn_cancel = QPushButton("❌  Hủy Bỏ (Không Mở Dự Án)")
        self.btn_cancel.setObjectName("btn_ghost")
        self.btn_cancel.setFixedHeight(32)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _on_use_suggested_clicked(self):
        self.result_action = "RELINK"
        self.selected_video_path = self.suggested_path
        self.accept()

    def _on_browse_clicked(self):
        initial_dir = os.path.dirname(self.missing_path) if self.missing_path else ""
        if not os.path.exists(initial_dir):
            initial_dir = ""

        filter_str = "Video Files (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.ts *.wmv);;All Files (*.*)"
        new_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file Video mới cho dự án",
            initial_dir,
            filter_str,
        )
        if new_path:
            self.result_action = "RELINK"
            self.selected_video_path = os.path.normpath(new_path)
            self.accept()

    def _on_open_no_video_clicked(self):
        self.result_action = "OPEN_WITHOUT_VIDEO"
        self.selected_video_path = None
        self.accept()

    def _on_cancel_clicked(self):
        self.result_action = "CANCEL"
        self.selected_video_path = None
        self.reject()
