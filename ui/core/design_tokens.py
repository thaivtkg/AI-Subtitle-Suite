"""Single source of truth for the UI: legacy palette identity + P0 visual grammar.

Colors are the original AI Subtitle Studio palette (deep slate/navy surfaces,
indigo primary, sky-blue accent, pink secondary gradient) re-expressed as semantic tokens.
Geometry follows the locked P0 grammar:
Control 8px / Surface 16px / Glass 24px / Pill for primary actions.
`ui.theme.Theme` aliases these values for backward compatibility.
"""


class ColorToken:
    # Surfaces (Studio Slate / Charcoal Neutral Palette)
    BG_APP = "#0B0F17"           # Deep Obsidian Slate (Main backdrop)
    SURFACE = "#151B28"          # Charcoal Surface (Panels, Sidebars, Cards)
    SURFACE_ELEVATED = "#1E293B" # Slate 800 Elevated (Active panels, containers)
    SURFACE_SOFT = "#334155"     # Slate 700 Soft (Hover, dividers, chips)
    BORDER = "#1E293B"           # Slate 800 Subtle border
    BORDER_MUTED = "#334155"     # Slate 700 Hairline border

    # Single Accent: Indigo / Sky (Eliminating #EC4899 and glowing #38BDF8)
    PRIMARY = "#4F46E5"          # Indigo 600 (Primary action)
    PRIMARY_HOVER = "#6366F1"    # Indigo 500
    PRIMARY_PRESSED = "#4338CA"  # Indigo 700
    PRIMARY_PINK = "#4F46E5"     # Deprecated alias to Primary
    PRIMARY_GREEN = "#10B981"    # Emerald 500 (Status only)
    PRIMARY_GRADIENT = "#4F46E5" # Single-hue solid primary
    ACCENT = "#6366F1"           # Clean Indigo accent (Focus ring / Active tag)
    ACCENT_HOVER = "#4F46E5"

    # Semantic Status
    SUCCESS = "#10B981"
    DANGER = "#EF4444"
    WARNING = "#F59E0B"
    INFO = "#3B82F6"

    # Text hierarchy (Slate typography)
    TEXT_PRIMARY = "#F8FAFC"       # Slate 50
    TEXT_SECONDARY = "#94A3B8"     # Slate 400
    TEXT_MUTED = "#64748B"         # Slate 500
    TEXT_DISABLED = "#475569"      # Slate 600

    # Interaction overlays
    GLASS_SURFACE = "rgba(21, 27, 40, 0.85)"
    GLASS_EDGE = "rgba(255, 255, 255, 0.05)"
    GLASS_EDGE_TOP = "rgba(255, 255, 255, 0.10)"
    HOVER_OVERLAY = "rgba(255, 255, 255, 0.05)"
    SELECTED_SURFACE = "rgba(79, 70, 229, 0.16)"


class RadiusToken:
    INNER = 4      # Checkbox, radio, scrollbar handle, tiny tags
    CONTROL = 8    # Input, combo, buttons, tabs, list items (6-8px standard)
    SURFACE = 12   # Content surfaces, cards, dialogs, popovers (10-12px nested)
    FLOATING = 12  # Glass outer (sidebar dock, overlays)
    PILL = 8       # Primary actions standardize to 8px control radius (eliminated 999px)


class SpacingToken:
    XS = 4
    SM = 8    # Control-to-control, icon-to-text
    MD = 16
    LG = 24   # Section-to-section, surface padding
    XL = 32


class SizeToken:
    CONTROL_HEIGHT = 32
    ICON_BUTTON = 36        # Standard icon-only button
    SIDEBAR_WIDTH = 64
    TOPBAR_HEIGHT = 42


class TypographyToken:
    FONT_FAMILY = '"Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif'
    CAPTION = 11
    BODY = 13
    SECTION_TITLE = 13   # Semi-bold, title case
    PAGE_TITLE = 20
