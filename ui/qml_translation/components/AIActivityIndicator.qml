import QtQuick 2.15
import "../theme"

Item {
    id: root
    implicitWidth: 14
    implicitHeight: 14
    property bool active: false
    property color color: Theme.accentCyan
    property int penWidth: 2
    visible: active

    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var radius = Math.min(width, height) / 2 - root.penWidth / 2
            ctx.beginPath()
            ctx.arc(width / 2, height / 2, radius, 0, Math.PI * 1.5, false)
            ctx.strokeStyle = root.color
            ctx.lineWidth = root.penWidth
            ctx.lineCap = "round"
            ctx.stroke()
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        RotationAnimator on rotation {
            running: root.active
            loops: Animation.Infinite
            from: 0
            to: 360
            duration: 1000
        }
    }
}
