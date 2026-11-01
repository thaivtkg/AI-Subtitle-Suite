import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

Rectangle {
    id: root
    implicitHeight: mainCol.implicitHeight + 12
    radius: 12
    color: Theme.glassPodRaised
    border.color: Theme.accentSapphire
    border.width: 1.5

    signal closeRequested()

    property string findText: findInput.text
    property string replaceText: replaceInput.text
    property string scope: scopeCombo.currentIndex === 0 ? "TRANSLATION" : (scopeCombo.currentIndex === 2 ? "ORIGINAL" : "ALL")
    property bool matchCase: chkMatchCase.checked
    property bool wholeWord: chkWholeWord.checked
    property bool isRegex: chkRegex.checked
    property bool addToGlossary: chkGlossary.checked
    property string statusMessage: ""
    property int previewCount: -1

    function focusFind() {
        findInput.forceActiveFocus()
        findInput.selectAll()
    }

    function doPreview() {
        if (!findInput.text.trim()) {
            statusMessage = "Vui lòng nhập từ khóa tìm kiếm"
            previewCount = -1
            return
        }
        if (typeof projectController !== "undefined") {
            var res = projectController.previewFindReplace(
                findInput.text,
                root.scope,
                root.matchCase,
                root.wholeWord,
                root.isRegex
            )
            if (res.error) {
                statusMessage = "⚠️ " + res.error
                previewCount = -1
            } else {
                previewCount = res.total_matches
                statusMessage = "Tìm thấy " + res.total_matches + " kết quả (" + res.affected_rows.length + " câu)"
            }
        }
    }

    function doReplaceAll() {
        if (!findInput.text.trim()) {
            statusMessage = "Vui lòng nhập từ khóa tìm kiếm"
            return
        }
        if (typeof projectController !== "undefined") {
            var count = projectController.executeFindReplace(
                findInput.text,
                replaceInput.text,
                root.scope,
                root.matchCase,
                root.wholeWord,
                root.isRegex,
                root.addToGlossary
            )
            previewCount = -1
            statusMessage = "Đã thay thế " + count + " vị trí"
        }
    }

    ColumnLayout {
        id: mainCol
        anchors.fill: parent
        anchors.margins: 6
        spacing: 5

        // Row 1: Search input ➔ Replace input + Close button
        RowLayout {
            Layout.fillWidth: true
            spacing: 5

            Text {
                text: "🔍"
                font.pixelSize: 11
            }

            TextField {
                id: findInput
                objectName: "findReplaceFindInput"
                Layout.fillWidth: true
                Layout.minimumWidth: 60
                implicitHeight: 24
                placeholderText: "Tìm..."
                placeholderTextColor: Theme.textMuted
                font.pixelSize: 11
                color: Theme.textPrimary
                leftPadding: 6
                rightPadding: 6
                background: Rectangle {
                    radius: 6
                    color: Theme.glassPodLuminous
                    border.color: findInput.activeFocus ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                    border.width: 1
                }
                onTextChanged: root.previewCount = -1
                onAccepted: root.doPreview()
            }

            Text {
                text: "➔"
                color: Theme.textSecondary
                font.pixelSize: 11
            }

            TextField {
                id: replaceInput
                objectName: "findReplaceReplaceInput"
                Layout.fillWidth: true
                Layout.minimumWidth: 60
                implicitHeight: 24
                placeholderText: "Thay..."
                placeholderTextColor: Theme.textMuted
                font.pixelSize: 11
                color: Theme.textPrimary
                leftPadding: 6
                rightPadding: 6
                background: Rectangle {
                    radius: 6
                    color: Theme.glassPodLuminous
                    border.color: replaceInput.activeFocus ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                    border.width: 1
                }
                onAccepted: root.doReplaceAll()
            }

            Button {
                id: btnClose
                implicitWidth: 20
                implicitHeight: 20
                contentItem: Text {
                    text: "✕"
                    color: Theme.textSecondary
                    font.pixelSize: 11
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 10
                    color: btnClose.hovered ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
                }
                onClicked: root.closeRequested()
            }
        }

        // Row 2: Scope ComboBox, Filter Toggles, and Action Buttons
        RowLayout {
            Layout.fillWidth: true
            spacing: 3

            ComboBox {
                id: scopeCombo
                implicitWidth: 78
                implicitHeight: 23
                model: ["Bản dịch", "Tất cả", "Câu gốc"]
                font.pixelSize: 10

                indicator: Text {
                    x: scopeCombo.width - width - 5
                    anchors.verticalCenter: parent.verticalCenter
                    text: "▾"
                    font.pixelSize: 9
                    color: Theme.textSecondary
                }

                contentItem: Text {
                    leftPadding: 6
                    rightPadding: scopeCombo.indicator ? scopeCombo.indicator.width + 4 : 14
                    text: scopeCombo.currentText
                    font.pixelSize: 10
                    font.bold: true
                    color: Theme.textPrimary
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                background: Rectangle {
                    radius: 5
                    color: Theme.glassPodLuminous
                    border.color: Theme.glassBorderSpecularUpper
                    border.width: 1
                }
            }

            CheckBox {
                id: chkMatchCase
                text: "Aa"
                font.pixelSize: 10
                implicitHeight: 22
                implicitWidth: 24
                padding: 0
                spacing: 2
                indicator: Rectangle {
                    implicitWidth: 10
                    implicitHeight: 10
                    x: 0
                    y: parent.height / 2 - height / 2
                    radius: 2
                    border.color: chkMatchCase.checked ? Theme.accentSapphire : "#94A3B8"
                    color: chkMatchCase.checked ? Theme.accentSapphire : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: "✓"
                        font.pixelSize: 8
                        color: "#FFFFFF"
                        visible: chkMatchCase.checked
                    }
                }
                contentItem: Text {
                    text: chkMatchCase.text
                    font.pixelSize: 9
                    color: chkMatchCase.checked ? Theme.accentSapphire : Theme.textSecondary
                    leftPadding: 12
                    verticalAlignment: Text.AlignVCenter
                }
                ToolTip.visible: hovered
                ToolTip.text: "Phân biệt hoa/thường"
                ToolTip.delay: 400
            }

            CheckBox {
                id: chkWholeWord
                text: "Từ"
                font.pixelSize: 10
                implicitHeight: 22
                implicitWidth: 24
                padding: 0
                spacing: 2
                indicator: Rectangle {
                    implicitWidth: 10
                    implicitHeight: 10
                    x: 0
                    y: parent.height / 2 - height / 2
                    radius: 2
                    border.color: chkWholeWord.checked ? Theme.accentSapphire : "#94A3B8"
                    color: chkWholeWord.checked ? Theme.accentSapphire : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: "✓"
                        font.pixelSize: 8
                        color: "#FFFFFF"
                        visible: chkWholeWord.checked
                    }
                }
                contentItem: Text {
                    text: chkWholeWord.text
                    font.pixelSize: 9
                    color: chkWholeWord.checked ? Theme.accentSapphire : Theme.textSecondary
                    leftPadding: 12
                    verticalAlignment: Text.AlignVCenter
                }
                ToolTip.visible: hovered
                ToolTip.text: "Khớp trọn vẹn từ"
                ToolTip.delay: 400
            }

            CheckBox {
                id: chkRegex
                text: ".*"
                font.pixelSize: 10
                implicitHeight: 22
                implicitWidth: 22
                padding: 0
                spacing: 2
                indicator: Rectangle {
                    implicitWidth: 10
                    implicitHeight: 10
                    x: 0
                    y: parent.height / 2 - height / 2
                    radius: 2
                    border.color: chkRegex.checked ? Theme.accentSapphire : "#94A3B8"
                    color: chkRegex.checked ? Theme.accentSapphire : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: "✓"
                        font.pixelSize: 8
                        color: "#FFFFFF"
                        visible: chkRegex.checked
                    }
                }
                contentItem: Text {
                    text: chkRegex.text
                    font.pixelSize: 9
                    color: chkRegex.checked ? Theme.accentSapphire : Theme.textSecondary
                    leftPadding: 12
                    verticalAlignment: Text.AlignVCenter
                }
                ToolTip.visible: hovered
                ToolTip.text: "Biểu thức chính quy (Regex)"
                ToolTip.delay: 400
            }

            CheckBox {
                id: chkGlossary
                text: "📌"
                checked: true
                font.pixelSize: 10
                implicitHeight: 22
                implicitWidth: 20
                padding: 0
                spacing: 2
                indicator: Rectangle {
                    implicitWidth: 10
                    implicitHeight: 10
                    x: 0
                    y: parent.height / 2 - height / 2
                    radius: 2
                    border.color: chkGlossary.checked ? Theme.accentSapphire : "#94A3B8"
                    color: chkGlossary.checked ? Theme.accentSapphire : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: "✓"
                        font.pixelSize: 8
                        color: "#FFFFFF"
                        visible: chkGlossary.checked
                    }
                }
                contentItem: Text {
                    text: chkGlossary.text
                    font.pixelSize: 9
                    leftPadding: 12
                    verticalAlignment: Text.AlignVCenter
                }
                ToolTip.visible: hovered
                ToolTip.text: "Tự ghim vào Glossary"
                ToolTip.delay: 400
            }

            Item {
                Layout.fillWidth: true
            }

            Button {
                id: btnPreview
                objectName: "btnFindPreview"
                text: root.previewCount >= 0 ? "Tìm (" + root.previewCount + ")" : "Tìm"
                implicitHeight: 23
                implicitWidth: root.previewCount >= 0 ? 48 : 34
                contentItem: Text {
                    text: btnPreview.text
                    color: Theme.accentSapphire
                    font.pixelSize: 10
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 5
                    color: btnPreview.hovered ? Qt.rgba(0.0, 0.45, 1.0, 0.15) : Qt.rgba(0.0, 0.45, 1.0, 0.08)
                    border.color: Theme.accentSapphire
                    border.width: 1
                }
                onClicked: root.doPreview()
            }

            Button {
                id: btnReplace
                objectName: "btnFindReplaceAll"
                text: "Thay thế"
                implicitHeight: 23
                implicitWidth: 50
                contentItem: Text {
                    text: btnReplace.text
                    color: "#FFFFFF"
                    font.pixelSize: 10
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 5
                    color: Theme.accentSapphire
                }
                onClicked: root.doReplaceAll()
            }
        }

        // Row 3: Status feedback (auto-collapses when empty)
        Text {
            id: statusLbl
            visible: text.length > 0
            text: root.statusMessage
            color: root.statusMessage.indexOf("⚠️") !== -1 ? Theme.danger : Theme.accentSapphire
            font.pixelSize: 10
            font.bold: true
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
