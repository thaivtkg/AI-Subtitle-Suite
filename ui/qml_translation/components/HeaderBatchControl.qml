import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

Item {
    id: root
    objectName: "batchControlBar"

    signal modelManagerClicked()
    property bool showModelManager: false

    property var customModelController: null

    property var controller: typeof batchController !== "undefined" ? batchController : null
    property string sourceLanguage: "English"
    property string targetLanguage: "Vietnamese"
    property string storySummary: ""
    property bool isCompact: false

    property int selectedLimit: 50
    property int currentSubtitleIndex: 0
    property var selectedIndices: []
    readonly property bool hasMultiSelection: root.selectedIndices && root.selectedIndices.length > 1

    readonly property int totalSubtitles: (typeof subtitleModel !== "undefined" && subtitleModel && subtitleModel.progressStats) ? (subtitleModel.progressStats.total || 0) : 0
    readonly property int pendingCount: (typeof subtitleModel !== "undefined" && subtitleModel && subtitleModel.progressStats) ? (subtitleModel.progressStats.pending || 0) : 0
    readonly property var activeModelCtrl: root.customModelController || (typeof modelController !== "undefined" ? modelController : null)
    readonly property bool hasValidModel: activeModelCtrl ? (typeof activeModelCtrl.hasValidModel !== "undefined" ? activeModelCtrl.hasValidModel : true) : true
    readonly property int targetCount: Math.min(root.selectedLimit === 0 ? pendingCount : root.selectedLimit, pendingCount)

    implicitWidth: contentRow.implicitWidth
    implicitHeight: 32

    RowLayout {
        id: contentRow
        anchors.fill: parent
        spacing: Theme.spaceSmall

        Text {
            objectName: "batchStatusText"
            visible: root.controller.state !== "IDLE"
            text: {
                if (root.controller.cancelPending) return "Đang hủy…"
                if (root.controller.state === "PAUSING") return "Đang tạm dừng…"
                if (root.controller.state === "PAUSED") return "Đã tạm dừng"
                if (root.controller.state === "RUNNING") return "Đang dịch lô…"
                if (root.controller.state === "CANCELLED") return "Đã hủy"
                if (root.controller.state === "FAILED") return "Thất bại"
                if (root.controller.state === "COMPLETED") {
                    return root.controller.failedCount > 0 ? "Hoàn tất có lỗi" : "Hoàn tất"
                }
                return ""
            }
            color: root.controller.state === "FAILED" || root.controller.failedCount > 0 ? Theme.danger :
                   root.controller.state === "PAUSED" ? Theme.warning : Theme.textSecondary
            font.pixelSize: 12
            font.bold: true
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            objectName: "batchProgressText"
            visible: root.controller.state !== "IDLE" && root.controller.totalCount > 0
            text: root.controller.totalCount > 0
                  ? root.controller.progressPercent + "% · "
                    + root.controller.completedCount + "/"
                    + root.controller.totalCount
                    + (root.controller.failedCount > 0 ? " · " + root.controller.failedCount + " lỗi" : "")
                  : ""
            color: Theme.textMuted
            font.pixelSize: 12
            Layout.alignment: Qt.AlignVCenter
        }

        RowLayout {
            spacing: 2
            visible: ["IDLE", "COMPLETED", "CANCELLED", "FAILED"].indexOf(root.controller.state) >= 0

            AppButton {
                objectName: "btnBatchStart"
            text: {
                if (root.hasMultiSelection) {
                    return root.isCompact ? ("⚡ Chọn (" + root.selectedIndices.length + ")") : ("⚡ Dịch đã chọn (" + root.selectedIndices.length + " câu)")
                }
                if (root.pendingCount === 0) {
                    return "⚡ Đã hoàn tất dịch"
                }
                if (root.isCompact) {
                    return root.selectedLimit === 0 ? ("⚡ Toàn bộ (" + root.targetCount + ")") : ("⚡ " + root.targetCount + " câu")
                }
                return root.selectedLimit === 0 ? ("⚡ Dịch toàn bộ (" + root.targetCount + " câu)") : ("⚡ Dịch hàng loạt (" + root.targetCount + " câu)")
            }
            tooltip: {
                if (!root.hasMultiSelection && root.pendingCount === 0) {
                    return "Không có câu phụ đề nào cần dịch"
                }
                return root.hasMultiSelection ? "Dịch các câu đã chọn (Ctrl/Shift + Click)" : "Dịch tự động phụ đề theo lô"
            }
            isPrimary: true
            visible: ["IDLE", "COMPLETED", "CANCELLED", "FAILED"].indexOf(root.controller.state) >= 0
            enabled: root.controller.canStart && (root.hasMultiSelection ? root.selectedIndices.length > 0 : root.pendingCount > 0) && root.hasValidModel
            onClicked: {
                if (root.sourceLanguage && root.targetLanguage && root.sourceLanguage.trim().toLowerCase() === root.targetLanguage.trim().toLowerCase()) {
                    if (typeof toast !== "undefined" && toast) {
                        toast.show("CẢNH BÁO", "Ngôn ngữ nguồn và ngôn ngữ đích không được trùng nhau!")
                    }
                    return
                }
                if (!root.hasValidModel) {
                    if (typeof toast !== "undefined" && toast) {
                        toast.show("CẢNH BÁO", "Mô hình AI chưa được tải về máy. Vui lòng chọn hoặc tải mô hình!")
                    }
                    root.modelManagerClicked()
                    return
                }
                if (root.hasMultiSelection) {
                    root.controller.startBatchWithIndices(
                        root.sourceLanguage,
                        root.targetLanguage,
                        root.storySummary,
                        root.selectedIndices
                    )
                } else {
                    root.controller.startBatch(
                        root.sourceLanguage,
                        root.targetLanguage,
                        root.storySummary,
                        root.currentSubtitleIndex >= 0 ? root.currentSubtitleIndex : 0,
                        root.selectedLimit
                    )
                }
            }
        }

        AppButton {
            objectName: "btnBatchPresetMenu"
            text: "▾"
            tooltip: "Chọn số lượng câu dịch mỗi lần"
            isPrimary: true
            Layout.preferredWidth: 26
            visible: ["IDLE", "COMPLETED", "CANCELLED", "FAILED"].indexOf(root.controller.state) >= 0
            enabled: root.controller.canStart && root.pendingCount > 0 && root.hasValidModel
            onClicked: presetMenu.open()

            Menu {
                id: presetMenu
                x: -(width - parent.width)
                y: parent.height + 6
                width: 200
                topPadding: 6
                bottomPadding: 6
                leftPadding: 6
                rightPadding: 6

                background: Rectangle {
                    color: Qt.rgba(0.08, 0.11, 0.17, 0.96)
                    border.color: Theme.glassBorderSpecularUpper
                    border.width: 1.5
                    radius: 14
                }

                MenuItem {
                    id: mItemMulti
                    visible: root.hasMultiSelection
                    height: visible ? 36 : 0
                    implicitHeight: visible ? 36 : 0
                    background: Rectangle {
                        radius: 10
                        color: mItemMulti.hovered ? Qt.rgba(0.0, 0.4, 1.0, 0.08) : Qt.rgba(0.0, 0.4, 1.0, 0.04)
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Text { text: "⚡"; color: Theme.accentSapphire; font.pixelSize: 12 }
                        Text {
                            text: "Các câu đã chọn (" + (root.selectedIndices ? root.selectedIndices.length : 0) + ")"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: true
                            Layout.fillWidth: true
                        }
                    }
                    onTriggered: {
                        root.controller.startBatchWithIndices(
                            root.sourceLanguage,
                            root.targetLanguage,
                            root.storySummary,
                            root.selectedIndices
                        )
                    }
                }

                MenuItem {
                    id: mItem5
                    implicitHeight: 36
                    enabled: root.totalSubtitles >= 5
                    opacity: enabled ? 1.0 : 0.4
                    background: Rectangle {
                        radius: 10
                        color: (!root.hasMultiSelection && root.selectedLimit === 5) ? Qt.rgba(0.0, 0.4, 1.0, 0.10) :
                               mItem5.hovered ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                        border.color: (!root.hasMultiSelection && root.selectedLimit === 5) ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                        border.width: 1
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Text { text: "⚡"; color: Theme.accentSapphire; font.pixelSize: 12 }
                        Text {
                            text: "5 câu (Đoạn ngắn)"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: !root.hasMultiSelection && root.selectedLimit === 5
                            Layout.fillWidth: true
                        }
                        Text {
                            text: "✓"
                            color: Theme.accentSapphire
                            font.pixelSize: 12
                            font.bold: true
                            visible: !root.hasMultiSelection && root.selectedLimit === 5
                        }
                    }
                    onTriggered: root.selectedLimit = 5
                }

                MenuItem {
                    id: mItem10
                    implicitHeight: 36
                    enabled: root.totalSubtitles >= 10
                    opacity: enabled ? 1.0 : 0.4
                    background: Rectangle {
                        radius: 10
                        color: (!root.hasMultiSelection && root.selectedLimit === 10) ? Qt.rgba(0.0, 0.4, 1.0, 0.10) :
                               mItem10.hovered ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                        border.color: (!root.hasMultiSelection && root.selectedLimit === 10) ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                        border.width: 1
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Text { text: "⚡"; color: Theme.accentSapphire; font.pixelSize: 12 }
                        Text {
                            text: "10 câu (Thử AI)"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: !root.hasMultiSelection && root.selectedLimit === 10
                            Layout.fillWidth: true
                        }
                        Text {
                            text: "✓"
                            color: Theme.accentSapphire
                            font.pixelSize: 12
                            font.bold: true
                            visible: !root.hasMultiSelection && root.selectedLimit === 10
                        }
                    }
                    onTriggered: root.selectedLimit = 10
                }

                MenuItem {
                    id: mItem20
                    implicitHeight: 36
                    enabled: root.totalSubtitles >= 20
                    opacity: enabled ? 1.0 : 0.4
                    background: Rectangle {
                        radius: 10
                        color: (!root.hasMultiSelection && root.selectedLimit === 20) ? Qt.rgba(0.0, 0.4, 1.0, 0.10) :
                               mItem20.hovered ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                        border.color: (!root.hasMultiSelection && root.selectedLimit === 20) ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                        border.width: 1
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Text { text: "⚡"; color: Theme.accentSapphire; font.pixelSize: 12 }
                        Text {
                            text: "20 câu (Vừa phải)"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: !root.hasMultiSelection && root.selectedLimit === 20
                            Layout.fillWidth: true
                        }
                        Text {
                            text: "✓"
                            color: Theme.accentSapphire
                            font.pixelSize: 12
                            font.bold: true
                            visible: !root.hasMultiSelection && root.selectedLimit === 20
                        }
                    }
                    onTriggered: root.selectedLimit = 20
                }

                MenuItem {
                    id: mItem50
                    implicitHeight: 36
                    enabled: root.totalSubtitles >= 50
                    opacity: enabled ? 1.0 : 0.4
                    background: Rectangle {
                        radius: 10
                        color: (!root.hasMultiSelection && root.selectedLimit === 50) ? Qt.rgba(0.0, 0.4, 1.0, 0.10) :
                               mItem50.hovered ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                        border.color: (!root.hasMultiSelection && root.selectedLimit === 50) ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                        border.width: 1
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Text { text: "⚡"; color: Theme.accentSapphire; font.pixelSize: 12 }
                        Text {
                            text: "50 câu (Khuyên dùng)"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: !root.hasMultiSelection && root.selectedLimit === 50
                            Layout.fillWidth: true
                        }
                        Text {
                            text: "✓"
                            color: Theme.accentSapphire
                            font.pixelSize: 12
                            font.bold: true
                            visible: !root.hasMultiSelection && root.selectedLimit === 50
                        }
                    }
                    onTriggered: root.selectedLimit = 50
                }

                MenuItem {
                    id: mItem0
                    implicitHeight: 36
                    enabled: root.totalSubtitles > 0
                    opacity: enabled ? 1.0 : 0.4
                    background: Rectangle {
                        radius: 10
                        color: (!root.hasMultiSelection && root.selectedLimit === 0) ? Qt.rgba(0.0, 0.4, 1.0, 0.10) :
                               mItem0.hovered ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                        border.color: (!root.hasMultiSelection && root.selectedLimit === 0) ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                        border.width: 1
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Text { text: "⚡"; color: "#F59E0B"; font.pixelSize: 12 }
                        Text {
                            text: "Toàn bộ tệp"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: !root.hasMultiSelection && root.selectedLimit === 0
                            Layout.fillWidth: true
                        }
                        Text {
                            text: "✓"
                            color: Theme.accentSapphire
                            font.pixelSize: 12
                            font.bold: true
                            visible: !root.hasMultiSelection && root.selectedLimit === 0
                        }
                    }
                    onTriggered: root.selectedLimit = 0
                }
            }
        }
    }

        AppButton {
            objectName: "btnBatchPause"
            text: "Tạm dừng"
            tooltip: "Tạm dừng tiến trình dịch"
            visible: root.controller.state === "RUNNING" && !root.controller.cancelPending
            enabled: root.controller.canPause
            onClicked: root.controller.pauseBatch()
        }

        AppButton {
            objectName: "btnBatchResume"
            text: "Tiếp tục"
            tooltip: "Tiếp tục tiến trình dịch"
            visible: root.controller.state === "PAUSED"
            enabled: root.controller.canResume
            onClicked: root.controller.resumeBatch()
        }

        AppButton {
            objectName: "btnBatchCancel"
            text: root.controller.cancelPending ? "Đang hủy…" : "Hủy"
            tooltip: "Hủy tiến trình dịch"
            visible: root.controller.state === "RUNNING" || root.controller.cancelPending
            enabled: root.controller.canCancel
            onClicked: root.controller.cancelBatch()
        }

        AppButton {
            objectName: "btnBatchRetryFailed"
            text: "Thử lại lỗi"
            tooltip: "Dịch lại các câu bị lỗi"
            visible: root.controller.canRetryFailed
            enabled: root.controller.canRetryFailed
            onClicked: root.controller.retryFailed()
        }

        Item {
            visible: root.showModelManager
            Layout.fillWidth: root.showModelManager
        }

        AppButton {
            id: btnModelManager
            objectName: root.showModelManager ? "btnModelManager" : "btnModelManagerHidden"
            visible: root.showModelManager
            text: {
                var mc = root.customModelController || (typeof modelController !== "undefined" ? modelController : null)
                if (!mc) return "🔮 Mô hình AI ▼"
                var name = mc.activeModelDisplayName || "Mô hình AI"
                var shortName = name.split('/')[0].replace(/\s+(?:Instruct|Distill|Default|IT).*$/i, "").replace(/\s*\(.*\)$/, "").trim()
                return "🔮 " + shortName + " ▼"
            }
            tooltip: "Quản lý & Chọn Mô hình AI GGUF"
            onClicked: root.modelManagerClicked()
        }
    }
}
