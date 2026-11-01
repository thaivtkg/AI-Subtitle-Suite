import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "../theme"

Dialog {
    id: root
    objectName: "hotkeysDialog"

    title: ""
    modal: true
    dim: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    anchors.centerIn: Overlay.overlay

    width: Math.min(560, Overlay.overlay ? Overlay.overlay.width - 32 : 560)
    height: Math.min(560, Overlay.overlay ? Overlay.overlay.height - 32 : 560)
    padding: 0

    Shortcut {
        sequence: "F1"
        enabled: root.visible
        onActivated: root.close()
    }

    background: Rectangle {
        color: "#131824"
        radius: 18
        border.color: Theme.glassBorderSpecularUpper
        border.width: 1.5
    }

    component KeyCap: Rectangle {
        property alias text: keyText.text
        implicitHeight: 22
        implicitWidth: keyText.implicitWidth + 12
        radius: 6
        color: Theme.glassPodRaised
        border.color: Theme.glassBorderSpecularUpper
        border.width: 1

        Text {
            id: keyText
            anchors.centerIn: parent
            font.pixelSize: 11
            font.bold: true
            color: Theme.textPrimary
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
            implicitHeight: 48
            color: "#1C2436"
            radius: 18

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 16
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
                spacing: 8

                Text {
                    text: "⌨"
                    color: Theme.accentCyan
                    font.pixelSize: 16
                }

                Text {
                    text: "BẢNG TRA CỨU PHÍM TẮT NHANH (PRO CAT HOTKEYS)"
                    color: Theme.textPrimary
                    font.pixelSize: 13
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
        // CONTENT FLICKABLE (NO WINDOWS SCROLLBAR)
        // ==========================================
        Flickable {
            id: cheatsheetScroll
            objectName: "cheatsheetScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            property real topPadding: 16
            property real bottomPadding: 20
            property real leftPadding: 20
            property real rightPadding: 20
            contentWidth: width
            contentHeight: cheatsheetColumn.implicitHeight + topPadding + bottomPadding
            boundsBehavior: Flickable.StopAtBounds

            ColumnLayout {
                id: cheatsheetColumn
                x: cheatsheetScroll.leftPadding
                y: cheatsheetScroll.topPadding
                width: cheatsheetScroll.width - cheatsheetScroll.leftPadding - cheatsheetScroll.rightPadding
                spacing: 11

                // --- GROUP 1: BIÊN DỊCH & DUYỆT BÀI ---
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Text {
                        text: "✦ BIÊN DỊCH & DUYỆT BÀI (PRO KEY-FLOW)"
                        color: Theme.accentSapphire
                        font.pixelSize: 11
                        font.bold: true
                        font.letterSpacing: 0.5
                    }

                    // Row: Ctrl + Enter
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "Enter" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Duyệt câu hiện tại & Nhảy câu kế tiếp"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: true
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + Shift + Enter
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "Shift" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "Enter" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Kích hoạt dịch AI (Pro Flow)"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: true
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + T
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "T" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Kích hoạt dịch AI (Kinh điển)"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + G
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "G" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Ghim nhanh từ bôi đen vào Glossary"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }
                }

                // Divider
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Qt.rgba(1, 1, 1, 0.08)
                }

                // --- GROUP 2: ĐIỀU HƯỚNG & CÔNG CỤ ---
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: "✦ ĐIỀU HƯỚNG & CÔNG CỤ (NAVIGATION & TOOLS)"
                        color: Theme.accentSapphire
                        font.pixelSize: 11
                        font.bold: true
                        font.letterSpacing: 0.5
                    }

                    // Row: Alt + Up / Alt + Down
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Alt" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "▲ / ▼" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Di chuyển lên / xuống giữa các câu"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + H
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "H" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Bật / Tắt thanh Tìm kiếm & Thay thế"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }
                }

                // Divider
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Qt.rgba(1, 1, 1, 0.08)
                }

                // --- GROUP 3: QUẢN LÝ TỆP & DỰ ÁN ---
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: "✦ QUẢN LÝ TỆP & DỰ ÁN (FILE & PROJECT)"
                        color: Theme.accentSapphire
                        font.pixelSize: 11
                        font.bold: true
                        font.letterSpacing: 0.5
                    }

                    // Row: Ctrl + O
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "O" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Mở file phụ đề SRT gốc"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + Shift + O
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "Shift" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "O" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Mở file dự án .aisrt"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + S
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "S" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Lưu dự án / Đồng bộ trực tiếp về Studio"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + Shift + S
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "Shift" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "S" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Xuất file phụ đề SRT"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }

                    // Row: Ctrl + W
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "Ctrl" }
                            Text { text: "+"; color: Theme.textSecondary; font.bold: true; font.pixelSize: 11 }
                            KeyCap { text: "W" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Đóng dự án hiện tại"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                    }

                    // Row: F1
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        RowLayout {
                            implicitWidth: 175
                            spacing: 4
                            KeyCap { text: "F1" }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            text: "Bật / Đóng bảng phím tắt này"
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: true
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }
}
