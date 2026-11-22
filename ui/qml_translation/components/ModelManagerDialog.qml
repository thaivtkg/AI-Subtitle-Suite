import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

Dialog {
    id: root

    property var controller: typeof modelController !== "undefined" ? modelController : null

    title: ""
    modal: true
    dim: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    anchors.centerIn: Overlay.overlay

    width: Math.min(780, Overlay.overlay ? Overlay.overlay.width - 40 : 780)
    height: Math.min(560, Overlay.overlay ? Overlay.overlay.height - 48 : 560)
    padding: 0

    background: Rectangle {
        color: "#131824"
        radius: 20
        border.color: Theme.glassBorderSpecularUpper
        border.width: 1.5
    }

    Connections {
        target: root.controller
        function onDownloadProgress(modelId, percent, speed, eta) {
            // Danh sách tự cập nhật qua modelListChanged signal từ controller
        }
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ==========================================
        // HEADER DIALOG
        // ==========================================
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 52
            color: "#1C2436"
            radius: 20

            // Bo góc chỉ ở trên
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 20
                color: "#1C2436"
            }
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Qt.rgba(1, 1, 1, 0.08)
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 16
                spacing: Theme.spaceSmall

                Text {
                    text: "Quản lý mô hình dịch thuật AI (LLM)"
                    color: Theme.textPrimary
                    font.pixelSize: 15
                    font.bold: true
                    Layout.fillWidth: true
                }

                Rectangle {
                    implicitWidth: 32
                    implicitHeight: 28
                    radius: 8
                    color: closeMouse.containsMouse ? "#EF4444" : Qt.rgba(1, 1, 1, 0.06)
                    border.color: Qt.rgba(1, 1, 1, 0.12)
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        color: closeMouse.containsMouse ? "#FFFFFF" : Theme.textSecondary
                        font.pixelSize: 12
                        font.bold: true
                    }

                    MouseArea {
                        id: closeMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }
            }
        }

        // ==========================================
        // HARDWARE BANNER
        // ==========================================
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: hwLayout.implicitHeight + 16
            color: Theme.glassPodLuminous
            border.color: Theme.glassBorderSubtle
            border.width: 1

            RowLayout {
                id: hwLayout
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                spacing: Theme.spaceLarge

                RowLayout {
                    spacing: 6
                    Text { text: "GPU:"; color: "#94A3B8"; font.pixelSize: 12; font.bold: true }
                    Text {
                        text: root.controller && root.controller.hardwareSummary ? root.controller.hardwareSummary.gpu_name : "N/A"
                        color: Theme.textPrimary
                        font.pixelSize: 12
                        font.bold: true
                    }
                }

                RowLayout {
                    spacing: 6
                    Text { text: "VRAM:"; color: "#94A3B8"; font.pixelSize: 12; font.bold: true }
                    Text {
                        text: root.controller && root.controller.hardwareSummary ? (root.controller.hardwareSummary.vram_gb.toFixed(1) + " GB") : "0 GB"
                        color: Theme.accentSapphire
                        font.pixelSize: 12
                        font.bold: true
                        font.family: "JetBrains Mono, Consolas, monospace"
                        font.features: { "tnum": 1 }
                    }
                }

                RowLayout {
                    spacing: 6
                    Text { text: "Backend:"; color: "#94A3B8"; font.pixelSize: 12; font.bold: true }
                    Text {
                        text: root.controller && root.controller.hardwareSummary ? root.controller.hardwareSummary.backend_status : "CPU"
                        color: root.controller && root.controller.hardwareSummary && root.controller.hardwareSummary.has_cuda ? Theme.success : Theme.warning
                        font.pixelSize: 12
                        font.bold: true
                    }
                }

                Item { Layout.fillWidth: true }
            }
        }

        // ==========================================
        // GEMINI CLOUD API KEY & TEST CONNECTION
        // ==========================================
        Rectangle {
            id: geminiPanel
            objectName: "geminiApiPanel"
            Layout.fillWidth: true
            implicitHeight: geminiCol.implicitHeight + 18
            color: Qt.rgba(0.09, 0.13, 0.22, 0.9)
            border.color: Theme.glassBorderSubtle
            border.width: 1

            property bool showApiKey: false

            Connections {
                target: root.controller
                function onGeminiSettingsChanged() {
                    if (root.controller && geminiApiKeyField.text !== root.controller.geminiApiKey) {
                        geminiApiKeyField.text = root.controller.geminiApiKey
                    }
                }
            }

            ColumnLayout {
                id: geminiCol
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                anchors.topMargin: 9
                anchors.bottomMargin: 9
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spaceSmall

                    Text {
                        text: "Gemini API Key:"
                        color: "#CBD5E1"
                        font.pixelSize: 12
                        font.bold: true
                    }

                    TextField {
                        id: geminiApiKeyField
                        objectName: "geminiApiKeyField"
                        Layout.fillWidth: true
                        implicitHeight: 32
                        placeholderText: "Nhập Google Gemini API Key (AIza...)"
                        placeholderTextColor: "#64748B"
                        color: "#F8FAFC"
                        font.pixelSize: 12
                        font.family: "JetBrains Mono, Consolas, monospace"
                        echoMode: geminiPanel.showApiKey ? TextInput.Normal : TextInput.Password
                        passwordCharacter: "•"
                        selectByMouse: true
                        leftPadding: 10
                        rightPadding: 10
                        background: Rectangle {
                            radius: 8
                            color: "#0B1120"
                            border.color: geminiApiKeyField.activeFocus ? Theme.accentSapphire : Qt.rgba(1, 1, 1, 0.16)
                            border.width: 1
                        }
                        Component.onCompleted: {
                            if (root.controller && root.controller.geminiApiKey) {
                                text = root.controller.geminiApiKey
                            }
                        }
                        onTextChanged: {
                            if (root.controller && text !== root.controller.geminiApiKey) {
                                root.controller.setGeminiApiKey(text)
                            }
                        }
                    }

                    AppButton {
                        objectName: "btnToggleGeminiKeyVisibility"
                        text: geminiPanel.showApiKey ? "Ẩn" : "Hiện"
                        implicitHeight: 32
                        onClicked: geminiPanel.showApiKey = !geminiPanel.showApiKey
                    }

                    AppButton {
                        objectName: "btnTestGeminiConnection"
                        text: (root.controller && root.controller.isTestingGemini) ? "Đang test..." : "Test kết nối"
                        isPrimary: true
                        implicitHeight: 32
                        enabled: root.controller && !root.controller.isTestingGemini
                        onClicked: {
                            if (root.controller) {
                                root.controller.setGeminiApiKey(geminiApiKeyField.text)
                                root.controller.testGeminiConnection(geminiApiKeyField.text)
                            }
                        }
                    }
                }

                Text {
                    objectName: "geminiConnectionStatus"
                    Layout.fillWidth: true
                    visible: root.controller && root.controller.geminiTestStatus !== ""
                    text: root.controller ? root.controller.geminiTestStatus : ""
                    color: (root.controller && root.controller.isTestingGemini)
                           ? "#38BDF8"
                           : ((root.controller && root.controller.geminiTestOk) ? "#4ADE80" : "#F87171")
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
            }
        }

        // ==========================================
        // MODEL LIST
        // ==========================================
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: modelListView
                anchors.fill: parent
                clip: true
                spacing: Theme.spaceMedium
                topMargin: Theme.spaceMedium
                bottomMargin: Theme.spaceMedium
                leftMargin: Theme.spaceLarge
                rightMargin: Theme.spaceLarge

                model: root.controller ? root.controller.models : []

                delegate: ModelCard {
                    width: modelListView.width - (modelListView.leftMargin + modelListView.rightMargin)
                    controller: root.controller
                    
                    property var itemData: modelListView.model[index]
                    modelData: itemData

                    modelId: itemData ? (itemData.model_id || "") : ""
                    displayName: itemData ? (itemData.display_name || "") : ""
                    sizeText: itemData ? (itemData.size_gb_formatted || itemData.size_formatted || "") : ""
                    description: itemData ? (itemData.description || "") : ""
                    recommendationBadge: itemData ? (itemData.recommendation || itemData.badge || "") : ""
                    recommendationReason: itemData ? (itemData.recommendation_reason || itemData.reason || "") : ""
                    status: itemData ? (itemData.status || "NOT_DOWNLOADED") : "NOT_DOWNLOADED"
                    downloadPercent: itemData ? (itemData.download_percent !== undefined ? itemData.download_percent : (itemData.progress_percent || 0)) : 0
                    downloadSpeed: itemData ? (itemData.download_speed || itemData.speed || "") : ""
                    downloadEta: itemData ? (itemData.download_eta || itemData.eta || "") : ""

                    onDownloadClicked: function(mId) {
                        var id = mId || (itemData ? itemData.model_id : "")
                        if (root.controller) root.controller.startDownload(id)
                    }

                    onCancelClicked: function(mId) {
                        var id = mId || (itemData ? itemData.model_id : "")
                        if (root.controller) root.controller.cancelDownload(id)
                    }

                    onSelectClicked: function(mId) {
                        var id = mId || (itemData ? itemData.model_id : "")
                        if (root.controller) root.controller.selectActiveModel(id)
                    }

                    onDeleteClicked: function(mId) {
                        var id = mId || (itemData ? itemData.model_id : "")
                        if (root.controller) root.controller.deleteModelFile(id)
                    }
                }
            }

            Rectangle {
                anchors.right: parent.right
                anchors.rightMargin: 6
                y: modelListView.visibleArea.yPosition * modelListView.height
                width: 5
                height: Math.max(24, modelListView.visibleArea.heightRatio * modelListView.height)
                radius: 2.5
                color: Qt.rgba(1, 1, 1, 0.25)
                visible: modelListView.contentHeight > modelListView.height
            }

            Text {
                anchors.centerIn: parent
                visible: !root.controller || !root.controller.models || root.controller.models.length === 0
                text: "Không có mô hình nào trong danh mục."
                color: Theme.textMuted
                font.pixelSize: 14
            }
        }
    }
}
