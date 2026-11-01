import copy
from typing import Dict, Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.subtitle_quality.style_preset_resolver import (
    DEFAULT_STYLE_PRESETS,
    StylePresetResolver,
)
from ui.theme import Theme


class PresetConfigDialog(QDialog):
    """Dialog cấu hình thông số cho các Style Preset (Loud, Whisper) kèm nút khôi phục mặc định từng tab."""

    presets_configured = Signal(dict)

    def __init__(
        self,
        current_presets: Optional[Dict[str, Dict[str, Any]]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Cấu hình Style Presets")
        self.setMinimumWidth(420)

        defaults = StylePresetResolver.get_default_presets()
        incoming = current_presets or {}
        self._presets: Dict[str, Dict[str, Any]] = {
            "loud": {**defaults["loud"], **copy.deepcopy(incoming.get("loud") or {})},
            "whisper": {**defaults["whisper"], **copy.deepcopy(incoming.get("whisper") or {})},
        }
        self._controls: Dict[str, Dict[str, Any]] = {}

        self._setup_ui()
        self._load_preset_into_ui("loud", self._presets["loud"])
        self._load_preset_into_ui("whisper", self._presets["whisper"])

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget(self)
        self.tab_loud = self._create_preset_tab("loud", "🔄 Khôi phục mặc định Loud")
        self.tab_whisper = self._create_preset_tab("whisper", "🔄 Khôi phục mặc định Whisper")
        self.tabs.addTab(self.tab_loud, "⚡ Loud (Nhấn mạnh)")
        self.tabs.addTab(self.tab_whisper, "🤫 Whisper (Thì thầm)")
        layout.addWidget(self.tabs)

        self.btn_reset_loud = self._controls["loud"]["btn_reset"]
        self.btn_reset_whisper = self._controls["whisper"]["btn_reset"]

        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Lưu áp dụng")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save_clicked)

        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_save)
        layout.addLayout(footer)

        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {Theme.BG_APP};
                color: {Theme.TEXT_PRIMARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                background-color: {Theme.SURFACE};
                padding: 8px;
            }}
            QTabBar::tab {{
                background-color: {Theme.SURFACE_SOFT};
                color: {Theme.TEXT_SECONDARY};
                padding: 6px 14px;
                border: 1px solid {Theme.BORDER};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {Theme.SURFACE};
                color: {Theme.CYAN};
                font-weight: bold;
            }}
            """
        )

    def _create_preset_tab(self, key: str, reset_label: str) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        spin_scale = QSpinBox()
        spin_scale.setRange(50, 300)
        spin_scale.setSuffix(" %")
        form.addRow("Tỷ lệ kích thước:", spin_scale)

        btn_color = QPushButton()
        btn_color.setCursor(Qt.PointingHandCursor)
        btn_color.clicked.connect(lambda _=False, k=key: self._choose_color_for(k))
        form.addRow("Màu chữ:", btn_color)

        spin_outline = QDoubleSpinBox()
        spin_outline.setRange(0.0, 20.0)
        spin_outline.setSingleStep(0.5)
        spin_outline.setDecimals(1)
        spin_outline.setSuffix(" px")
        form.addRow("Độ dày viền:", spin_outline)

        btn_outline_color = QPushButton()
        btn_outline_color.setCursor(Qt.PointingHandCursor)
        btn_outline_color.clicked.connect(lambda _=False, k=key: self._choose_outline_color_for(k))
        form.addRow("Màu viền:", btn_outline_color)

        style_row = QHBoxLayout()
        chk_bold = QCheckBox("In đậm (Bold)")
        chk_italic = QCheckBox("In nghiêng (Italic)")
        style_row.addWidget(chk_bold)
        style_row.addWidget(chk_italic)
        style_row.addStretch()
        form.addRow("Kiểu chữ:", style_row)

        vbox.addLayout(form)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        btn_reset = QPushButton(reset_label)
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.clicked.connect(lambda _=False, k=key: self.reset_preset(k))
        reset_row.addWidget(btn_reset)
        vbox.addLayout(reset_row)

        self._controls[key] = {
            "spin_scale": spin_scale,
            "btn_color": btn_color,
            "color": QColor(DEFAULT_STYLE_PRESETS[key]["font_color"]),
            "spin_outline": spin_outline,
            "btn_outline_color": btn_outline_color,
            "outline_color": QColor(DEFAULT_STYLE_PRESETS[key].get("outline_color", "#000000")),
            "chk_bold": chk_bold,
            "chk_italic": chk_italic,
            "btn_reset": btn_reset,
        }
        return page

    def _update_color_btn(self, key: str, color: QColor):
        ctrl = self._controls[key]
        ctrl["color"] = color
        hex_code = color.name().upper()
        text_fg = "#000000" if color.lightness() > 140 else "#FFFFFF"
        ctrl["btn_color"].setText(hex_code)
        ctrl["btn_color"].setStyleSheet(
            f"background-color: {hex_code}; color: {text_fg}; font-weight: bold; "
            "border: 1px solid #555; border-radius: 4px; min-height: 26px; padding: 2px 8px;"
        )

    def _choose_color_for(self, key: str):
        ctrl = self._controls[key]
        color = QColorDialog.getColor(ctrl["color"], self, "Chọn màu chữ Preset")
        if color.isValid():
            self._update_color_btn(key, color)

    def _update_outline_color_btn(self, key: str, color: QColor):
        ctrl = self._controls[key]
        ctrl["outline_color"] = color
        hex_code = color.name().upper()
        text_fg = "#000000" if color.lightness() > 140 else "#FFFFFF"
        ctrl["btn_outline_color"].setText(hex_code)
        ctrl["btn_outline_color"].setStyleSheet(
            f"background-color: {hex_code}; color: {text_fg}; font-weight: bold; "
            "border: 1px solid #555; border-radius: 4px; min-height: 26px; padding: 2px 8px;"
        )

    def _choose_outline_color_for(self, key: str):
        ctrl = self._controls[key]
        color = QColorDialog.getColor(ctrl["outline_color"], self, "Chọn màu viền Preset")
        if color.isValid():
            self._update_outline_color_btn(key, color)

    def _load_preset_into_ui(self, key: str, cfg: Dict[str, Any]):
        ctrl = self._controls[key]
        scale_pct = int(round(float(cfg.get("scale", 1.0)) * 100))
        ctrl["spin_scale"].setValue(scale_pct)
        self._update_color_btn(key, QColor(cfg.get("font_color", DEFAULT_STYLE_PRESETS[key]["font_color"])))
        ctrl["spin_outline"].setValue(float(cfg.get("outline_width", DEFAULT_STYLE_PRESETS[key]["outline_width"])))
        self._update_outline_color_btn(
            key, QColor(cfg.get("outline_color", DEFAULT_STYLE_PRESETS[key].get("outline_color", "#000000")))
        )
        ctrl["chk_bold"].setChecked(bool(cfg.get("bold", DEFAULT_STYLE_PRESETS[key]["bold"])))
        ctrl["chk_italic"].setChecked(bool(cfg.get("italic", DEFAULT_STYLE_PRESETS[key]["italic"])))

    def reset_preset(self, key: str):
        """Khôi phục thông số mặc định cho riêng tab key ('loud' hoặc 'whisper')."""
        if key not in DEFAULT_STYLE_PRESETS:
            return
        default_cfg = copy.deepcopy(DEFAULT_STYLE_PRESETS[key])
        self._load_preset_into_ui(key, default_cfg)

    def get_presets(self) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for key in ("loud", "whisper"):
            ctrl = self._controls[key]
            result[key] = {
                "scale": round(ctrl["spin_scale"].value() / 100.0, 2),
                "font_color": ctrl["color"].name().upper(),
                "outline_width": round(float(ctrl["spin_outline"].value()), 1),
                "outline_color": ctrl["outline_color"].name().upper(),
                "bold": bool(ctrl["chk_bold"].isChecked()),
                "italic": bool(ctrl["chk_italic"].isChecked()),
            }
        return result

    def _on_save_clicked(self):
        self._presets = self.get_presets()
        self.presets_configured.emit(copy.deepcopy(self._presets))
        self.accept()
