import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import QtQuick.Effects
import "../theme"

Item {
    id: workspace
    
    property bool hasSelection: typeof subtitleModel !== "undefined" && subtitleModel !== null && subtitleModel.rowCount() > 0 && typeof translationController !== "undefined" && translationController.currentOriginal !== ""
    property bool executionLocked: typeof batchController !== "undefined" && batchController.state !== "IDLE" && batchController.state !== "PAUSED" && batchController.state !== "COMPLETED"
    property int totalCount: 0
    property bool compactActions: width < 600
    property string altTranslation: ""
    property string altStyleMode: "CREATIVE"
    property bool altLoading: false
    
    signal translateRequested(string sourceLang)
    signal acceptRequested(string text)
    signal openSrtRequested()
    signal openProjectRequested()
    signal addGlossaryRequested(string sourceText, string targetText)
    signal hotkeysRequested()
    signal cancelRequested()
    
    onCancelRequested: {
        if (typeof translationController !== "undefined" && translationController !== null) {
            translationController.cancelTranslation()
        }
    }
    
    function setSourceLanguage(lang) { langSelector.setLanguage(lang) }
    function getSourceLanguage() { return langSelector.sourceLang }
    
    Rectangle { anchors.fill: parent; color: "transparent" }
    
    EmptyWorkspace {
        anchors.fill: parent
        visible: !workspace.hasSelection
        emptyStateMode: typeof projectController !== "undefined" && projectController.hasProject ? "no_selection" : "no_project"
        onOpenSrtClicked: workspace.openSrtRequested()
        onOpenProjectClicked: workspace.openProjectRequested()
    }
    
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12
        visible: workspace.hasSelection
        
        // Status & Language Header Row
        RowLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Theme.spaceSmall
            
            Text {
                text: (typeof translationController !== "undefined" && translationController.currentOriginal !== "")
                      ? ("⚡ KHÔNG GIAN DỊCH THUẬT (CÂU #" + translationController.currentDisplayIndex + ")")
                      : "⚡ KHÔNG GIAN DỊCH THUẬT"
                color: "#FFFFFF"
                font.pixelSize: 13
                font.bold: true
            }

            // QUAN TRỌNG: Spacer này đẩy Badge trạng thái sang sát mép phải
            Item {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
            }

            Rectangle {
                implicitWidth: statusBadge.implicitWidth + 18
                implicitHeight: 22
                radius: 11
                color: translationController.status === "ACCEPTED" ? Theme.badgeSolidEmerald :
                       (translationController.status === "TRANSLATED" || translationController.status === "EDITED") ? "#FEF08A" :
                       translationController.status === "TRANSLATING" ? Qt.rgba(0.0, 0.4, 1.0, 0.20) :
                       translationController.status === "ERROR" ? "#FFE4E6" : Qt.rgba(0.58, 0.64, 0.72, 0.20)
                border.color: translationController.status === "ACCEPTED" ? "#10B981" :
                              (translationController.status === "TRANSLATED" || translationController.status === "EDITED") ? "#FDE047" :
                              translationController.status === "TRANSLATING" ? Theme.accentSapphire :
                              translationController.status === "ERROR" ? "#EF4444" : "#94A3B8"
                border.width: 1.5

                Text {
                    id: statusBadge
                    anchors.centerIn: parent
                    text: translationController.status === "ACCEPTED" ? "✓ ĐÃ DUYỆT" :
                          (translationController.status === "TRANSLATED" || translationController.status === "EDITED") ? "⌛ CHỜ DUYỆT" :
                          translationController.status === "TRANSLATING" ? "⚡ ĐANG DỊCH" :
                          translationController.status === "ERROR" ? "🛑 LỖI" : "⏳ CHỜ DỊCH"
                    color: translationController.status === "ACCEPTED" ? "#FFFFFF" :
                           (translationController.status === "TRANSLATED" || translationController.status === "EDITED") ? "#854D0E" :
                           translationController.status === "TRANSLATING" ? "#38BDF8" :
                           translationController.status === "ERROR" ? "#EF4444" : "#94A3B8"
                    font.pixelSize: 10
                    font.bold: true
                }
            }

            LanguageSelector {
                id: langSelector
                objectName: "sourceLangCombo"
                visible: false
                compact: workspace.width < 580
                Layout.alignment: Qt.AlignRight
            }
        }

        
        // Workspace Liquid Glide Container (Elastic transition on subtitle switch)
        Item {
            id: workspaceGlideContainer
            Layout.fillWidth: true
            implicitHeight: glideColumn.implicitHeight
            Layout.preferredHeight: implicitHeight

            property real glideOffset: 0
            property real glideOpacity: 1.0

            Connections {
                target: typeof translationController !== "undefined" ? translationController : null
                function onCurrentOriginalChanged() {
                    if (typeof translationController !== "undefined" && translationController.status !== "TRANSLATING") {
                        glideAnim.restart()
                    }
                    workspace.altTranslation = ""
                    workspace.altLoading = false
                }
                function onAlternativeTranslationReady(idx, altText, mode) {
                    workspace.altLoading = false
                    workspace.altTranslation = altText
                    workspace.altStyleMode = mode
                }
                function onAlternativeTranslationLoading(loading) {
                    workspace.altLoading = loading
                }
            }

            SequentialAnimation {
                id: glideAnim
                PropertyAction { target: workspaceGlideContainer; property: "glideOffset"; value: 12 }
                PropertyAction { target: workspaceGlideContainer; property: "glideOpacity"; value: 0.35 }
                ParallelAnimation {
                    NumberAnimation {
                        target: workspaceGlideContainer
                        property: "glideOffset"
                        to: 0
                        duration: 220
                        easing.type: Easing.OutCubic
                    }
                    NumberAnimation {
                        target: workspaceGlideContainer
                        property: "glideOpacity"
                        to: 1.0
                        duration: 220
                        easing.type: Easing.OutCubic
                    }
                }
            }

            Item {
                anchors.fill: parent
                anchors.topMargin: workspaceGlideContainer.glideOffset
                opacity: workspaceGlideContainer.glideOpacity

                ColumnLayout {
                    id: glideColumn
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 12

                    // Original Subtitle Pod
                    Rectangle {
                        id: originalPod
                        Layout.fillWidth: true
                        Layout.preferredHeight: 110
                        Layout.maximumHeight: 110
                        color: Theme.glassPodLuminous
                        radius: 16
                        border.color: Theme.glassBorderSpecularUpper
                        border.width: 1.5

                        layer.enabled: true
                        layer.effect: MultiEffect {
                            shadowEnabled: true
                            shadowColor: Qt.rgba(0.08, 0.04, 0.22, 0.16)
                            shadowBlur: 0.45
                            shadowVerticalOffset: 4
                        }

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Rectangle {
                                    implicitWidth: originalBadgeText.implicitWidth + 16
                                    implicitHeight: 20
                                    radius: 10
                                    color: Theme.accentSapphire

                                    Text {
                                        id: originalBadgeText
                                        anchors.centerIn: parent
                                        text: "CÂU GỐC (" + ((typeof translationController !== "undefined" && translationController.currentSourceLanguage)
                                              ? translationController.currentSourceLanguage.toUpperCase()
                                              : (langSelector.sourceLang ? langSelector.sourceLang.toUpperCase() : "ENGLISH")) + ")"
                                        color: "#FFFFFF"
                                        font.pixelSize: 10
                                        font.bold: true
                                        font.letterSpacing: 0.5
                                    }
                                }

                                Rectangle {
                                    visible: typeof translationController.currentStartTime !== "undefined" && translationController.currentStartTime !== ""
                                    implicitWidth: timeRangeText.implicitWidth + 16
                                    implicitHeight: 20
                                    radius: 10
                                    color: Qt.rgba(0.0, 0.4, 1.0, 0.12)
                                    border.color: Qt.rgba(0.24, 0.65, 0.98, 0.40)
                                    border.width: 1

                                    Text {
                                        id: timeRangeText
                                        anchors.centerIn: parent
                                        text: (typeof translationController.currentStartTime !== "undefined" ? translationController.currentStartTime : "") +
                                              " ➔ " +
                                              (typeof translationController.currentEndTime !== "undefined" ? translationController.currentEndTime : "")
                                        color: "#60A5FA"
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }

                                Item { Layout.fillWidth: true }
                            }

                            ScrollView {
                                id: origScroll
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                TextArea {
                                    id: origTextArea
                                    objectName: "origTextArea"
                                    width: origScroll.availableWidth
                                    text: translationController.currentOriginal
                                    color: Theme.textOnLightPod
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                    readOnly: true
                                    background: null
                                    selectByMouse: true
                                    selectionColor: Theme.accentSapphire
                                    selectedTextColor: "#FFFFFF"
                                }
                            }
                        }
                    }

                    // AI Translation Pod
                    Rectangle {
                        id: translationBox
                        Layout.fillWidth: true
                        Layout.preferredHeight: 140
                        Layout.maximumHeight: 140
                        color: Theme.glassPodRaised
                        radius: 16
                        border.color: translationController.status === "TRANSLATING" ? Theme.accentCyan : 
                                      (translationInput.activeFocus ? Theme.accentSapphire : Theme.glassBorderSpecularUpper)
                        border.width: (translationController.status === "TRANSLATING" || translationInput.activeFocus) ? 2 : 1.5
                        clip: true

                        Behavior on border.color { ColorAnimation { duration: Theme.animFocus } }

                        layer.enabled: true
                        layer.effect: MultiEffect {
                            shadowEnabled: true
                            shadowColor: Qt.rgba(0.08, 0.04, 0.22, 0.16)
                            shadowBlur: 0.45
                            shadowVerticalOffset: 4
                        }


                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Rectangle {
                                    implicitWidth: transBadgeText.implicitWidth + 16
                                    implicitHeight: 20
                                    radius: 10
                                    gradient: Gradient {
                                        orientation: Gradient.Horizontal
                                        GradientStop { position: 0.0; color: Theme.badgePurpleGradientStart }
                                        GradientStop { position: 1.0; color: Theme.badgePurpleGradientEnd }
                                    }

                                    Text {
                                        id: transBadgeText
                                        anchors.centerIn: parent
                                        text: "✨ BẢN DỊCH TIẾNG VIỆT (AI)"
                                        color: "#FFFFFF"
                                        font.pixelSize: 10
                                        font.bold: true
                                        font.letterSpacing: 0.5
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                Button {
                                    id: btnAltStyle
                                    objectName: "btnAltStyle"
                                    implicitHeight: 22
                                    implicitWidth: 140
                                    contentItem: Text {
                                        text: "🎲 Đổi văn phong ▼"
                                        color: Theme.accentPurple
                                        font.pixelSize: 10
                                        font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Rectangle {
                                        radius: 6
                                        color: btnAltStyle.hovered ? Qt.rgba(0.5, 0.2, 0.9, 0.15) : Qt.rgba(0.5, 0.2, 0.9, 0.08)
                                        border.color: Theme.accentPurple
                                        border.width: 1
                                    }
                                    visible: ["TRANSLATED", "EDITED", "ACCEPTED"].indexOf(translationController.status) >= 0
                                    enabled: !workspace.executionLocked && !workspace.altLoading && translationController.currentOriginal.length > 0
                                    onClicked: altStyleMenu.popup(btnAltStyle, 0, btnAltStyle.height + 4)
                                }

                                Rectangle {
                                    visible: translationController.status !== "TRANSLATING" && translationInput.text.trim().length > 0
                                    implicitWidth: confText.implicitWidth + 16
                                    implicitHeight: 22
                                    radius: 11
                                    color: "#EDE7F6"
                                    border.color: "#D1C4E9"
                                    border.width: 1

                                    Text {
                                        id: confText
                                        anchors.centerIn: parent
                                        text: "✦ Độ tin cậy: 98%"
                                        color: "#6A1B9A"
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }

                                Rectangle {
                                    visible: translationController.status === "TRANSLATING"
                                    implicitWidth: liveTranslatingRow.implicitWidth + 16
                                    implicitHeight: 20
                                    radius: 10
                                    color: Qt.rgba(Theme.accentCyan.r, Theme.accentCyan.g, Theme.accentCyan.b, 0.2)
                                    border.color: Theme.accentCyan
                                    border.width: 1

                                    RowLayout {
                                        id: liveTranslatingRow
                                        anchors.centerIn: parent
                                        spacing: 4
                                        Text { text: "⚡"; color: Theme.accentCyan; font.pixelSize: 10 }
                                        Text {
                                            text: "ĐANG DỊCH " + (typeof translationController !== "undefined" && typeof translationController.translationProgress !== "undefined" ? translationController.translationProgress : 0) + "%"
                                            color: Theme.accentCyan
                                            font.pixelSize: 9
                                            font.bold: true
                                        }
                                    }

                                    SequentialAnimation on opacity {
                                        running: translationController.status === "TRANSLATING"
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 1.0; to: 0.4; duration: 600; easing.type: Easing.InOutQuad }
                                        NumberAnimation { from: 0.4; to: 1.0; duration: 600; easing.type: Easing.InOutQuad }
                                    }
                                }

                                RowLayout {
                                    spacing: 6
                                    visible: translationController.status === "TRANSLATING" || translationInput.text.length > 0

                                    property int wordCount: {
                                        var s = translationInput.text.trim();
                                        return s.length > 0 ? s.split(/\s+/).length : 0;
                                    }

                                    Text {
                                        text: parent.wordCount + " từ"
                                        color: translationController.status === "TRANSLATING" ? Theme.accentCyan : Theme.textSecondary
                                        font.pixelSize: 11
                                        font.bold: true
                                    }

                                    Text {
                                        text: "•"
                                        color: "#94A3B8"
                                        font.pixelSize: 10
                                    }

                                    Text {
                                        text: translationInput.text.length + " ký tự"
                                        color: Theme.textSecondary
                                        font.pixelSize: 11
                                        font.bold: true
                                    }
                                }
                            }

                            // Translating stream scanner divider
                            Item {
                                id: scannerContainer
                                Layout.fillWidth: true
                                Layout.preferredHeight: 2
                                clip: true
                                visible: translationController.status === "TRANSLATING" && !scrambleOverlay.visible
                                opacity: (translationController.status === "TRANSLATING" && !scrambleOverlay.visible) ? 1.0 : 0.0
                                Behavior on opacity { NumberAnimation { duration: 250 } }

                                Rectangle {
                                    anchors.fill: parent
                                    color: Qt.rgba(Theme.accentCyan.r, Theme.accentCyan.g, Theme.accentCyan.b, 0.12)
                                    radius: 1
                                }

                                Rectangle {
                                    id: streamScanner
                                    height: parent.height
                                    width: Math.max(scannerContainer.width * 0.35, 60)
                                    radius: 1
                                    gradient: Gradient {
                                        orientation: Gradient.Horizontal
                                        GradientStop { position: 0.0; color: "transparent" }
                                        GradientStop { position: 0.5; color: Theme.accentCyan }
                                        GradientStop { position: 1.0; color: "transparent" }
                                    }

                                    NumberAnimation on x {
                                        from: -streamScanner.width
                                        to: scannerContainer.width > 0 ? scannerContainer.width : 300
                                        duration: 1200
                                        loops: Animation.Infinite
                                        running: translationController.status === "TRANSLATING"
                                    }
                                }
                            }


                            ScrollView {
                                id: transScroll
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true

                                TextArea {
                                    objectName: "translationInput"
                                    id: translationInput
                                    width: transScroll.availableWidth
                                    text: translationController.currentTranslation
                                    placeholderText: translationController.status === "TRANSLATING" ? "" : "Nhập bản dịch tiếng Việt tại đây..."
                                    placeholderTextColor: "#94A3B8"
                                    color: Theme.textOnLightPod
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                    background: null
                                    selectByMouse: true
                                    selectionColor: Theme.accentSapphire
                                    selectedTextColor: "#FFFFFF"
                                    readOnly: translationController.status === "TRANSLATING" || workspace.executionLocked
                                    onTextChanged: {
                                        if (focus && translationController.currentTranslation !== text) {
                                            translationController.updateCurrentTranslation(text)
                                        }
                                    }
                                }
                            }
                        }

                        // Neural Status Overlay (AUD-UX-001)
                        Item {
                            id: scrambleOverlay
                            anchors.fill: parent
                            anchors.margins: Theme.spaceMedium
                            anchors.topMargin: 40
                            visible: translationController.status === "TRANSLATING" && translationInput.text.trim().length === 0
                            z: 5

                            property int currentProgress: typeof translationController !== "undefined" ? translationController.translationProgress : 10

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 10

                                RowLayout {
                                    Layout.alignment: Qt.AlignHCenter
                                    spacing: 8

                                    Text {
                                        text: scrambleOverlay.currentProgress < 25 ? "⚡" : "🧠"
                                        color: Theme.accentCyan
                                        font.pixelSize: 16
                                        font.bold: true
                                    }

                                    Text {
                                        text: scrambleOverlay.currentProgress < 25 ? "ĐANG KHỞI TẠO BỐI CẢNH & NẠP MODEL..." : "AI ĐANG SUY LUẬN NGỮ NGHĨA & DỊCH THUẬT..."
                                        color: Theme.accentCyan
                                        font.pixelSize: 13
                                        font.bold: true
                                        font.letterSpacing: 0.8
                                    }

                                    // Blinking cyber block cursor
                                    Rectangle {
                                        width: 8
                                        height: 15
                                        color: Theme.accentCyan
                                        radius: 1
                                        SequentialAnimation on opacity {
                                            loops: Animation.Infinite
                                            NumberAnimation { from: 1.0; to: 0.15; duration: 320 }
                                            NumberAnimation { from: 0.15; to: 1.0; duration: 320 }
                                        }
                                    }
                                }

                                // Thanh tiến trình trực quan
                                Rectangle {
                                    Layout.alignment: Qt.AlignHCenter
                                    implicitWidth: 260
                                    implicitHeight: 4
                                    radius: 2
                                    color: Qt.rgba(1, 1, 1, 0.12)
                                    clip: true

                                    Rectangle {
                                        height: parent.height
                                        width: parent.width * Math.min(1.0, Math.max(0.1, scrambleOverlay.currentProgress / 100.0))
                                        radius: 2
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.0; color: Theme.accentSapphire }
                                            GradientStop { position: 1.0; color: Theme.accentCyan }
                                        }
                                        Behavior on width { NumberAnimation { duration: 200 } }
                                    }
                                }

                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "Tiến trình: " + scrambleOverlay.currentProgress + "% — Bản dịch sẽ xuất hiện trực tiếp ngay khi có token đầu tiên."
                                    color: Theme.textMuted
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }

                    // A/B Alternative Translation Pod (Feature 6)
                    Rectangle {
                        id: altTranslationBox
                        visible: workspace.altLoading || workspace.altTranslation.length > 0
                        Layout.fillWidth: true
                        implicitHeight: altCol.implicitHeight + 20
                        color: Theme.glassPodLuminous
                        radius: 14
                        border.color: Theme.accentPurple
                        border.width: 1.5

                        ColumnLayout {
                            id: altCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Rectangle {
                                    implicitWidth: altBadgeText.implicitWidth + 14
                                    implicitHeight: 20
                                    radius: 10
                                    color: Theme.accentPurple

                                    Text {
                                        id: altBadgeText
                                        anchors.centerIn: parent
                                        text: "🎲 " + (workspace.altStyleMode === "CREATIVE" ? "PHONG CÁCH PHÓNG KHOÁNG" : "PHONG CÁCH SÁT NGHĨA")
                                        color: "#FFFFFF"
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                Button {
                                    implicitWidth: 22
                                    implicitHeight: 22
                                    contentItem: Text {
                                        text: "✕"
                                        color: "#64748B"
                                        font.pixelSize: 11
                                        font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Rectangle {
                                        radius: 11
                                        color: "transparent"
                                    }
                                    onClicked: {
                                        workspace.altTranslation = ""
                                        workspace.altLoading = false
                                    }
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: workspace.altLoading ? "◌ Đang suy luận bản dịch thay thế..." : workspace.altTranslation
                                color: workspace.altLoading ? Theme.textMuted : Theme.textOnLightPod
                                font.pixelSize: 14
                                font.weight: Font.Medium
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                visible: !workspace.altLoading && workspace.altTranslation.length > 0
                                spacing: 8

                                Item { Layout.fillWidth: true }

                                Button {
                                    id: btnApplyAlt
                                    objectName: "btnApplyAltTranslation"
                                    implicitHeight: 26
                                    contentItem: Text {
                                        text: "➔ Áp dụng bản dịch này"
                                        color: "#FFFFFF"
                                        font.pixelSize: 11
                                        font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Rectangle {
                                        radius: 6
                                        color: Theme.accentPurple
                                    }
                                    onClicked: {
                                        if (typeof translationController !== "undefined") {
                                            var rowIdx = (typeof subListView !== "undefined" && subListView.currentRawIndex >= 0) ? subListView.currentRawIndex : 0
                                            translationController.applyAlternativeTranslation(rowIdx, workspace.altTranslation)
                                            workspace.altTranslation = ""
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // LIVE TRANSLATING HUD
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceMedium
            visible: translationController.status === "TRANSLATING"

            property int wordCount: {
                var s = translationInput.text.trim();
                return s.length > 0 ? s.split(/\s+/).length : 0;
            }
            property int charCount: translationInput.text.length
            property int lineCount: {
                var t = translationInput.text.trim();
                return t ? t.split('\n').length : 0;
            }

            Rectangle {
                implicitWidth: liveStreamRow.implicitWidth + 24
                implicitHeight: 24
                radius: 12
                color: Qt.rgba(Theme.accentCyan.r, Theme.accentCyan.g, Theme.accentCyan.b, 0.15)
                border.color: Theme.accentCyan
                border.width: 1
                RowLayout {
                    id: liveStreamRow
                    anchors.centerIn: parent
                    spacing: 5
                    Text {
                        id: liveSpinner
                        text: "⠋"
                        color: Theme.accentCyan
                        font.pixelSize: 13
                        font.bold: true
                        property var frames: ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                        property int frameIdx: 0
                        Timer {
                            interval: 80
                            running: translationController.status === "TRANSLATING"
                            repeat: true
                            onTriggered: {
                                liveSpinner.frameIdx = (liveSpinner.frameIdx + 1) % liveSpinner.frames.length
                                liveSpinner.text = liveSpinner.frames[liveSpinner.frameIdx]
                            }
                        }
                    }
                    Text {
                        text: translationInput.text.trim().length === 0 ? "Khởi tạo neural..." : "Đang sinh từ..."
                        color: Theme.accentCyan
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }

            Rectangle {
                implicitWidth: liveWordsRow.implicitWidth + 24
                implicitHeight: 24
                radius: 12
                color: Qt.rgba(Theme.accentPurple.r, Theme.accentPurple.g, Theme.accentPurple.b, 0.15)
                border.color: Theme.accentPurple
                border.width: 1
                RowLayout {
                    id: liveWordsRow
                    anchors.centerIn: parent
                    spacing: 4
                    Text { text: "📝"; font.pixelSize: 10 }
                    Text { text: parent.parent.parent.wordCount + " Từ"; color: Theme.accentPurple; font.pixelSize: 11; font.bold: true }
                }
            }

            Rectangle {
                implicitWidth: liveCharsRow.implicitWidth + 24
                implicitHeight: 24
                radius: 12
                color: Qt.rgba(Theme.textSecondary.r, Theme.textSecondary.g, Theme.textSecondary.b, 0.15)
                border.color: Theme.textMuted
                border.width: 1
                RowLayout {
                    id: liveCharsRow
                    anchors.centerIn: parent
                    spacing: 4
                    Text { text: "🔤"; font.pixelSize: 10 }
                    Text { text: parent.parent.parent.charCount + " Ký tự"; color: Theme.textPrimary; font.pixelSize: 11; font.bold: true }
                }
            }

            Rectangle {
                implicitWidth: liveLinesCountRow.implicitWidth + 24
                implicitHeight: 24
                radius: 12
                color: parent.lineCount > 2 ? Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.15) : Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.15)
                border.color: parent.lineCount > 2 ? Theme.danger : Theme.success
                border.width: 1
                RowLayout {
                    id: liveLinesCountRow
                    anchors.centerIn: parent
                    spacing: 4
                    Text { text: parent.parent.parent.lineCount > 2 ? "🛑" : "🟢"; font.pixelSize: 10 }
                    Text { text: parent.parent.parent.lineCount + " Dòng"; color: parent.parent.parent.lineCount > 2 ? Theme.danger : Theme.success; font.pixelSize: 11; font.bold: true }
                }
            }

            Item { Layout.fillWidth: true }
        }
        
        // QA HUD
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceMedium
            visible: translationController.status !== "TRANSLATING" && translationController.status !== "PENDING"
            
            property real durationSec: {
                if (!translationController.currentStartTime || !translationController.currentEndTime) return 1.0;
                function toSec(t) {
                    var p = t.replace(',', ':').split(':');
                    if (p.length < 4) return 0;
                    return parseInt(p[0])*3600 + parseInt(p[1])*60 + parseInt(p[2]) + parseInt(p[3])/1000;
                }
                var d = toSec(translationController.currentEndTime) - toSec(translationController.currentStartTime);
                return d > 0.001 ? d : 1.0;
            }
            property string cleanText: {
                return translationInput.text.replace(/<[^>]*>/g, "");
            }
            property real cps: {
                return cleanText.length / durationSec;
            }
            property int cpl: {
                var lines = cleanText.split('\n');
                var max = 0;
                for (var i=0; i<lines.length; i++) {
                    if (lines[i].length > max) max = lines[i].length;
                }
                return max;
            }
            property int lineCount: {
                return cleanText ? cleanText.split('\n').length : 0;
            }
            
            property color cpsColor: cps <= 17 ? Theme.success : (cps <= 20 ? Theme.warning : Theme.danger)
            property color cplColor: cpl <= 40 ? Theme.success : (cpl <= 42 ? Theme.warning : Theme.danger)
            property color lineCountColor: lineCount <= 2 ? Theme.success : Theme.danger
            
            Rectangle {
                implicitWidth: cpsRow.implicitWidth + 24
                implicitHeight: 24
                radius: 12
                color: Qt.rgba(parent.cpsColor.r, parent.cpsColor.g, parent.cpsColor.b, 0.15)
                border.color: parent.cpsColor
                border.width: 1
                RowLayout {
                    id: cpsRow
                    anchors.centerIn: parent
                    spacing: 4
                    Text { text: parent.parent.parent.cpsColor === Theme.danger ? "🛑" : parent.parent.parent.cpsColor === Theme.warning ? "🟡" : "🟢"; font.pixelSize: 10 }
                    Text { text: "CPS: " + parent.parent.parent.cps.toFixed(1); color: parent.parent.parent.cpsColor; font.pixelSize: 11; font.bold: true }
                }
            }
            
            Rectangle {
                implicitWidth: cplRow.implicitWidth + 24
                implicitHeight: 24
                radius: 12
                color: Qt.rgba(parent.cplColor.r, parent.cplColor.g, parent.cplColor.b, 0.15)
                border.color: parent.cplColor
                border.width: 1
                RowLayout {
                    id: cplRow
                    anchors.centerIn: parent
                    spacing: 4
                    Text { text: parent.parent.parent.cplColor === Theme.danger ? "🛑" : parent.parent.parent.cplColor === Theme.warning ? "🟡" : "🟢"; font.pixelSize: 10 }
                    Text { text: "CPL: " + parent.parent.parent.cpl + "/42"; color: parent.parent.parent.cplColor; font.pixelSize: 11; font.bold: true }
                }
            }
            
            Rectangle {
                implicitWidth: linesRow.implicitWidth + 24
                implicitHeight: 24
                radius: 12
                color: Qt.rgba(parent.lineCountColor.r, parent.lineCountColor.g, parent.lineCountColor.b, 0.15)
                border.color: parent.lineCountColor
                border.width: 1
                RowLayout {
                    id: linesRow
                    anchors.centerIn: parent
                    spacing: 4
                    Text { text: parent.parent.parent.lineCountColor === Theme.danger ? "🛑" : "🟢"; font.pixelSize: 10 }
                    Text { text: parent.parent.parent.lineCount + " Dòng"; color: parent.parent.parent.lineCountColor; font.pixelSize: 11; font.bold: true }
                }
            }
            Item { Layout.fillWidth: true }
        }

        // ==========================================
        // DẢI TỪ GỐC & NÚT TRA CỨU (DƯỚI CPL, CPS, DÒNG)
        // ==========================================
        Flow {
            id: termAlignmentFlow
            objectName: "termAlignmentFlow"
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 6
            visible: typeof translationController !== "undefined" && (
                translationController.currentOriginal !== "" ||
                (translationController.currentAppliedTerms && translationController.currentAppliedTerms.length > 0)
            )

            // THẺ CHỦ NGỮ (SUBJECT TAG CHIP)
            Rectangle {
                id: subjectTagChip
                objectName: "subjectTagChip"
                visible: typeof translationController !== "undefined" && translationController.currentOriginal !== ""
                implicitHeight: 26
                implicitWidth: subjectChipRow.implicitWidth + 20
                radius: 13
                color: subjectChipMouse.containsMouse ? Qt.rgba(0.545, 0.361, 0.965, 0.28) : Qt.rgba(0.545, 0.361, 0.965, 0.18)
                border.color: "#8B5CF6"
                border.width: 1.5

                RowLayout {
                    id: subjectChipRow
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: (typeof translationController !== "undefined" && translationController.currentSubjectTag && translationController.currentSubjectTag.is_detected) ? "👑" : "👤"
                        font.pixelSize: 11
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Text {
                        text: "Chủ ngữ:"
                        color: "#C4B5FD"
                        font.pixelSize: 11
                        font.bold: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Text {
                        objectName: "subjectTagText"
                        text: (typeof translationController !== "undefined" && translationController.currentSubjectTag && translationController.currentSubjectTag.text)
                              ? translationController.currentSubjectTag.text
                              : "Tự do"
                        color: "#F8FAFC"
                        font.pixelSize: 11
                        font.bold: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Text {
                        text: "▾"
                        color: "#A78BFA"
                        font.pixelSize: 10
                        font.bold: true
                        Layout.alignment: Qt.AlignVCenter
                    }
                }

                MouseArea {
                    id: subjectChipMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    ToolTip.visible: containsMouse
                    ToolTip.text: "Nhấp để chọn nhanh cặp ngôi xưng / chủ ngữ cho câu thoại"
                    onClicked: subjectPronounMenu.open()
                }

                Menu {
                    id: subjectPronounMenu
                    y: subjectTagChip.height + 4
                    width: 290
                    background: Rectangle {
                        color: "#0F172A"
                        border.color: "#8B5CF6"
                        border.width: 1
                        radius: 8
                    }

                    Repeater {
                        model: [
                            { pair: "Ta - Ngươi", label: "👑 Ta ➔ Ngươi (Ngạo mạn / Chiến đấu)" },
                            { pair: "Tôi - Cậu", label: "👤 Tôi ➔ Cậu (Đồng trang lứa / Hiện đại)" },
                            { pair: "Tớ - Cậu", label: "🌸 Tớ ➔ Cậu (Thanh xuân / Học đường)" },
                            { pair: "Anh - Em", label: "💫 Anh ➔ Em (Lãng mạn / Thân thiết)" },
                            { pair: "Em - Tiền bối", label: "🎓 Em ➔ Tiền bối (Senpai - Kouhai)" },
                            { pair: "Tự do", label: "🔮 Tự do (Tự động theo ngữ cảnh)" }
                        ]
                        delegate: MenuItem {
                            id: pronItem
                            implicitHeight: 32
                            background: Rectangle {
                                color: pronItem.highlighted ? Qt.rgba(0.545, 0.361, 0.965, 0.25) : "transparent"
                                radius: 4
                            }
                            contentItem: Text {
                                text: modelData.label
                                color: "#F8FAFC"
                                font.pixelSize: 12
                                font.bold: (typeof translationController !== "undefined" && translationController.currentSubjectTag && translationController.currentSubjectTag.pair === modelData.pair)
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            onTriggered: {
                                if (typeof translationController !== "undefined") {
                                    translationController.setSubjectPronoun(modelData.pair)
                                }
                            }
                        }
                    }
                }
            }

            Repeater {
                model: (typeof translationController !== "undefined" && translationController.currentAppliedTerms) ? translationController.currentAppliedTerms : []
                delegate: Rectangle {
                    implicitHeight: 26
                    implicitWidth: termChipRow.implicitWidth + 20
                    radius: 13
                    color: modelData.is_glossary ? Qt.rgba(0.06, 0.72, 0.50, 0.18) : (chipMouse.containsMouse ? Theme.glassPodRaised : Theme.glassPodLuminous)
                    border.color: modelData.is_glossary ? "#10B981" : Theme.glassBorderSpecularUpper
                    border.width: 1.5

                    RowLayout {
                        id: termChipRow
                        anchors.centerIn: parent
                        spacing: 6

                        Text {
                            text: "🏷️"
                            font.pixelSize: 11
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Text {
                            text: modelData.source
                            color: Theme.textPrimary
                            font.pixelSize: 11
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Text {
                            text: "➔"
                            color: "#64748B"
                            font.pixelSize: 11
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Text {
                            text: modelData.target
                            color: modelData.is_glossary ? "#34D399" : "#60A5FA"
                            font.pixelSize: 11
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Text {
                            text: (modelData.is_glossary && chipMouse.containsMouse) ? "✕" : "✓"
                            color: (modelData.is_glossary && chipMouse.containsMouse) ? "#EF4444" : "#10B981"
                            font.pixelSize: 11
                            font.bold: true
                            visible: modelData.is_glossary
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Rectangle {
                            id: btnPinChip
                            implicitWidth: 18
                            implicitHeight: 18
                            radius: 9
                            color: chipMouse.containsMouse ? Qt.rgba(0.15, 0.45, 0.95, 0.18) : Qt.rgba(0.0, 0.0, 0.0, 0.05)
                            border.color: chipMouse.containsMouse ? "#2563EB" : Qt.rgba(0.0, 0.0, 0.0, 0.15)
                            border.width: 1
                            visible: !modelData.is_glossary
                            Layout.alignment: Qt.AlignVCenter

                            Text {
                                anchors.centerIn: parent
                                text: "📌"
                                font.pixelSize: 10
                            }
                        }
                    }

                    MouseArea {
                        id: chipMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        ToolTip.visible: containsMouse
                        ToolTip.text: modelData.is_glossary ? "Nhấp để bỏ ghim khỏi Thuật ngữ dự án" : "1-Click để ghim vĩnh viễn vào Thuật ngữ dự án"
                        onClicked: {
                            if (typeof translationController !== "undefined") {
                                if (modelData.is_glossary) {
                                    translationController.unpinTermFromGlossary(modelData.source)
                                } else {
                                    translationController.pinTermToGlossary(modelData.source, modelData.target)
                                }
                            }
                        }
                    }
                }
            }

            // Nút Tra từ gốc tinh gọn (cho câu đã có bản dịch sẵn)
            Rectangle {
                id: btnExtractTerms
                objectName: "btnExtractTerms"
                visible: (!translationController.currentAppliedTerms || translationController.currentAppliedTerms.length === 0) &&
                         translationController.currentOriginal !== "" &&
                         translationController.currentTranslation !== "" &&
                         translationController.status !== "TRANSLATING"
                implicitHeight: 26
                implicitWidth: extractBtnRow.implicitWidth + 20
                radius: 13
                color: extractMouse.containsMouse ? Theme.glassPodRaised : Theme.glassPodLuminous
                border.color: extractMouse.containsMouse ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                border.width: 1.5

                RowLayout {
                    id: extractBtnRow
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: "🔍"
                        font.pixelSize: 11
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Text {
                        text: "Tra từ gốc & nghĩa"
                        color: "#60A5FA"
                        font.pixelSize: 11
                        font.bold: true
                        Layout.alignment: Qt.AlignVCenter
                    }
                }

                MouseArea {
                    id: extractMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    ToolTip.visible: containsMouse
                    ToolTip.text: "Bóc tách từ gốc và nghĩa cho câu hiện tại (0.5s)"
                    onClicked: {
                        if (typeof translationController !== "undefined") {
                            translationController.extractTermsForSubtitle(translationController.currentSubtitleIndex)
                        }
                    }
                }
            }
        }
        
        Text {
            visible: translationController.status === "ERROR"
            text: "Dịch thất bại. Lỗi xử lý mô hình AI."
            color: Theme.danger
            font.pixelSize: 12
            Layout.fillWidth: true
        }
        
        Item { Layout.fillHeight: true }
        
        // 3. THANH FOOTER ĐÁY CỘT GIỮA (Chứa phím tắt bên trái & 2 nút bấm bên phải)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: Qt.rgba(1, 1, 1, 0.08)
            radius: 12


            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12

                // Gợi ý phím tắt bên trái (Matching Design Mockup)
                Item {
                    id: shortcutHintContainer
                    objectName: "shortcutHintContainer"
                    Layout.alignment: Qt.AlignVCenter
                    implicitWidth: shortcutHintRow.implicitWidth
                    implicitHeight: shortcutHintRow.implicitHeight
                    visible: workspace.width >= 520

                    RowLayout {
                        id: shortcutHintRow
                        anchors.fill: parent
                        spacing: 6
                        Text {
                            text: "Nhấn"
                            color: Qt.rgba(1, 1, 1, 0.85)
                            font.pixelSize: 12
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                        }
                        Rectangle {
                            implicitWidth: keyHintText.implicitWidth + 12
                            implicitHeight: 22
                            radius: 6
                            color: Theme.glassPodRaised
                            border.color: Theme.glassBorderSpecularUpper
                            border.width: 1
                            Layout.alignment: Qt.AlignVCenter
                            Text {
                                id: keyHintText
                                anchors.centerIn: parent
                                text: "Ctrl + Enter"
                                font.pixelSize: 11
                                font.bold: true
                                color: Theme.textPrimary
                            }
                        }
                        Text {
                            text: "duyệt câu kế"
                            color: Qt.rgba(1, 1, 1, 0.85)
                            font.pixelSize: 12
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                        }
                    }

                    MouseArea {
                        id: hintMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        ToolTip.visible: containsMouse
                        ToolTip.text: "Click đúp để xem toàn bộ phím tắt — F1"
                        onDoubleClicked: workspace.hotkeysRequested()
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                }

                AppButton {
                    objectName: "btnHotkeys"
                    text: "⌨ Phím tắt (F1)"
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 120
                    Layout.minimumWidth: 85
                    isDarkGlass: true
                    onClicked: workspace.hotkeysRequested()
                }

                AppButton {
                    objectName: "btnRetry"
                    text: "⚡ Dịch lại"
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 105
                    Layout.minimumWidth: 70
                    isDarkGlass: true
                    visible: ["ERROR", "TRANSLATED", "EDITED", "ACCEPTED"].indexOf(translationController.status) >= 0
                    enabled: !workspace.executionLocked && translationController.engineStatus !== "Translating" &&
                             ["ERROR", "TRANSLATED", "EDITED", "ACCEPTED"].indexOf(translationController.status) >= 0
                    onClicked: translateRequested((typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : langSelector.sourceLang)
                }

                AppButton {
                    objectName: "btnCancelTranslation"
                    text: "🛑 Hủy dịch (Esc)"
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 125
                    Layout.minimumWidth: 85
                    isDestructive: true
                    visible: translationController.status === "TRANSLATING"
                    enabled: translationController.status === "TRANSLATING"
                    onClicked: workspace.cancelRequested()
                }

                AppButton {
                    objectName: "btnTranslate"
                    visible: translationController.status !== "TRANSLATING" &&
                             ["TRANSLATED", "EDITED", "ACCEPTED"].indexOf(translationController.status) < 0
                    text: "⚡ Dịch (Ctrl+T)"
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 112
                    Layout.minimumWidth: 80
                    isPrimary: true
                    enabled: !workspace.executionLocked && translationController.engineStatus !== "Translating" &&
                             translationController.status !== "TRANSLATING"
                    onClicked: translateRequested((typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : langSelector.sourceLang)
                }

                AppButton {
                    objectName: "btnAccept"
                    text: "✓ Chấp nhận (Accept) ➔"
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 148
                    Layout.minimumWidth: 100
                    isPrimary: true
                    visible: true
                    enabled: !workspace.executionLocked && (translationController.status === "TRANSLATED" || translationController.status === "EDITED" || translationController.status === "ACCEPTED")
                    onClicked: acceptRequested(translationInput.text)
                }
            }
        }
    }

    // PRO KEY-FLOW SHORTCUTS
    Shortcut {
        sequences: ["Ctrl+Return", "Ctrl+Enter"]
        enabled: workspace.hasSelection && !workspace.executionLocked
        onActivated: {
            if (translationController.status === "TRANSLATED" || translationController.status === "EDITED" || translationController.status === "ACCEPTED" || translationInput.text.trim().length > 0) {
                acceptRequested(translationInput.text)
                translationInput.forceActiveFocus()
            } else {
                translateRequested((typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : langSelector.sourceLang)
            }
        }
    }

    Shortcut {
        sequences: ["Ctrl+Shift+Return", "Ctrl+Shift+Enter", "Ctrl+T"]
        enabled: workspace.hasSelection && !workspace.executionLocked
        onActivated: {
            translateRequested((typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : langSelector.sourceLang)
        }
    }

    Shortcut {
        sequence: "Alt+Up"
        enabled: workspace.hasSelection
        onActivated: {
            if (typeof subListView !== "undefined" && typeof subListView.selectPrevRowAndFocus === "function") {
                subListView.selectPrevRowAndFocus()
                translationInput.forceActiveFocus()
            }
        }
    }

    Shortcut {
        sequence: "Alt+Down"
        enabled: workspace.hasSelection
        onActivated: {
            if (typeof subListView !== "undefined" && typeof subListView.selectNextRowAndFocus === "function") {
                subListView.selectNextRowAndFocus()
                translationInput.forceActiveFocus()
            }
        }
    }

    Shortcut {
        sequence: "Ctrl+G"
        enabled: workspace.hasSelection && !workspace.executionLocked
        onActivated: {
            var src = (typeof origTextArea !== "undefined" && origTextArea.selectedText) ? origTextArea.selectedText.trim() : ""
            var tgt = (typeof translationInput !== "undefined" && translationInput.selectedText) ? translationInput.selectedText.trim() : ""
            workspace.addGlossaryRequested(src, tgt)
        }
    }

    Shortcut {
        sequence: "Escape"
        enabled: translationController.status === "TRANSLATING"
        onActivated: workspace.cancelRequested()
    }

    Shortcut {
        sequence: "F1"
        onActivated: workspace.hotkeysRequested()
    }

    Menu {
        id: altStyleMenu
        width: 260
        MenuItem {
            text: "✨ Phóng khoáng (Tự nhiên, biểu cảm)"
            font.pixelSize: 11
            onTriggered: {
                var rowIdx = (typeof subListView !== "undefined" && subListView.currentRawIndex >= 0) ? subListView.currentRawIndex : 0
                translationController.requestAlternativeTranslation(rowIdx, (typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : langSelector.sourceLang, "CREATIVE")
            }
        }
        MenuItem {
            text: "📐 Sát nghĩa (Literal, chuẩn xác)"
            font.pixelSize: 11
            onTriggered: {
                var rowIdx = (typeof subListView !== "undefined" && subListView.currentRawIndex >= 0) ? subListView.currentRawIndex : 0
                translationController.requestAlternativeTranslation(rowIdx, (typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : langSelector.sourceLang, "LITERAL")
            }
        }
    }
}