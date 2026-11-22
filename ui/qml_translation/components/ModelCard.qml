import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

Rectangle {
    id: root

    property var modelData: null
    property var controller: null

    // Thuộc tính tường minh hỗ trợ cả binding trực tiếp hoặc fallback từ modelData
    property string modelId: modelData ? (modelData.model_id || "") : ""
    property string displayName: modelData ? (modelData.display_name || "") : ""
    property string sizeText: modelData ? (modelData.size_gb_formatted || modelData.size_formatted || "") : ""
    property string description: modelData ? (modelData.description || "") : ""
    property string recommendationBadge: modelData ? (modelData.recommendation || modelData.badge || "") : ""
    property string recommendationReason: modelData ? (modelData.recommendation_reason || modelData.reason || "") : ""
    property string status: modelData ? (modelData.status || "") : "NOT_DOWNLOADED"
    property bool isCloud: modelData && modelData.is_cloud ? true : false
    property int downloadPercent: modelData ? (modelData.download_percent !== undefined ? modelData.download_percent : (modelData.progress_percent || 0)) : 0
    property string downloadSpeed: modelData ? (modelData.download_speed || modelData.speed || "") : ""
    property string downloadEta: modelData ? (modelData.download_eta || modelData.eta || "") : ""

    readonly property bool isDownloaded: status === "DOWNLOADED" || status === "ACTIVE" || (modelData && modelData.is_downloaded)
    readonly property bool isDownloading: status === "DOWNLOADING" || (modelData && modelData.is_downloading)
    readonly property bool isActive: status === "ACTIVE" || (modelData && modelData.is_active)
    readonly property bool canDownload: !isCloud && (status === "NOT_DOWNLOADED" || (!isDownloaded && !isDownloading)) && (modelData ? modelData.can_download : true)
    readonly property bool canSelect: isDownloaded && !isActive && (modelData ? modelData.can_select : true)
    readonly property bool canDelete: !isCloud && isDownloaded && !isActive && (modelData ? modelData.can_delete : true)

    signal downloadClicked(string modelId)
    signal cancelClicked(string modelId)
    signal useClicked(string modelId)
    signal selectClicked(string modelId)
    signal deleteClicked(string modelId)

    // Lắng nghe trực tiếp tiến trình tải mà không làm giật/reset danh sách
    Connections {
        target: root.controller
        function onDownloadProgress(mId, percent, speed, eta) {
            if (mId === root.modelId) {
                root.downloadPercent = percent
                root.downloadSpeed = speed
                root.downloadEta = eta
            }
        }
    }

    implicitHeight: mainLayout.implicitHeight + Theme.spaceLarge
    color: root.isActive ? Qt.rgba(0.0, 0.40, 1.0, 0.18) : Theme.glassPodLuminous
    radius: 16
    border.color: root.isActive ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
    border.width: root.isActive ? 2 : 1.5

    ColumnLayout {
        id: mainLayout
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        // Hàng 1: Tiêu đề, Badge khuyên dùng, Kích thước file
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceSmall

            Text {
                text: root.displayName
                color: Theme.textPrimary
                font.pixelSize: 15
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            // Recommendation Badge
            Rectangle {
                id: badgeRect
                implicitWidth: badgeText.implicitWidth + 16
                implicitHeight: 22
                radius: 11
                visible: root.recommendationBadge !== ""
                color: {
                    if (root.recommendationBadge === "RECOMMENDED") return Qt.rgba(0.06, 0.72, 0.50, 0.15)
                    if (root.recommendationBadge === "COMPATIBLE") return Qt.rgba(0.0, 0.4, 1.0, 0.12)
                    return Qt.rgba(0.96, 0.62, 0.04, 0.15)
                }
                border.color: {
                    if (root.recommendationBadge === "RECOMMENDED") return "#10B981"
                    if (root.recommendationBadge === "COMPATIBLE") return Theme.accentSapphire
                    return "#F59E0B"
                }
                border.width: 1

                Text {
                    id: badgeText
                    anchors.centerIn: parent
                    text: {
                        if (root.recommendationBadge === "RECOMMENDED") return "Khuyên dùng"
                        if (root.recommendationBadge === "COMPATIBLE") return "Tương thích"
                        return "Chưa tối ưu"
                    }
                    color: {
                        if (root.recommendationBadge === "RECOMMENDED") return "#34D399"
                        if (root.recommendationBadge === "COMPATIBLE") return Theme.accentSapphire
                        return "#FBBF24"
                    }
                    font.pixelSize: 11
                    font.bold: true
                }

                ToolTip.visible: badgeMouse.containsMouse
                ToolTip.text: root.recommendationReason
                MouseArea {
                    id: badgeMouse
                    anchors.fill: parent
                    hoverEnabled: true
                }
            }

            // Kích thước dung lượng
            Text {
                text: root.sizeText
                color: Theme.textSecondary
                font.pixelSize: 13
                font.bold: true
                font.family: "JetBrains Mono, Consolas, monospace"
                font.features: { "tnum": 1 }
            }
        }

        // Hàng 2: Mô tả chi tiết
        Text {
            Layout.fillWidth: true
            text: root.description
            color: Theme.textSecondary
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            lineHeight: 1.2
        }

        // Hàng 3: Tiến trình tải nếu đang downloading
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.isDownloading
            spacing: Theme.spaceXs

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "Đang tải: " + root.downloadPercent + "%"
                    color: Theme.accentCyan
                    font.pixelSize: 12
                    font.bold: true
                    font.family: "JetBrains Mono, Consolas, monospace"
                    font.features: { "tnum": 1 }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: root.downloadSpeed + (root.downloadEta !== "" ? (" · ETA: " + root.downloadEta) : "")
                    color: Theme.textMuted
                    font.pixelSize: 12
                    font.family: "JetBrains Mono, Consolas, monospace"
                    font.features: { "tnum": 1 }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 6
                color: Qt.rgba(0.0, 0.4, 1.0, 0.12)
                radius: 3
                clip: true

                Rectangle {
                    width: Math.max(0, Math.min(parent.width, parent.width * (root.downloadPercent / 100.0)))
                    height: parent.height
                    color: Theme.accentCyan
                    radius: 3
                }
            }
        }

        // Hàng 4: Trạng thái và Nút bấm thao tác
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.spaceXs
            spacing: Theme.spaceSmall

            // Tag trạng thái: Active, Downloaded hoặc cần API Key
            Rectangle {
                implicitWidth: statusLabel.implicitWidth + 16
                implicitHeight: 24
                radius: 8
                visible: (root.isActive || root.isDownloaded || root.isCloud) && !root.isDownloading
                color: root.isActive ? Qt.rgba(0.0, 0.4, 1.0, 0.12) : (root.isDownloaded ? Qt.rgba(0.06, 0.72, 0.50, 0.12) : Qt.rgba(0.96, 0.62, 0.04, 0.15))
                border.color: root.isActive ? Theme.accentSapphire : (root.isDownloaded ? "#10B981" : "#F59E0B")
                border.width: 1

                Text {
                    id: statusLabel
                    anchors.centerIn: parent
                    text: root.isActive ? "Đang sử dụng" : (root.isCloud ? (root.isDownloaded ? "Sẵn sàng (Cloud)" : "Cần API Key") : "Đã tải về")
                    color: root.isActive ? Theme.accentSapphire : (root.isDownloaded ? "#34D399" : "#FBBF24")
                    font.pixelSize: 11
                    font.bold: true
                }
            }

            Item { Layout.fillWidth: true }

            // Nút: Tải về (Đồng bộ 100% màu xanh Sapphire nổi bật)
            AppButton {
                text: "Tải model"
                isPrimary: true
                visible: root.canDownload
                onClicked: root.downloadClicked(root.modelId)
            }

            // Nút: Hủy tải
            AppButton {
                text: "Hủy tải"
                visible: root.isDownloading
                onClicked: root.cancelClicked(root.modelId)
            }

            // Nút: Chọn sử dụng
            AppButton {
                text: "Sử dụng"
                isPrimary: true
                visible: root.canSelect
                onClicked: {
                    root.useClicked(root.modelId)
                    root.selectClicked(root.modelId)
                }
            }

            // Nút: Xóa file
            AppButton {
                text: "Xóa"
                visible: root.canDelete
                onClicked: root.deleteClicked(root.modelId)
            }
        }
    }
}
