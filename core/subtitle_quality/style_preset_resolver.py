import copy
from typing import Dict, Any, Optional

DEFAULT_STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "loud": {
        "scale": 1.20,
        "font_color": "#FFE600",
        "outline_color": "#000000",
        "outline_width": 3.5,
        "bold": True,
        "italic": False,
    },
    "whisper": {
        "scale": 0.85,
        "font_color": "#D0D0D0",
        "outline_color": "#000000",
        "outline_width": 1.5,
        "bold": False,
        "italic": True,
    },
}


class StylePresetResolver:
    """
    Quy đổi Style Preset (normal, loud, whisper) thành các thuộc tính trực quan
    (font_size, font_color, outline_width, bold, italic) dựa trên cấu hình global_style
    và custom_presets (nếu có).
    """

    @classmethod
    def get_default_presets(cls) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(DEFAULT_STYLE_PRESETS)

    @classmethod
    def resolve_style(
        cls,
        preset: str,
        global_style: Dict[str, Any],
        custom_presets: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        base = dict(global_style or {})
        base_size = int(base.get("font_size", 20) or 20)
        font_name = base.get("font_name", "Segoe UI")
        preset_clean = (preset or "normal").lower().strip()

        if preset_clean in ("loud", "whisper"):
            presets_pool = custom_presets or {}
            cfg = {
                **DEFAULT_STYLE_PRESETS[preset_clean],
                **(presets_pool.get(preset_clean) or {}),
            }
            scale = float(cfg.get("scale", 1.0))
            return {
                **base,
                "font_name": font_name,
                "font_size": int(round(base_size * scale)),
                "font_color": cfg.get("font_color", base.get("font_color", "#FFFFFF")),
                "outline_color": cfg.get("outline_color", base.get("outline_color", "#000000")),
                "outline_width": float(cfg.get("outline_width", base.get("outline_width", 2.0))),
                "bold": bool(cfg.get("bold", False)),
                "italic": bool(cfg.get("italic", False)),
            }

        # Normal fallback
        return {
            **base,
            "font_name": font_name,
            "font_size": base_size,
            "font_color": base.get("font_color", "#FFFFFF"),
            "outline_color": base.get("outline_color", "#000000"),
            "outline_width": float(base.get("outline_width", 2.0) or 2.0),
            "bold": False,
            "italic": False,
        }
