import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import QtQuick.Effects
import "../theme"

Rectangle {
    id: root
    width: Math.min(Math.max(messageText.implicitWidth + 80, 260), 460)
    height: Math.max(46, messageText.implicitHeight + Theme.spaceLarge)
    radius: height / 2

    // Dark Liquid Glass Capsule chuẩn Studio (thay thế capsule trắng gây mất chữ)
    color: Qt.rgba(0.10, 0.14, 0.22, 0.96)
    border.color: Theme.glassBorderSpecularUpper
    border.width: 1.2

    opacity: 0.0
    visible: opacity > 0

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Qt.rgba(0.0, 0.0, 0.0, 0.40)
        shadowBlur: 0.50
        shadowVerticalOffset: 4
    }

    property string message: ""
    property string type: "INFO"

    y: parent ? parent.height - height - 30 : 0
    anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
    z: 999

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.spaceSmall
        anchors.leftMargin: Theme.spaceMedium
        anchors.rightMargin: Theme.spaceMedium
        spacing: Theme.spaceMedium

        // Icon capsule
        Rectangle {
            width: 26
            height: 26
            radius: 13
            color: root.type === "SUCCESS" ? Qt.rgba(0.13, 0.77, 0.37, 0.20) :
                   (root.type === "ERROR" ? Qt.rgba(0.94, 0.27, 0.27, 0.20) : Qt.rgba(0.0, 0.45, 1.0, 0.20))
            Layout.alignment: Qt.AlignVCenter

            Text {
                anchors.centerIn: parent
                text: root.type === "SUCCESS" ? "✓" : (root.type === "ERROR" ? "✕" : "ℹ")
                color: root.type === "SUCCESS" ? "#10B981" : (root.type === "ERROR" ? "#EF4444" : "#38BDF8")
                font.pixelSize: 13
                font.bold: true
            }
        }

        Text {
            id: messageText
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            text: root.message
            color: Theme.textPrimary   // Slate 50 (#F8FAFC) - Tương phản sắc nét trên nền Dark Glass
            font.pixelSize: 13
            font.bold: true
            wrapMode: Text.WordWrap
            lineHeight: 1.2
        }
    }

    Timer {
        id: hideTimer
        interval: 3500
        onTriggered: hide()
    }

    function show(title, msg) {
        root.type = title || "INFO"
        root.message = msg || ""
        root.opacity = 1.0
        slideOut.stop()
        slideIn.start()
        hideTimer.restart()
    }

    function hide() {
        slideIn.stop()
        slideOut.start()
    }

    ParallelAnimation {
        id: slideIn
        NumberAnimation {
            target: root
            property: "opacity"
            from: 0.0
            to: 1.0
            duration: 250
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: root
            property: "y"
            from: (root.parent ? root.parent.height - root.height - 10 : root.y + 20)
            to: (root.parent ? root.parent.height - root.height - 30 : root.y)
            duration: 250
            easing.type: Easing.OutBack
        }
    }

    ParallelAnimation {
        id: slideOut
        NumberAnimation {
            target: root
            property: "opacity"
            from: 1.0
            to: 0.0
            duration: 200
            easing.type: Easing.InQuad
        }
        NumberAnimation {
            target: root
            property: "y"
            from: (root.parent ? root.parent.height - root.height - 30 : root.y)
            to: (root.parent ? root.parent.height - root.height - 10 : root.y + 20)
            duration: 200
            easing.type: Easing.InQuad
        }
    }
}
