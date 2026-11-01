import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

RowLayout {
    id: root
    property alias sourceLang: sourceCombo.currentText
    property bool compact: false

    Layout.minimumWidth: 0
    spacing: root.compact ? Theme.spaceXs : Theme.spaceMedium

    Text { text: "SOURCE"; color: "#FFFFFF"; font.pixelSize: 11; font.bold: true; visible: !root.compact }

    ComboBox {
        objectName: "sourceLanguageCombo"
        id: sourceCombo
        model: ["English", "Japanese", "Chinese (Simplified)", "Chinese (Traditional)", "Korean", "Spanish", "French", "German", "Russian", "Vietnamese"]
        font.pixelSize: root.compact ? 12 : 14
        Layout.minimumWidth: root.compact ? 75 : 110
        Layout.preferredWidth: root.compact ? 95 : 160
        Layout.maximumWidth: root.compact ? 120 : 180
        Layout.fillWidth: true
        contentItem: Text {
            text: sourceCombo.currentText
            color: Theme.textPrimary
            font.pixelSize: root.compact ? 12 : 14
            font.bold: true
            verticalAlignment: Text.AlignVCenter
            leftPadding: root.compact ? 4 : Theme.spaceSmall
            rightPadding: sourceCombo.indicator.width + (root.compact ? 4 : Theme.spaceSmall)
            elide: Text.ElideRight
        }
        
        indicator: Text {
            x: sourceCombo.width - width - Theme.spaceSmall
            anchors.verticalCenter: parent.verticalCenter
            text: sourcePopup.visible ? "▴" : "▾"
            color: Theme.accentSapphire
            font.pixelSize: 12
            font.bold: true
        }

        delegate: ItemDelegate {
            width: sourceCombo.width - 12
            implicitHeight: 34
            contentItem: RowLayout {
                spacing: 8
                Text {
                    text: modelData
                    color: Theme.textPrimary
                    font.pixelSize: 12
                    font.bold: highlighted || sourceCombo.currentIndex === index
                    verticalAlignment: Text.AlignVCenter
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Text {
                    text: "✓"
                    color: Theme.accentSapphire
                    font.pixelSize: 12
                    font.bold: true
                    visible: sourceCombo.currentIndex === index
                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                }
            }
            background: Rectangle {
                radius: 8
                color: sourceCombo.currentIndex === index ? Qt.rgba(0.0, 0.4, 1.0, 0.12) :
                       highlighted ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                border.color: sourceCombo.currentIndex === index ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                border.width: 1
            }
        }

        popup: Popup {
            id: sourcePopup
            y: sourceCombo.height + 4
            width: sourceCombo.width
            padding: 6
            implicitHeight: Math.min(contentItem.implicitHeight + padding * 2, 260)

            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: sourcePopup.visible ? sourceCombo.delegateModel : null
                currentIndex: sourceCombo.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator { }
            }

            background: Rectangle {
                color: Qt.rgba(0.08, 0.11, 0.17, 0.96)
                border.color: Theme.glassBorderSpecularUpper
                border.width: 1.5
                radius: 14
            }
        }
        background: Rectangle {
            color: Theme.glassPodLuminous
            radius: 12
            border.color: sourceCombo.activeFocus || sourcePopup.visible ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
            border.width: 1
        }
    }

    Text { text: root.compact ? "→" : " ➔ "; color: Qt.rgba(1.0, 1.0, 1.0, 0.8); font.pixelSize: root.compact ? 13 : 16; font.bold: true }

    Text { text: "TARGET"; color: "#FFFFFF"; font.pixelSize: 11; font.bold: true; visible: !root.compact }

    ComboBox {
        id: targetCombo
        model: ["Vietnamese"]
        font.pixelSize: root.compact ? 12 : 14
        Layout.minimumWidth: root.compact ? 75 : 95
        Layout.preferredWidth: root.compact ? 95 : 120
        Layout.maximumWidth: root.compact ? 110 : 140
        Layout.fillWidth: true
        contentItem: Text {
            text: targetCombo.currentText
            color: Theme.textSecondary
            font.pixelSize: root.compact ? 12 : 14
            font.bold: true
            verticalAlignment: Text.AlignVCenter
            leftPadding: root.compact ? 4 : Theme.spaceSmall
            rightPadding: targetIndicator.width + (root.compact ? 4 : Theme.spaceSmall)
            elide: Text.ElideRight
        }
        indicator: Text {
            id: targetIndicator
            x: targetCombo.width - width - Theme.spaceSmall
            anchors.verticalCenter: parent.verticalCenter
            text: "▾"
            color: "#94A3B8"
            font.pixelSize: 12
        }
        background: Rectangle {
            color: Theme.glassIslandSurface
            radius: 12
            border.color: Theme.glassBorderSubtle
            border.width: 1
        }
        enabled: false // Target luôn cố định
    }

    function setLanguage(lang) {
        let idx = sourceCombo.find(lang)
        if (idx !== -1) sourceCombo.currentIndex = idx
    }
}
