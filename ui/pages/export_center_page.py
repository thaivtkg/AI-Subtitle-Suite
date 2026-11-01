from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme


class ExportCenterPage(QWidget):
    export_srt_requested = Signal()
    burn_hardsub_requested = Signal()
    export_batch_translation_requested = Signal(int, int)  # (start_index_1_based, count)
    import_batch_translation_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("🚀 Export & Delivery Center")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {Theme.TEXT_PRIMARY}; border: none;")
        layout.addWidget(title)

        # 1. Format Selection Card
        fmt_frame = QFrame()
        fmt_frame.setObjectName("fmt_frame")
        fmt_frame.setStyleSheet(
            f"QFrame#fmt_frame {{ background-color: {Theme.SURFACE_ELEVATED}; border: 1px solid {Theme.BORDER}; border-radius: 8px; }}"
        )
        fmt_layout = QVBoxLayout(fmt_frame)
        fmt_layout.setContentsMargins(16, 14, 16, 14)
        fmt_layout.setSpacing(10)

        lbl_f_title = QLabel("Định dạng xuất phụ đề (Softsub):")
        lbl_f_title.setStyleSheet(f"font-weight: bold; color: {Theme.CYAN}; border: none;")
        fmt_layout.addWidget(lbl_f_title)

        self.chk_srt = QCheckBox("SubRip Subtitle (*.srt) — Chuẩn phát hành quốc tế")
        self.chk_srt.setChecked(True)
        self.chk_vtt = QCheckBox("WebVTT (*.vtt) — Chuẩn Web & HTML5 Video")
        self.chk_txt = QCheckBox("Plain Text (*.txt) — Bản gỡ băng thuần văn bản")

        fmt_layout.addWidget(self.chk_srt)
        fmt_layout.addWidget(self.chk_vtt)
        fmt_layout.addWidget(self.chk_txt)
        layout.addWidget(fmt_frame)

        # 2. Hardsub Options Card
        hs_frame = QFrame()
        hs_frame.setObjectName("hs_frame")
        hs_frame.setStyleSheet(
            f"QFrame#hs_frame {{ background-color: {Theme.SURFACE}; border: 1px solid {Theme.BORDER}; border-radius: 8px; }}"
        )
        hs_layout = QVBoxLayout(hs_frame)
        hs_layout.setContentsMargins(16, 14, 16, 14)
        hs_layout.setSpacing(10)

        lbl_hs_title = QLabel("Xuất Video Hardsub (FFmpeg GPU Acceleration):")
        lbl_hs_title.setStyleSheet(f"font-weight: bold; color: {Theme.CYAN}; border: none;")
        hs_layout.addWidget(lbl_hs_title)

        self.chk_hardsub = QCheckBox("Render MP4 Hardsub (Chèn cứng phụ đề vào video)")
        self.chk_hardsub.setChecked(True)
        hs_layout.addWidget(self.chk_hardsub)
        layout.addWidget(hs_frame)

        # 3. Output Directory
        out_frame = QFrame()
        out_frame.setObjectName("out_frame")
        out_frame.setStyleSheet(
            f"QFrame#out_frame {{ background-color: {Theme.SURFACE}; border: 1px solid {Theme.BORDER}; border-radius: 8px; }}"
        )
        out_layout = QHBoxLayout(out_frame)
        out_layout.setContentsMargins(16, 12, 16, 12)
        out_layout.setSpacing(8)

        lbl_out = QLabel("📁 Thư mục lưu:")
        lbl_out.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-weight: bold; border: none;")
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Đường dẫn lưu trữ kết quả...")
        btn_browse = QPushButton("Chọn...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.clicked.connect(self._select_dir)

        out_layout.addWidget(lbl_out)
        out_layout.addWidget(self.out_edit, stretch=1)
        out_layout.addWidget(btn_browse)
        layout.addWidget(out_frame)

        # 4. External Translation Batching Frame
        batch_frame = QFrame()
        batch_frame.setObjectName("batch_frame")
        batch_frame.setStyleSheet(
            f"QFrame#batch_frame {{ background-color: {Theme.SURFACE}; border: 1px solid {Theme.BORDER}; border-radius: 8px; }}"
        )
        batch_layout = QVBoxLayout(batch_frame)
        batch_layout.setContentsMargins(16, 12, 16, 12)
        batch_layout.setSpacing(8)
        lbl_batch_title = QLabel("🌐 Dịch ngoài theo đợt (External Translation Batch)")
        lbl_batch_title.setStyleSheet(f"font-weight: bold; color: {Theme.CYAN}; border: none;")
        batch_layout.addWidget(lbl_batch_title)
        self.lbl_batch_progress = QLabel("Tiến độ: Chưa có phụ đề trong dự án.")
        self.lbl_batch_progress.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; border: none;")
        batch_layout.addWidget(self.lbl_batch_progress)
        row_ctrl = QHBoxLayout()
        row_ctrl.setSpacing(10)
        lbl_start = QLabel("Bắt đầu từ câu #:")
        lbl_start.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; border: none;")
        row_ctrl.addWidget(lbl_start)
        self._total_count = 0
        self._translated_count = 0
        self.spin_batch_start = QSpinBox()
        self.spin_batch_start.setRange(1, 99999)
        self.spin_batch_start.setValue(1)
        self.spin_batch_start.setFixedWidth(85)
        self.spin_batch_start.valueChanged.connect(self._on_batch_start_changed)
        row_ctrl.addWidget(self.spin_batch_start)
        lbl_count = QLabel("Số câu xuất:")
        lbl_count.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; border: none;")
        row_ctrl.addWidget(lbl_count)
        self.spin_batch_count = QSpinBox()
        self.spin_batch_count.setRange(1, 500)
        self.spin_batch_count.setValue(5)
        self.spin_batch_count.setFixedWidth(85)
        self.spin_batch_count.valueChanged.connect(self._on_batch_count_changed)
        row_ctrl.addWidget(self.spin_batch_count)
        row_ctrl.addStretch()
        self.btn_export_batch = QPushButton("Xuất đợt dịch (SRT)")
        self.btn_export_batch.setObjectName("btn_secondary")
        self.btn_export_batch.clicked.connect(self._on_export_batch_clicked)
        row_ctrl.addWidget(self.btn_export_batch)
        self.btn_import_batch = QPushButton("Nạp bản dịch vào Studio (SRT)")
        self.btn_import_batch.setObjectName("btn_secondary")
        self.btn_import_batch.clicked.connect(self.import_batch_translation_requested.emit)
        row_ctrl.addWidget(self.btn_import_batch)
        batch_layout.addLayout(row_ctrl)
        layout.addWidget(batch_frame)

        layout.addStretch()

        # Action Buttons
        act_row = QHBoxLayout()
        act_row.setSpacing(10)

        btn_exp_sub = QPushButton("💾 Xuất file Phụ đề (Softsub)")
        btn_exp_sub.setObjectName("btn_secondary")
        btn_exp_sub.clicked.connect(self.export_srt_requested.emit)

        btn_exp_video = QPushButton("🎬 Render Video Hardsub")
        btn_exp_video.setObjectName("btn_primary")
        btn_exp_video.clicked.connect(self.burn_hardsub_requested.emit)

        act_row.addWidget(btn_exp_sub)
        act_row.addWidget(btn_exp_video, stretch=1)
        layout.addLayout(act_row)

    def _select_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất kết quả")
        if d:
            self.out_edit.setText(d)

    def _on_export_batch_clicked(self):
        start = self.spin_batch_start.value()
        count = self.spin_batch_count.value()
        self.export_batch_translation_requested.emit(start, count)

    def _on_batch_start_changed(self, new_start: int):
        if self._total_count > 0:
            remaining = max(1, self._total_count - new_start + 1)
            self.spin_batch_count.setMaximum(remaining)
            if self.spin_batch_count.value() > remaining:
                self.spin_batch_count.setValue(remaining)
            self._update_batch_label()

    def _on_batch_count_changed(self, _new_count: int):
        self._update_batch_label()

    def _update_batch_label(self):
        if self._total_count == 0 or self._translated_count >= self._total_count:
            return
        start = self.spin_batch_start.value()
        count = self.spin_batch_count.value()
        end_suggest = min(self._total_count, start + count - 1)
        self.lbl_batch_progress.setText(
            f"Tiến độ: Đã dịch {self._translated_count}/{self._total_count} câu  •  Đợt tiếp theo: Câu #{start} đến #{end_suggest}"
        )
        self.lbl_batch_progress.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; border: none;")

    def update_translation_progress(self, current_start: Optional[int], total_count: int, translated_count: int):
        self._total_count = total_count
        self._translated_count = translated_count
        if total_count == 0:
            self.lbl_batch_progress.setText("Tiến độ: Chưa có phụ đề trong dự án.")
            self.lbl_batch_progress.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; border: none;")
            self.spin_batch_start.setValue(1)
            self.spin_batch_start.setMaximum(1)
            self.spin_batch_count.setValue(1)
            self.spin_batch_count.setMaximum(1)
            return

        self.spin_batch_start.setMaximum(total_count)
        if current_start is None or (total_count > 0 and translated_count >= total_count):
            self.lbl_batch_progress.setText(
                f"Tiến độ: 🎉 Đã hoàn thành dịch toàn bộ ({translated_count}/{total_count} câu)!"
            )
            self.lbl_batch_progress.setStyleSheet(f"color: {Theme.SUCCESS}; font-weight: bold; font-size: 11px; border: none;")
            self.spin_batch_start.setValue(total_count)
            self.spin_batch_count.setValue(1)
            self.spin_batch_count.setMaximum(1)
            return

        start_val = min(total_count, max(1, current_start))
        remaining = max(1, total_count - start_val + 1)

        self.spin_batch_start.setValue(start_val)
        self.spin_batch_count.setMaximum(remaining)
        suggested_count = min(5, remaining)
        self.spin_batch_count.setValue(suggested_count)

        end_suggest = min(total_count, start_val + suggested_count - 1)
        self.lbl_batch_progress.setText(
            f"Tiến độ: Đã dịch {translated_count}/{total_count} câu  •  Đợt tiếp theo: Câu #{start_val} đến #{end_suggest}"
        )
        self.lbl_batch_progress.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; border: none;")
