import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

Item {
    id: root
    property string emptyStateMode: "no_selection"
    signal openSrtClicked()
    signal openProjectClicked()

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.85, 520)
        implicitHeight: cardContent.implicitHeight + Theme.spaceLarge * 2
        radius: 18
        color: Theme.glassPodLuminous
        border.color: Theme.glassBorderSpecularUpper
        border.width: 1.5


        ColumnLayout {
            id: cardContent
            anchors.centerIn: parent
            width: parent.width - Theme.spaceLarge * 2
            spacing: Theme.spaceMedium

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "⚡ HƯỚNG DẪN THAO TÁC NHANH"
                color: Theme.accentSapphire
                font.pixelSize: 14
                font.bold: true
                font.letterSpacing: 1.5
            }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "Chọn một câu phụ đề bên trái để bắt đầu dịch"
                color: Theme.textOnLightPodMuted
                font.pixelSize: 13
                font.bold: true
                Layout.bottomMargin: Theme.spaceSmall
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spaceMedium
                columnSpacing: Theme.spaceLarge

                // Phím tắt 1
                RowLayout {
                    spacing: Theme.spaceSmall
                    Rectangle {
                        width: 32; height: 32; radius: 8; color: Theme.glassPodRaised; border.color: Theme.glassBorderSpecularUpper; border.width: 1
                        Text { anchors.centerIn: parent; text: "T"; color: Theme.textOnLightPod; font.bold: true; font.pixelSize: 14 }
                    }
                    Text { text: "Dịch bằng AI"; color: Theme.textOnLightPod; font.pixelSize: 12; font.bold: true }
                }

                // Phím tắt 2
                RowLayout {
                    spacing: Theme.spaceSmall
                    Rectangle {
                        width: 32; height: 32; radius: 8; color: Theme.glassPodRaised; border.color: Theme.glassBorderSpecularUpper; border.width: 1
                        Text { anchors.centerIn: parent; text: "↵"; color: Theme.textOnLightPod; font.bold: true; font.pixelSize: 16 }
                    }
                    Text { text: "Duyệt & Tới câu tiếp"; color: Theme.textOnLightPod; font.pixelSize: 12; font.bold: true }
                }

                // Phím tắt 3
                RowLayout {
                    spacing: Theme.spaceSmall
                    Rectangle {
                        width: 32; height: 32; radius: 8; color: Theme.glassPodRaised; border.color: Theme.glassBorderSpecularUpper; border.width: 1
                        Text { anchors.centerIn: parent; text: "↑↓"; color: Theme.textOnLightPod; font.bold: true; font.pixelSize: 14 }
                    }
                    Text { text: "Điều hướng danh sách câu"; color: Theme.textOnLightPod; font.pixelSize: 12; font.bold: true }
                }

                // Phím tắt 4
                RowLayout {
                    spacing: Theme.spaceSmall
                    Rectangle {
                        width: 32; height: 32; radius: 8; color: Theme.glassPodRaised; border.color: Theme.glassBorderSpecularUpper; border.width: 1
                        Text { anchors.centerIn: parent; text: "S"; color: Theme.textOnLightPod; font.bold: true; font.pixelSize: 14 }
                    }
                    Text { text: "Lưu dự án"; color: Theme.textOnLightPod; font.pixelSize: 12; font.bold: true }
                }
            }
        }
    }
}
