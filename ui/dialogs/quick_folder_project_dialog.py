# -*- coding: utf-8 -*-
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QFrame,
)

from core.services.project_service import ProjectService


class QuickFolderProjectDialog(QDialog):
    """Hộp thoại Tạo Dự Án Nhanh Từ Thư Mục Video (DEV-SPEC-FOLDER-PROJECT-001 & 002)

    Hiển thị danh sách các tệp video trong thư mục, cho phép lọc, tích chọn hàng loạt,
    và tự động tạo các bundle .ai-subtitle tương ứng.
    """

    def __init__(
        self,
        folder_path: str = "",
        project_service: ProjectService | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.project_service = project_service or ProjectService()
        self.current_folder = folder_path
        self._scanned_items: list[dict] = []

        # Chuẩn hóa tiêu đề: loại bỏ emoji 📁 để thanh tiêu đề Windows chỉ hiển thị 1 icon app
        self.setWindowTitle("Tạo Dự Án Nhanh Từ Thư Mục Video - AI Subtitle Suite")
        self.setMinimumSize(720, 500)
        self.resize(780, 540)
        # Thiết lập tường minh các cờ cửa sổ tiêu chuẩn với nút đóng Windows Close Button
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        self._setup_ui()
        if self.current_folder:
            self.set_folder(self.current_folder)

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
            QLineEdit {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #38BDF8;
            }
            QTableWidget {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                gridline-color: #334155;
                selection-background-color: #0369A1;
                selection-color: #F8FAFC;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #0F172A;
                color: #94A3B8;
                font-weight: 600;
                font-size: 12px;
                border: none;
                border-bottom: 1px solid #334155;
                padding: 8px 6px;
            }
            QPushButton {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
                font-weight: 500;
                padding: 6px 14px;
                border-radius: 6px;
                background-color: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton#btn_close_header {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                font-size: 15px;
                font-weight: bold;
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton#btn_close_header:hover {
                background-color: #EF4444;
                color: #FFFFFF;
            }
            QPushButton#btn_primary {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                font-weight: 600;
                padding: 7px 18px;
            }
            QPushButton#btn_primary:hover {
                background-color: #0369A1;
            }
            QPushButton#btn_primary:disabled {
                background-color: #1E293B;
                color: #64748B;
            }
            QFrame.card {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        # Giảm contentsMargins đáy từ 16px xuống 10px để triệt tiêu khoảng trống thừa
        layout.setContentsMargins(18, 14, 18, 10)
        layout.setSpacing(10)

        # 1. HEADER (Có nút đóng ✕ tinh gọn)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        lbl_title = QLabel("📁 Tạo Dự Án Nhanh Từ Thư Mục Video")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #38BDF8;")
        lbl_subtitle = QLabel("Tự động quét video, kiểm tra dự án kề bên và nạp hàng loạt vào Workspace & Hàng đợi.")
        lbl_subtitle.setStyleSheet("font-size: 12px; color: #94A3B8;")
        title_vbox.addWidget(lbl_title)
        title_vbox.addWidget(lbl_subtitle)

        header_layout.addLayout(title_vbox, stretch=1)

        self.btn_close_header = QPushButton("✕")
        self.btn_close_header.setObjectName("btn_close_header")
        self.btn_close_header.setFixedSize(28, 28)
        self.btn_close_header.setCursor(Qt.PointingHandCursor)
        self.btn_close_header.setToolTip("Đóng (Esc)")
        self.btn_close_header.clicked.connect(self.reject)
        header_layout.addWidget(self.btn_close_header, alignment=Qt.AlignTop)

        layout.addLayout(header_layout)

        # 2. FOLDER SELECTOR BAR
        folder_layout = QHBoxLayout()
        folder_layout.setSpacing(8)
        lbl_folder = QLabel("Thư mục:")
        lbl_folder.setStyleSheet("font-weight: 600; color: #CBD5E1;")
        self.folder_path_input = QLineEdit()
        self.folder_path_input.setPlaceholderText("Đường dẫn thư mục chứa video...")
        self.folder_path_input.returnPressed.connect(self._on_folder_input_submitted)

        self.btn_browse = QPushButton("Chọn Thư Mục...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.clicked.connect(self._on_browse_folder)

        folder_layout.addWidget(lbl_folder)
        folder_layout.addWidget(self.folder_path_input, stretch=1)
        folder_layout.addWidget(self.btn_browse)
        layout.addLayout(folder_layout)

        # 3. SEARCH & FILTER BAR
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Tìm kiếm video trong thư mục...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # 4. VIDEO TABLE
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Chọn", "Tên Tệp Video", "Kích Thước", "Trạng Thái"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.table, stretch=1)

        # 5. UNIFIED BOTTOM BAR (DEV-SPEC-FOLDER-PROJECT-002: Hợp nhất hàng thao tác & hàng nút thành 1 hàng ngang duy nhất)
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)

        self.btn_select_all = QPushButton("Chọn tất cả")
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._on_select_all)

        self.btn_deselect_all = QPushButton("Bỏ chọn")
        self.btn_deselect_all.setCursor(Qt.PointingHandCursor)
        self.btn_deselect_all.clicked.connect(self._on_deselect_all)

        self.lbl_summary = QLabel("Đã chọn: 0 / 0 video")
        self.lbl_summary.setStyleSheet("font-weight: 600; color: #38BDF8; margin-left: 8px;")

        bottom_layout.addWidget(self.btn_select_all)
        bottom_layout.addWidget(self.btn_deselect_all)
        bottom_layout.addWidget(self.lbl_summary)
        bottom_layout.addStretch(1)

        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_create = QPushButton("🚀 Khởi Tạo Dự Án & Mở Workspace")
        self.btn_create.setObjectName("btn_primary")
        self.btn_create.setCursor(Qt.PointingHandCursor)
        self.btn_create.setEnabled(False)  # Mặc định disabled khi chưa có video nào được chọn
        self.btn_create.clicked.connect(self.accept)

        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_create)
        layout.addLayout(bottom_layout)

    def keyPressEvent(self, event):
        """Hỗ trợ phím Esc thoát hộp thoại an toàn."""
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _on_browse_folder(self):
        initial = self.folder_path_input.text().strip() or os.path.expanduser("~")
        selected = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Chứa Video", initial)
        if selected:
            self.set_folder(selected)

    def _on_folder_input_submitted(self):
        text = self.folder_path_input.text().strip()
        if text and os.path.isdir(text):
            self.set_folder(text)

    def set_folder(self, folder_path: str):
        """Quét và nạp dữ liệu video từ thư mục chỉ định."""
        self.current_folder = os.path.abspath(folder_path)
        self.folder_path_input.setText(self.current_folder)

        self._scanned_items = self.project_service.scan_video_folder(self.current_folder)
        self._populate_table()

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._scanned_items))

        for row, item in enumerate(self._scanned_items):
            # Cột 0: Checkbox (Phương án B: Mặc định Qt.Unchecked)
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, check_item)

            # Cột 1: Tên Video
            name_item = QTableWidgetItem(item["filename"])
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            name_item.setToolTip(item["video_path"])
            self.table.setItem(row, 1, name_item)

            # Cột 2: Kích thước
            size_item = QTableWidgetItem(item["size_str"])
            size_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            size_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, size_item)

            # Cột 3: Trạng thái
            if item["has_project"]:
                status_text = "📂 Đã có dự án"
            else:
                status_text = "✨ Mới"
            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            status_item.setForeground(Qt.GlobalColor.white)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setToolTip(item["expected_project_dir"])
            self.table.setItem(row, 3, status_item)

        self.table.blockSignals(False)
        self._apply_search_filter()
        self._update_summary()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            self._update_summary()

    def _on_search_text_changed(self, _text: str):
        self._apply_search_filter()

    def _apply_search_filter(self):
        query = self.search_input.text().strip().lower()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            filename = name_item.text().lower() if name_item else ""
            hidden = bool(query and query not in filename)
            self.table.setRowHidden(row, hidden)

    def _on_select_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
        self.table.blockSignals(False)
        self._update_summary()

    def _on_deselect_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_summary()

    def _update_summary(self):
        total = self.table.rowCount()
        selected = len(self.get_selected_videos())
        self.lbl_summary.setText(f"Đã chọn: {selected} / {total} video")
        self.btn_create.setEnabled(selected > 0)

    def get_selected_videos(self) -> list[dict]:
        """Trả về danh sách metadata các video được tích chọn."""
        selected = []
        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                if row < len(self._scanned_items):
                    selected.append(self._scanned_items[row])
        return selected

    @property
    def selected_video_paths(self) -> list[str]:
        """Trả về danh sách đường dẫn tuyệt đối của các video được chọn."""
        return [item["video_path"] for item in self.get_selected_videos()]
