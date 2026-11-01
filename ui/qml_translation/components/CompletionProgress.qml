import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../theme"

ColumnLayout {
    id: root

    property int acceptedCount: 0
    property int totalCount: 0
    property real progressRatio: totalCount > 0 ? acceptedCount / totalCount : 0
    property int progressPercent: Math.round(progressRatio * 100)
    property bool isComplete: totalCount > 0 && acceptedCount === totalCount

    visible: totalCount > 0
    spacing: Theme.spaceSmall

    RowLayout {
        Layout.fillWidth: true
        Text {
            text: root.acceptedCount + " / " + root.totalCount + " Accepted"
            color: root.isComplete ? Theme.success : Theme.textSecondary
            font.pixelSize: 12
            font.bold: true
        }
        Item { Layout.fillWidth: true }
        Text {
            text: root.progressPercent + "%"
            color: root.isComplete ? Theme.success : Theme.textPrimary
            font.pixelSize: 12
            font.bold: true
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 4
        color: Theme.bgSurfaceSoft
        radius: 2
        clip: true
        Rectangle {
            width: parent.width * root.progressRatio
            height: parent.height
            color: root.isComplete ? Theme.success : Theme.accentCyan
            radius: 2
            Behavior on width { NumberAnimation { duration: Theme.animProgress; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation { duration: Theme.animState; easing.type: Easing.OutQuad } }
        }
    }
}
