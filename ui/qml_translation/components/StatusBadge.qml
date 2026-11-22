import QtQuick 2.15
import "../theme"

Rectangle {
    id: badge
    property string status: "PENDING"

    implicitWidth: statusText.width + Theme.spaceSmall * 2
    implicitHeight: 18
    radius: 2 // Bo góc sắc sảo hơn

    // Nền mờ (Opacity 15%)
    color: {
        if (status === "ACCEPTED") return Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.15)
        if (status === "TRANSLATING") return Qt.rgba(Theme.accentCyan.r, Theme.accentCyan.g, Theme.accentCyan.b, 0.15)
        if (status === "TRANSLATED" || status === "EDITED") return Qt.rgba(Theme.accentPurple.r, Theme.accentPurple.g, Theme.accentPurple.b, 0.15)
        if (status === "ERROR") return Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.15)
        return "transparent"
    }

    // Viền chìm
    border.color: {
        if (status === "ACCEPTED") return Theme.success
        if (status === "TRANSLATING") return Theme.accentCyan
        if (status === "TRANSLATED" || status === "EDITED") return Theme.accentPurple
        if (status === "ERROR") return Theme.danger
        return Theme.border
    }
    border.width: 1

    Text {
        id: statusText
        anchors.centerIn: parent
        text: badge.status === "PENDING" ? "○ Chờ dịch" :
              badge.status === "TRANSLATING" ? "◉ Đang dịch" :
              badge.status === "ACCEPTED" ? "✓ Đã duyệt" :
              badge.status === "EDITED" ? "● Đã sửa" :
              badge.status === "TRANSLATED" ? "✦ Đã dịch" :
              badge.status === "ERROR" ? "✕ Lỗi" : badge.status

        font.pixelSize: 10
        font.bold: true
        color: badge.status === "PENDING" ? Theme.textMuted : badge.border.color
    }
}
