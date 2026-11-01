pragma Singleton
import QtQuick 2.15

QtObject {
    // --- Legacy / Base Backgrounds (Preserved for compatibility) ---
    readonly property color bgApp: "#090D16"
    readonly property color bgSurface: "#0F172A"
    readonly property color bgSurfaceElevated: "#172033"
    readonly property color bgSurfaceSoft: "#1E293B"
    readonly property color border: "#273247"
    readonly property color borderDisabled: "#273247"
    // Bổ sung màu nền chuẩn Dark Deep Navy của Studio
    readonly property color colorBackground: "#0B0F19"

    // --- Dark Liquid Glass Surfaces (Đồng bộ chuẩn Studio Obsidian / Navy) ---
    readonly property color glassBackground: Qt.rgba(0.05, 0.07, 0.10, 0.75)
    readonly property color glassIslandSurface: Qt.rgba(0.08, 0.10, 0.15, 0.70)      // Phủ mờ Slate tối
    readonly property color glassIslandActive: Qt.rgba(0.39, 0.40, 0.95, 0.25)       // Viền Indigo nổi bật (#6366F1)
    readonly property color glassPodLuminous: Qt.rgba(0.12, 0.15, 0.21, 0.85)       // Thay thế nền trắng bằng Surface Elevated (#1E2536)
    readonly property color glassPodRaised: Qt.rgba(0.15, 0.18, 0.25, 0.90)         // Phím bấm Surface Soft (#262E40)
    readonly property color glassDarkPill: Qt.rgba(0.07, 0.09, 0.14, 0.80)
    readonly property color glassDarkPillHover: Qt.rgba(0.12, 0.15, 0.23, 0.90)
    readonly property color badgeSolidEmerald: "#10B981"

    // --- Specular Bevels & Refractive Rims ---
    readonly property color glassBorderSpecularUpper: Qt.rgba(1.0, 1.0, 1.0, 0.12)  // Viền sáng tinh tế, không chói
    readonly property color glassBorderSpecularLower: Qt.rgba(1.0, 1.0, 1.0, 0.05)
    readonly property color glassBorderSubtle: Qt.rgba(1.0, 1.0, 1.0, 0.04)
    readonly property color glassBevelInner: Qt.rgba(0.0, 0.0, 0.0, 0.08)          // Đổ bóng lồi mép kính 3D
    readonly property color glassGleamWhite: Qt.rgba(1.0, 1.0, 1.0, 0.55)          // Vệt sáng lóa bề mặt (Specular Gleam)

    // --- Sapphire Blue Theme Accents ---
    readonly property color accentSapphire: "#0066FF"
    readonly property color accentSapphireHover: "#1A75FF"
    readonly property color accentSapphireGradientEnd: "#0284C7"

    // --- High-Contrast Typography (Chữ sáng trên nền tối) ---
    readonly property color textOnLightPod: "#F8FAFC"       // Slate 50 (Trắng ngà sắc nét)
    readonly property color textOnLightPodMuted: "#94A3B8"  // Slate 400 (Xám bạc)
    readonly property color textPrimaryGlass: "#F8FAFC"
    readonly property color textSecondaryGlass: "#94A3B8"
    readonly property color textMutedGlass: "#64748B"

    // --- Vibrant Badges & Accents ---
    readonly property color badgeEmeraldBg: "#DCFCE7"
    readonly property color badgeEmeraldText: "#15803D"
    readonly property color badgeAmberBg: "#FEF3C7"
    readonly property color badgeAmberText: "#B45309"
    readonly property color badgePurpleGradientStart: "#8B5CF6"
    readonly property color badgePurpleGradientEnd: "#EC4899"
    readonly property color accentOrangeKeyword: "#EA580C"

    // --- Dimension & Corner Radius Metrics ---
    readonly property int radiusIsland: 26
    readonly property int radiusPill: 22
    readonly property int islandSpacing: 12
    readonly property int windowPadding: 14

    // --- Existing Accents ---
    readonly property color accentPurple: "#8B5CF6"
    readonly property color accentPink: "#EC4899"
    readonly property color accentCyan: "#38BDF8"
    readonly property color success: "#34D399"
    readonly property color warning: "#FBBF24"
    readonly property color danger: "#F43F5E"

    // --- Existing Text ---
    readonly property color textPrimary: "#F8FAFC"
    readonly property color textSecondary: "#CBD5E1"
    readonly property color textMuted: "#94A3B8"
    readonly property color textDisabled: "#64748B"

    // --- Spacing ---
    readonly property int spaceXs: 4
    readonly property int spaceSmall: 8
    readonly property int spaceMedium: 16
    readonly property int spaceLarge: 24
    readonly property int spaceXl: 32

    // --- Radius & Animation ---
    readonly property int radius: 6
    readonly property int animDuration: 150

    // --- Micro-interaction Tokens (T12) ---
    readonly property int animHover: 120
    readonly property int animFocus: 150
    readonly property int animState: 150
    readonly property int animProgress: 220
}
