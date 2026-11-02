import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../theme"

ToolBar {
    id: root
    property string projectName: "Untitled"
    property bool isSaved: true
    property bool hasProject: false
    property bool hasProjectData: false
    property bool projectMutationLocked: false
    property string sourceLanguage: "English"
    property string targetLanguage: "Vietnamese"
    property string storySummary: ""
    property int currentSubtitleIndex: 0
    property var selectedIndices: []
    readonly property bool isCompact: width < 1320
    readonly property bool isMinimum: width < 1100

    function getLangCode(lang) {
        if (!lang) return ""
        var l = lang.toLowerCase()
        if (l.indexOf("eng") !== -1 || l.indexOf("anh") !== -1) return "EN"
        if (l.indexOf("viet") !== -1) return "VI"
        if (l.indexOf("japan") !== -1 || l.indexOf("nhật") !== -1) return "JA"
        if (l.indexOf("korea") !== -1 || l.indexOf("hàn") !== -1) return "KO"
        if (l.indexOf("chin") !== -1 || l.indexOf("trung") !== -1) return "ZH"
        if (l.indexOf("french") !== -1 || l.indexOf("pháp") !== -1) return "FR"
        if (l.indexOf("german") !== -1 || l.indexOf("đức") !== -1) return "DE"
        if (l.indexOf("span") !== -1 || l.indexOf("tây") !== -1) return "ES"
        if (l.indexOf("russ") !== -1 || l.indexOf("nga") !== -1) return "RU"
        return lang.substring(0, 2).toUpperCase()
    }

    signal openSrtClicked()
    signal openProjectClicked()
    signal saveClicked()
    signal exportClicked()
    signal modelManagerClicked()
    signal archetypeClicked()
    signal closeProjectClicked()
    signal syncStudioClicked()
    signal appendBatchClicked()
    signal hotkeysClicked()

    property bool isBatchMode: false
    property string batchLabel: ""
    property string originalSourcePath: ""

    implicitHeight: 48
    padding: 0

    background: Rectangle {
        color: "transparent"
    }

    contentItem: Item {
        // SEAMLESS LIQUID GLASS HEADER BAR
        Rectangle {
            id: headerCapsule
            anchors.fill: parent
            radius: 0
            color: Qt.rgba(1.0, 1.0, 1.0, 0.18)
            border.color: "transparent"
            clip: true

            // Bottom 1px glass divider line
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: Theme.glassBorderSubtle
                antialiasing: false
            }

            MouseArea {
                anchors.fill: parent
                z: -1
                acceptedButtons: Qt.LeftButton
                onPressed: Window.window.startSystemMove()
                onDoubleClicked: {
                    if (Window.window.visibility === Window.Maximized) Window.window.showNormal()
                    else Window.window.showMaximized()
                }
            }

            // CỤM TRÁI: LOGO STUDIO + TÊN DỰ ÁN
            RowLayout {
                id: leftBrandingRow
                objectName: "leftBrandingRow"
                anchors.left: parent.left
                anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.spaceSmall

                Text {
                    text: root.isCompact ? "◈ Suite" : "◈ AI Subtitle Suite"
                    color: Theme.textPrimaryGlass
                    font.pixelSize: 13
                    font.bold: true
                }

                Rectangle {
                    visible: !root.hasProject
                    implicitWidth: verText.implicitWidth + 12
                    implicitHeight: 18
                    radius: 9
                    color: Qt.rgba(1, 1, 1, 0.22)
                    border.color: Theme.glassBorderSpecularUpper
                    border.width: 1
                    Layout.alignment: Qt.AlignVCenter
                    Text {
                        id: verText
                        anchors.centerIn: parent
                        text: "v1.2 Liquid Glass"
                        color: Theme.textPrimaryGlass
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                Rectangle {
                    visible: root.hasProject && root.projectName !== "Workspace" && root.projectName !== "Untitled"
                    implicitWidth: 1
                    implicitHeight: 14
                    color: Theme.glassBorderSubtle
                    Layout.leftMargin: Theme.spaceXs
                    Layout.rightMargin: Theme.spaceXs
                }

                Text {
                    visible: root.hasProject && root.projectName !== "Workspace" && root.projectName !== "Untitled"
                    text: root.projectName
                    color: Theme.textPrimaryGlass
                    font.pixelSize: 13
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.maximumWidth: root.isCompact ? 100 : 180
                }

                Rectangle {
                    visible: root.hasProject
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: root.hasProject ? implicitWidth : 0
                    implicitWidth: statusText.implicitWidth + (root.isCompact ? Theme.spaceSmall : Theme.spaceMedium)
                    implicitHeight: 20
                    radius: 10
                    color: root.isSaved ? Theme.badgeEmeraldBg : Theme.badgeAmberBg
                    border.color: root.isSaved ? Theme.badgeEmeraldText : Theme.badgeAmberText
                    border.width: 1

                    Text {
                        id: statusText
                        anchors.centerIn: parent
                        text: root.isSaved ? (root.isCompact ? "✓" : "✓ Đã lưu") : (root.isCompact ? "●" : "● Chưa lưu")
                        color: root.isSaved ? Theme.badgeEmeraldText : Theme.badgeAmberText
                        font.pixelSize: 10
                        font.bold: true
                    }

                    ToolTip.visible: chipMouse.containsMouse
                    ToolTip.text: root.isSaved ? "Dự án đã được lưu" : "Có thay đổi chưa lưu"
                    MouseArea {
                        id: chipMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }
                }

                Rectangle {
                    id: batchCapsule
                    objectName: "batchCapsule"
                    visible: root.hasProject && root.isBatchMode && root.batchLabel !== ""
                    implicitWidth: batchText.implicitWidth + 16
                    implicitHeight: 20
                    radius: 10
                    color: Qt.rgba(0.0, 0.45, 1.0, 0.15)
                    border.color: Theme.accentSapphire
                    border.width: 1
                    Layout.alignment: Qt.AlignVCenter

                    Text {
                        id: batchText
                        anchors.centerIn: parent
                        text: "🌐 " + root.batchLabel
                        color: Theme.accentSapphire
                        font.pixelSize: 10
                        font.bold: true
                    }

                    ToolTip.visible: batchMouse.containsMouse
                    ToolTip.text: "Đợt dịch từ ai-subtitle-studio: " + root.batchLabel + "\nNguồn: " + root.originalSourcePath
                    MouseArea {
                        id: batchMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }
                }
            }

            // CỤM NÚT ĐIỀU KHIỂN CỬA SỔ WINDOWS 11 (ANCHORED TOP-RIGHT)
            RowLayout {
                id: windowControlsRow
                objectName: "windowControlsRow"
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                z: 5

                Button {
                    id: btnHotkeys
                    objectName: "btnHotkeys"
                    implicitWidth: 32
                    implicitHeight: 28
                    padding: 0
                    ToolTip.visible: hovered
                    ToolTip.text: "Bảng phím tắt — F1"
                    contentItem: Text {
                        text: "⌨"
                        color: Theme.textPrimaryGlass
                        font.pixelSize: 13
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: 8
                        color: btnHotkeys.pressed ? Qt.rgba(1, 1, 1, 0.25) : (btnHotkeys.hovered ? Qt.rgba(1, 1, 1, 0.15) : "transparent")
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    onClicked: root.hotkeysClicked()
                }

                Button {
                    id: btnMinimize
                    objectName: "btnMinimize"
                    implicitWidth: 36
                    implicitHeight: 28
                    padding: 0
                    ToolTip.visible: hovered
                    ToolTip.text: "Thu nhỏ"
                    contentItem: Text {
                        text: "—"
                        color: Theme.textPrimaryGlass
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: 8
                        color: btnMinimize.pressed ? Qt.rgba(1, 1, 1, 0.25) : (btnMinimize.hovered ? Qt.rgba(1, 1, 1, 0.15) : "transparent")
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    onClicked: Window.window.showMinimized()
                }

                Button {
                    id: btnMaximize
                    objectName: "btnMaximize"
                    implicitWidth: 36
                    implicitHeight: 28
                    padding: 0
                    ToolTip.visible: hovered
                    ToolTip.text: Window.window.visibility === Window.Maximized ? "Khôi phục" : "Phóng to"
                    contentItem: Text {
                        text: Window.window.visibility === Window.Maximized ? "🗗" : "🗖"
                        color: Theme.textPrimaryGlass
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: 8
                        color: btnMaximize.pressed ? Qt.rgba(1, 1, 1, 0.25) : (btnMaximize.hovered ? Qt.rgba(1, 1, 1, 0.15) : "transparent")
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    onClicked: {
                        if (Window.window.visibility === Window.Maximized) Window.window.showNormal()
                        else Window.window.showMaximized()
                    }
                }

                Button {
                    id: btnClose
                    objectName: "btnClose"
                    implicitWidth: 36
                    implicitHeight: 28
                    padding: 0
                    ToolTip.visible: hovered
                    ToolTip.text: "Đóng"
                    contentItem: Text {
                        text: "✕"
                        color: btnClose.hovered ? "#FFFFFF" : Theme.textPrimaryGlass
                        font.pixelSize: 12
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: 8
                        color: btnClose.pressed ? "#C42B1C" : (btnClose.hovered ? "#E81123" : "transparent")
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    onClicked: Window.window.close()
                }
            }

            // CỤM PHẢI: CÁC THAO TÁC CHÍNH (DẠNG VIÊN THUỐC ĐẶT CẠNH WINDOW CONTROLS)
            RowLayout {
                id: rightActionsRow
                objectName: "rightActionsRow"
                anchors.right: windowControlsRow.left
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: root.isCompact ? Theme.spaceXs : Theme.spaceSmall
                z: 10
                // ẨN TOÀN BỘ KHI Ở MÀN HÌNH KHỞI ĐỘNG
                visible: root.hasProject

                // Ẩn Mở SRT và Đóng khỏi thanh Header để chống chật chội
                AppButton {
                    objectName: "btnOpenSrt"
                    visible: false
                    text: root.isCompact ? "SRT" : "📁 Mở SRT"
                    tooltip: "Mở hoặc đổi file SRT khác — Ctrl + O"
                    enabled: !root.projectMutationLocked
                    onClicked: root.openSrtClicked()
                }
                AppButton {
                    id: btnCloseProject
                    objectName: "btnCloseProject"
                    visible: false
                    text: root.isCompact ? "⌂" : "⌂ Đóng & Khởi động"
                    tooltip: "Đóng file phụ đề hiện tại và quay về màn hình khởi động — Ctrl + W"
                    isPrimary: false
                    isDarkGlass: true
                    enabled: !root.projectMutationLocked
                    onClicked: root.closeProjectClicked()
                }
                AppButton {
                    objectName: "btnOpenProject"
                    visible: false
                    text: root.isCompact ? "Dự án" : "Mở dự án"
                    tooltip: "Mở file dự án — Ctrl + Shift + O"
                    enabled: !root.projectMutationLocked
                    onClicked: root.openProjectClicked()
                }

                // CHỈ HIỂN THỊ 2 NÚT THỰC THI CHÍNH KHI ĐANG DỊCH
                HeaderBatchControl {
                    id: headerBatch
                    visible: true
                    sourceLanguage: root.sourceLanguage
                    targetLanguage: root.targetLanguage
                    storySummary: root.storySummary
                    isCompact: root.isCompact
                    currentSubtitleIndex: root.currentSubtitleIndex
                    selectedIndices: root.selectedIndices
                    onModelManagerClicked: root.modelManagerClicked()
                }

                AppButton {
                    objectName: "btnSave"
                    visible: false
                    text: "💾 Lưu"
                    tooltip: "Lưu dự án — Ctrl + S"
                    enabled: root.hasProject && !root.isSaved
                    onClicked: root.saveClicked()
                }
                AppButton {
                    id: btnSyncStudio
                    objectName: "btnSyncStudio"
                    visible: root.hasProject && root.hasProjectData && root.isBatchMode
                    text: "⟳ Studio"
                    tooltip: "Ghi đè trực tiếp về Studio: " + root.originalSourcePath + " — Ctrl + S"
                    isPrimary: true
                    enabled: !root.projectMutationLocked
                    onClicked: root.syncStudioClicked()
                }

                AppButton {
                    id: btnAppendBatch
                    objectName: "btnAppendBatch"
                    visible: root.hasProject && root.hasProjectData && root.isBatchMode
                    text: "+ Đợt mới"
                    tooltip: "Nối file đợt tiếp theo từ Studio (kế thừa toàn bộ TM & Glossary)"
                    isDarkGlass: true
                    enabled: !root.projectMutationLocked
                    onClicked: root.appendBatchClicked()
                }

                AppButton {
                    objectName: "btnExport"
                    visible: true
                    text: (root.isCompact || root.isBatchMode) ? "💾 Xuất" : "💾 Xuất SRT"
                    tooltip: root.isBatchMode && root.originalSourcePath !== ""
                             ? ("Xuất file phụ đề SRT (Lưu trực tiếp vào: " + root.originalSourcePath + ") — Ctrl + Shift + S")
                             : "Xuất file phụ đề SRT — Ctrl + Shift + S"
                    isPrimary: false
                    isDarkGlass: true
                    enabled: root.hasProject && root.hasProjectData
                    onClicked: root.exportClicked()
                }
            }

            // CỤM GIỮA: REFRACIVE LANGUAGE CAPSULE + AI MODEL MANAGER
            Item {
                id: centerCluster
                anchors.left: leftBrandingRow.right
                anchors.leftMargin: 8
                anchors.right: rightActionsRow.left
                anchors.rightMargin: 8
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                clip: true

                RowLayout {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 6

                    Rectangle {
                        id: langCapsule
                        objectName: "langCapsule"
                        visible: root.hasProject && centerCluster.width >= 70
                        implicitHeight: 26
                        implicitWidth: langContent.implicitWidth + 16
                        radius: 13
                        color: Qt.rgba(1, 1, 1, 0.45)
                        border.color: Theme.glassBorderSpecularUpper
                        border.width: 1

                        RowLayout {
                            id: langContent
                            anchors.centerIn: parent
                            spacing: 4
                            Text {
                                text: root.getLangCode(root.sourceLanguage)
                                font.pixelSize: 11
                                font.bold: true
                                color: Theme.textOnLightPod
                            }
                            Text {
                                text: "➔"
                                font.pixelSize: 11
                                font.bold: true
                                color: Theme.accentSapphire
                            }
                            Text {
                                text: root.getLangCode(root.targetLanguage)
                                font.pixelSize: 11
                                font.bold: true
                                color: Theme.accentSapphire
                            }
                        }

                        ToolTip.visible: langMouse.containsMouse
                        ToolTip.text: "Cặp ngôn ngữ dịch: " + root.sourceLanguage + " ➔ " + root.targetLanguage
                        MouseArea {
                            id: langMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                        }
                    }

                    

                    AppButton {
                        id: btnModelManager
                        objectName: "btnModelManager"
                        visible: centerCluster.width >= 140
                        Layout.maximumWidth: 175
                        text: {
                            if (typeof modelController === "undefined") return "🔮 Qwen 2.5 3B ▼"
                            var name = modelController.activeModelDisplayName || "Mô hình AI"
                            var shortName = name.split('/')[0].replace(/\s+(?:Instruct|Distill|Default|IT).*$/i, "").replace(/\s*\(.*\)$/, "").trim()
                            if (centerCluster.width < 280) {
                                if (shortName.length > 10) shortName = shortName.substring(0, 10) + "…"
                            } else {
                                if (shortName.length > 14) shortName = shortName.substring(0, 14) + "…"
                            }
                            return "🔮 " + shortName + " ▼"
                        }
                        tooltip: typeof modelController !== "undefined"
                                 ? ("Mô hình đang dùng: " + modelController.activeModelDisplayName + " — Click để thay đổi")
                                 : "Quản lý & Chọn Mô hình AI — Click để thay đổi"
                        onClicked: root.modelManagerClicked()
                    }
                }
            }
        }
    }
}
