import os
import uuid

from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtWidgets import ( QLineEdit, QListWidget, QListWidgetItem,

    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QToolTip,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.subtitle_generation.subtitle_generation_request import (
    SubtitleGenerationRequest,
)
from core.project.project_state import TimingState
from ui.theme import Theme
from ui.core.icons import get_icon


class SubtitleGenerationPanel(QWidget):
    """Qt view for robust subtitle generation; project data comes from the core."""

    # Timing Draft dùng pipeline VAD riêng, không khởi tạo Whisper ASR.
    timing_start_requested = Signal(int, dict)
    timing_resume_requested = Signal(int, dict)
    timing_cancel_requested = Signal()
    request_context_edit = Signal()
    request_model_config_dialog = Signal()
    request_asr_vad_dialog = Signal()
    _timing_settings_controls = (
        "cmb_model", "cmb_specialized_model", "cmb_compute", "chk_vad", "chk_fix_overlap", "spin_overlap_gap"
    )

    def __init__(self, generation_service, parent=None):
        super().__init__(parent)
        self.generation_service = generation_service
        self._context_compiled = None
        self._context_configured = False
        self._timing_start_fresh = False
        self.video_duration_ms = 0
        self._setup_ui()
        self._connect_signals()
        self.refresh_history()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_batch_mode_availability()
        self._sync_batch_spin_limits(reset_default=False)

    def _setup_ui(self):
        # Panel uses global styling from LiquidThemeEngine

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.settings_scroll_area = QScrollArea(self)
        self.settings_scroll_area.setWidgetResizable(True)
        self.settings_scroll_area.setFrameShape(QFrame.NoFrame)
        self.settings_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.settings_scroll_area.setMinimumHeight(60)
        self.settings_scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )

        self.settings_scroll_content = QWidget()
        self.settings_scroll_content.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        settings_layout = QVBoxLayout(self.settings_scroll_content)
        settings_layout.setContentsMargins(0, 0, 8, 0)
        settings_layout.setSpacing(12)

        title = QLabel("Generate Subtitle")
        title.setProperty("class", "SectionTitle")
        settings_layout.addWidget(title)
        # --- PHASE 5: SUBTITLE SOURCE ---
        source_title = QLabel("Subtitle Source")
        source_title.setProperty("class", "SectionTitle")
        settings_layout.addWidget(source_title)
        
        source_h_layout = QHBoxLayout()
        source_h_layout.setSpacing(8)
        self.cmb_subtitle_source = QComboBox()
        self.cmb_subtitle_source.addItem("Auto-detected SRT", "default")
        self.cmb_subtitle_source.setFixedHeight(32)
        self.cmb_subtitle_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        source_h_layout.addWidget(self.cmb_subtitle_source, 1)
        
        self.btn_add_external_srt = QPushButton("+ Add SRT...")
        self.btn_add_external_srt.setObjectName("btn_add_external_srt")
        self.btn_add_external_srt.setFixedHeight(32)
        source_h_layout.addWidget(self.btn_add_external_srt)
        settings_layout.addLayout(source_h_layout)
        
        self.btn_add_external_srt.clicked.connect(self._on_add_external_srt)
        self.cmb_subtitle_source.currentIndexChanged.connect(self._on_subtitle_source_changed)

        # --- PHASE 3: RANGE GENERATION ---
        self.range_group = QGroupBox("Generate theo khoảng thời gian")
        range_layout = QVBoxLayout(self.range_group)
        range_layout.setContentsMargins(12, 12, 12, 12)
        range_layout.setSpacing(8)
        
        # RANGE_TIME_INPUT_UNIT_SELECTOR: explicit units prevent 1-5 ambiguity.
        range_grid = QGridLayout()
        range_grid.setContentsMargins(0, 0, 0, 0)
        range_grid.setHorizontalSpacing(8)
        range_grid.setVerticalSpacing(8)

        unit_lbl = QLabel("Đơn vị:")
        unit_lbl.setFixedWidth(44)
        unit_tooltip = "Chọn rõ đơn vị trước khi nhập để tránh nhầm 1–5 giây với 1–5 phút."
        unit_lbl.setToolTip(unit_tooltip)
        self.cmb_range_unit = QComboBox()
        self.cmb_range_unit.addItem("Giây (s)", "seconds")
        self.cmb_range_unit.addItem("Phút (min)", "minutes")
        self._range_input_unit = "seconds"
        self.cmb_range_unit.setMinimumWidth(140)
        self.cmb_range_unit.setFixedHeight(32)
        self.cmb_range_unit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cmb_range_unit.setToolTip(unit_tooltip)

        self.txt_start = QLineEdit()
        self.txt_start.setPlaceholderText("Ví dụ: 60,5")
        self.txt_start.setFixedHeight(32)
        self.txt_start.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.txt_end = QLineEdit()
        self.txt_end.setPlaceholderText("Ví dụ: 70")
        self.txt_end.setFixedHeight(32)
        self.txt_end.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        lbl_from = QLabel("Từ:")
        lbl_from.setFixedWidth(44)
        lbl_to = QLabel("Đến:")
        lbl_to.setFixedWidth(34)

        self.txt_start.textChanged.connect(
            lambda _text: self._clear_range_input_error(self.txt_start)
        )
        self.txt_end.textChanged.connect(
            lambda _text: self._clear_range_input_error(self.txt_end)
        )
        self.cmb_range_unit.currentIndexChanged.connect(
            lambda _index: self._on_range_unit_changed()
        )
        self._refresh_range_input_help()

        self.btn_range_timeline = QPushButton("Lấy từ vùng Timeline")
        self.btn_range_timeline.setIcon(get_icon("clock", "#94A3B8", 14))
        self.btn_range_timeline.setIconSize(QSize(14, 14))
        self.btn_range_timeline.setProperty("variant", "secondary")
        self.btn_range_timeline.setFixedHeight(34)
        self.btn_range_timeline.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.btn_range_preview = QPushButton("Preview Range")
        self.btn_range_preview.setProperty("variant", "primary")
        self.btn_range_preview.setFixedHeight(34)
        self.btn_range_preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        range_grid.addWidget(unit_lbl, 0, 0)
        range_grid.addWidget(self.cmb_range_unit, 0, 1, 1, 3)
        range_grid.addWidget(lbl_from, 1, 0)
        range_grid.addWidget(self.txt_start, 1, 1)
        range_grid.addWidget(lbl_to, 1, 2)
        range_grid.addWidget(self.txt_end, 1, 3)
        range_grid.addWidget(self.btn_range_timeline, 2, 1)
        range_grid.addWidget(self.btn_range_preview, 2, 3)
        range_grid.setColumnStretch(1, 1)
        range_grid.setColumnStretch(3, 1)
        range_layout.addLayout(range_grid)
        
        settings_layout.addWidget(self.range_group)
        
        self.btn_range_preview.clicked.connect(self._on_preview_range_clicked)
        # ---------------------------------


        self._vad_row_widgets = {}

        def _kv_row(
            label_text,
            widget,
            min_width=None,
            hint_text=None,
            tooltip=None,
            fixed_width=None,
            store_key=None,
            expand=False,
        ):
            row = QHBoxLayout()
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(12)
            lbl = QLabel(label_text)
            lbl.setProperty("class", "Caption")
            lbl.setFixedWidth(100)
            if fixed_width is not None:
                widget.setFixedWidth(fixed_width)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setFixedWidth(min_width if min_width is not None else 148)
            else:
                target_min_width = min_width if min_width is not None else max(widget.minimumWidth(), 160)
                widget.setMinimumWidth(target_min_width)
            if tooltip:
                lbl.setToolTip(tooltip)
                widget.setToolTip(tooltip)
            row.addWidget(lbl)
            if expand and fixed_width is None:
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                row.addWidget(widget, 1)
            else:
                row.addWidget(widget)
            hint_lbl = None
            if hint_text is not None:
                hint_lbl = QLabel(hint_text)
                hint_lbl.setWordWrap(False)
                hint_lbl.setStyleSheet("color: #64748B; font-size: 11px; background: transparent;")
                if tooltip:
                    hint_lbl.setToolTip(tooltip)
                row.addWidget(hint_lbl)
            if store_key:
                self._vad_row_widgets[store_key] = (lbl, widget, hint_lbl)
            if not (expand and fixed_width is None):
                row.addStretch()
            return row

        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 4, 0, 4)
        mode_layout.setSpacing(12)
        mode_lbl = QLabel("Task Mode:")
        mode_lbl.setProperty("class", "Caption")
        mode_lbl.setFixedWidth(100)
        mode_layout.addWidget(mode_lbl)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("Full Subtitle (Whisper ASR)", "asr")
        self.cmb_mode.addItem("Timing Draft (VAD Only)", "timing")
        self.cmb_mode.setMinimumWidth(160)
        self.cmb_mode.setFixedHeight(32)
        self.cmb_mode.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        mode_layout.addWidget(self.cmb_mode, 1)
        settings_layout.addLayout(mode_layout)
        # Adapt Qt's int payload to the no-argument policy slot.
        self.cmb_mode.currentIndexChanged.connect(
            lambda _index: self._on_mode_changed()
        )
        self.cmb_mode.currentIndexChanged.connect(self._on_task_mode_changed)

        self.model_group = QGroupBox("Model Configuration")
        model_layout = QVBoxLayout(self.model_group)
        model_layout.setContentsMargins(0, 6, 0, 6)
        model_layout.setSpacing(8)

        model_box_width = 188

        # --- Model Size row: combo + Download button ---
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 2, 0, 2)
        model_row.setSpacing(10)
        model_lbl = QLabel("Model Size:")
        model_lbl.setProperty("class", "Caption")
        model_lbl.setFixedWidth(100)
        self.cmb_model = QComboBox()
        self.cmb_model.setFixedWidth(model_box_width)
        self.cmb_model.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cmb_model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.btn_download_model = QPushButton("⬇ Download")
        self.btn_download_model.setProperty("variant", "secondary")
        self.btn_download_model.setFixedHeight(28)
        self.btn_download_model.setFixedWidth(98)
        self.btn_download_model.setStyleSheet("padding: 2px 6px;")
        self.btn_download_model.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_download_model.setToolTip("Download model from HuggingFace")
        self.btn_download_model.clicked.connect(self._on_download_model_clicked)
        self.btn_delete_model = QPushButton("Xóa")
        self.btn_delete_model.setObjectName("btn_delete_model")
        self.btn_delete_model.setProperty("variant", "danger")
        self.btn_delete_model.setIcon(get_icon("trash", "#EF4444", 14))
        self.btn_delete_model.setIconSize(QSize(14, 14))
        self.btn_delete_model.setFixedHeight(28)
        self.btn_delete_model.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_delete_model.setToolTip("Xóa model khỏi máy tính để giải phóng dung lượng ổ đĩa")
        self.btn_delete_model.clicked.connect(self._on_delete_model_clicked)
        self.btn_delete_model.setVisible(False)
        model_row.addWidget(model_lbl)
        model_row.addWidget(self.cmb_model)
        model_row.addWidget(self.btn_download_model)
        model_row.addWidget(self.btn_delete_model)
        model_row.addStretch()
        model_layout.addLayout(model_row)

        # --- Specialized Language ASR Model row (kotoba-whisper-v2.0 / v2.2) ---
        spec_row = QHBoxLayout()
        spec_row.setContentsMargins(0, 2, 0, 2)
        spec_row.setSpacing(10)
        spec_lbl = QLabel("Chuyên Ngữ:")
        spec_lbl.setProperty("class", "Caption")
        spec_lbl.setFixedWidth(100)
        self.cmb_specialized_model = QComboBox()
        self.cmb_specialized_model.setObjectName("cmb_specialized_model")
        self.cmb_specialized_model.setFixedWidth(model_box_width)
        self.cmb_specialized_model.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cmb_specialized_model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_specialized_model.setToolTip(
            "Chỉ dùng khi muốn thay thế Model Size ở trên bằng model chuyên ngôn ngữ (như kotoba-whisper cho tiếng Nhật)."
        )
        self.btn_download_specialized_model = QPushButton("⬇ Download")
        self.btn_download_specialized_model.setObjectName("btn_download_specialized_model")
        self.btn_download_specialized_model.setProperty("variant", "secondary")
        self.btn_download_specialized_model.setFixedHeight(28)
        self.btn_download_specialized_model.setFixedWidth(98)
        self.btn_download_specialized_model.setStyleSheet("padding: 2px 6px;")
        self.btn_download_specialized_model.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_download_specialized_model.setToolTip("Tải model chuyên ngôn ngữ từ HuggingFace")
        self.btn_download_specialized_model.clicked.connect(self._on_download_specialized_model_clicked)
        self.btn_download_specialized_model.setVisible(False)
        self.btn_delete_specialized_model = QPushButton("Xóa")
        self.btn_delete_specialized_model.setObjectName("btn_delete_specialized_model")
        self.btn_delete_specialized_model.setProperty("variant", "danger")
        self.btn_delete_specialized_model.setIcon(get_icon("trash", "#EF4444", 14))
        self.btn_delete_specialized_model.setIconSize(QSize(14, 14))
        self.btn_delete_specialized_model.setFixedHeight(28)
        self.btn_delete_specialized_model.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_delete_specialized_model.setToolTip("Xóa model chuyên ngôn ngữ khỏi ổ đĩa")
        self.btn_delete_specialized_model.clicked.connect(self._on_delete_specialized_model_clicked)
        self.btn_delete_specialized_model.setVisible(False)
        spec_row.addWidget(spec_lbl)
        spec_row.addWidget(self.cmb_specialized_model)
        spec_row.addWidget(self.btn_download_specialized_model)
        spec_row.addWidget(self.btn_delete_specialized_model)
        spec_row.addStretch()
        model_layout.addLayout(spec_row)

        # --- Compute Type row with recommendation ---
        self.cmb_compute = QComboBox()
        self.cmb_compute.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._populate_compute_combo()
        model_layout.addLayout(_kv_row("Compute Type:", self.cmb_compute, fixed_width=model_box_width))

        self.lbl_effective_compute = QLabel("Effective: not run")
        self.lbl_effective_compute.setProperty("class", "Caption")
        model_layout.addWidget(self.lbl_effective_compute)

        self.cmb_language = QComboBox()
        self.cmb_language.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cmb_language.addItems(["Auto Detect", "vi", "en", "ja", "ko", "zh"])
        model_layout.addLayout(_kv_row("Language:", self.cmb_language, fixed_width=model_box_width))
        settings_layout.addWidget(self.model_group)

        # Populate model combos after widget tree is ready
        self._populate_model_combo()
        self._populate_specialized_model_combo()

        # Compact shortcut buttons shown inside Drawer only after sections are popped out to dialogs
        self._settings_layout = settings_layout
        self.config_shortcuts_group = QWidget(self.settings_scroll_content)
        self.config_shortcuts_group.setObjectName("config_shortcuts_group")
        self.config_shortcuts_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.config_shortcuts_group.setMinimumHeight(42)
        shortcuts_row = QHBoxLayout(self.config_shortcuts_group)
        shortcuts_row.setContentsMargins(0, 4, 0, 4)
        shortcuts_row.setSpacing(8)
        self.btn_open_model_config_dialog = QPushButton("Cấu hình Model…")
        self.btn_open_model_config_dialog.setObjectName("btn_open_model_config_dialog")
        self.btn_open_model_config_dialog.setIcon(get_icon("box", "#38BDF8", 14))
        self.btn_open_model_config_dialog.setIconSize(QSize(14, 14))
        self.btn_open_model_config_dialog.setProperty("variant", "secondary")
        self.btn_open_model_config_dialog.setFixedHeight(34)
        self.btn_open_model_config_dialog.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_open_model_config_dialog.clicked.connect(self.request_model_config_dialog)
        self.btn_open_model_config_dialog.hide()
        self.btn_open_asr_vad_dialog = QPushButton("Cấu hình ASR / VAD…")
        self.btn_open_asr_vad_dialog.setObjectName("btn_open_asr_vad_dialog")
        self.btn_open_asr_vad_dialog.setIcon(get_icon("sliders", "#38BDF8", 14))
        self.btn_open_asr_vad_dialog.setIconSize(QSize(14, 14))
        self.btn_open_asr_vad_dialog.setProperty("variant", "secondary")
        self.btn_open_asr_vad_dialog.setFixedHeight(34)
        self.btn_open_asr_vad_dialog.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_open_asr_vad_dialog.clicked.connect(self.request_asr_vad_dialog)
        self.btn_open_asr_vad_dialog.hide()
        shortcuts_row.addWidget(self.btn_open_model_config_dialog, 1)
        shortcuts_row.addWidget(self.btn_open_asr_vad_dialog, 1)
        self.config_shortcuts_group.hide()
        settings_layout.addWidget(self.config_shortcuts_group)

        self.asr_vad_group = QGroupBox("ASR / VAD Preset & Thông số")
        self.asr_vad_group.setObjectName("asr_vad_group")
        asr_vad_layout = QVBoxLayout(self.asr_vad_group)
        asr_vad_layout.setContentsMargins(0, 6, 0, 6)
        asr_vad_layout.setSpacing(8)

        advanced_group = QGroupBox("Advanced Settings")
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setContentsMargins(0, 6, 0, 6)
        advanced_layout.setSpacing(8)

        self.chk_vad = QCheckBox("Enable VAD (lọc khoảng lặng)")
        self.chk_vad.setChecked(True)
        advanced_layout.addWidget(self.chk_vad)

        self.chk_music_mode = QCheckBox("Chế độ Nhạc / Concert (Tối ưu ngắt câu bài hát)")
        self.chk_music_mode.setToolTip(
            "Tắt bộ lọc VAD gây nuốt tiếng hát khi nhạc nền lớn, kích hoạt tách câu tự nhiên theo nhịp điệu bài hát."
        )
        self.chk_music_mode.setChecked(False)
        advanced_layout.addWidget(self.chk_music_mode)

        self.chk_fix_overlap = QCheckBox("Fix subtitle overlap")
        self.chk_fix_overlap.setChecked(True)
        advanced_layout.addWidget(self.chk_fix_overlap)

        self.spin_overlap_gap = QSpinBox()
        self.spin_overlap_gap.setRange(1, 500)
        self.spin_overlap_gap.setValue(50)
        self.spin_overlap_gap.setSuffix(" ms")
        advanced_layout.addLayout(_kv_row("Overlap gap:", self.spin_overlap_gap))

        self.chk_word_timestamps = QCheckBox("Word-level Timestamps")
        advanced_layout.addWidget(self.chk_word_timestamps)

        self.cmb_vad_preset = QComboBox()
        self.cmb_vad_preset.setObjectName("cmb_vad_preset")
        self.cmb_vad_preset.addItem("Standard", "standard")
        for _preset in self._FIXED_VAD_PRESETS:
            if _preset["scope"] == "all":
                self.cmb_vad_preset.addItem(_preset["label"], _preset["key"])
        self.cmb_vad_preset.addItem("Custom", "custom")
        self.cmb_vad_preset.setMinimumWidth(270)
        asr_vad_layout.addLayout(_kv_row("ASR / VAD Preset:", self.cmb_vad_preset, min_width=270, store_key="vad_preset"))

        self.spin_min_silence = QSpinBox()
        self.spin_min_silence.setObjectName("spin_min_silence")
        self.spin_min_silence.setRange(50, 5000)
        self.spin_min_silence.setSingleStep(50)
        self.spin_min_silence.setValue(350)
        self.spin_min_silence.setSuffix(" ms")
        asr_vad_layout.addLayout(_kv_row(
            "Min Silence:",
            self.spin_min_silence,
            min_width=148,
            hint_text="↑ Gộp câu dài · ↓ Tách câu vụn",
            tooltip=(
                "Thời gian im lặng tối thiểu để tách câu (CFG-9: 300ms).\n"
                "• Tăng (400–800ms): Gộp các nhịp nghỉ ngắn thành câu dài.\n"
                "• Giảm (150–250ms): Tách câu nhanh, dễ chia nhỏ câu thoại."
            ),
            store_key="min_silence",
        ))

        self.spin_vad_threshold = QDoubleSpinBox()
        self.spin_vad_threshold.setObjectName("spin_vad_threshold")
        self.spin_vad_threshold.setRange(0.05, 0.95)
        self.spin_vad_threshold.setSingleStep(0.05)
        self.spin_vad_threshold.setDecimals(2)
        self.spin_vad_threshold.setValue(0.25)
        asr_vad_layout.addLayout(_kv_row(
            "VAD Threshold:",
            self.spin_vad_threshold,
            min_width=148,
            hint_text="↑ Lọc tạp âm · ↓ Bắt tiếng thì thầm",
            tooltip=(
                "Ngưỡng nhạy phát hiện giọng nói (CFG-9: 0.35).\n"
                "• Tăng (0.45–0.60): Lọc nhạc nền/tạp âm gắt hơn, nhưng dễ bỏ sót tiếng nói nhỏ.\n"
                "• Giảm (0.20–0.30): Bắt nhạy tiếng thì thầm/lẩm bẩm, nhưng dễ nhận nhầm tạp âm."
            ),
            store_key="vad_threshold",
        ))

        self.spin_speech_pad = QSpinBox()
        self.spin_speech_pad.setObjectName("spin_speech_pad")
        self.spin_speech_pad.setRange(0, 2000)
        self.spin_speech_pad.setSingleStep(50)
        self.spin_speech_pad.setValue(350)
        self.spin_speech_pad.setSuffix(" ms")
        asr_vad_layout.addLayout(_kv_row(
            "Speech Pad:",
            self.spin_speech_pad,
            min_width=148,
            hint_text="↑ Chống cụt âm · ↓ Bám sát tiếng",
            tooltip=(
                "Khoảng đệm mở rộng đầu và cuối câu (CFG-9: 300ms).\n"
                "• Tăng (350–500ms): Chống nuốt âm đầu/âm cuối câu.\n"
                "• Giảm (100–200ms): Timing bám sát khẩu hình nhưng dễ cụt chữ cuối."
            ),
            store_key="speech_pad",
        ))

        self.spin_max_speech = QDoubleSpinBox()
        self.spin_max_speech.setObjectName("spin_max_speech")
        self.spin_max_speech.setRange(1.0, 60.0)
        self.spin_max_speech.setSingleStep(0.5)
        self.spin_max_speech.setDecimals(1)
        self.spin_max_speech.setValue(8.0)
        self.spin_max_speech.setSuffix(" s")
        asr_vad_layout.addLayout(_kv_row(
            "Max Speech:",
            self.spin_max_speech,
            min_width=148,
            hint_text="↑ Cho phép câu dài · ↓ Ép ngắt câu",
            tooltip=(
                "Độ dài tối đa của 1 câu phụ đề (CFG-9: 6.0s).\n"
                "• Tăng (8–15s): Cho phép câu độc thoại kéo dài.\n"
                "• Giảm (3–5s): Ép cắt thành các câu ngắn dễ đọc."
            ),
            store_key="max_speech",
        ))
        self._refresh_vad_guidance_for_model(apply_values=True)

        self.chk_condition_on_previous_text = QCheckBox(
            "Giữ ngữ cảnh câu trước cho Large-v3 (Tắt khi gặp cảnh rên/lặp từ)"
        )
        self.chk_condition_on_previous_text.setObjectName("chk_condition_on_previous_text")
        self.chk_condition_on_previous_text.setToolTip(
            "Bật: giữ ngữ cảnh câu trước giúp mạch thoại liền lạc.\n"
            "Tắt: ngăn dây chuyền rên/lặp từ lan sang câu sau (tự động tắt với Live-Action / Tokusatsu (18+)).\n"
            "Lưu ý: Backend luôn giữ tắt tùy chọn này đối với kotoba-whisper."
        )
        self.chk_condition_on_previous_text.setChecked(True)
        asr_vad_layout.addWidget(self.chk_condition_on_previous_text)

        self.chk_apply_preset_rescan = QCheckBox(
            "Áp dụng Preset cho 'Gen Sub các câu đang chọn' và 'Quét lại'"
        )
        self.chk_apply_preset_rescan.setObjectName("chk_apply_preset_rescan")
        self.chk_apply_preset_rescan.setToolTip(
            "Khi bật, thao tác '🔍 Quét lại' và 'Gen Sub các câu đã chọn' sẽ dùng bộ thông số VAD/ASR của Preset đang chọn."
        )
        self.chk_apply_preset_rescan.setChecked(False)
        asr_vad_layout.addWidget(self.chk_apply_preset_rescan)
        settings_layout.addWidget(self.asr_vad_group)

        self.cmb_batch_mode = QComboBox()
        self.cmb_batch_mode.addItem("Time-based (Minutes)", "time")
        self.cmb_batch_mode.addItem("Segment-based (Count)", "segments")
        self.cmb_batch_mode.setMinimumWidth(160)
        self.cmb_batch_mode.setFixedHeight(32)
        advanced_layout.addLayout(_kv_row("Batch Mode:", self.cmb_batch_mode, expand=True))

        self.spin_batch_val = QSpinBox()
        self.spin_batch_val.setRange(1, 30)
        self.spin_batch_val.setValue(5)
        self.spin_batch_val.setSuffix(" min")
        self.spin_batch_val.setFixedHeight(32)
        # Compatibility alias for existing timing-panel integrations.
        self.spin_batch = self.spin_batch_val
        self.lbl_batch_size_hint = QLabel("")
        self.lbl_batch_size_hint.setWordWrap(False)
        self.lbl_batch_size_hint.setStyleSheet("color: #64748B; font-size: 11px; background: transparent;")
        batch_row = _kv_row("Batch Size:", self.spin_batch_val)
        batch_row.insertWidget(batch_row.count() - 1, self.lbl_batch_size_hint)
        advanced_layout.addLayout(batch_row)
        self.cmb_batch_mode.currentIndexChanged.connect(
            lambda _index: self._on_batch_mode_changed()
        )
        self.cmb_vad_preset.currentIndexChanged.connect(self._on_vad_preset_changed)
        self.spin_min_silence.valueChanged.connect(self._on_vad_param_edited)
        self.spin_vad_threshold.valueChanged.connect(self._on_vad_param_edited)
        self.spin_speech_pad.valueChanged.connect(self._on_vad_param_edited)
        self.spin_max_speech.valueChanged.connect(self._on_vad_param_edited)
        self.chk_condition_on_previous_text.toggled.connect(self._on_timing_setting_changed)
        self.chk_apply_preset_rescan.toggled.connect(self._on_timing_setting_changed)
        self.chk_fix_overlap.toggled.connect(self._on_timing_setting_changed)
        self.spin_overlap_gap.valueChanged.connect(self._on_timing_setting_changed)
        self.cmb_model.currentTextChanged.connect(self._on_timing_setting_changed)
        self.cmb_specialized_model.currentIndexChanged.connect(self._on_timing_setting_changed)
        self.cmb_compute.currentTextChanged.connect(self._on_timing_setting_changed)
        self.chk_vad.toggled.connect(self._on_timing_setting_changed)
        self.chk_music_mode.toggled.connect(self._on_timing_setting_changed)
        self.cmb_language.currentIndexChanged.connect(self._on_timing_setting_changed)
        settings_layout.addWidget(advanced_group)
        # --- PHASE 3: GENERATION HISTORY ---
        self.history_group = QGroupBox("↩ Generation History")
        history_layout = QVBoxLayout(self.history_group)
        history_layout.setContentsMargins(12, 12, 12, 12)
        
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(110)
        self.history_list.setMaximumHeight(150)
        self.history_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        history_layout.addWidget(self.history_list)
        
        self.btn_rollback = QPushButton("Khôi phục (Rollback)")
        self.btn_rollback.setProperty("variant", "danger")
        self.btn_rollback.setFixedHeight(34)
        self.btn_rollback.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_rollback.setEnabled(False)
        history_layout.addWidget(self.btn_rollback)
        
        
        # Quick Rollback row
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        quick_lbl = QLabel("Rollback:")
        quick_row.addWidget(quick_lbl)
        self.btn_rb_10 = QPushButton("10")
        self.btn_rb_30 = QPushButton("30")
        self.btn_rb_50 = QPushButton("50")
        self.btn_rb_60 = QPushButton("60")
        self.btn_rb_initial = QPushButton("Initial")
        for btn in (self.btn_rb_10, self.btn_rb_30, self.btn_rb_50, self.btn_rb_60, self.btn_rb_initial):
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("padding: 0px 6px;")
            quick_row.addWidget(btn, 1)
            btn.clicked.connect(lambda checked=False, b=btn: self._on_quick_rollback_clicked(b.text()))
            
        history_layout.addLayout(quick_row)

        settings_layout.addWidget(self.history_group)
        
        self.history_list.itemSelectionChanged.connect(self._on_history_selection_changed)
        self.btn_rollback.clicked.connect(self._on_rollback_clicked)
        # -----------------------------------


        context_layout = QHBoxLayout()
        context_layout.setContentsMargins(0, 6, 0, 0)
        self.lbl_context_status = QLabel("Context: not configured")
        self.lbl_context_status.setProperty("class", "Caption")
        self.lbl_context_status.setWordWrap(True)
        self.btn_context_edit = QPushButton("Edit context")
        self.btn_context_edit.setFixedHeight(32)
        self.btn_context_edit.setProperty("variant", "secondary")
        self.context_status_label = self.lbl_context_status
        self.edit_context_btn = self.btn_context_edit
        context_layout.addWidget(self.lbl_context_status, stretch=1)
        context_layout.addWidget(self.btn_context_edit)
        settings_layout.addLayout(context_layout)

        settings_layout.addStretch()
        self.settings_scroll_area.setWidget(self.settings_scroll_content)
        layout.addWidget(self.settings_scroll_area, stretch=1)

        self.action_footer = QWidget(self)
        self.action_footer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        footer_layout = QVBoxLayout(self.action_footer)
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(6)

        self.lbl_status = QLabel("Ready")
        self._configure_status_label(self.lbl_status)
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setProperty("class", "Caption")
        self.lbl_status.setStyleSheet(f"background: transparent; color: {Theme.TEXT_PRIMARY};")
        footer_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("pbar_generation")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setFormat("0%")
        self.progress_bar.setStyleSheet(f"""
            QProgressBar#pbar_generation {{
                background-color: {Theme.SURFACE_SOFT};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                min-height: 20px;
                max-height: 22px;
                text-align: center;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 700;
            }}
            QProgressBar#pbar_generation::chunk {{
                background: {Theme.PRIMARY_GRADIENT};
                border-radius: 5px;
            }}
        """)
        footer_layout.addWidget(self.progress_bar)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        self.btn_generate = QPushButton("Generate Subtitle")
        self.btn_generate.setFixedHeight(34)
        self.btn_generate.setObjectName("btn_primary")
        self.btn_generate.setProperty("variant", "primary")
        self.btn_generate.setIcon(get_icon("play", "#FFFFFF", 14))
        self.btn_generate.setIconSize(QSize(14, 14))

        self.btn_resume = QPushButton("Resume")
        self.btn_resume.setFixedHeight(34)
        self.btn_resume.setObjectName("btn_warning")
        self.btn_resume.setProperty("variant", "warning")
        self.btn_resume.setVisible(False)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setObjectName("btn_danger")
        self.btn_cancel.setProperty("variant", "danger")
        self.btn_cancel.setEnabled(False)

        button_layout.addWidget(self.btn_generate, stretch=3)
        button_layout.addWidget(self.btn_resume, stretch=3)
        button_layout.addWidget(self.btn_cancel, stretch=1)
        footer_layout.addLayout(button_layout)
        layout.addWidget(self.action_footer, stretch=0)

        # Apply the initial batching and ASR/Timing policies before the panel is shown.
        self._on_batch_mode_changed()
        self.refresh_batch_mode_availability()
        self._on_mode_changed()

    def take_action_footer(self):
        """Detach the action footer so the host can pin it outside the tab stack.

        The buttons remain owned by this panel logically: their signal handlers,
        progress callbacks, and state updates continue to target this instance.
        Only the QWidget parent/layout position changes.
        """
        footer = getattr(self, "action_footer", None)
        if footer is None:
            return None
        panel_layout = self.layout()
        if panel_layout is not None:
            panel_layout.removeWidget(footer)
        footer.setParent(None)
        return footer

    def _detach_section_widget(self, attr_name: str, shortcut_btn_attr: str):
        section = getattr(self, attr_name, None)
        if section is None:
            return None
        layout = getattr(self, "_settings_layout", None)
        if layout is not None:
            layout.removeWidget(section)
        section.setParent(None)
        shortcuts_group = getattr(self, "config_shortcuts_group", None)
        if shortcuts_group is not None:
            shortcuts_group.show()
        shortcut_btn = getattr(self, shortcut_btn_attr, None)
        if shortcut_btn is not None:
            shortcut_btn.show()
        return section

    def take_model_config_widget(self):
        """Detach Model Configuration group for hosting inside ModelConfigDialog."""
        return self._detach_section_widget("model_group", "btn_open_model_config_dialog")

    def take_asr_vad_config_widget(self):
        """Detach ASR / VAD Preset group for hosting inside AsrVadConfigDialog."""
        return self._detach_section_widget("asr_vad_group", "btn_open_asr_vad_dialog")

    @staticmethod
    def _configure_status_label(label):
        """Keep long errors inside the drawer's existing width."""
        label.setWordWrap(True)

    def _connect_signals(self):
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        self.btn_resume.clicked.connect(self._on_resume_clicked)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.btn_context_edit.clicked.connect(self.request_context_edit)
        self.generation_service.on_progress = self._update_progress
        self.generation_service.on_error = self._on_error
        self.generation_service.on_finish = self._on_finish
        history_changed = getattr(self.generation_service, "history_changed", None)
        if history_changed is not None:
            history_changed.connect(self.refresh_history)
        self.cmb_model.currentIndexChanged.connect(self._on_model_selection_changed)
        if hasattr(self, "cmb_specialized_model"):
            self.cmb_specialized_model.currentIndexChanged.connect(
                self._on_specialized_model_selection_changed
            )

    # ── Model list helpers ────────────────────────────────────────────────────

    @staticmethod
    def _combo_value(combo):
        if hasattr(combo, "currentData"):
            val = combo.currentData()
            if val is not None:
                return val
        return combo.currentText() if hasattr(combo, "currentText") else ""

    _ALL_MODELS = ["tiny", "base", "small", "large-v3-turbo", "medium", "large-v2", "large-v3"]

    @classmethod
    def _select_best_model(cls, info: dict, preferred: str | None = None) -> str:
        """Chọn model đã tải trên máy; nếu tải nhiều/tất cả size thì chọn size phù hợp nhất với cấu hình."""
        installed = [m for m in cls._ALL_MODELS if info.get(m, False)]
        if preferred and info.get(preferred, False):
            return preferred
        if installed:
            try:
                import torch
                has_cuda = torch.cuda.is_available()
                vram_gb = (
                    torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                    if has_cuda else 0.0
                )
            except Exception:
                has_cuda = False
                vram_gb = 0.0

            if has_cuda and vram_gb >= 3.5:
                priority = ["large-v3", "large-v3-turbo", "large-v2", "medium", "small", "base", "tiny"]
            else:
                priority = ["small", "base", "tiny", "large-v3-turbo", "medium", "large-v2", "large-v3"]

            for m in priority:
                if m in installed:
                    return m
            return installed[-1]
        return preferred or "large-v3-turbo"

    def _populate_model_combo(self, preferred: str | None = None) -> None:
        """Fill cmb_model with install-status icons; auto-select installed or best-fit model."""
        from core.services.model_manager import ModelManager
        prev = self.cmb_model.currentData() or preferred
        self.cmb_model.blockSignals(True)
        self.cmb_model.clear()
        try:
            info = {m["size"]: m["installed"] for m in ModelManager.get_discovery_list()}
        except Exception:
            info = {m: False for m in self._ALL_MODELS}
        for size in self._ALL_MODELS:
            installed = info.get(size, False)
            icon = "✅" if installed else "⬇"
            weight = ModelManager.SUPPORTED_MODELS.get(size, "")
            label = f"{icon} {size}  ({weight})"
            self.cmb_model.addItem(label, size)  # userData = bare model size
        self.cmb_model.blockSignals(False)
        target = self._select_best_model(info, prev)
        for i in range(self.cmb_model.count()):
            if self.cmb_model.itemData(i) == target:
                self.cmb_model.setCurrentIndex(i)
                break
        self._on_model_selection_changed()

    def _populate_specialized_model_combo(self, preferred: str | None = None) -> None:
        """Fill cmb_specialized_model with language-specialized ASR models (kotoba-whisper)."""
        if not hasattr(self, "cmb_specialized_model"):
            return
        from core.services.model_manager import ModelManager
        prev = self.cmb_specialized_model.currentData() if preferred is None else preferred
        self.cmb_specialized_model.blockSignals(True)
        self.cmb_specialized_model.clear()
        self.cmb_specialized_model.addItem("— Không dùng —", "")
        try:
            items = ModelManager.get_specialized_discovery_list()
        except Exception:
            items = []
        for idx_offset, item in enumerate(items, start=1):
            icon = "✅" if item.get("installed") else "⬇"
            label = f"{icon} {item['label']}"
            self.cmb_specialized_model.addItem(label, item["size"])
            self.cmb_specialized_model.setItemData(
                idx_offset,
                f"{item['size']} ({item['repo_id']}) · {item['weight']}",
                Qt.ToolTipRole,
            )
        self.cmb_specialized_model.blockSignals(False)
        target = prev or ""
        idx = self.cmb_specialized_model.findData(target)
        self.cmb_specialized_model.setCurrentIndex(idx if idx >= 0 else 0)
        self._on_specialized_model_selection_changed()

    @staticmethod
    def _is_ctrl_checked(ctrl, default: bool = False) -> bool:
        if ctrl is None:
            return default
        fn = getattr(ctrl, "isChecked", None)
        if callable(fn):
            return bool(fn())
        if hasattr(ctrl, "checked"):
            val = getattr(ctrl, "checked")
            return default if val is None else bool(val)
        return default

    def _get_effective_model_size(self) -> str:
        spec_combo = getattr(self, "cmb_specialized_model", None)
        if spec_combo is not None:
            spec_val = self._combo_value(spec_combo)
            if spec_val:
                return spec_val
        return self._combo_value(self.cmb_model)

    _STANDARD_VAD_PRESET = {
        "min_silence": 350,
        "threshold": 0.25,
        "speech_pad": 350,
        "max_speech": 8.0,
    }

    _FIXED_VAD_PRESETS = (
        {
            "key": "cfg9",
            "label": "CFG-9 Anime JA",
            "short_label": "CFG-9",
            "scope": "all",
            "min_silence": 300,
            "threshold": 0.35,
            "speech_pad": 300,
            "max_speech": 6.0,
            "condition_on_previous_text": True,
        },
        {
            "key": "anime_ja_large_v3",
            "label": "Anime JA — Riêng large-v3",
            "short_label": "Anime JA large-v3",
            "scope": "large-v3",
            "min_silence": 300,
            "threshold": 0.30,
            "speech_pad": 250,
            "max_speech": 6.0,
            "condition_on_previous_text": True,
        },
        {
            "key": "anime_ja_kotoba",
            "label": "Anime JA — Riêng kotoba-whisper",
            "short_label": "Anime JA Kotoba",
            "scope": "kotoba",
            "min_silence": 350,
            "threshold": 0.25,
            "speech_pad": 400,
            "max_speech": 10.0,
            "condition_on_previous_text": False,
        },
        {
            "key": "live_action",
            "label": "Live-Action / Tokusatsu (18+)",
            "short_label": "Live-Action / Tokusatsu",
            "scope": "all",
            "min_silence": 300,
            "threshold": 0.35,
            "speech_pad": 250,
            "max_speech": 6.0,
            "condition_on_previous_text": False,
        },
    )

    @classmethod
    def _is_preset_available_for_model(cls, preset_def: dict, model_id: str | None) -> bool:
        scope = preset_def.get("scope", "all")
        if scope == "all":
            return True
        lowered = str(model_id or "").strip().lower()
        if scope == "large-v3":
            return lowered == "large-v3"
        if scope == "kotoba":
            return "kotoba" in lowered
        return False

    @classmethod
    def get_fixed_vad_preset(cls, key: str | None) -> dict | None:
        from core.project.project_state import normalize_vad_preset_key

        normalized = normalize_vad_preset_key(key)
        for preset in cls._FIXED_VAD_PRESETS:
            if preset["key"] == normalized:
                return preset
        return None

    _MODEL_VAD_PROFILES = {
        "kotoba": {
            "preset_label": "Standard",
            "preset_tooltip": (
                "Preset dùng chung (350ms / 0.25 / 350ms / 8.0s) tối ưu cho thoại anime tiếng Nhật có BGM và tiếng thở.\n"
                "• Đủ nhạy để kotoba-whisper không mất từ mở đầu nhẹ (ねぇ, ほら) và giữ Max Speech 8.0s."
            ),
            "standard": dict(_STANDARD_VAD_PRESET),
            "hints": {
                "min_silence": "↑ Gộp câu dài · Kotoba gợi ý 300–400ms",
                "vad_threshold": "↑ Lọc BGM · Kotoba gợi ý 0.25–0.35",
                "speech_pad": "↑ Giữ âm cuối (わ/よ/ね) · Gợi ý 350–400ms",
                "max_speech": "↑ Cho phép câu dài · Kotoba tối ưu 8–12s",
            },
            "tooltips": {
                "min_silence": (
                    "[Model: {model}] Thời gian im lặng tối thiểu để tách câu.\n"
                    "• Đề xuất Kotoba JA: 300–400ms (mặc định 350ms) để tách tự nhiên theo nhịp thoại Nhật.\n"
                    "• Tăng (>500ms): Gộp câu dài · Giảm (<250ms): Tách câu ngắn."
                ),
                "vad_threshold": (
                    "[Model: {model}] Ngưỡng nhạy phát hiện giọng nói.\n"
                    "• Đề xuất Kotoba JA: 0.25–0.35 (mặc định 0.25) để bắt trọn âm đầu/cuối nhẹ như ねぇ/わ/よ/ね.\n"
                    "• Tăng (>0.45): Lọc BGM gắt hơn · Giảm (<0.25): Bắt tiếng thì thầm."
                ),
                "speech_pad": (
                    "[Model: {model}] Khoảng đệm mở rộng đầu và cuối câu.\n"
                    "• Đề xuất Kotoba JA: 350–400ms để giữ trọn trợ từ cuối câu (わ, よ, ね, かしら).\n"
                    "• Tăng: Chống rớt âm cuối · Giảm: Bám sát khẩu hình."
                ),
                "max_speech": (
                    "[Model: {model}] Độ dài tối đa của 1 câu phụ đề.\n"
                    "• Đề xuất Kotoba JA: 8–12s (Standard: 8.0s · Riêng Kotoba: 10.0s).\n"
                    "• Tăng: Giữ câu độc thoại dài · Giảm: Ép ngắt ngắn."
                ),
            },
        },
        "large": {
            "preset_label": "Standard",
            "preset_tooltip": (
                "Preset dùng chung (350ms / 0.25 / 350ms / 8.0s) cân bằng cho thoại anime có BGM và tiếng thở.\n"
                "• Có thể chọn thêm preset Riêng large-v3 (300ms / 0.30 / 250ms / 6.0s) hoặc Live-Action / Tokusatsu (300ms / 0.35 / 250ms / 6.0s)."
            ),
            "standard": dict(_STANDARD_VAD_PRESET),
            "hints": {
                "min_silence": "↑ Gộp câu dài · Large gợi ý 300–400ms",
                "vad_threshold": "↑ Lọc BGM · Large gợi ý 0.25–0.35",
                "speech_pad": "↑ Chống mất đầu/đuôi · Large gợi ý 250–350ms",
                "max_speech": "↑ Cho phép câu dài · Large gợi ý 6–8s",
            },
            "tooltips": {
                "min_silence": (
                    "[Model: {model}] Thời gian im lặng tối thiểu để tách câu.\n"
                    "• Standard: 350ms | Riêng large-v3 & CFG-9: 300ms.\n"
                    "• Tăng: Gộp các nhịp nghỉ ngắn thành câu dài · Giảm: Tách câu nhanh."
                ),
                "vad_threshold": (
                    "[Model: {model}] Ngưỡng nhạy phát hiện giọng nói.\n"
                    "• Standard: 0.25 | Riêng large-v3: 0.30 giúp giảm lỗi nuốt âm đầu câu.\n"
                    "• Tăng: Lọc tạp âm gắt · Giảm (0.25–0.30): Bắt tiếng nhỏ/thì thầm."
                ),
                "speech_pad": (
                    "[Model: {model}] Khoảng đệm mở rộng đầu và cuối câu.\n"
                    "• Đề xuất cho {model}: 250–350ms (Riêng large-v3: 250ms, Standard: 350ms) để giữ âm bật hơi đầu và gọn tiếng thở nền.\n"
                    "• Tăng: Chống cụt âm · Giảm: Bám sát tiếng."
                ),
                "max_speech": (
                    "[Model: {model}] Độ dài tối đa của 1 câu phụ đề.\n"
                    "• Standard: 8.0s | Riêng large-v3 & CFG-9: 6.0s hạn chế ảo giác lặp chữ khi dính tiếng thở/BGM.\n"
                    "• Tăng: Cho phép câu dài · Giảm: Ép ngắt câu."
                ),
            },
        },
        "compact": {
            "preset_label": "Standard",
            "preset_tooltip": (
                "Preset dùng chung (350ms / 0.25 / 350ms / 8.0s) cho nhóm model nhẹ/trung (tiny / base / small / medium).\n"
                "• Giữ Max Speech 8.0s giúp model nhẹ không bị lệch ngữ cảnh hay rớt chữ cuối câu."
            ),
            "standard": dict(_STANDARD_VAD_PRESET),
            "hints": {
                "min_silence": "↑ Gộp câu dài · Tiny–Med gợi ý 350–450ms",
                "vad_threshold": "↑ Lọc tạp âm · Tiny–Med gợi ý 0.25–0.40",
                "speech_pad": "↑ Chống cụt chữ · Tiny–Med gợi ý 350ms",
                "max_speech": "↑ Độ dài câu · Tiny–Med tối ưu 6–10s",
            },
            "tooltips": {
                "min_silence": (
                    "[Model: {model}] Thời gian im lặng tối thiểu để tách câu.\n"
                    "• Đề xuất Tiny–Medium: 350–450ms (mặc định 350ms) để model nhẹ không bị quá tải ngữ cảnh.\n"
                    "• Tăng: Gộp câu dài · Giảm: Tách câu vụn."
                ),
                "vad_threshold": (
                    "[Model: {model}] Ngưỡng nhạy phát hiện giọng nói.\n"
                    "• Đề xuất Tiny–Medium: 0.25–0.40 (mặc định 0.25).\n"
                    "• Tăng: Lọc nhạc nền · Giảm: Bắt âm nhẹ."
                ),
                "speech_pad": (
                    "[Model: {model}] Khoảng đệm mở rộng đầu và cuối câu.\n"
                    "• Đề xuất Tiny–Medium: 300–400ms (mặc định 350ms) giúp bù biên cắt của model nhẹ.\n"
                    "• Tăng: Chống cụt âm · Giảm: Bám sát tiếng."
                ),
                "max_speech": (
                    "[Model: {model}] Độ dài tối đa của 1 câu phụ đề.\n"
                    "• Đề xuất Tiny–Medium: <=8.0–12.0s; câu quá dài ở model nhỏ dễ mất chữ giữa/cuối câu.\n"
                    "• Tăng: Cho phép câu dài · Giảm: Ép ngắt câu."
                ),
            },
        },
    }

    def _get_model_vad_profile(self, model_id: str | None = None) -> tuple[str, dict]:
        active_model = str(
            model_id
            if model_id is not None
            else (self._get_effective_model_size() if hasattr(self, "cmb_model") else "large-v3")
        ).strip()
        lowered = active_model.lower()
        if "kotoba" in lowered:
            return active_model or "kotoba-whisper-v2.0", self._MODEL_VAD_PROFILES["kotoba"]
        if any(tag in lowered for tag in ("large-v3", "large-v2", "large-v1")):
            return active_model, self._MODEL_VAD_PROFILES["large"]
        return active_model or "small", self._MODEL_VAD_PROFILES["compact"]

    def _rebuild_vad_preset_items(self, model_name: str, profile: dict, *, fallback_to_standard: bool) -> bool:
        """Đồng bộ danh sách preset hiển thị theo model đang chọn; trả về True nếu preset cũ không còn hợp lệ và fallback về standard."""
        if not hasattr(self, "cmb_vad_preset"):
            return False
        prev_key = self.cmb_vad_preset.currentData() or "standard"
        desired: list[tuple[str, str]] = [(profile["preset_label"], "standard")]
        for preset in self._FIXED_VAD_PRESETS:
            if self._is_preset_available_for_model(preset, model_name):
                desired.append((preset["label"], preset["key"]))
        desired.append(("Custom", "custom"))

        current = [
            (self.cmb_vad_preset.itemText(i), self.cmb_vad_preset.itemData(i))
            for i in range(self.cmb_vad_preset.count())
        ]
        if current == desired:
            return False

        fell_back_to_standard = False
        self._updating_vad_preset = True
        self.cmb_vad_preset.blockSignals(True)
        try:
            self.cmb_vad_preset.clear()
            for label, key in desired:
                self.cmb_vad_preset.addItem(label, key)
            idx = self.cmb_vad_preset.findData(prev_key)
            if idx >= 0:
                self.cmb_vad_preset.setCurrentIndex(idx)
            else:
                target = "standard" if fallback_to_standard else "custom"
                fell_back_to_standard = target == "standard"
                t_idx = self.cmb_vad_preset.findData(target)
                self.cmb_vad_preset.setCurrentIndex(t_idx if t_idx >= 0 else 0)
        finally:
            self.cmb_vad_preset.blockSignals(False)
            self._updating_vad_preset = False
        return fell_back_to_standard

    def _refresh_vad_guidance_for_model(self, *, apply_values: bool = False) -> None:
        if not hasattr(self, "spin_min_silence"):
            return
        model_name, profile = self._get_model_vad_profile()
        row_widgets = getattr(self, "_vad_row_widgets", {})

        fell_back = False
        if hasattr(self, "cmb_vad_preset"):
            fell_back = self._rebuild_vad_preset_items(
                model_name,
                profile,
                fallback_to_standard=(apply_values and not getattr(self, "_restoring_timing_settings", False)),
            )
            preset_row = row_widgets.get("vad_preset")
            if preset_row:
                lbl, widget, _ = preset_row
                lbl.setToolTip(profile["preset_tooltip"])
                widget.setToolTip(profile["preset_tooltip"])

        self._refresh_vad_preset_hints()

        if apply_values and not getattr(self, "_restoring_timing_settings", False):
            current_preset = self.cmb_vad_preset.currentData() if hasattr(self, "cmb_vad_preset") else "standard"
            if current_preset == "standard" or fell_back:
                std = profile["standard"]
                self._updating_vad_preset = True
                try:
                    if hasattr(self, "cmb_vad_preset"):
                        std_idx = self.cmb_vad_preset.findData("standard")
                        if std_idx >= 0:
                            self.cmb_vad_preset.setCurrentIndex(std_idx)
                    self.spin_min_silence.setValue(int(std["min_silence"]))
                    self.spin_vad_threshold.setValue(float(std["threshold"]))
                    self.spin_speech_pad.setValue(int(std["speech_pad"]))
                    self.spin_max_speech.setValue(float(std["max_speech"]))
                    if hasattr(self, "chk_condition_on_previous_text"):
                        self.chk_condition_on_previous_text.setChecked(
                            "kotoba" not in model_name.lower()
                        )
                finally:
                    self._updating_vad_preset = False
                self._refresh_vad_preset_hints()

    def _refresh_vad_preset_hints(self) -> None:
        """Đồng bộ chú thích cạnh từng ô thông số VAD theo model và preset đang chọn."""
        row_widgets = getattr(self, "_vad_row_widgets", {})
        if not row_widgets:
            return
        from core.project.project_state import normalize_vad_preset_key

        model_name, profile = self._get_model_vad_profile()
        preset_key = normalize_vad_preset_key(
            self.cmb_vad_preset.currentData() if hasattr(self, "cmb_vad_preset") else "standard"
        )
        hints = dict(profile["hints"])
        if preset_key == "live_action":
            hints["vad_threshold"] = "↑ Lọc BGM/SFX · Tokusatsu gợi ý 0.35"
            hints["speech_pad"] = "↑ Gọn tiếng thở · Tokusatsu gợi ý 250ms"
            hints["max_speech"] = "↑ Độc thoại gọn · Tokusatsu gợi ý 5–6s"
        for key in ("min_silence", "vad_threshold", "speech_pad", "max_speech"):
            entry = row_widgets.get(key)
            if not entry:
                continue
            lbl, widget, hint_lbl = entry
            tip = profile["tooltips"][key].format(model=model_name)
            lbl.setToolTip(tip)
            widget.setToolTip(tip)
            if hint_lbl is not None:
                hint_lbl.setText(hints[key])
                hint_lbl.setToolTip(tip)

    def _on_model_selection_changed(self, *_args, apply_vad_defaults: bool = True) -> None:
        """Show/hide Download and Delete buttons based on whether selected model is installed."""
        from core.services.model_manager import ModelManager
        size = self.cmb_model.currentData()
        installed = ModelManager.is_installed(size) if size else False
        self.btn_download_model.setVisible(not installed)
        if hasattr(self, "btn_delete_model"):
            self.btn_delete_model.setVisible(installed)
        if not getattr(self, "cmb_specialized_model", None) or not self.cmb_specialized_model.currentData():
            self._refresh_vad_guidance_for_model(apply_values=apply_vad_defaults)

    def _sync_model_box_exclusivity(self) -> None:
        """Khóa Model Size chung khi đang chọn model Chuyên Ngữ để tránh hiểu nhầm chạy 2 model song song."""
        if not hasattr(self, "cmb_specialized_model") or not hasattr(self, "cmb_model"):
            return
        running = hasattr(self, "_is_any_service_running") and self._is_any_service_running()
        if running:
            return
        has_spec = bool(self._combo_value(self.cmb_specialized_model))
        self.cmb_model.setEnabled(not has_spec)
        if hasattr(self, "btn_download_model"):
            self.btn_download_model.setEnabled(not has_spec)
        if hasattr(self, "btn_delete_model"):
            self.btn_delete_model.setEnabled(not has_spec)
        if has_spec:
            self.cmb_model.setToolTip(
                "Đang dùng Model Chuyên Ngữ bên dưới. Chọn '— Không dùng —' ở Chuyên Ngữ để dùng lại Model Size."
            )
        else:
            self.cmb_model.setToolTip("Chọn kích thước Whisper chuẩn để tạo Timing / Phụ đề.")

    def _on_specialized_model_selection_changed(self, *_args, apply_vad_defaults: bool = True) -> None:
        """Show/hide Download and Delete buttons for specialized ASR model."""
        if not hasattr(self, "cmb_specialized_model"):
            return
        from core.services.model_manager import ModelManager
        model_id = self.cmb_specialized_model.currentData()
        if not model_id:
            self.btn_download_specialized_model.setVisible(False)
            self.btn_delete_specialized_model.setVisible(False)
            self._sync_model_box_exclusivity()
            self._refresh_vad_guidance_for_model(apply_values=apply_vad_defaults)
            return
        installed = ModelManager.is_installed(model_id)
        self.btn_download_specialized_model.setVisible(not installed)
        self.btn_delete_specialized_model.setVisible(installed)
        self._sync_model_box_exclusivity()
        self._refresh_vad_guidance_for_model(apply_values=apply_vad_defaults)

    def _delete_model_for(self, combo, refresh_fn) -> None:
        from core.services.model_manager import ModelManager
        from PySide6.QtWidgets import QMessageBox

        size = combo.currentData() if combo is not None else None
        if not size or not ModelManager.is_installed(size):
            return

        spec_info = ModelManager.get_specialized_info(size)
        weight = spec_info["weight"] if spec_info else ModelManager.SUPPORTED_MODELS.get(size, "")
        confirm = QMessageBox.question(
            self,
            "Xác nhận xóa Model",
            f"Bạn có chắc muốn xóa mô hình '{size}' ({weight}) khỏi ổ đĩa?\n\n"
            "Thao tác này sẽ giải phóng dung lượng ổ đĩa. Bạn có thể tải lại bất kỳ lúc nào.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            whisper_service = getattr(self.generation_service, "whisper_service", None)
            if whisper_service and getattr(whisper_service, "current_model_size", None) == size:
                whisper_service.unload_model()
            win = self.window()
            win_whisper = getattr(win, "subtitle_whisper_service", None)
            if win_whisper and getattr(win_whisper, "current_model_size", None) == size:
                win_whisper.unload_model()

            deleted = ModelManager.delete_model(size)
            refresh_fn(preferred=size)
            if deleted:
                from ui.toast import Toast
                Toast.show_success(self, f"Đã xóa thành công model '{size}'")
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi khi xóa Model", f"Không thể xóa model '{size}': {exc}")

    def _download_model_for(self, combo, btn_dl, refresh_fn) -> None:
        if self._is_any_service_running():
            return
        from PySide6.QtCore import QThread
        from core.services.model_manager import ModelManager

        size = combo.currentData() if combo is not None else None
        if not size:
            return
        if ModelManager.is_installed(size):
            refresh_fn(preferred=size)
            return

        btn_dl.setEnabled(False)
        btn_dl.setText("Đang tải…")
        self.lbl_effective_compute.setText(f"Đang tải {size}…")

        class _DlThread(QThread):
            def __init__(self, model_size):
                super().__init__()
                self._size = model_size
                self.error = None
            def run(self):
                try:
                    ModelManager.download_model_sync(self._size)
                except Exception as exc:
                    self.error = exc

        thread = _DlThread(size)
        thread.setParent(self)

        def _done():
            btn_dl.setEnabled(True)
            btn_dl.setText("⬇ Download")
            self.lbl_effective_compute.setText("Effective: not run")
            refresh_fn(preferred=size)
            if thread.error is not None:
                QMessageBox.warning(self, "Lỗi tải Model", f"Không thể tải '{size}': {thread.error}")

        thread.finished.connect(_done)
        thread.start()

    def _on_delete_model_clicked(self) -> None:
        """Confirm and delete the currently selected installed model."""
        self._delete_model_for(self.cmb_model, self._populate_model_combo)

    def _on_download_model_clicked(self) -> None:
        """Trigger background download for the currently selected uninstalled model."""
        self._download_model_for(self.cmb_model, self.btn_download_model, self._populate_model_combo)

    def _on_delete_specialized_model_clicked(self) -> None:
        self._delete_model_for(
            getattr(self, "cmb_specialized_model", None),
            self._populate_specialized_model_combo,
        )

    def _on_download_specialized_model_clicked(self) -> None:
        self._download_model_for(
            getattr(self, "cmb_specialized_model", None),
            getattr(self, "btn_download_specialized_model", None),
            self._populate_specialized_model_combo,
        )

    # ── Compute type recommendation ───────────────────────────────────────────

    def _populate_compute_combo(self) -> None:
        """Populate compute combo with ★ marker on the option best for this machine."""
        try:
            import torch
            has_cuda = torch.cuda.is_available()
            vram_gb = (
                torch.cuda.get_device_properties(0).total_memory // (1024 ** 3)
                if has_cuda else 0
            )
        except Exception:
            has_cuda = False
            vram_gb = 0

        # Determine recommended option:
        # GPU >= 6 GB VRAM → float16 (fastest, full precision)
        # GPU <= 4.5 GB VRAM (e.g. RTX 3050 4GB) → int8_float16 (saves VRAM, prevents OOM on large-v3)
        # CPU only         → int8 (CPU only option)
        if has_cuda and vram_gb >= 6:
            recommended = "float16"
        elif has_cuda:
            recommended = "int8_float16"
        else:
            recommended = "int8"

        options = ["float16", "int8_float16", "int8"]
        self.cmb_compute.clear()
        for opt in options:
            label = f"{opt}  (Khuyên dùng)" if opt == recommended else opt
            self.cmb_compute.addItem(label, opt)
        # Select recommended by default
        for i in range(self.cmb_compute.count()):
            if self.cmb_compute.itemData(i) == recommended:
                self.cmb_compute.setCurrentIndex(i)
                break

    def apply_recommended_settings(self, model: str, compute: str) -> None:
        """Apply recommended model and compute type to panel combos."""
        try:
            from core.services.model_manager import ModelManager
            info = {m["size"]: m["installed"] for m in ModelManager.get_discovery_list()}
            if not info.get(model, False) and any(info.values()):
                model = self._select_best_model(info, model)
        except Exception:
            pass
        for i in range(self.cmb_model.count()):
            if self.cmb_model.itemData(i) == model:
                self.cmb_model.setCurrentIndex(i)
                break
        for i in range(self.cmb_compute.count()):
            if self.cmb_compute.itemData(i) == compute:
                self.cmb_compute.setCurrentIndex(i)
                break

    def set_context_status(self, compiled, configured: bool) -> None:
        self._context_compiled = compiled
        self._context_configured = configured
        self._render_context_status()

    def _render_context_status(self) -> None:
        label = getattr(self, "context_status_label", None)
        if label is None:
            return
        if self._is_timing_mode():
            label.setText("Context: not used in Timing Draft")
            return
        if not self._context_configured or self._context_compiled is None:
            label.setText("Context: not configured")
            return
        compiled = self._context_compiled
        total_glossary = compiled.glossary_items_used + compiled.glossary_items_dropped
        label.setText(
            "Context: configured · "
            f"{compiled.glossary_items_used}/{total_glossary} glossary · "
            f"~{compiled.token_count}/{compiled.max_tokens} tokens"
        )

    @Slot()
    def _on_mode_changed(self):
        """Apply the settings policy for the selected generation pipeline."""
        is_asr = self.cmb_mode.currentData() == "asr"

        # Lock each control directly so a stylesheet cannot hide the disabled
        # state of the individual model settings.
        self.model_group.setEnabled(True)
        self.cmb_model.setEnabled(True)
        if hasattr(self, "cmb_specialized_model"):
            self.cmb_specialized_model.setEnabled(True)
            self._sync_model_box_exclusivity()
        self.cmb_compute.setEnabled(True)
        self.cmb_language.setEnabled(True)
        self.chk_word_timestamps.setEnabled(is_asr)
        self.cmb_batch_mode.setEnabled(True)
        # Timing Draft accepts both the legacy time setting and its native
        # segment-count setting. The worker already consumes this value as a
        # target segment count.
        self.spin_batch_val.setEnabled(True)

        if is_asr:
            self.chk_vad.setEnabled(True)
            self.chk_vad.setText("Enable VAD (Lọc khoảng lặng)")
        else:
            self.chk_vad.setChecked(True)
            self.chk_vad.setEnabled(False)
            self.chk_vad.setText("Enable VAD (Bắt buộc cho chế độ này)")

        if hasattr(self, "btn_generate"):
            self.btn_generate.setText("Generate Subtitle" if is_asr else "Generate Timing")

        fix_overlap = getattr(self, "chk_fix_overlap", None)
        overlap_gap = getattr(self, "spin_overlap_gap", None)
        if fix_overlap is not None:
            fix_overlap.setEnabled(not is_asr)
        if overlap_gap is not None:
            overlap_gap.setEnabled(not is_asr and self._is_ctrl_checked(fix_overlap))

        if not (hasattr(self, "_is_any_service_running") and self._is_any_service_running()):
            for ctrl_name in (
                "cmb_vad_preset", "spin_min_silence", "spin_vad_threshold",
                "spin_speech_pad", "spin_max_speech", "chk_condition_on_previous_text",
                "chk_apply_preset_rescan",
                "chk_music_mode", "btn_download_model", "btn_delete_model",
                "cmb_specialized_model", "btn_download_specialized_model", "btn_delete_specialized_model",
                "cmb_subtitle_source", "btn_add_external_srt", "cmb_range_unit",
                "txt_start", "txt_end", "btn_range_timeline", "btn_range_preview",
                "btn_context_edit",
            ):
                ctrl = getattr(self, ctrl_name, None)
                if ctrl is not None and hasattr(ctrl, "setEnabled"):
                    ctrl.setEnabled(True)
            if hasattr(self, "_on_model_selection_changed"):
                try:
                    self._on_model_selection_changed(apply_vad_defaults=False)
                except Exception:
                    pass
            if hasattr(self, "_sync_model_box_exclusivity"):
                try:
                    self._sync_model_box_exclusivity()
                except Exception:
                    pass

        if hasattr(self, "btn_resume"):
            self.check_resumable_state()
        self.refresh_batch_mode_availability()
        self._render_context_status()

    def _is_timing_mode(self) -> bool:
        return self.cmb_mode.currentData() == "timing"

    def _on_task_mode_changed(self, *_args):
        if getattr(self, "_restoring_timing_settings", False):
            return
        project_service = getattr(self.generation_service, "project_service", None)
        project = getattr(project_service, "current_project", None)
        state = getattr(project, "state", None)
        if state is None or not hasattr(state, "task_mode"):
            return
        state.task_mode = self.cmb_mode.currentData()
        project_service.mark_dirty()

    @Slot()
    def _on_batch_mode_changed(self):
        """Update batch-value range and suffix for the selected mode."""
        if (
            self.cmb_batch_mode.currentData() == "segments"
            and not self._is_timing_mode()
            and not self._timing_segments_available()
        ):
            res = QMessageBox.question(
                self,
                "Yêu cầu Timing Draft",
                "Chế độ băm theo số câu (Segment-based) cần mốc câu có sẵn từ Timing Draft để Whisper biết vị trí từng câu.\n\n"
                "Bạn có muốn chuyển sang chế độ 'Timing Draft (VAD Only)' để tạo mốc câu trước không (chỉ mất vài giây)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if res == QMessageBox.Yes:
                idx = self.cmb_mode.findData("timing") if hasattr(self.cmb_mode, "findData") else -1
                if idx >= 0:
                    self.cmb_mode.setCurrentIndex(idx)
                    if hasattr(self.spin_batch_val, "setRange"):
                        self.spin_batch_val.setRange(5, 50)
                        self.spin_batch_val.setValue(10)
                        self.spin_batch_val.setSuffix(" segs")
                    return
            self.cmb_batch_mode.setCurrentIndex(0)
            return
        self._sync_batch_spin_limits(reset_default=True)

    def _get_timing_segment_counts(self) -> tuple[int, int]:
        live = []
        if hasattr(self, "_get_current_segments"):
            try:
                live = self._get_current_segments() or []
            except Exception:
                live = []
        if live:
            from core.subtitle_generation.generation_service import SubtitleGenerationService
            unfilled = 0
            for seg in live:
                txt = str(seg.get("text", "") if isinstance(seg, dict) else "").strip()
                if SubtitleGenerationService._is_unfilled_timing_text(txt):
                    unfilled += 1
            return len(live), unfilled
        gen_svc = getattr(self, "generation_service", None)
        if gen_svc is not None and hasattr(gen_svc, "get_timing_segment_counts"):
            try:
                return gen_svc.get_timing_segment_counts()
            except Exception:
                pass
        return 0, 0

    def _sync_batch_spin_limits(self, reset_default: bool = False):
        if not hasattr(self, "cmb_batch_mode") or not hasattr(self, "spin_batch_val"):
            return
        hint_lbl = getattr(self, "lbl_batch_size_hint", None)
        if self.cmb_batch_mode.currentData() == "time":
            if hasattr(self.spin_batch_val, "setRange"):
                self.spin_batch_val.setRange(1, 30)
            if reset_default and hasattr(self.spin_batch_val, "setValue"):
                self.spin_batch_val.setValue(5)
            if hasattr(self.spin_batch_val, "setSuffix"):
                self.spin_batch_val.setSuffix(" min")
            if hint_lbl is not None:
                hint_lbl.setText("")
            return

        if hasattr(self.spin_batch_val, "setSuffix"):
            self.spin_batch_val.setSuffix(" segs")
        if self._is_timing_mode():
            if hasattr(self.spin_batch_val, "setRange"):
                self.spin_batch_val.setRange(5, 50)
            if reset_default and hasattr(self.spin_batch_val, "setValue"):
                self.spin_batch_val.setValue(10)
            if hint_lbl is not None:
                hint_lbl.setText("")
            return

        total_count, pending_count = self._get_timing_segment_counts()
        if total_count > 0:
            if hasattr(self.spin_batch_val, "setRange"):
                self.spin_batch_val.setRange(1, total_count)
            cur_val = self.spin_batch_val.value() if hasattr(self.spin_batch_val, "value") else 5
            if reset_default and hasattr(self.spin_batch_val, "setValue"):
                target_val = min(5, pending_count if pending_count > 0 else total_count, total_count)
                self.spin_batch_val.setValue(max(1, target_val))
            elif hasattr(self.spin_batch_val, "setValue") and (cur_val > total_count or cur_val < 1):
                self.spin_batch_val.setValue(max(1, min(cur_val, total_count)))
            if hint_lbl is not None:
                hint_lbl.setText(f"Tổng {total_count} câu · {pending_count} câu trống")
        else:
            if hasattr(self.spin_batch_val, "setRange"):
                self.spin_batch_val.setRange(5, 50)
            if reset_default and hasattr(self.spin_batch_val, "setValue"):
                self.spin_batch_val.setValue(10)
            if hint_lbl is not None:
                hint_lbl.setText("")

    def set_video_duration(self, duration_ms: int):
        self.video_duration_ms = max(0, int(duration_ms or 0))
        self.refresh_batch_mode_availability()

    def _has_timing_artifact(self) -> bool:
        project_service = getattr(self.generation_service, "project_service", None)
        project = getattr(project_service, "current_project", None)
        timing_state = getattr(getattr(project, "state", None), "timing", None)
        artifact_id = getattr(timing_state, "timing_artifact_id", None)
        store = getattr(project_service, "artifact_store", None)
        artifact = store.get(artifact_id) if store and artifact_id else None
        return bool(artifact and getattr(artifact, "path", None))

    def _timing_segments_available(self) -> bool:
        project_service = getattr(self.generation_service, "project_service", None)
        project = getattr(project_service, "current_project", None)
        timing_status = getattr(
            getattr(project, "state", None), "timing_status", None
        )
        if timing_status in {"DRAFT", "READY"} and self._has_timing_artifact():
            return True
        return self._get_timing_segment_counts()[0] > 0

    def refresh_batch_mode_availability(self):
        """Allow true segment-count batching only when Timing ranges exist; hide otherwise."""
        if not hasattr(self, "cmb_batch_mode"):
            return
        seg_idx = -1
        if hasattr(self.cmb_batch_mode, "findData"):
            seg_idx = self.cmb_batch_mode.findData("segments")
        if seg_idx < 0:
            seg_idx = 1
        item = (
            self.cmb_batch_mode.model().item(seg_idx)
            if hasattr(self.cmb_batch_mode, "model")
            else None
        )
        if item is None:
            return
        # Timing Draft is what creates the Timing Artifact, so it must be
        # allowed to use segment-count batching before an artifact exists.
        enabled = self._is_timing_mode() or (
            self._timing_segments_available()
        )
        if hasattr(item, "setEnabled"):
            item.setEnabled(enabled)
        view = getattr(self.cmb_batch_mode, "view", None)
        if callable(view):
            v = view()
            if hasattr(v, "setRowHidden"):
                v.setRowHidden(seg_idx, not enabled)
        if not enabled and self.cmb_batch_mode.currentData() == "segments":
            self.cmb_batch_mode.setCurrentIndex(0)
        self._sync_batch_spin_limits(reset_default=False)

    def check_resumable_state(self):
        if self._is_any_service_running():
            return
        current_request = getattr(self.generation_service, "current_request", None)
        current_checkpoint = getattr(self.generation_service, "current_checkpoint", None)
        range_run_terminal = bool(
            current_request
            and current_request.range_start_ms is not None
            and current_checkpoint
            and current_checkpoint.status in {"COMPLETED", "CANCELLED", "FAILED"}
        )
        if range_run_terminal:
            resumable = False
        elif self._is_timing_mode():
            resumable = self._has_resumable_timing_checkpoint()
        else:
            checkpoint = self.generation_service.checkpoint_manager.load_checkpoint()
            resumable = bool(
                checkpoint
                and checkpoint.status in {"RUNNING", "CANCELLED", "FAILED"}
            )
        self.btn_resume.setVisible(resumable)
        service_running = self._is_any_service_running()
        self.btn_resume.setEnabled(resumable and not service_running)

    def _has_resumable_timing_checkpoint(self) -> bool:
        project_service = getattr(self.generation_service, "project_service", None)
        load_checkpoint = getattr(project_service, "load_timing_checkpoint", None)
        checkpoint = load_checkpoint() if callable(load_checkpoint) else None
        if not checkpoint:
            return False

        project = getattr(project_service, "current_project", None)
        timing_state = getattr(getattr(project, "state", None), "timing", None)
        if getattr(timing_state, "status", None) == "COMPLETED":
            return False
        active_batch = getattr(checkpoint, "active_batch", None)
        return bool(active_batch and active_batch.get("status") in {"RUNNING", "FAILED", "CANCELLED"})

    @Slot()
    def _on_generate_clicked(self):
        if self.video_duration_ms <= 0:
            project = getattr(
                getattr(self.generation_service, "project_service", None),
                "current_project",
                None,
            )
            video_path = getattr(getattr(project, "source", None), "path", "")
            if video_path and os.path.exists(video_path):
                try:
                    from workers.TaskQueue import get_video_duration

                    dur_sec = get_video_duration(video_path)
                    if dur_sec > 0:
                        self.set_video_duration(int(dur_sec * 1000))
                except Exception:
                    pass

        if self.video_duration_ms <= 0:
            QMessageBox.warning(self, "Lỗi", "Chưa tải Video hoặc không đọc được thời lượng.")
            return

        if self._is_timing_mode():
            timing_settings = self._timing_settings()
            self._timing_start_fresh = False
            if self._has_resumable_timing_checkpoint():
                reply = QMessageBox.question(
                    self,
                    "Tiến trình Timing Draft",
                    "Đã tìm thấy tiến trình Timing trước đó chưa hoàn thành.\n\n"
                    "• Bấm 'Yes' để Tiếp tục (Resume) từ vị trí đang dở.\n"
                    "• Bấm 'No' để Bắt đầu lại từ đầu (Start Fresh).",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Cancel:
                    return
                self._set_ui_state_running()
                if reply == QMessageBox.Yes:
                    self.timing_resume_requested.emit(
                        self.spin_batch_val.value(), timing_settings
                    )
                else:
                    self._timing_start_fresh = True
                    self.timing_start_requested.emit(
                        self.spin_batch_val.value(), timing_settings
                    )
            else:
                self._set_ui_state_running()
                project_service = getattr(self.generation_service, "project_service", None)
                load_checkpoint = getattr(project_service, "load_timing_checkpoint", None)
                checkpoint = load_checkpoint() if callable(load_checkpoint) else None
                signal = (
                    self.timing_resume_requested
                    if checkpoint and checkpoint.timing_artifact_id
                    else self.timing_start_requested
                )
                signal.emit(self.spin_batch_val.value(), timing_settings)
            return

        request = self._build_asr_request()
        if request is None:
            return

        self._set_ui_state_running()
        try:
            self.generation_service.start_generation(request, self.video_duration_ms)
        except Exception as exc:
            self._on_error(str(exc))

    def _build_asr_request(self, range_start_ms=None, range_end_ms=None):
        project = self.generation_service.project_service.current_project
        if not project:
            QMessageBox.warning(self, "Lỗi", "Chưa có dự án nào được mở.")
            return None
        source = getattr(project, "source", None)
        video_path = getattr(source, "path", "")
        if not video_path:
            QMessageBox.warning(self, "Lỗi", "Không tìm thấy đường dẫn Video gốc trong Dự án.")
            return None
        from core.subtitle_generation.language_utils import (
            extract_glossary_hotwords,
            normalize_to_iso_code,
        )
        from core.subtitle_generation.faster_whisper_service import FasterWhisperService
        from core.services.model_manager import ModelManager

        effective_model = self._get_effective_model_size()
        spec_info = ModelManager.get_specialized_info(effective_model)

        tx_ctx = getattr(project, "transcription_context", None)
        ref_story_summary = str(getattr(tx_ctx, "context", "") or "").strip()
        language = self.cmb_language.currentText()
        final_lang = None if (not language or language == "Auto Detect") else language
        if final_lang is None:
            win = self.window()
            proj_ctrl = getattr(getattr(win, "page_translation", None), "project_controller", None)
            if proj_ctrl and getattr(proj_ctrl, "_is_ja_origin", False):
                final_lang = "ja"
        if final_lang is None and spec_info is not None:
            final_lang = spec_info.get("language")

        # Tách triệt để Tóm tắt cốt truyện khỏi ASR ở mọi Preset/Model; chỉ dùng Từ điển (hotwords) cho non-Kotoba
        prompt_text = ""
        if FasterWhisperService.is_kotoba_model(effective_model) or not ModelManager.supports_word_timestamps(effective_model):
            hotwords = ""
        else:
            hotwords = extract_glossary_hotwords(tx_ctx)

        min_sil = self.spin_min_silence.value() if hasattr(self, "spin_min_silence") else self._STANDARD_VAD_PRESET["min_silence"]
        vad_thresh = self.spin_vad_threshold.value() if hasattr(self, "spin_vad_threshold") else self._STANDARD_VAD_PRESET["threshold"]
        vad_pad = self.spin_speech_pad.value() if hasattr(self, "spin_speech_pad") else self._STANDARD_VAD_PRESET["speech_pad"]
        vad_max_sp = self.spin_max_speech.value() if hasattr(self, "spin_max_speech") else self._STANDARD_VAD_PRESET["max_speech"]
        cond_prev = self._is_ctrl_checked(getattr(self, "chk_condition_on_previous_text", None), default=True)
        return SubtitleGenerationRequest(
            request_id=str(uuid.uuid4()),
            project_id=project.project_id,
            source_fingerprint=getattr(source, "fingerprint", ""),
            video_path=video_path,
            model_size=effective_model,
            compute_type=self._combo_value(self.cmb_compute),
            language=final_lang,
            use_vad=self._is_ctrl_checked(getattr(self, "chk_vad", None), default=True),
            min_silence_ms=min_sil,
            word_timestamps=self._is_ctrl_checked(getattr(self, "chk_word_timestamps", None), default=False),
            batch_mode=self.cmb_batch_mode.currentData(),
            batch_size_value=self.spin_batch_val.value(),
            overlap_ms=2000,
            prompt_context=prompt_text,
            range_start_ms=range_start_ms,
            range_end_ms=range_end_ms,
            condition_on_previous_text=cond_prev,
            vad_threshold=vad_thresh,
            vad_speech_pad_ms=vad_pad,
            vad_max_speech_duration_s=vad_max_sp,
            min_speech_duration_ms=120,
            speech_filter=True,
            hotwords=hotwords,
            reference_context=ref_story_summary,
            patience=1.5,
            hallucination_silence_threshold=2.5,
        )

    def start_range_generation(self, start_ms, end_ms, existing_segments):
        if self.video_duration_ms <= 0 or self._is_timing_mode():
            self._on_error("Range generation requires loaded media in Full Subtitle mode.")
            return
        request = self._build_asr_request(start_ms, end_ms)
        if request is None:
            return
        self._set_ui_state_running()
        try:
            self.generation_service.start_generation(
                request,
                self.video_duration_ms,
                existing_segments=existing_segments,
            )
        except Exception as exc:
            self._on_error(self._range_error_message(str(exc)))

    @staticmethod
    def _range_error_message(message):
        if message.startswith("TIMING_RECONCILIATION_REQUIRED:"):
            return "Kết quả phụ đề vượt ngoài khoảng thời gian đã chọn. Khoảng hiện có chưa được thay đổi."
        if message.startswith("STALE_RANGE_CONFLICT:"):
            return "Khoảng đã chọn đã thay đổi. Vui lòng kiểm tra lại trước khi tạo."
        if message.startswith("RECONCILIATION_UNSAFE:"):
            return "Không thể tự điều chỉnh thời gian an toàn. Phụ đề chưa được thêm."
        if message.startswith("OVERLAPS_SUBTITLE:"):
            return "Khoảng đã chọn hiện có phụ đề; hãy chọn một khoảng trống khác."
        return message

    @Slot()
    def _on_resume_clicked(self):
        self._set_ui_state_running()
        try:
            if self._is_timing_mode():
                self.timing_resume_requested.emit(
                    self.spin_batch_val.value(),
                    self._timing_settings(),
                )
            else:
                self.generation_service.resume_generation()
        except Exception as exc:
            self._on_error(str(exc))

    @Slot()
    def _on_cancel_clicked(self):
        self.lbl_status.setText("Cancelling...")
        self.btn_cancel.setEnabled(False)
        if self._is_timing_mode():
            self.timing_cancel_requested.emit()
        else:
            self.generation_service.cancel_generation()

    def _get_window(self):
        try:
            if callable(getattr(self, "window", None)):
                return self.window()
        except (RuntimeError, Exception):
            return None
        return None

    def _is_any_service_running(self) -> bool:
        def _check_running(obj):
            if obj is None:
                return False
            is_run = getattr(obj, "is_running", None)
            if is_run is not None:
                res = is_run() if callable(is_run) else is_run
                if res is True or (isinstance(res, bool) and res):
                    return True
            is_running_method = getattr(obj, "isRunning", None)
            if callable(is_running_method):
                res = is_running_method()
                if res is True or (isinstance(res, bool) and res):
                    return True
            return False

        if _check_running(getattr(self, "generation_service", None)):
            return True
        win = self._get_window()
        timing_svc = getattr(win, "timing_service", None) if win is not None else getattr(self, "timing_service", None)
        if _check_running(timing_svc):
            return True
        return False

    def _set_ui_state_running(self):
        self.btn_rollback.setEnabled(False)
        self.history_list.setEnabled(False)
        for button in (self.btn_rb_10, self.btn_rb_30, self.btn_rb_50, self.btn_rb_60, self.btn_rb_initial):
            button.setEnabled(False)
        self.btn_generate.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.cmb_mode.setEnabled(False)
        self.cmb_model.setEnabled(False)
        self.cmb_compute.setEnabled(False)
        self.cmb_language.setEnabled(False)
        self.cmb_batch_mode.setEnabled(False)
        self.spin_batch_val.setEnabled(False)
        self.chk_vad.setEnabled(False)
        self.chk_word_timestamps.setEnabled(False)
        if hasattr(self, "chk_fix_overlap"):
            self.chk_fix_overlap.setEnabled(False)
        if hasattr(self, "spin_overlap_gap"):
            self.spin_overlap_gap.setEnabled(False)
        for ctrl_name in (
            "cmb_vad_preset", "spin_min_silence", "spin_vad_threshold",
            "spin_speech_pad", "spin_max_speech", "chk_condition_on_previous_text",
            "chk_apply_preset_rescan",
            "chk_music_mode", "btn_download_model", "btn_delete_model",
            "cmb_specialized_model", "btn_download_specialized_model", "btn_delete_specialized_model",
            "cmb_subtitle_source", "btn_add_external_srt", "cmb_range_unit",
            "txt_start", "txt_end", "btn_range_timeline", "btn_range_preview",
            "btn_context_edit",
        ):
            ctrl = getattr(self, ctrl_name, None)
            if ctrl is not None and hasattr(ctrl, "setEnabled"):
                ctrl.setEnabled(False)
        win = self._get_window()
        timeline = getattr(win, "timeline_widget", None) if win is not None else None
        if timeline is not None and hasattr(timeline, "set_generation_busy"):
            timeline.set_generation_busy(True)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setStyleSheet(f"color: {Theme.TEXT_PRIMARY};")

    def _reset_ui_state(self):
        service_running = self._is_any_service_running()
        if service_running:
            # A cancel/error callback must not re-enable controls while the
            # underlying QThread is still winding down.
            self._set_ui_state_running()
            return
        win = self._get_window()
        timeline = getattr(win, "timeline_widget", None) if win is not None else None
        if timeline is not None and hasattr(timeline, "set_generation_busy"):
            timeline.set_generation_busy(False)
        self.btn_generate.setEnabled(True)
        self.cmb_mode.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.cmb_batch_mode.setEnabled(True)
        self.spin_batch_val.setEnabled(True)
        for ctrl_name in (
            "cmb_vad_preset", "spin_min_silence", "spin_vad_threshold",
            "spin_speech_pad", "spin_max_speech", "chk_condition_on_previous_text",
            "chk_apply_preset_rescan",
            "chk_music_mode", "btn_download_model", "btn_delete_model",
            "cmb_specialized_model", "btn_download_specialized_model", "btn_delete_specialized_model",
            "cmb_subtitle_source", "btn_add_external_srt", "cmb_range_unit",
            "txt_start", "txt_end", "btn_range_timeline", "btn_range_preview",
            "btn_context_edit",
        ):
            ctrl = getattr(self, ctrl_name, None)
            if ctrl is not None and hasattr(ctrl, "setEnabled"):
                ctrl.setEnabled(True)
        if hasattr(self, "_on_model_selection_changed"):
            try:
                self._on_model_selection_changed(apply_vad_defaults=False)
            except Exception:
                pass
        if hasattr(self, "_on_specialized_model_selection_changed"):
            try:
                self._on_specialized_model_selection_changed(apply_vad_defaults=False)
            except Exception:
                pass
        self.check_resumable_state()
        # Re-apply the current mode after every run/error/cancel transition.
        self._on_mode_changed()
        self.history_list.setEnabled(True)
        self.refresh_history()
        # Nếu không còn tác vụ nào đang chạy, đảm bảo thanh tiến trình trả về 0
        if self.progress_bar.value() == 100:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(800, lambda: self.progress_bar.setValue(0))

    def _on_vad_preset_changed(self, *_args):
        if getattr(self, "_restoring_timing_settings", False) or getattr(self, "_updating_vad_preset", False):
            return
        preset = self.cmb_vad_preset.currentData() if hasattr(self, "cmb_vad_preset") else "standard"
        fixed_preset = self.get_fixed_vad_preset(preset)
        self._updating_vad_preset = True
        try:
            model_name, profile = self._get_model_vad_profile()
            if fixed_preset is not None:
                from core.services.model_manager import ModelManager
                self.chk_vad.setChecked(True)
                self.chk_word_timestamps.setChecked(
                    True if preset == "cfg9" else ModelManager.supports_word_timestamps(model_name)
                )
                self.spin_min_silence.setValue(int(fixed_preset["min_silence"]))
                self.spin_vad_threshold.setValue(float(fixed_preset["threshold"]))
                self.spin_speech_pad.setValue(int(fixed_preset["speech_pad"]))
                self.spin_max_speech.setValue(float(fixed_preset["max_speech"]))
                if hasattr(self, "chk_condition_on_previous_text") and "condition_on_previous_text" in fixed_preset:
                    self.chk_condition_on_previous_text.setChecked(
                        bool(fixed_preset["condition_on_previous_text"])
                    )
                if hasattr(self, "chk_apply_preset_rescan"):
                    self.chk_apply_preset_rescan.setChecked(True)
            elif preset == "standard":
                std = profile["standard"]
                self.spin_min_silence.setValue(int(std["min_silence"]))
                self.spin_vad_threshold.setValue(float(std["threshold"]))
                self.spin_speech_pad.setValue(int(std["speech_pad"]))
                self.spin_max_speech.setValue(float(std["max_speech"]))
                if hasattr(self, "chk_condition_on_previous_text"):
                    self.chk_condition_on_previous_text.setChecked(
                        "kotoba" not in model_name.lower()
                    )
        finally:
            self._updating_vad_preset = False
        self._refresh_vad_preset_hints()
        self._on_timing_setting_changed()

    def _on_vad_param_edited(self, *_args):
        if getattr(self, "_restoring_timing_settings", False) or getattr(self, "_updating_vad_preset", False):
            return
        if hasattr(self, "cmb_vad_preset"):
            model_name, profile = self._get_model_vad_profile()
            std = profile["standard"]
            cur_sil = self.spin_min_silence.value()
            cur_thr = self.spin_vad_threshold.value()
            cur_pad = self.spin_speech_pad.value()
            cur_max = self.spin_max_speech.value()
            target_preset = None
            for fixed in self._FIXED_VAD_PRESETS:
                if not self._is_preset_available_for_model(fixed, model_name):
                    continue
                if (
                    cur_sil == int(fixed["min_silence"])
                    and abs(cur_thr - float(fixed["threshold"])) < 1e-3
                    and cur_pad == int(fixed["speech_pad"])
                    and abs(cur_max - float(fixed["max_speech"])) < 1e-3
                ):
                    target_preset = fixed["key"]
                    break
            if target_preset is None:
                is_std = (
                    cur_sil == int(std["min_silence"])
                    and abs(cur_thr - float(std["threshold"])) < 1e-3
                    and cur_pad == int(std["speech_pad"])
                    and abs(cur_max - float(std["max_speech"])) < 1e-3
                )
                target_preset = "standard" if is_std else "custom"
            if self.cmb_vad_preset.currentData() != target_preset:
                self._updating_vad_preset = True
                try:
                    idx = self.cmb_vad_preset.findData(target_preset)
                    if idx >= 0:
                        self.cmb_vad_preset.setCurrentIndex(idx)
                finally:
                    self._updating_vad_preset = False
                self._refresh_vad_preset_hints()
        self._on_timing_setting_changed()

    def _timing_settings(self) -> dict:
        project_service = getattr(self.generation_service, "project_service", None)
        timing = getattr(
            getattr(getattr(project_service, "current_project", None), "state", None),
            "timing",
            None,
        )
        music_mode = getattr(timing, "music_mode", False) if timing is not None else (
            self._is_ctrl_checked(getattr(self, "chk_music_mode", None), default=False)
        )
        lang_text = self.cmb_language.currentText() if hasattr(self, "cmb_language") else ""
        lang_val = None if (not lang_text or lang_text == "Auto Detect") else lang_text
        preset_val = self.cmb_vad_preset.currentData() if hasattr(self, "cmb_vad_preset") else "standard"
        min_sil_ui = self.spin_min_silence.value() if hasattr(self, "spin_min_silence") else self._STANDARD_VAD_PRESET["min_silence"]
        thresh_ui = self.spin_vad_threshold.value() if hasattr(self, "spin_vad_threshold") else self._STANDARD_VAD_PRESET["threshold"]
        pad_ui = self.spin_speech_pad.value() if hasattr(self, "spin_speech_pad") else self._STANDARD_VAD_PRESET["speech_pad"]
        max_sp_ui = self.spin_max_speech.value() if hasattr(self, "spin_max_speech") else self._STANDARD_VAD_PRESET["max_speech"]
        apply_rescan_ui = self._is_ctrl_checked(getattr(self, "chk_apply_preset_rescan", None), default=False)
        cond_prev_ui = self._is_ctrl_checked(getattr(self, "chk_condition_on_previous_text", None), default=True)

        if timing is not None and hasattr(timing, "model_size"):
            values = {
                name: getattr(timing, name, getattr(TimingState(), name))
                for name in (
                    "model_size", "compute_type", "use_vad", "min_silence_ms",
                    "fix_overlap", "overlap_gap_ms", "overlap_ms", "max_window_ms",
                )
            }
            if hasattr(self, "cmb_model"):
                values["model_size"] = self._combo_value(self.cmb_model)
            if hasattr(self, "cmb_specialized_model"):
                spec_model = self._combo_value(self.cmb_specialized_model)
                values["specialized_model"] = spec_model
                if spec_model:
                    values["model_size"] = spec_model
            if hasattr(self, "cmb_compute"):
                values["compute_type"] = self._combo_value(self.cmb_compute)
            if self._is_timing_mode():
                values["use_vad"] = True
            if music_mode:
                values["music_mode"] = True
            if lang_val:
                values["language"] = lang_val
            else:
                values["language"] = None
            values["vad_preset"] = preset_val
            values["min_silence_ms"] = min_sil_ui
            values["vad_threshold"] = thresh_ui
            values["vad_speech_pad_ms"] = pad_ui
            values["vad_max_speech_duration_s"] = max_sp_ui
            values["apply_preset_to_rescan"] = apply_rescan_ui
            values["condition_on_previous_text"] = cond_prev_ui
            values["word_timestamps"] = self._is_ctrl_checked(getattr(self, "chk_word_timestamps", None), default=False)
            return values

        values = {
            "model_size": self._combo_value(self.cmb_model),
            "compute_type": self._combo_value(self.cmb_compute),
            "use_vad": True,
            "min_silence_ms": min_sil_ui,
            "fix_overlap": self._is_ctrl_checked(getattr(self, "chk_fix_overlap", None), default=True),
            "overlap_gap_ms": getattr(self, "spin_overlap_gap", None).value()
            if hasattr(self, "spin_overlap_gap") else 50,
            "overlap_ms": 800,
            "max_window_ms": 120000,
            "vad_preset": preset_val,
            "vad_threshold": thresh_ui,
            "vad_speech_pad_ms": pad_ui,
            "vad_max_speech_duration_s": max_sp_ui,
            "apply_preset_to_rescan": apply_rescan_ui,
            "condition_on_previous_text": cond_prev_ui,
            "word_timestamps": self._is_ctrl_checked(getattr(self, "chk_word_timestamps", None), default=False),
        }
        if getattr(self, "cmb_specialized_model", None) is not None:
            spec_model = self._combo_value(self.cmb_specialized_model)
            if spec_model:
                values["specialized_model"] = spec_model
                values["model_size"] = spec_model
        if self._is_ctrl_checked(getattr(self, "chk_music_mode", None), default=False):
            values["music_mode"] = True
        if lang_val:
            values["language"] = lang_val
        return values

    def _on_timing_setting_changed(self, *_args):
        if getattr(self, "_restoring_timing_settings", False):
            return
        project_service = getattr(self.generation_service, "project_service", None)
        project = getattr(project_service, "current_project", None)
        timing = getattr(getattr(project, "state", None), "timing", None)
        if timing is None:
            return
        if not self._is_timing_mode():
            # Vẫn lưu cấu hình preset & rescan & specialized_model vào timing state của project ngay cả ở chế độ Full Subtitle
            if hasattr(self, "cmb_specialized_model") and hasattr(timing, "specialized_model"):
                timing.specialized_model = str(self._combo_value(self.cmb_specialized_model) or "")
            if hasattr(self, "cmb_vad_preset"):
                timing.vad_preset = self.cmb_vad_preset.currentData()
                timing.min_silence_ms = self.spin_min_silence.value()
                timing.vad_threshold = self.spin_vad_threshold.value()
                timing.vad_speech_pad_ms = self.spin_speech_pad.value()
                timing.vad_max_speech_duration_s = self.spin_max_speech.value()
                timing.apply_preset_to_rescan = self._is_ctrl_checked(getattr(self, "chk_apply_preset_rescan", None), default=False)
                timing._has_explicit_apply_preset_to_rescan = True
                if hasattr(self, "chk_condition_on_previous_text") and hasattr(timing, "condition_on_previous_text"):
                    timing.condition_on_previous_text = self._is_ctrl_checked(self.chk_condition_on_previous_text, default=True)
            return
        values = self._timing_settings()
        lang_text = self.cmb_language.currentText() if hasattr(self, "cmb_language") else ""
        lang_val = None if (not lang_text or lang_text == "Auto Detect") else lang_text
        values.update(
            {
                "model_size": self._combo_value(self.cmb_model),
                "specialized_model": str(self._combo_value(self.cmb_specialized_model) or "") if hasattr(self, "cmb_specialized_model") else "",
                "compute_type": self._combo_value(self.cmb_compute),
                "use_vad": True,
                "min_silence_ms": self.spin_min_silence.value() if hasattr(self, "spin_min_silence") else 500,
                "fix_overlap": self._is_ctrl_checked(getattr(self, "chk_fix_overlap", None), default=True),
                "overlap_gap_ms": self.spin_overlap_gap.value(),
                "music_mode": self._is_ctrl_checked(getattr(self, "chk_music_mode", None), default=False),
                "language": lang_val,
                "vad_preset": self.cmb_vad_preset.currentData() if hasattr(self, "cmb_vad_preset") else "standard",
                "vad_threshold": self.spin_vad_threshold.value() if hasattr(self, "spin_vad_threshold") else 0.50,
                "vad_speech_pad_ms": self.spin_speech_pad.value() if hasattr(self, "spin_speech_pad") else 400,
                "vad_max_speech_duration_s": self.spin_max_speech.value() if hasattr(self, "spin_max_speech") else 30.0,
                "apply_preset_to_rescan": self._is_ctrl_checked(getattr(self, "chk_apply_preset_rescan", None), default=False),
                "condition_on_previous_text": self._is_ctrl_checked(getattr(self, "chk_condition_on_previous_text", None), default=True),
            }
        )
        for name, value in values.items():
            if hasattr(timing, name):
                setattr(timing, name, value)
        timing._has_explicit_apply_preset_to_rescan = True
        project_service.mark_dirty()
        if hasattr(self, "spin_overlap_gap"):
            self.spin_overlap_gap.setEnabled(self._is_ctrl_checked(getattr(self, "chk_fix_overlap", None), default=True))

    def sync_timing_settings_from_project(self):
        if self._is_any_service_running():
            return
        project_service = getattr(self.generation_service, "project_service", None)
        timing = getattr(
            getattr(getattr(project_service, "current_project", None), "state", None),
            "timing",
            None,
        )
        if not isinstance(timing, TimingState):
            return
        self._restoring_timing_settings = True
        try:
            task_mode = getattr(getattr(project_service.current_project, "state", None), "task_mode", "asr")
            mode_index = self.cmb_mode.findData(task_mode)
            if mode_index >= 0:
                self.cmb_mode.setCurrentIndex(mode_index)
            target_model = timing.model_size
            try:
                from core.services.model_manager import ModelManager
                info = {m["size"]: m["installed"] for m in ModelManager.get_discovery_list()}
                is_default_unconfigured = (
                    timing == TimingState()
                    and task_mode == "asr"
                    and not getattr(project_service.current_project.state, "dirty", False)
                )
                if is_default_unconfigured and not info.get(target_model, False) and any(info.values()):
                    target_model = self._select_best_model(info, target_model)
                    timing.model_size = target_model
            except Exception:
                pass
            for i in range(self.cmb_model.count()):
                if self.cmb_model.itemData(i) == target_model:
                    self.cmb_model.setCurrentIndex(i)
                    break
            if hasattr(self, "cmb_specialized_model"):
                target_spec = str(getattr(timing, "specialized_model", "") or "")
                spec_idx = self.cmb_specialized_model.findData(target_spec)
                self.cmb_specialized_model.setCurrentIndex(spec_idx if spec_idx >= 0 else 0)
            for i in range(self.cmb_compute.count()):
                if self.cmb_compute.itemData(i) == timing.compute_type:
                    self.cmb_compute.setCurrentIndex(i)
                    break
            self.chk_vad.setChecked(timing.use_vad)
            self.chk_fix_overlap.setChecked(timing.fix_overlap)
            self.spin_overlap_gap.setValue(timing.overlap_gap_ms)
            if hasattr(self, "chk_music_mode") and hasattr(timing, "music_mode"):
                self.chk_music_mode.setChecked(timing.music_mode)
            if hasattr(self, "cmb_language") and hasattr(timing, "language"):
                lang_target = timing.language or "Auto Detect"
                lang_idx = self.cmb_language.findText(lang_target)
                if lang_idx >= 0:
                    self.cmb_language.setCurrentIndex(lang_idx)
            self._refresh_vad_guidance_for_model(apply_values=False)
            from core.project.project_state import normalize_vad_preset_key
            saved_preset = normalize_vad_preset_key(getattr(timing, "vad_preset", "standard"))
            if hasattr(self, "cmb_vad_preset"):
                preset_idx = self.cmb_vad_preset.findData(saved_preset)
                if preset_idx >= 0:
                    self.cmb_vad_preset.setCurrentIndex(preset_idx)
            self._refresh_vad_preset_hints()
            legacy_defaults = TimingState()
            use_standard_vals = (
                saved_preset == "standard"
                and int(getattr(timing, "min_silence_ms", legacy_defaults.min_silence_ms)) == legacy_defaults.min_silence_ms
                and abs(float(getattr(timing, "vad_threshold", legacy_defaults.vad_threshold)) - legacy_defaults.vad_threshold) < 1e-3
                and int(getattr(timing, "vad_speech_pad_ms", legacy_defaults.vad_speech_pad_ms)) == legacy_defaults.vad_speech_pad_ms
                and abs(float(getattr(timing, "vad_max_speech_duration_s", legacy_defaults.vad_max_speech_duration_s)) - legacy_defaults.vad_max_speech_duration_s) < 1e-3
            )
            fixed_for_saved = self.get_fixed_vad_preset(saved_preset)
            if fixed_for_saved is not None:
                from core.services.model_manager import ModelManager
                eff_model = self._get_effective_model_size()
                if hasattr(self, "chk_word_timestamps"):
                    self.chk_word_timestamps.setChecked(
                        True if saved_preset == "cfg9" else ModelManager.supports_word_timestamps(eff_model)
                    )
                if hasattr(self, "spin_min_silence"):
                    self.spin_min_silence.setValue(int(fixed_for_saved["min_silence"]))
                if hasattr(self, "spin_vad_threshold"):
                    self.spin_vad_threshold.setValue(float(fixed_for_saved["threshold"]))
                if hasattr(self, "spin_speech_pad"):
                    self.spin_speech_pad.setValue(int(fixed_for_saved["speech_pad"]))
                if hasattr(self, "spin_max_speech"):
                    self.spin_max_speech.setValue(float(fixed_for_saved["max_speech"]))
                timing.min_silence_ms = int(fixed_for_saved["min_silence"])
                timing.vad_threshold = float(fixed_for_saved["threshold"])
                timing.vad_speech_pad_ms = int(fixed_for_saved["speech_pad"])
                timing.vad_max_speech_duration_s = float(fixed_for_saved["max_speech"])
            elif use_standard_vals:
                std = self._STANDARD_VAD_PRESET
                if hasattr(self, "spin_min_silence"):
                    self.spin_min_silence.setValue(int(std["min_silence"]))
                if hasattr(self, "spin_vad_threshold"):
                    self.spin_vad_threshold.setValue(float(std["threshold"]))
                if hasattr(self, "spin_speech_pad"):
                    self.spin_speech_pad.setValue(int(std["speech_pad"]))
                if hasattr(self, "spin_max_speech"):
                    self.spin_max_speech.setValue(float(std["max_speech"]))
            else:
                if hasattr(self, "spin_min_silence"):
                    self.spin_min_silence.setValue(int(getattr(timing, "min_silence_ms", self._STANDARD_VAD_PRESET["min_silence"])))
                if hasattr(self, "spin_vad_threshold"):
                    self.spin_vad_threshold.setValue(float(getattr(timing, "vad_threshold", self._STANDARD_VAD_PRESET["threshold"])))
                if hasattr(self, "spin_speech_pad"):
                    self.spin_speech_pad.setValue(int(getattr(timing, "vad_speech_pad_ms", self._STANDARD_VAD_PRESET["speech_pad"])))
                if hasattr(self, "spin_max_speech"):
                    self.spin_max_speech.setValue(float(getattr(timing, "vad_max_speech_duration_s", self._STANDARD_VAD_PRESET["max_speech"])))
            if hasattr(self, "chk_apply_preset_rescan"):
                has_explicit_flag = (
                    hasattr(timing, "apply_preset_to_rescan")
                    and getattr(timing, "_has_explicit_apply_preset_to_rescan", True)
                )
                if has_explicit_flag:
                    apply_rescan_val = bool(timing.apply_preset_to_rescan)
                else:
                    apply_rescan_val = fixed_for_saved is not None
                    timing.apply_preset_to_rescan = apply_rescan_val
                self.chk_apply_preset_rescan.setChecked(apply_rescan_val)
            if hasattr(self, "chk_condition_on_previous_text"):
                default_cond = "kotoba" not in self._get_effective_model_size().lower()
                if saved_preset == "live_action":
                    default_cond = False
                self.chk_condition_on_previous_text.setChecked(
                    bool(getattr(timing, "condition_on_previous_text", default_cond))
                )
            self._on_mode_changed()
            win = self.window()
            if hasattr(win, "_refresh_workspace_model_banner"):
                win._refresh_workspace_model_banner()
        finally:
            self._restoring_timing_settings = False

    def set_effective_compute_type(self, configured: str, effective: str):
        self.lbl_effective_compute.setText(
            f"Configured: {configured} · Effective: {effective}"
        )

    @staticmethod
    def _extract_progress_bar_format(percent: int, message: str) -> str:
        """Trích xuất chuỗi hiển thị ngắn gọn, sắc nét trên thanh tiến trình: % + số câu đã gen."""
        import re
        clamped = max(0, min(100, int(percent)))
        msg = str(message or "").strip()
        if not msg or msg.lower() in {"ready", "sẵn sàng"}:
            return "0%" if clamped == 0 else f"{clamped}%"

        gen_match = re.search(r"Đã gen\s+([0-9]+/[0-9]+\s+câu|[0-9]+\s+câu)", msg, re.IGNORECASE)
        total_match = re.search(r"Tổng\s+([0-9]+\s+câu)", msg, re.IGNORECASE)

        count_part = ""
        if gen_match:
            count_part = f"Đã gen {gen_match.group(1)}"
            if total_match:
                count_part += f" ({total_match.group(0)})"
        elif "hoàn tất" in msg.lower():
            if gen_match:
                count_part = f"Hoàn tất ({gen_match.group(1)})"
            else:
                count_part = "Hoàn tất 100%"

        if count_part:
            return f"{clamped}% · {count_part}"
        elif clamped > 0:
            return f"{clamped}%"
        else:
            return msg if len(msg) <= 30 else f"{msg[:28]}..."

    def _update_progress(self, percent: int, message: str):
        clamped = max(0, min(100, int(percent)))
        self.progress_bar.setValue(clamped)
        bar_text = self._extract_progress_bar_format(clamped, message)
        if hasattr(self.progress_bar, "setFormat"):
            self.progress_bar.setFormat(bar_text)
        self.lbl_status.setText(message)
        if hasattr(self.lbl_status, "update"):
            self.lbl_status.update()
        win = self._get_window()
        if win is not None and win is not self and not getattr(win, "_queue_generation_active", False):
            pbar = getattr(win, "progress_bar", None)
            if pbar is not None:
                pbar.setValue(clamped)
                if hasattr(pbar, "setFormat"):
                    pbar.setFormat(bar_text)
            dash = getattr(win, "page_dashboard", None)
            quick_pbar = getattr(dash, "quick_progress", None) if dash is not None else None
            if quick_pbar is not None:
                quick_pbar.setValue(clamped)
            lbl_eta = getattr(win, "lbl_speed_eta", None)
            if lbl_eta is not None and message:
                lbl_eta.setText(message)


    def _on_quick_rollback_clicked(self, target_str):
        if target_str == "Initial":
            target_count = 0
        else:
            try:
                target_count = int(target_str)
            except ValueError:
                return
                
        cp = self.generation_service.get_rollback_checkpoint(target_count=target_count)
        if not cp:
            self._on_error(f"Không có checkpoint nào tương ứng với {target_str} subtitles.")
            return
            
        self._trigger_rollback(cp)

    def _trigger_rollback(self, cp):
        from ui.dialogs.restore_preview_dialog import RestorePreviewDialog
        
        current_segments = self._get_current_segments()
        current_count = len(current_segments)
        target_count = cp.generated_count
        
        manual_edits = 0
        # Check manual edits
        if len(current_segments) == len(cp.segments_snapshot):
            for cur, snap in zip(current_segments, cp.segments_snapshot):
                if cur.get("source") == "manual" and snap.get("source") != "manual":
                    manual_edits += 1
                elif cur.get("start") != snap.get("start") or cur.get("end") != snap.get("end") or cur.get("text") != snap.get("text"):
                    manual_edits += 1
        else:
            manual_edits = sum(1 for s in current_segments if s.get("source") == "manual")
            
        dialog = RestorePreviewDialog(current_count, target_count, manual_edits, self)
        if dialog.exec():
            # Perform rollback
            main_window = self.window()
            if main_window and hasattr(main_window, 'undo_manager'):
                try:
                    self.generation_service.execute_rollback(target_count, self._get_current_segments(), main_window.undo_manager, checkpoint_id=cp.checkpoint_id)
                    if hasattr(main_window, 'sub_editor'):
                        main_window.sub_editor.render_page()
                    # We might need to refresh history UI
                    self.refresh_history_ui()
                except Exception as e:
                    self._on_error(str(e))
            else:
                self._on_error("Khong tim thay Undo Manager.")

    def refresh_history_ui(self):
        self.refresh_history()

    def _on_error(self, error_message: str):
        self.lbl_status.setText(f"Error: {error_message}")
        self.lbl_status.setStyleSheet(f"color: {Theme.DANGER};")
        QMessageBox.critical(self, "Generation Error", error_message)
        self._reset_ui_state()

    def _on_finish(self):
        current = getattr(self.generation_service, "current_checkpoint", None)
        range_run = bool(
            getattr(self.generation_service, "current_request", None)
            and self.generation_service.current_request.range_start_ms is not None
        )
        checkpoint = (
            None if range_run
            else self.generation_service.checkpoint_manager.load_checkpoint()
        )
        if (range_run and current and current.status == "CANCELLED") or (
            checkpoint and checkpoint.status == "CANCELLED"
        ):
            self.lbl_status.setText("Cancelled. Resume when ready.")
            self.lbl_status.setStyleSheet(f"color: {Theme.TEXT_MUTED};")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0%")
        else:
            self.lbl_status.setStyleSheet(f"color: {Theme.SUCCESS};")
            self.progress_bar.setValue(100)
            # Tự động trả thanh tiến trình về 0 sau 800ms khi hoàn tất
            from PySide6.QtCore import QTimer
            def _reset_done():
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("0%")
            QTimer.singleShot(800, _reset_done)
        self._reset_ui_state()

    # --- PHASE 3: RANGE & HISTORY LOGIC ---
    def _range_unit_factor_ms(self, unit=None):
        unit = unit or self._range_input_unit
        return 1000 if unit == "seconds" else 60000

    def _range_unit_label(self, unit=None):
        unit = unit or self._range_input_unit
        return "giây" if unit == "seconds" else "phút"

    def _range_input_help(self):
        if self._range_input_unit == "seconds":
            return (
                "Nhập số giây không âm, không cần gõ s. Ví dụ: 60–70 hoặc "
                "60,5–70. Dấu phẩy (,) và dấu chấm (.) đều dùng được cho số lẻ."
            )
        return (
            "Nhập số phút không âm, không cần gõ chữ phút. Ví dụ: 1–5 hoặc "
            "1,5–2. Dấu phẩy (,) và dấu chấm (.) đều dùng được cho số lẻ."
        )

    def _refresh_range_input_help(self):
        help_text = self._range_input_help()
        for widget in (self.txt_start, self.txt_end):
            widget.setToolTip(help_text)
        if self._range_input_unit == "seconds":
            self.txt_start.setPlaceholderText("Ví dụ: 60,5")
            self.txt_end.setPlaceholderText("Ví dụ: 70")
        else:
            self.txt_start.setPlaceholderText("Ví dụ: 1,5")
            self.txt_end.setPlaceholderText("Ví dụ: 5")

    def _clear_range_input_error(self, widget):
        widget.setStyleSheet("")
        if hasattr(self, "_range_input_unit"):
            widget.setToolTip(self._range_input_help())

    def _show_range_input_error(self, widget, message):
        help_text = f"{message}\n\nCách nhập đúng: {self._range_input_help()}"
        widget.setStyleSheet("border: 1px solid #ff5252;")
        widget.setToolTip(help_text)
        widget.setFocus()
        QToolTip.showText(
            widget.mapToGlobal(widget.rect().bottomLeft()),
            help_text,
            widget,
            widget.rect(),
            7000,
        )

    def _on_range_unit_changed(self):
        from core.subtitle_generation.range_time_input import (
            RangeInputError, parse_range_value_ms, format_range_value_ms,
        )
        old_unit = getattr(self, "_range_input_unit", "seconds")
        new_unit = self.cmb_range_unit.currentData()
        if new_unit == old_unit:
            self._refresh_range_input_help()
            return

        converted = []
        for widget in (self.txt_start, self.txt_end):
            raw = widget.text().strip()
            if not raw:
                converted.append((widget, ""))
                continue
            try:
                value_ms = parse_range_value_ms(raw, old_unit)
            except RangeInputError as exc:
                self.cmb_range_unit.blockSignals(True)
                self.cmb_range_unit.setCurrentIndex(
                    self.cmb_range_unit.findData(old_unit)
                )
                self.cmb_range_unit.blockSignals(False)
                self._show_range_input_error(
                    widget,
                    f"Không thể đổi đơn vị vì giá trị đang nhập chưa hợp lệ: {exc}",
                )
                return
            converted.append((widget, value_ms))

        self._range_input_unit = new_unit
        for widget, value in converted:
            widget.setText(
                "" if value == "" else format_range_value_ms(value, new_unit)
            )
        self._refresh_range_input_help()

    def set_range(self, start_ms: int, end_ms: int):
        from core.subtitle_generation.range_time_input import format_range_value_ms
        unit = getattr(self, "_range_input_unit", "seconds")
        self.txt_start.setText(format_range_value_ms(start_ms, unit))
        self.txt_end.setText(format_range_value_ms(end_ms, unit))

    def _on_preview_range_clicked(self):
        from ui.SubEditor import ms_to_time_str
        from core.subtitle_generation.range_time_input import (
            RangeInputError, parse_range_value_ms, format_range_value_ms,
        )
        from core.subtitle_generation.range_validation import RangeValidator, RangeErrorCode
        from ui.dialogs.preview_range_dialog import PreviewRangeDialog

        try:
            start_ms = parse_range_value_ms(
                self.txt_start.text(), self._range_input_unit
            )
        except RangeInputError as exc:
            self._show_range_input_error(
                self.txt_start, f"Thời điểm bắt đầu không hợp lệ: {exc}"
            )
            return
        try:
            end_ms = parse_range_value_ms(
                self.txt_end.text(), self._range_input_unit
            )
        except RangeInputError as exc:
            self._show_range_input_error(
                self.txt_end, f"Thời điểm kết thúc không hợp lệ: {exc}"
            )
            return

        self._clear_range_input_error(self.txt_start)
        self._clear_range_input_error(self.txt_end)
        if start_ms >= end_ms:
            self._show_range_input_error(
                self.txt_end,
                "Thời điểm kết thúc phải lớn hơn thời điểm bắt đầu.",
            )
            return

        # Call Validator
        result = RangeValidator.preview_range(
            start_ms, end_ms, self.video_duration_ms, 
            self._get_current_segments(), 
            self.generation_service.is_running
        )
        
        if not result.is_valid:
            if result.suggested_end_ms:
                # Keep the existing explicit clamp confirmation, but display the
                # proposed value in the currently selected input unit.
                from PySide6.QtWidgets import QMessageBox
                suggested = format_range_value_ms(
                    result.suggested_end_ms, self._range_input_unit
                )
                ans = QMessageBox.question(
                    self,
                    "Khoảng thời gian vượt video",
                    f"⚠ {result.message}\nBạn có muốn đưa thời điểm kết thúc về {suggested} {self._range_unit_label()}?",
                )
                if ans == QMessageBox.Yes:
                    self.txt_end.setText(suggested)
                    self._on_preview_range_clicked()  # Re-preview
                else:
                    self._show_range_input_error(
                        self.txt_end,
                        f"Thời điểm kết thúc vượt thời lượng video. Giá trị gợi ý: {suggested} {self._range_unit_label()}.",
                    )
            else:
                if result.status == RangeErrorCode.START_BEYOND_END:
                    if start_ms > self.video_duration_ms:
                        target = self.txt_start
                        message = "Thời điểm bắt đầu vượt quá thời lượng video. Hãy giảm giá trị bắt đầu."
                    else:
                        target = self.txt_end
                        message = "Thời điểm kết thúc phải lớn hơn thời điểm bắt đầu."
                elif result.status == RangeErrorCode.RANGE_TOO_SHORT:
                    target = self.txt_end
                    message = "Khoảng chọn quá ngắn. Hãy chọn khoảng dài hơn ít nhất 0,05 giây."
                elif result.status == RangeErrorCode.BEYOND_VIDEO_DURATION:
                    target = self.txt_end
                    message = "Thời điểm kết thúc vượt quá thời lượng video. Hãy nhập giá trị nhỏ hơn hoặc bằng thời lượng video."
                else:
                    target = self.txt_end
                    message = result.message
                self._show_range_input_error(target, message)
            return
            
        dialog = PreviewRangeDialog(ms_to_time_str(start_ms), ms_to_time_str(end_ms), result, self)
        if dialog.exec():
            # If accepted, trigger range generation
            strategy = dialog.selected_strategy
            # Call generation with strategy
            self._start_generation_with_strategy(start_ms, end_ms, strategy)

    def _start_generation_with_strategy(self, start_ms, end_ms, strategy):
        request = self._build_asr_request(start_ms, end_ms)
        if request is None:
            return
        self._set_ui_state_running()
        try:
            self.generation_service.start_generation(
                request,
                self.video_duration_ms,
                existing_segments=self._get_current_segments(),
                conflict_strategy=strategy
            )
        except Exception as exc:
            self._on_error(str(exc))
            self._reset_ui_state()
        self.refresh_history_ui()
            
    def _get_current_segments(self):
        # The panel lives inside MainWindow's overlay drawer; window() reaches it.
        win = self._get_window()
        sub_editor = getattr(win, "sub_editor", None) if win is not None else None
        if sub_editor is not None:
            return getattr(sub_editor, "all_segments", None) or []
        provider = getattr(getattr(self, "generation_service", None), "range_segments_provider", None)
        if callable(provider):
            try:
                return provider() or []
            except Exception:
                return []
        return []
        
    def refresh_history(self):
        from PySide6.QtWidgets import QListWidgetItem

        ensure_loaded = getattr(self.generation_service, "_ensure_history_loaded", None)
        if ensure_loaded is not None:
            ensure_loaded()
        selected = self.history_list.currentItem()
        selected_id = selected.data(Qt.UserRole) if selected else None
        
        self.history_list.clear()
        
        history = []
        initial_state = getattr(self.generation_service, "initial_state", None)
        if initial_state:
            history.append(initial_state)
        history.extend(getattr(self.generation_service, "checkpoint_history", []))
        
        for cp in reversed(history): # Latest first
            label = f"{cp.checkpoint_type} - {cp.generated_count} subs"
            if cp.checkpoint_type == "INITIAL":
                label = "Initial State"
                
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, cp.checkpoint_id)
            self.history_list.addItem(item)
            if cp.checkpoint_id == selected_id:
                self.history_list.setCurrentItem(item)

        running = not self.btn_generate.isEnabled()
        get_rollback = getattr(self.generation_service, "get_rollback_checkpoint", None)
        for count, button in ((10, self.btn_rb_10), (30, self.btn_rb_30), (50, self.btn_rb_50), (60, self.btn_rb_60), (0, self.btn_rb_initial)):
            button.setEnabled(not running and get_rollback is not None and get_rollback(target_count=count) is not None)
        self._on_history_selection_changed()
            
    def _on_history_selection_changed(self):
        self.btn_rollback.setEnabled(self.btn_generate.isEnabled() and bool(self.history_list.selectedItems()))

    def _on_rollback_clicked(self):
        selected = self.history_list.selectedItems()
        if not selected:
            return
            
        cp_id = selected[0].data(Qt.UserRole)
        cp = self.generation_service.get_rollback_checkpoint(checkpoint_id=cp_id)
        if not cp:
            return
            
        self._trigger_rollback(cp)

    def _replace_editor_segments(self, segments):
        """Load segments into MainWindow's editor, timeline and draft."""
        win = self.window()
        sub_editor = getattr(win, "sub_editor", None)
        if sub_editor is None:
            return False
        sub_editor.all_segments.clear()
        sub_editor.all_segments.extend(segments)
        sub_editor.current_index = 0 if sub_editor.all_segments else -1
        if hasattr(sub_editor, "current_page"):
            sub_editor.current_page = 0

        auto_saved = False
        apply_auto = getattr(win, "_apply_auto_audio_style_if_enabled", None)
        if callable(apply_auto):
            auto_saved = bool(apply_auto())

        sub_editor.render_page()
        provider = getattr(win, "timeline_data_provider", None)
        if provider is not None:
            duration_ms = self.video_duration_ms or 3600000
            provider.load_runtime_data(sub_editor.all_segments, duration_ms)
            win.timeline_widget.load_project_data(duration_ms, provider.get_all_segments())

        saved_path = None
        if not auto_saved:
            project_service = getattr(self.generation_service, "project_service", None)
            project_dir = getattr(project_service, "project_dir", None)
            if not getattr(sub_editor, "srt_path", None) and isinstance(project_dir, str) and project_dir:
                project = getattr(project_service, "current_project", None)
                source_id = getattr(getattr(project, "state", None), "active_subtitle_source_id", None) or "external_srt"
                saved_path = sub_editor.save_draft(
                    filepath=os.path.join(project_dir, f"{source_id}.ai-subtitle-draft"),
                    silent=True,
                )
            else:
                saved_path = sub_editor.save_draft(silent=True)
        else:
            saved_path = getattr(sub_editor, "srt_path", None)

        if isinstance(saved_path, str) and saved_path and os.path.exists(saved_path):
            queue_mgr = getattr(win, "queue_mgr", None)
            target_item = (
                getattr(queue_mgr, "active_item_key", None)
                or getattr(queue_mgr, "active_vid", None)
                or getattr(win, "active_item_key", None)
                or getattr(win, "active_vid", None)
            )
            if queue_mgr is not None and isinstance(target_item, str) and target_item and hasattr(queue_mgr, "set_srt_for_video"):
                queue_mgr.set_srt_for_video(target_item, saved_path)

        self.refresh_history()
        return True

    def _invalidate_stale_timing_checkpoint(self, project_service) -> None:
        """Clear stale timing checkpoint when replacing or switching the active SRT source."""
        project_dir = getattr(project_service, "project_dir", None)
        project = getattr(project_service, "current_project", None)
        if not isinstance(project_dir, str) or not project_dir:
            return
        checkpoint_path = os.path.join(project_dir, "artifacts", "timing", "checkpoint.json")
        if os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
            except OSError:
                pass
        timing_state = getattr(getattr(project, "state", None), "timing", None)
        if timing_state is not None:
            timing_state.status = "IDLE"
            timing_state.checkpoint_id = None
    # ----------------------------------------

    def sync_subtitle_sources_from_project(self):
        self.refresh_history()
        project_service = getattr(self.generation_service, "project_service", None)
        project = getattr(project_service, "current_project", None)
        if not project: return
        sources = getattr(project.state, "subtitle_sources", [])
        active_id = getattr(project.state, "active_subtitle_source_id", "default")
        
        self.cmb_subtitle_source.blockSignals(True)
        self.cmb_subtitle_source.clear()
        self.cmb_subtitle_source.addItem("Auto-detected SRT", "default")
        for src in sources:
            self.cmb_subtitle_source.addItem(src.get("name", "External SRT"), src.get("id"))
        
        idx = self.cmb_subtitle_source.findData(active_id)
        if idx >= 0:
            self.cmb_subtitle_source.setCurrentIndex(idx)
        self.cmb_subtitle_source.blockSignals(False)

    def _on_add_external_srt(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(self, "Ch?n file SRT...", "", "Subtitle Files (*.srt)")
        if not path: return
        
        from core.srt_parser import SrtParser
        
        try:
            segments = SrtParser.parse(path)
            if not segments:
                raise ValueError("File SRT tr?ng ho?c khng h?p l?.")
                
            source_id = f"ext_srt_{uuid.uuid4().hex[:8]}"
            project_service = getattr(self.generation_service, "project_service", None)
            project = getattr(project_service, "current_project", None)
            if not project: return
            
            # Lưu snapshot cho nguồn hiện tại trước khi chuyển sang nguồn mới (BUG-DATA-002)
            win = self.window()
            sub_editor = getattr(win, "sub_editor", None)
            current_segments = list(getattr(sub_editor, "all_segments", []))
            current_source_id = getattr(project.state, "active_subtitle_source_id", "default")
            if not hasattr(project.state, "subtitle_source_segments") or not isinstance(project.state.subtitle_source_segments, dict):
                project.state.subtitle_source_segments = {}
            if current_segments:
                import copy
                project.state.subtitle_source_segments[current_source_id] = copy.deepcopy(current_segments)

            new_source = {
                "id": source_id,
                "name": os.path.basename(path),
                "original_path": path,
            }
            if not hasattr(project.state, "subtitle_sources"):
                project.state.subtitle_sources = []
            project.state.subtitle_sources.append(new_source)
            project.state.active_subtitle_source_id = source_id
            import copy
            project.state.subtitle_source_segments[source_id] = copy.deepcopy(segments)
            if hasattr(project_service, "mark_dirty"):
                project_service.mark_dirty()
                
            self._invalidate_stale_timing_checkpoint(project_service)
            self.sync_subtitle_sources_from_project()
            
            # Store initial checkpoint for new source
            self.generation_service.create_history_checkpoint(segments, is_initial=True)
            
            # Refresh UI
            self._replace_editor_segments(segments)
            self.check_resumable_state()
                
        except Exception as e:
            QMessageBox.critical(self, "Lỗi import", f"Không thể đọc file SRT:\n{e}")

    def _on_subtitle_source_changed(self, idx):
        if idx < 0: return
        source_id = self.cmb_subtitle_source.itemData(idx)
        project_service = getattr(self.generation_service, "project_service", None)
        project = getattr(project_service, "current_project", None)
        if not project: return
        
        current_active = getattr(project.state, "active_subtitle_source_id", "default")
        if current_active == source_id:
            return

        import copy
        win = self.window()
        sub_editor = getattr(win, "sub_editor", None)
        current_segments = list(getattr(sub_editor, "all_segments", []))
        if not hasattr(project.state, "subtitle_source_segments") or not isinstance(project.state.subtitle_source_segments, dict):
            project.state.subtitle_source_segments = {}
        if current_segments:
            project.state.subtitle_source_segments[current_active] = copy.deepcopy(current_segments)
            
        project.state.active_subtitle_source_id = source_id
        if hasattr(project_service, "mark_dirty"):
            project_service.mark_dirty()
            
        # 1. Ưu tiên 1: Đọc snapshot đã lưu cho source_id này (BUG-DATA-002)
        target_segments = project.state.subtitle_source_segments.get(source_id)
        
        # 2. Nếu là nguồn "default" và chưa có trong snapshot dict, nạp từ artifact gốc
        if target_segments is None and source_id == "default":
            art_id = getattr(project.state, "active_artifact_id", None) or getattr(project.state, "subtitle_artifact_id", None)
            if art_id and project_service and hasattr(project_service, "artifact_store"):
                art = project_service.artifact_store.get(art_id)
                if art and os.path.exists(art.path):
                    try:
                        import json
                        with open(art.path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        loaded = data.get("segments", [])
                        if loaded:
                            target_segments = copy.deepcopy(loaded)
                    except Exception:
                        pass
                        
        # 3. Fallback sang checkpoint_history nếu không tìm thấy ở trên
        if target_segments is None:
            history = self.generation_service.checkpoint_history
            cp = history[-1] if history else self.generation_service.initial_state
            target_segments = copy.deepcopy(getattr(cp, "segments_snapshot", None) or [])
            
        self._invalidate_stale_timing_checkpoint(project_service)
        self._replace_editor_segments(target_segments or [])
        self.check_resumable_state()
