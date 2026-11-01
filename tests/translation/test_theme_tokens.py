import pytest
from pathlib import Path


def test_theme_contains_liquid_glass_tokens():
    theme_file = Path("ui/qml_translation/theme/Theme.qml")
    assert theme_file.exists(), "Theme.qml must exist"
    content = theme_file.read_text(encoding="utf-8")

    required_tokens = [
        "glassBackground",
        "glassIslandSurface",
        "glassIslandActive",
        "glassPodLuminous",
        "glassPodRaised",
        "glassBorderSpecularUpper",
        "glassBorderSpecularLower",
        "glassBorderSubtle",
        "glassGleamWhite",
        "accentSapphire",
        "accentSapphireHover",
        "accentSapphireGradientEnd",
        "textOnLightPod",
        "textOnLightPodMuted",
        "textPrimaryGlass",
        "badgeEmeraldBg",
        "badgeEmeraldText",
        "badgeAmberBg",
        "badgeAmberText",
        "radiusIsland",
        "radiusPill",
        "islandSpacing",
        "windowPadding",
    ]

    for token in required_tokens:
        assert token in content, f"Missing token '{token}' in Theme.qml"
