from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QCheckBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QPushButton, QColorDialog,
    QFontComboBox, QGroupBox, QLabel, QHBoxLayout,
)
from PySide6.QtCore import QSignalBlocker, Signal, Qt, Slot
from PySide6.QtGui import QColor
from ui.theme import Theme


class SubtitleInspectorPanel(QWidget):
    """Pure UI inspector for subtitle overlay styling."""

    style_changed = Signal(dict)
    preview_toggled = Signal(bool)
    preset_changed = Signal(str)
    presets_configured = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_color = QColor(255, 255, 255)
        self.outline_color = QColor(0, 0, 0)
        self.custom_presets: dict = {}
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        self.chk_preview = QCheckBox("Hiển thị Preview Phụ đề")
        self.chk_preview.setChecked(True)
        layout.addWidget(self.chk_preview)

        preset_group = QGroupBox("🎯 Tùy biến câu đang chọn")
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.setSpacing(6)
        preset_form = QFormLayout()
        preset_form.setSpacing(8)
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItem("Normal (Mặc định)", "normal")
        self.cmb_preset.addItem("⚡ Loud (Nhấn mạnh)", "loud")
        self.cmb_preset.addItem("🤫 Whisper (Thì thầm)", "whisper")
        self.cmb_preset.currentIndexChanged.connect(
            lambda _idx: self.preset_changed.emit(self.cmb_preset.currentData() or "normal")
        )
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        preset_row.addWidget(self.cmb_preset, stretch=1)
        self.btn_config_presets = QPushButton("⚙️ Cấu hình...")
        self.btn_config_presets.setCursor(Qt.PointingHandCursor)
        self.btn_config_presets.clicked.connect(self._open_preset_config_dialog)
        preset_row.addWidget(self.btn_config_presets)
        preset_form.addRow("Preset câu đang chọn:", preset_row)
        preset_layout.addLayout(preset_form)
        self.lbl_preset_hint = QLabel(
            "• ⚡ Loud: Tự động phóng to +20%, In đậm, Màu vàng chanh\n"
            "• 🤫 Whisper: Tự động thu nhỏ -15%, In nghiêng, Màu bạc xám"
        )
        self.lbl_preset_hint.setWordWrap(True)
        self.lbl_preset_hint.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; border: none;")
        preset_layout.addWidget(self.lbl_preset_hint)
        layout.addWidget(preset_group)

        style_group = QGroupBox("🌐 Style mặc định toàn dự án (Base Style)")
        form_layout = QFormLayout(style_group)
        form_layout.setSpacing(10)

        self.cmb_font = QFontComboBox()
        self.cmb_font.setEditable(False)
        form_layout.addRow("Font chữ cơ sở:", self.cmb_font)

        self.spin_size = QSpinBox()
        self.spin_size.setRange(10, 150)
        self.spin_size.setValue(20)
        form_layout.addRow("Cỡ chữ cơ sở:", self.spin_size)

        self.btn_text_color = QPushButton()
        self.btn_text_color.setCursor(Qt.PointingHandCursor)
        self._update_color_button(self.btn_text_color, self.text_color)
        form_layout.addRow("Màu chữ mặc định:", self.btn_text_color)

        self.spin_outline = QSpinBox()
        self.spin_outline.setRange(0, 20)
        self.spin_outline.setValue(2)
        form_layout.addRow("Độ dày viền:", self.spin_outline)

        self.btn_outline_color = QPushButton()
        self.btn_outline_color.setCursor(Qt.PointingHandCursor)
        self._update_color_button(self.btn_outline_color, self.outline_color)
        form_layout.addRow("Màu viền:", self.btn_outline_color)

        self.cmb_position = QComboBox()
        self.cmb_position.addItems(["Top", "Center", "Bottom", "Custom"])
        self.cmb_position.setCurrentText("Bottom")
        form_layout.addRow("Vị trí hiển thị:", self.cmb_position)

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(0.0, 100.0)
        self.spin_x.setDecimals(1)
        self.spin_x.setSuffix(" %")
        self.spin_x.setValue(50.0)
        form_layout.addRow("X:", self.spin_x)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(0.0, 100.0)
        self.spin_y.setDecimals(1)
        self.spin_y.setSuffix(" %")
        self.spin_y.setValue(85.0)
        form_layout.addRow("Y:", self.spin_y)

        self.chk_position_edit = QCheckBox("Position Edit Mode")
        form_layout.addRow(self.chk_position_edit)

        layout.addWidget(style_group)
        layout.addStretch()
        self.setStyleSheet(
            f"""
            QDoubleSpinBox {{
                background-color: {Theme.BG_APP};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 6px 18px 6px 10px;
            }}
            QDoubleSpinBox:hover {{
                border-color: {Theme.CYAN};
            }}
            QDoubleSpinBox:focus {{
                border-color: {Theme.PRIMARY_PURPLE};
            }}
            QDoubleSpinBox:disabled {{
                background-color: {Theme.SURFACE};
                color: {Theme.TEXT_DISABLED};
                border-color: {Theme.BORDER};
            }}
            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button {{
                background-color: {Theme.SURFACE_SOFT};
                border: none;
                width: 16px;
            }}
            QDoubleSpinBox::up-button:hover,
            QDoubleSpinBox::down-button:hover {{
                background-color: {Theme.BORDER};
            }}
            """
        )

    def _update_color_button(self, btn: QPushButton, color: QColor):
        btn.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #555; "
            "border-radius: 4px; min-height: 24px;"
        )

    def _connect_signals(self):
        self.chk_preview.toggled.connect(self.preview_toggled.emit)
        self.cmb_font.currentFontChanged.connect(self._on_style_changed)
        self.spin_size.valueChanged.connect(self._on_style_changed)
        self.spin_outline.valueChanged.connect(self._on_style_changed)
        self.cmb_position.currentIndexChanged.connect(self._on_style_changed)
        self.spin_x.editingFinished.connect(self._on_style_changed)
        self.spin_y.editingFinished.connect(self._on_style_changed)
        self.chk_position_edit.toggled.connect(self._on_style_changed)
        self.btn_text_color.clicked.connect(self._choose_text_color)
        self.btn_outline_color.clicked.connect(self._choose_outline_color)

    @Slot()
    def _choose_text_color(self):
        color = self._choose_color(self.text_color, "Chọn màu chữ")
        if color.isValid():
            self.text_color = color
            self._update_color_button(self.btn_text_color, color)
            self._on_style_changed()

    @Slot()
    def _choose_outline_color(self):
        color = self._choose_color(self.outline_color, "Chọn màu viền")
        if color.isValid():
            self.outline_color = color
            self._update_color_button(self.btn_outline_color, color)
            self._on_style_changed()

    def _choose_color(self, initial: QColor, title: str) -> QColor:
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle(title)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        dialog.setStyleSheet(
            f"""
            QColorDialog, QDialog {{ background: {Theme.BG_APP}; color: {Theme.TEXT_PRIMARY}; }}
            QColorDialog QLabel {{ color: {Theme.TEXT_SECONDARY}; }}
            QColorDialog QLineEdit, QColorDialog QSpinBox {{
                background: {Theme.SURFACE}; color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER}; border-radius: 5px; padding: 5px;
            }}
            QColorDialog QPushButton {{
                background: {Theme.SURFACE_ELEVATED}; color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER}; border-radius: 5px; padding: 6px 14px;
            }}
            QColorDialog QPushButton:hover {{ border-color: {Theme.CYAN}; color: {Theme.CYAN}; }}
            """
        )
        return dialog.currentColor() if dialog.exec() else QColor()

    @Slot()
    def _on_style_changed(self, *args):
        self.style_changed.emit(self.get_current_style())

    def get_current_style(self) -> dict:
        return {
            "font_name": self.cmb_font.currentFont().family(),
            "font_size": self.spin_size.value(),
            "font_color": self.text_color.name(),
            "outline_color": self.outline_color.name(),
            "outline_width": self.spin_outline.value(),
            "position": self.cmb_position.currentText().lower(),
            "x": self.spin_x.value() / 100.0,
            "y": self.spin_y.value() / 100.0,
            "position_edit_mode": self.chk_position_edit.isChecked(),
        }

    def set_placement_state(self, mode, x, y, emit=False):
        mode = str(mode).lower()
        mode_text = {"top": "Top", "center": "Center", "bottom": "Bottom", "custom": "Custom"}.get(mode, "Bottom")
        blockers = [
            QSignalBlocker(self.cmb_position),
            QSignalBlocker(self.spin_x),
            QSignalBlocker(self.spin_y),
        ]
        self.cmb_position.setCurrentText(mode_text)
        self.spin_x.setValue(max(0.0, min(100.0, float(x) * 100.0)))
        self.spin_y.setValue(max(0.0, min(100.0, float(y) * 100.0)))
        del blockers
        if emit:
            self._on_style_changed()

    def set_current_preset(self, preset: str):
        """Đồng bộ hiển thị preset của câu đang chọn."""
        preset_clean = (preset or "normal").lower().strip()
        idx = self.cmb_preset.findData(preset_clean)
        blocker = QSignalBlocker(self.cmb_preset)
        self.cmb_preset.setCurrentIndex(max(0, idx))

    def set_style(self, style: dict):
        """Khôi phục toàn bộ style từ dự án đã lưu."""
        if not style or not isinstance(style, dict):
            return
        blockers = [
            QSignalBlocker(self.cmb_font),
            QSignalBlocker(self.spin_size),
            QSignalBlocker(self.spin_outline),
            QSignalBlocker(self.cmb_position),
            QSignalBlocker(self.spin_x),
            QSignalBlocker(self.spin_y),
            QSignalBlocker(self.chk_position_edit),
        ]
        if "font_name" in style:
            from PySide6.QtGui import QFont
            self.cmb_font.setCurrentFont(QFont(style["font_name"]))
        if "font_size" in style:
            self.spin_size.setValue(int(style["font_size"]))
        if "font_color" in style:
            self.text_color = QColor(style["font_color"])
            self._update_color_button(self.btn_text_color, self.text_color)
        if "outline_color" in style:
            self.outline_color = QColor(style["outline_color"])
            self._update_color_button(self.btn_outline_color, self.outline_color)
        if "outline_width" in style:
            self.spin_outline.setValue(int(style["outline_width"]))
        if "position" in style:
            pos_text = {"top": "Top", "center": "Center", "middle": "Center", "bottom": "Bottom", "custom": "Custom"}.get(
                str(style["position"]).lower(), "Bottom"
            )
            self.cmb_position.setCurrentText(pos_text)
        if "x" in style:
            self.spin_x.setValue(max(0.0, min(100.0, float(style["x"]) * 100.0)))
        if "y" in style:
            self.spin_y.setValue(max(0.0, min(100.0, float(style["y"]) * 100.0)))
        if "position_edit_mode" in style:
            self.chk_position_edit.setChecked(bool(style["position_edit_mode"]))
        del blockers

    def _open_preset_config_dialog(self):
        from ui.preset_config_dialog import PresetConfigDialog
        dlg = PresetConfigDialog(self.custom_presets, self)
        dlg.presets_configured.connect(self._on_presets_configured_from_dialog)
        dlg.exec()

    def _on_presets_configured_from_dialog(self, new_presets: dict):
        self.update_preset_hints(new_presets)
        self.presets_configured.emit(new_presets)

    def update_preset_hints(self, custom_presets: dict | None = None):
        """Tự động cập nhật nhãn gợi ý hiển thị thông số Loud / Whisper hiện hành."""
        from core.subtitle_quality.style_preset_resolver import StylePresetResolver
        import copy
        self.custom_presets = copy.deepcopy(custom_presets or {})
        defaults = StylePresetResolver.get_default_presets()

        def _fmt(key: str, icon_label: str) -> str:
            cfg = {**defaults[key], **(self.custom_presets.get(key) or {})}
            scale = float(cfg.get("scale", 1.0))
            delta_pct = int(round((scale - 1.0) * 100))
            scale_str = f"Phóng to +{delta_pct}%" if delta_pct >= 0 else f"Thu nhỏ {delta_pct}%"
            parts = [scale_str]
            if cfg.get("bold"):
                parts.append("In đậm")
            if cfg.get("italic"):
                parts.append("In nghiêng")
            parts.append(f"Màu {str(cfg.get('font_color', '#FFFFFF')).upper()}")
            return f"• {icon_label}: " + ", ".join(parts)

        self.lbl_preset_hint.setText(
            _fmt("loud", "⚡ Loud") + "\n" + _fmt("whisper", "🤫 Whisper")
        )

    def emit_current_style(self):
        """Emit the current style snapshot after the panel is connected."""
        self._on_style_changed()
