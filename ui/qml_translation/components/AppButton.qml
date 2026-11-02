import QtQuick 2.15
import QtQuick.Controls.Basic
import "../theme"

Button {
    id: control
    property bool isPrimary: false
    property bool isDestructive: false
    property bool isDarkGlass: true  // Mặc định chuẩn Dark Liquid Glass cho toàn bộ hệ thống
    property string tooltip: ""

    implicitWidth: Math.max(80, contentItem.implicitWidth + Theme.spaceLarge)
    implicitHeight: 32
    focusPolicy: Qt.NoFocus
    z: 1

    ToolTip {
        id: appToolTip
        visible: control.hovered && control.tooltip !== ""
        text: control.tooltip
        delay: 400
        timeout: 3000
        background: Rectangle {
            color: Qt.rgba(0.08, 0.11, 0.17, 0.96)
            radius: 8
            border.color: Qt.rgba(1.0, 1.0, 1.0, 0.15)
            border.width: 1
        }
        contentItem: Text {
            text: appToolTip.text
            color: Theme.textPrimary
            font.pixelSize: 11
        }
    }

    contentItem: Text {
        text: control.text
        font.pixelSize: 12
        font.bold: true
        color: !control.enabled ? Qt.rgba(1, 1, 1, 0.40) : (control.hovered ? "#FFFFFF" : Theme.textPrimary)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        id: btnBg

        width: control.width
        height: control.height

        // Luôn bo góc dạng viên thuốc
        radius: Math.min(width, height) / 2
        antialiasing: true

        gradient: Gradient {
            orientation: Gradient.Horizontal

            GradientStop {
                position: 0.0
                color: !control.enabled
                       ? Qt.rgba(1, 1, 1, 0.08)
                       : control.isDestructive
                         ? (control.pressed ? "#991B1B" :
                            control.hovered ? "#DC2626" : "#B91C1C")
                         : control.isPrimary
                           ? (control.pressed ? "#1D4ED8" :
                              control.hovered ? "#3B82F6" : "#2563EB")
                           : control.hovered
                             ? Qt.rgba(0.20, 0.26, 0.38, 0.95)
                             : Qt.rgba(0.12, 0.16, 0.24, 0.85)
            }

            GradientStop {
                position: 1.0
                color: !control.enabled
                       ? Qt.rgba(1, 1, 1, 0.08)
                       : control.isDestructive
                         ? (control.pressed ? "#7F1D1D" :
                            control.hovered ? "#B91C1C" : "#991B1B")
                         : control.isPrimary
                           ? (control.pressed ? "#4338CA" :
                              control.hovered ? "#6366F1" : "#4F46E5")
                           : control.hovered
                             ? Qt.rgba(0.24, 0.30, 0.45, 0.95)
                             : Qt.rgba(0.15, 0.19, 0.28, 0.85)
            }
        }

        border.color: !control.enabled
                      ? Qt.rgba(1, 1, 1, 0.10)
                      : control.isDestructive
                        ? (control.hovered
                           ? Qt.rgba(1.0, 0.4, 0.4, 0.80)
                           : Qt.rgba(1.0, 0.2, 0.2, 0.40))
                        : control.isPrimary
                          ? (control.hovered
                             ? Qt.rgba(1, 1, 1, 0.60)
                             : Qt.rgba(1, 1, 1, 0.30))
                          : control.hovered
                            ? Theme.accentSapphire
                            : Qt.rgba(1, 1, 1, 0.15)

        border.width: 1

        Behavior on border.color {
            ColorAnimation { duration: 150 }
        }
    }
}
