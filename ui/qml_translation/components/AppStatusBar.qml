import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

Item {
    id: root
    implicitHeight: 32

    property int acceptedCount: 0
    property int totalCount: 0
    property string engineStatus: "Not loaded"
    property real vramUsed: -1.0
    property real vramTotal: -1.0
    property string gpuName: ""
    property string backendStatus: ""
    readonly property bool compactMode: width < 1150

    property real progressRatio: totalCount > 0 ? acceptedCount / totalCount : 0
    property int progressPercent: Math.round(progressRatio * 100)

    // Seamless Bottom Bar
    Rectangle {
        id: capsuleBar
        anchors.fill: parent
        radius: 0
        color: Theme.glassIslandSurface
        border.color: "transparent"

        // Top 1px glass divider line
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 1
            color: Theme.glassBorderSubtle
            antialiasing: false
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 12

            // LEFT SIDE: Status & GPU / Progress
            RowLayout {
                spacing: 8

                // Engine / Readiness Indicator
                RowLayout {
                    spacing: 6
                    Rectangle {
                        width: 8; height: 8; radius: 4
                        color: "#22C55E" // Neon emerald
                    }

                    Text {
                        objectName: "engineStatusText"
                        id: engineText
                        text: root.engineStatus === "Ready" || root.engineStatus === "Not loaded" ? "• Sẵn sàng" : ("• " + root.engineStatus)
                        color: "#22C55E"
                        font.pixelSize: 11
                        font.bold: true
                    }

                    Text {
                        text: "|"
                        color: Qt.rgba(1, 1, 1, 0.4)
                        font.pixelSize: 11
                    }

                    Text {
                        text: {
                            if (root.gpuName !== "" && root.gpuName !== "Unknown") {
                                var shortGpu = root.gpuName.replace("NVIDIA GeForce ", "").replace("AMD Radeon ", "")
                                return "GPU: " + shortGpu + (root.backendStatus !== "" ? (" (" + root.backendStatus + ")") : "")
                            }
                            return root.backendStatus !== "" ? ("Bộ tăng tốc: " + root.backendStatus) : "GPU: Tự động phát hiện"
                        }
                        color: Qt.rgba(1, 1, 1, 0.85)
                        font.pixelSize: 11
                        font.bold: true
                    }
                }

                Text {
                    visible: root.totalCount > 0
                    text: "|"
                    color: Qt.rgba(1, 1, 1, 0.4)
                    font.pixelSize: 11
                }

                // Progress Info if project active
                Text {
                    objectName: "statusProgressText"
                    id: progressText
                    visible: true
                    text: root.totalCount > 0 
                          ? ("✓ " + root.acceptedCount + " / " + root.totalCount + " Đã duyệt (" + root.progressPercent + "%)")
                          : "Chưa mở dự án"
                    color: Qt.rgba(1, 1, 1, 0.85)
                    font.pixelSize: 11
                    font.bold: true
                }

                // Optical Multi-Segment Progress Bar (Feature 5)
                RowLayout {
                    visible: root.totalCount > 0
                    spacing: 8

                    property var stats: (typeof subtitleModel !== "undefined" && subtitleModel) ? subtitleModel.progressStats : null
                    property int totalLines: stats && stats.total ? stats.total : root.totalCount
                    property int acceptedLines: stats && stats.accepted ? stats.accepted : root.acceptedCount
                    property int translatedLines: stats && stats.translated ? stats.translated : 0
                    property int pendingLines: stats && stats.pending ? stats.pending : (totalLines - acceptedLines - translatedLines)
                    property int qaIssuesCount: stats && (stats.error || stats.qa_issues) ? (stats.error + stats.qa_issues) : 0

                    // 4-Color Segmented Capsule
                    Rectangle {
                        implicitWidth: 140
                        implicitHeight: 8
                        radius: 4
                        color: Qt.rgba(1, 1, 1, 0.15)
                        clip: true

                        Row {
                            anchors.fill: parent
                            spacing: 0

                            // Green: Accepted
                            Rectangle {
                                height: parent.height
                                width: parent.parent.totalLines > 0 ? (parent.parent.acceptedLines / parent.parent.totalLines * parent.width) : 0
                                color: "#10B981"
                            }
                            // Blue: Translated/Edited
                            Rectangle {
                                height: parent.height
                                width: parent.parent.totalLines > 0 ? (parent.parent.translatedLines / parent.parent.totalLines * parent.width) : 0
                                color: "#3B82F6"
                            }
                            // Amber: Pending
                            Rectangle {
                                height: parent.height
                                width: parent.parent.totalLines > 0 ? (parent.parent.pendingLines / parent.parent.totalLines * parent.width) : 0
                                color: "#F59E0B"
                            }
                            // Ruby / Red: QA Issues
                            Rectangle {
                                height: parent.height
                                width: parent.parent.totalLines > 0 ? (parent.parent.qaIssuesCount / parent.parent.totalLines * parent.width) : 0
                                color: "#EF4444"
                            }
                        }
                    }

                    // 1-Click QA Filter Pill
                    Rectangle {
                        id: qaFilterPill
                        objectName: "qaFilterPill"
                        visible: parent.qaIssuesCount > 0
                        implicitWidth: qaFilterText.implicitWidth + 14
                        implicitHeight: 20
                        radius: 10
                        property bool isActive: typeof filteredSubtitleModel !== "undefined" && filteredSubtitleModel && filteredSubtitleModel.qaOnly
                        color: isActive ? "#EF4444" : Qt.rgba(0.94, 0.27, 0.27, 0.20)
                        border.color: "#EF4444"
                        border.width: 1

                        Text {
                            id: qaFilterText
                            anchors.centerIn: parent
                            text: qaFilterPill.isActive ? ("✓ Đang lọc " + parent.parent.qaIssuesCount + " lỗi QA") : ("🛑 " + parent.parent.qaIssuesCount + " lỗi QA")
                            color: qaFilterPill.isActive ? "#FFFFFF" : "#FCA5A5"
                            font.pixelSize: 10
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (typeof filteredSubtitleModel !== "undefined" && filteredSubtitleModel) {
                                    filteredSubtitleModel.setQaOnlyFilter(!filteredSubtitleModel.qaOnly)
                                }
                            }
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // RIGHT SIDE: VRAM & FPS
            RowLayout {
                spacing: 12

                FrameAnimation {
                    id: frameAnim
                    running: true
                }

                Timer {
                    id: fpsSampler
                    interval: 500
                    running: true
                    repeat: true
                    onTriggered: {
                        if (frameAnim.smoothFrameTime > 0) {
                            var liveFps = 1.0 / frameAnim.smoothFrameTime
                            fpsText.text = "FPS: " + liveFps.toFixed(1)
                        }
                    }
                }

                Text {
                    objectName: "vramStatusText"
                    id: vramText
                    text: (root.vramTotal > 0 && root.vramUsed >= 0)
                          ? ("Bộ nhớ VRAM: " + root.vramUsed.toFixed(1) + " / " + root.vramTotal.toFixed(1) + " GB")
                          : (root.vramTotal > 0
                             ? ("Bộ nhớ VRAM: " + root.vramTotal.toFixed(1) + " GB")
                             : "Bộ nhớ: RAM hệ thống")
                    color: Qt.rgba(1, 1, 1, 0.85)
                    font.pixelSize: 11
                    font.bold: true
                }

                Text {
                    id: fpsText
                    text: "FPS: 60.0"
                    color: Qt.rgba(1, 1, 1, 0.85)
                    font.pixelSize: 11
                    font.bold: true
                }
            }
        }
    }
}
