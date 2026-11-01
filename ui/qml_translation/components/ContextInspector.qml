import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import QtQuick.Effects
import "../theme"

ColumnLayout {
    id: inspectorRoot
    spacing: 8

    property bool showAddTermForm: false

    function switchToTab(idx) {
        if (contextTabs) {
            contextTabs.setCurrentIndex(idx)
        }
    }

    function openAddTerm(sourceText, targetText) {
        switchToTab(1)
        showAddTermForm = true
        if (typeof sourceText === "string" && sourceText.length > 0) {
            addTermSourceInput.text = sourceText
        }
        if (typeof targetText === "string" && targetText.length > 0) {
            addTermTargetInput.text = targetText
        }
        if (addTermSourceInput.text.length > 0) {
            addTermTargetInput.forceActiveFocus()
        } else {
            addTermSourceInput.forceActiveFocus()
        }
    }

    // HEADER CỘT PHẢI: THANH NGỮ CẢNH + SUBTITLE + HOT-L & ĐÓNG (MATCHING DESIGN)
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 6

            Text {
                text: "🟣 NGỮ CẢNH"
                color: "#FFFFFF"
                font.pixelSize: 12
                font.bold: true
            }
            Text {
                text: "(INSPECTOR)"
                color: Qt.rgba(1, 1, 1, 0.7)
                font.pixelSize: 11
                visible: inspectorRoot.width >= 310
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                radius: 8
                color: Qt.rgba(1, 1, 1, 0.16)
                border.color: Qt.rgba(1, 1, 1, 0.3)
                border.width: 1
                implicitWidth: closeLbl.implicitWidth + 12
                implicitHeight: 22
                Text {
                    id: closeLbl
                    anchors.centerIn: parent
                    text: "Hot-L & Đóng"
                    color: "#FFFFFF"
                    font.pixelSize: 11
                }
            }
        }

        Text {
            text: "⚡ Bấm đúp để sửa nhanh Mốc Giờ & Ràng Buộc ⚙"
            color: Qt.rgba(1, 1, 1, 0.75)
            font.pixelSize: 11
        }
    }

    // TAB BAR CAPSULE WITH HOLD & DRAG SLIDING PILL (E:\Liquid Effect.mp4)
    Rectangle {
        id: tabOuterContainer
        objectName: "tabOuterContainer"
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: Math.min(parent.width - 24, 258)
        Layout.maximumWidth: 265
        implicitHeight: 36
        radius: height / 2 // = 18px
        color: Qt.rgba(1.0, 1.0, 1.0, 0.16)
        border.color: Theme.glassBorderSpecularLower
        border.width: 1

        readonly property int tabCount: 3
        readonly property real baseTabWidth: Math.max(1, (tabOuterContainer.width - 6) / tabCount)
        readonly property real tabWidth: baseTabWidth
        property bool isDragging: false
        property real pillDragX: 0
        property real fluidScaleX: 1.0
        property real fluidScaleY: 1.0
        property real fluidOriginX: baseTabWidth / 2
        readonly property int activeHoverIndex: isDragging
            ? Math.max(0, Math.min(tabCount - 1, Math.floor((pillDragX + baseTabWidth / 2 - 3) / baseTabWidth)))
            : contextTabs.currentIndex

        Behavior on fluidScaleX { enabled: !tabSquashImpulse.running; NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }
        Behavior on fluidScaleY { enabled: !tabSquashImpulse.running; NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        // Bắt sự kiện đổi tab (do Click hoặc gọi lệnh)
        Connections {
            target: contextTabs
            function onCurrentIndexChanged() {
                if (!tabOuterContainer.isDragging) {
                    tabSquashImpulse.restart()
                }
            }
        }

        // Chuỗi xung lực biến dạng giọt nước: Phóng dãn -> Đập dẹt -> Nảy về ban đầu
        SequentialAnimation {
            id: tabSquashImpulse
            ParallelAnimation {
                NumberAnimation { target: tabOuterContainer; property: "fluidScaleX"; to: 1.15; duration: 90; easing.type: Easing.OutQuad }
                NumberAnimation { target: tabOuterContainer; property: "fluidScaleY"; to: 0.88; duration: 90; easing.type: Easing.OutQuad }
            }
            ParallelAnimation {
                NumberAnimation { target: tabOuterContainer; property: "fluidScaleX"; to: 0.94; duration: 110; easing.type: Easing.InOutQuad }
                NumberAnimation { target: tabOuterContainer; property: "fluidScaleY"; to: 1.04; duration: 110; easing.type: Easing.InOutQuad }
            }
            ParallelAnimation {
                NumberAnimation { target: tabOuterContainer; property: "fluidScaleX"; to: 1.0; duration: 100; easing.type: Easing.OutBack }
                NumberAnimation { target: tabOuterContainer; property: "fluidScaleY"; to: 1.0; duration: 100; easing.type: Easing.OutBack }
            }
        }

        // SLIDING LIQUID PILL (E:\Liquid Effect.mp4)
        Rectangle {
            id: slidingPill
            objectName: "slidingPill"
            y: 3
            height: tabOuterContainer.height - 6 // = 30px
            radius: height / 2 // = 15px (Concentric: 18px - 3px = 15px)

            // Dynamic X and constant width (True 1:1 Sliding Droplet Motion)
            x: tabOuterContainer.isDragging
               ? tabOuterContainer.pillDragX
               : (3 + contextTabs.currentIndex * tabOuterContainer.baseTabWidth)
            width: tabOuterContainer.baseTabWidth

            transform: Scale {
                origin.x: tabOuterContainer.fluidOriginX
                origin.y: slidingPill.height / 2
                xScale: tabOuterContainer.fluidScaleX
                yScale: tabOuterContainer.fluidScaleY
            }

            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(0.0, 0.45, 1.0, 0.50) }
                GradientStop { position: 1.0; color: Qt.rgba(0.02, 0.65, 0.98, 0.46) }
            }
            border.color: Qt.rgba(1.0, 1.0, 1.0, 0.85)
            border.width: 1.0
            z: 1

            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Qt.rgba(0.0, 0.15, 0.45, 0.20)
                shadowBlur: 0.35
                shadowVerticalOffset: 2
            }

            Behavior on x {
                enabled: !tabOuterContainer.isDragging
                SpringAnimation {
                    spring: 3.4
                    damping: 0.28
                    epsilon: 0.05
                }
            }
        }

        Item {
            id: contextTabs
            objectName: "contextTabs"
            property int currentIndex: 0
            readonly property int count: 3
            function setCurrentIndex(idx) {
                currentIndex = Math.max(0, Math.min(tabOuterContainer.tabCount - 1, idx))
            }
            anchors.fill: parent
            anchors.margins: 3
            clip: true
            z: 2

            Item {
                id: tabTimeline
                objectName: "tabTimeline"
                x: 0
                width: tabOuterContainer.baseTabWidth
                height: parent.height

                Text {
                    anchors.centerIn: parent
                    text: "TIMELINE"
                    font.pixelSize: 11
                    font.bold: true
                    color: tabOuterContainer.activeHoverIndex === 0 ? "#FFFFFF" : Qt.rgba(1, 1, 1, 0.55)
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    Behavior on color { ColorAnimation { duration: 160 } }
                }
            }

            Item {
                id: tabIntelligence
                objectName: "tabIntelligence"
                x: tabOuterContainer.baseTabWidth
                width: tabOuterContainer.baseTabWidth
                height: parent.height

                Text {
                    anchors.centerIn: parent
                    text: "INTELLIGENCE"
                    font.pixelSize: 11
                    font.bold: true
                    color: tabOuterContainer.activeHoverIndex === 1 ? "#FFFFFF" : Qt.rgba(1, 1, 1, 0.55)
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    Behavior on color { ColorAnimation { duration: 160 } }
                }
            }

            Item {
                id: tabSummary
                objectName: "tabSummary"
                x: tabOuterContainer.baseTabWidth * 2
                width: tabOuterContainer.baseTabWidth
                height: parent.height

                Text {
                    anchors.centerIn: parent
                    text: "SUMMARY"
                    font.pixelSize: 11
                    font.bold: true
                    color: tabOuterContainer.activeHoverIndex === 2 ? "#FFFFFF" : Qt.rgba(1, 1, 1, 0.55)
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    Behavior on color { ColorAnimation { duration: 160 } }
                }
            }
        }

        // MOUSE AREA FOR PRESS-AND-HOLD & HORIZONTAL DRAG PHYSICS (E:\Liquid Effect.mp4)
        MouseArea {
            id: tabDragArea
            anchors.fill: parent
            z: 3
            hoverEnabled: true
            cursorShape: tabOuterContainer.isDragging ? Qt.ClosedHandCursor : Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton

            property real startMouseX: 0
            property real initialPillX: 0
            property bool hasMoved: false

            onPressed: function(mouse) {
                startMouseX = mouse.x
                initialPillX = slidingPill.x
                tabOuterContainer.pillDragX = initialPillX
                hasMoved = false
            }

            onPositionChanged: function(mouse) {
                if (pressed) {
                    var dx = mouse.x - startMouseX

                    if (!tabOuterContainer.isDragging && Math.abs(dx) > 4) {
                        tabOuterContainer.isDragging = true
                    }
                    if (tabOuterContainer.isDragging) {
                        hasMoved = true
                        var minX = 3
                        var maxX = tabOuterContainer.width - 3 - tabOuterContainer.baseTabWidth
                        var rawX = initialPillX + dx
                        if (rawX < minX) rawX = minX - (minX - rawX) * 0.25
                        else if (rawX > maxX) rawX = maxX + (rawX - maxX) * 0.25
                        tabOuterContainer.pillDragX = rawX

                        tabOuterContainer.fluidScaleX = 1.0 + Math.min(Math.abs(dx) * 0.002, 0.08)
                        tabOuterContainer.fluidScaleY = Math.max(0.94, 1.0 - (tabOuterContainer.fluidScaleX - 1.0) * 0.75)
                    }
                }
            }

            onReleased: function(mouse) {
                if (tabOuterContainer.isDragging) {
                    tabOuterContainer.isDragging = false
                    tabOuterContainer.fluidScaleX = 1.0
                    tabOuterContainer.fluidScaleY = 1.0
                    var pillCenter = tabOuterContainer.pillDragX + tabOuterContainer.baseTabWidth / 2
                    var targetIndex = Math.floor((pillCenter - 3) / tabOuterContainer.baseTabWidth)
                    targetIndex = Math.max(0, Math.min(tabOuterContainer.tabCount - 1, targetIndex))
                    contextTabs.currentIndex = targetIndex
                } else if (!hasMoved) {
                    var clickIndex = Math.floor((mouse.x - 3) / tabOuterContainer.baseTabWidth)
                    clickIndex = Math.max(0, Math.min(tabOuterContainer.tabCount - 1, clickIndex))
                    contextTabs.currentIndex = clickIndex
                }
            }
        }
    }
    
    StackLayout {
        currentIndex: contextTabs.currentIndex
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: 4
        
        // TAB 1: TIMELINE (100% MATCHING DESIGN MOCKUP)
        ColumnLayout {
            spacing: 12

            // CARD 1: THỜI LƯỢNG & TỐC ĐỘ
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: timingCol.implicitHeight + 24
                radius: 16
                color: Theme.glassPodLuminous
                border.color: Theme.glassBorderSpecularUpper
                border.width: 1.5

                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0.08, 0.04, 0.22, 0.14)
                    shadowBlur: 0.4
                    shadowVerticalOffset: 3
                }


                ColumnLayout {
                    id: timingCol
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "⏱️ THỜI LƯỢNG & TỐC ĐỘ"
                            color: "#38BDF8"
                            font.pixelSize: 11
                            font.bold: true
                            font.letterSpacing: 0.5
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Text {
                        text: (typeof translationController !== "undefined" && translationController.currentStartTime !== ""
                               ? (translationController.currentStartTime + " ➔ " + translationController.currentEndTime)
                               : "00:01:14.200 ➔ 00:01:17.800")
                        color: "#F8FAFC"
                        font.pixelSize: 13
                        font.bold: true
                    }

                    Text {
                        text: "Thời lượng: 3.60s • Tốc độ: 14 ký tự/giây"
                        color: "#CBD5E1"
                        font.pixelSize: 11
                    }
                }
            }

            // CARD 2: KIỂM TRA QUY CHUẨN (QA)
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: qaCol.implicitHeight + 24
                radius: 16
                color: Theme.glassPodLuminous
                border.color: Theme.glassBorderSpecularUpper
                border.width: 1.5

                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0.08, 0.04, 0.22, 0.14)
                    shadowBlur: 0.4
                    shadowVerticalOffset: 3
                }


                ColumnLayout {
                    id: qaCol
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "✓ KIỂM TRA QUY CHUẨN (QA)"
                            color: "#4ADE80"
                            font.pixelSize: 11
                            font.bold: true
                            font.letterSpacing: 0.5
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Text {
                        text: "Không vượt giới hạn 37 ký tự/dòng"
                        color: "#F8FAFC"
                        font.pixelSize: 12
                        font.bold: true
                    }

                    Text {
                        text: "CPS tối ưu (Chuẩn Netflix/YouTube)"
                        color: "#86EFAC"
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }
        
        // TAB 2: INTELLIGENCE
        ScrollView {
            id: intelScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: intelScroll.availableWidth
                spacing: 12

                

                // CARD 2: THUẬT NGỮ & THỰC THỂ (EXTRACTED GLOSSARY)
                Rectangle {
                    id: glossaryCard
                    objectName: "glossaryCard"
                    Layout.fillWidth: true
                    implicitHeight: glossaryCardCol.implicitHeight + 32
                    radius: 16
                    color: Theme.glassPodLuminous
                    border.color: Theme.glassBorderSpecularUpper
                    border.width: 1.5

                    layer.enabled: true
                    layer.effect: MultiEffect {
                        shadowEnabled: true
                        shadowColor: Qt.rgba(0.08, 0.04, 0.22, 0.14)
                        shadowBlur: 0.4
                        shadowVerticalOffset: 3
                    }

                    ColumnLayout {
                        id: glossaryCardCol
                        anchors.fill: parent
                        anchors.topMargin: 14
                        anchors.bottomMargin: 14
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        spacing: 10

                        // Title: 📚 THUẬT NGỮ & THỰC THỂ (count)
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.rightMargin: 4
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: 0
                            spacing: 6

                            Text {
                                id: glossaryTitleText
                                objectName: "glossaryTitleText"
                                text: "📚 THUẬT NGỮ & THỰC THỂ (" + (typeof projectController !== "undefined" ? projectController.glossaryTerms.length : 0) + ")"
                                color: Theme.accentSapphire
                                font.pixelSize: 11
                                font.bold: true
                                font.letterSpacing: 0.5
                                Layout.fillWidth: true
                                Layout.minimumWidth: 60
                                elide: Text.ElideRight
                            }
                            Item { Layout.fillWidth: true }

                            Button {
                                id: btnToggleAddTerm
                                objectName: "btnToggleAddTerm"
                                implicitHeight: 22
                                implicitWidth: 56
                                contentItem: Text {
                                    text: inspectorRoot.showAddTermForm ? "✕ Đóng" : "+ Thêm"
                                    color: Theme.accentSapphire
                                    font.pixelSize: 10
                                    font.bold: true
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                background: Rectangle {
                                    radius: 6
                                    color: btnToggleAddTerm.hovered ? Qt.rgba(0.0, 0.45, 1.0, 0.18) : Qt.rgba(0.0, 0.45, 1.0, 0.08)
                                    border.color: Theme.accentSapphire
                                    border.width: 1
                                }
                                onClicked: {
                                    inspectorRoot.showAddTermForm = !inspectorRoot.showAddTermForm
                                    if (inspectorRoot.showAddTermForm) {
                                        addTermSourceInput.forceActiveFocus()
                                    }
                                }
                            }
                        }

                        // Form thêm thuật ngữ thủ công
                        Rectangle {
                            id: addTermBox
                            visible: inspectorRoot.showAddTermForm
                            Layout.fillWidth: true
                            implicitHeight: addTermCol.implicitHeight + 16
                            radius: 10
                            color: Qt.rgba(0.0, 0.45, 1.0, 0.06)
                            border.color: Qt.rgba(0.0, 0.45, 1.0, 0.3)
                            border.width: 1

                            ColumnLayout {
                                id: addTermCol
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 6

                                TextField {
                                    id: addTermSourceInput
                                    objectName: "addTermSourceInput"
                                    Layout.fillWidth: true
                                    placeholderText: "Thuật ngữ gốc (ví dụ: Senpai)"
                                    font.pixelSize: 11
                                    color: Theme.textOnLightPod
                                    background: Rectangle {
                                        radius: 6
                                        color: "#FFFFFF"
                                        border.color: addTermSourceInput.activeFocus ? Theme.accentSapphire : "#CBD5E1"
                                        border.width: 1
                                    }
                                }

                                TextField {
                                    id: addTermTargetInput
                                    objectName: "addTermTargetInput"
                                    Layout.fillWidth: true
                                    placeholderText: "Bản dịch ưu tiên (ví dụ: Tiền bối)"
                                    font.pixelSize: 11
                                    color: Theme.textOnLightPod
                                    background: Rectangle {
                                        radius: 6
                                        color: "#FFFFFF"
                                        border.color: addTermTargetInput.activeFocus ? Theme.accentSapphire : "#CBD5E1"
                                        border.width: 1
                                    }
                                }

                                TextField {
                                    id: addTermForbiddenInput
                                    objectName: "addTermForbiddenInput"
                                    Layout.fillWidth: true
                                    placeholderText: "Từ cấm, tách bằng dấu phẩy (tùy chọn)"
                                    font.pixelSize: 11
                                    color: Theme.textOnLightPod
                                    background: Rectangle {
                                        radius: 6
                                        color: "#FFFFFF"
                                        border.color: addTermForbiddenInput.activeFocus ? Theme.accentSapphire : "#CBD5E1"
                                        border.width: 1
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Item { Layout.fillWidth: true }

                                    Button {
                                        text: "Hủy"
                                        implicitHeight: 24
                                        contentItem: Text {
                                            text: "Hủy"
                                            color: "#64748B"
                                            font.pixelSize: 10
                                            font.bold: true
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        background: Rectangle {
                                            radius: 6
                                            color: "transparent"
                                        }
                                        onClicked: {
                                            inspectorRoot.showAddTermForm = false
                                            addTermSourceInput.text = ""
                                            addTermTargetInput.text = ""
                                            addTermForbiddenInput.text = ""
                                        }
                                    }

                                    Button {
                                        id: btnSaveTerm
                                        objectName: "btnSaveTerm"
                                        implicitHeight: 24
                                        contentItem: Text {
                                            text: "📌 Ghim Thuật Ngữ"
                                            color: "#FFFFFF"
                                            font.pixelSize: 10
                                            font.bold: true
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        background: Rectangle {
                                            radius: 6
                                            color: Theme.accentSapphire
                                        }
                                        onClicked: {
                                            if (typeof projectController !== "undefined") {
                                                var ok = projectController.addManualGlossaryTerm(
                                                    addTermSourceInput.text,
                                                    addTermTargetInput.text,
                                                    addTermForbiddenInput.text
                                                )
                                                if (ok) {
                                                    addTermSourceInput.text = ""
                                                    addTermTargetInput.text = ""
                                                    addTermForbiddenInput.text = ""
                                                    inspectorRoot.showAddTermForm = false
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Empty state khi chưa có thuật ngữ
                        Rectangle {
                            id: glossaryEmptyState
                            objectName: "glossaryEmptyState"
                            Layout.fillWidth: true
                            Layout.leftMargin: 4
                            Layout.rightMargin: 4
                            Layout.topMargin: 4
                            Layout.bottomMargin: 6
                            implicitHeight: emptyText.implicitHeight + 20
                            radius: 10
                            color: Theme.glassPodRaised
                            border.color: Theme.glassBorderSpecularLower
                            border.width: 1
                            visible: typeof projectController === "undefined" || projectController.glossaryTerms.length === 0

                            Text {
                                id: emptyText
                                anchors.fill: parent
                                anchors.margins: 10
                                text: "Chưa có thuật ngữ nào. Nhập tóm tắt (ví dụ: 'Nhân vật \"Lăng Ba\": Khinh công') ở tab SUMMARY để AI tự động trích xuất sau 2s."
                                color: Theme.textOnLightPodMuted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }

                        // Flow layout hiển thị các chip thuật ngữ
                        Flow {
                            id: termsFlow
                            objectName: "termsFlow"
                            Layout.fillWidth: true
                            width: parent ? parent.width : 260
                            spacing: 6
                            visible: typeof projectController !== "undefined" && projectController.glossaryTerms.length > 0

                            Repeater {
                                id: termsRepeater
                                objectName: "termsRepeater"
                                model: typeof projectController !== "undefined" ? projectController.glossaryTerms : []

                                Rectangle {
                                    id: termChip
                                    objectName: "termChip_" + modelData.source_term
                                    implicitWidth: Math.min(chipRow.implicitWidth + 16, termsFlow.width > 0 ? termsFlow.width : 260)
                                    implicitHeight: 26
                                    radius: 13
                                    color: Theme.glassPodRaised
                                    border.color: modelData.is_auto ? Theme.accentSapphire : Theme.glassBorderSpecularLower
                                    border.width: 1

                                    RowLayout {
                                        id: chipRow
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        spacing: 6

                                        Rectangle {
                                            implicitWidth: chipBadgeText.implicitWidth + 8
                                            implicitHeight: 16
                                            radius: 8
                                            color: modelData.is_auto ? Theme.accentSapphire : Qt.rgba(0.4, 0.45, 0.55, 0.25)

                                            Text {
                                                id: chipBadgeText
                                                anchors.centerIn: parent
                                                text: modelData.is_auto ? "AI" : "Thủ công"
                                                color: modelData.is_auto ? "#FFFFFF" : Theme.textOnLightPodMuted
                                                font.pixelSize: 9
                                                font.bold: true
                                            }
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: modelData.source_term + " ➔ " + modelData.preferred_translation
                                            color: Theme.textOnLightPod
                                            font.pixelSize: 11
                                            font.bold: true
                                            elide: Text.ElideRight
                                        }

                                        Rectangle {
                                            id: btnDismissTerm
                                            objectName: "btnDismissTerm_" + modelData.source_term
                                            visible: true
                                            implicitWidth: 16
                                            implicitHeight: 16
                                            radius: 8
                                            color: dismissMouse.containsMouse ? Qt.rgba(0.9, 0.2, 0.2, 0.2) : "transparent"

                                            Text {
                                                anchors.centerIn: parent
                                                text: "✕"
                                                color: dismissMouse.containsMouse ? "#EF4444" : Theme.textOnLightPodMuted
                                                font.pixelSize: 10
                                                font.bold: true
                                            }

                                            MouseArea {
                                                id: dismissMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    if (typeof projectController !== "undefined") {
                                                        projectController.removeGlossaryTerm(modelData.source_term)
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    ToolTip.visible: chipMouse.containsMouse
                                    ToolTip.text: modelData.source_term + " ➔ " + modelData.preferred_translation +
                                                  (modelData.forbidden_alternatives && modelData.forbidden_alternatives.length > 0
                                                   ? "\n(Cấm: " + modelData.forbidden_alternatives.join(", ") + ")" : "")
                                    ToolTip.delay: 400

                                    MouseArea {
                                        id: chipMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        acceptedButtons: Qt.NoButton
                                        z: -1
                                    }
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
        
        // TAB 3: SUMMARY
        ColumnLayout {
            spacing: 8
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 130
                color: Theme.glassPodRaised
                radius: 16
                border.color: summaryInput.activeFocus ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                border.width: summaryInput.activeFocus ? 2 : 1.5

                Behavior on border.color { ColorAnimation { duration: Theme.animFocus } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Rectangle {
                            implicitWidth: summaryBadge.implicitWidth + 14
                            implicitHeight: 20
                            radius: 10
                            color: "#AD1457"

                            Text {
                                id: summaryBadge
                                anchors.centerIn: parent
                                text: "📌 TÓM TẮT CỐT TRUYỆN"
                                color: "#FFFFFF"
                                font.pixelSize: 10
                                font.bold: true
                                font.letterSpacing: 0.5
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true

                        TextArea {
                            objectName: "storySummaryInput"
                            id: summaryInput
                            text: typeof globalStorySummary !== "undefined" ? globalStorySummary : ""
                            placeholderText: "Nhập quy tắc dịch, bối cảnh, xưng hô..."
                            placeholderTextColor: "#94A3B8"
                            color: Theme.textOnLightPod
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                            background: null
                            selectByMouse: true
                            selectionColor: Theme.accentSapphire
                            selectedTextColor: "#FFFFFF"
                            Keys.onPressed: function(event) {
                                if (event.key !== Qt.Key_Tab) return

                                const nextItem = summaryInput.nextItemInFocusChain(!(event.modifiers & Qt.ShiftModifier))
                                if (nextItem) {
                                    nextItem.forceActiveFocus(Qt.TabFocusReason)
                                    event.accepted = true
                                }
                            }
                            onTextChanged: {
                                globalStorySummary = text
                                if (typeof projectController !== "undefined") projectController.markDirty()
                                summaryDebounceTimer.restart()
                            }
                        }
                    }
                }
            }

            Timer {
                id: summaryDebounceTimer
                objectName: "summaryDebounceTimer"
                interval: 2000
                repeat: false
                onTriggered: {
                    if (typeof projectController !== "undefined" && summaryInput.text.trim().length > 0) {
                        projectController.analyzeSummary(summaryInput.text)
                    }
                }
            }

            // Thanh capsule thông tin nhỏ
            Rectangle {
                id: summaryArchetypeCapsule
                objectName: "summaryArchetypeCapsule"
                Layout.fillWidth: true
                implicitHeight: summaryCapsuleCol.implicitHeight + 16
                radius: 12
                color: Theme.glassPodRaised
                border.color: Theme.glassBorderSpecularLower
                border.width: 1
                visible: typeof projectController !== "undefined"

                ColumnLayout {
                    id: summaryCapsuleCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            id: summaryCapsuleIcon
                            text: {
                                if (typeof projectController === "undefined") return "🎭"
                                var list = projectController.archetypeList || []
                                for (var i = 0; i < list.length; i++) {
                                    if (list[i].id === projectController.activeArchetype) {
                                        return list[i].icon || "🎭"
                                    }
                                }
                                return "🎭"
                            }
                            font.pixelSize: 13
                        }

                        Text {
                            id: summaryCapsuleLabel
                            objectName: "summaryCapsuleLabel"
                            text: typeof projectController !== "undefined" ? projectController.archetypeDisplayLabel : "Tự do"
                            color: Theme.textOnLightPod
                            font.pixelSize: 11
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        Text {
                            id: summaryCapsulePronouns
                            objectName: "summaryCapsulePronouns"
                            text: typeof projectController !== "undefined" ? projectController.activePronounPair : ""
                            color: Theme.accentSapphire
                            font.pixelSize: 11
                            font.bold: true
                        }
                    }

                    Text {
                        id: summaryCapsuleStatus
                        objectName: "summaryCapsuleStatus"
                        text: typeof projectController !== "undefined" && projectController.isArchetypeLocked
                              ? "🔒 Đã khóa thủ công"
                              : "✨ Tự động nhận diện sau 2s"
                        color: typeof projectController !== "undefined" && projectController.isArchetypeLocked
                               ? "#D97706"
                               : "#16A34A"
                        font.pixelSize: 10
                        font.bold: true
                    }
                }
            }

            // Nút bấm tương tác: Đánh dấu phụ đề dịch từ tiếng Nhật (BẬT / TẮT)
            Rectangle {
                objectName: "btnOriginCapsule"
                Layout.fillWidth: true
                implicitHeight: 28
                radius: 14
                color: (typeof projectController !== "undefined" && projectController.isJaOrigin)
                       ? Qt.rgba(0.96, 0.45, 0.71, 0.15) 
                       : Qt.rgba(0.58, 0.64, 0.72, 0.12)
                border.color: (typeof projectController !== "undefined" && projectController.isJaOrigin)
                             ? "#F472B6" 
                             : "#94A3B8"
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 6

                    Text {
                        text: (typeof projectController !== "undefined" && projectController.isJaOrigin) ? "🌸" : "🌐"
                        font.pixelSize: 11
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        elide: Text.ElideRight
                        text: (typeof projectController !== "undefined" && projectController.isJaOrigin)
                              ? "Nguồn: Tiếng Nhật"
                              : "Nguồn: Tiếng Anh bản ngữ"
                        color: (typeof projectController !== "undefined" && projectController.isJaOrigin) ? "#BE185D" : Theme.textSecondary
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                ToolTip.visible: originMouse.containsMouse
                ToolTip.text: (typeof projectController !== "undefined" && projectController.isJaOrigin)
                              ? "Nguồn gốc: Dịch từ tiếng Nhật ('senior' / 'senpai' ➔ 'tiền bối', 'junior' ➔ 'hậu bối/em') — Bấm để chuyển"
                              : "Nguồn gốc: Tiếng Anh bản ngữ ('senior' dịch tự nhiên) — Bấm để chuyển sang gốc Nhật"

                MouseArea {
                    id: originMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (typeof projectController !== "undefined") {
                            projectController.setIsJaOrigin(!projectController.isJaOrigin)
                        }
                    }
                }
            }

            // Đẩy thẻ Summary lên trên, giữ khoảng trống kính mờ bên dưới
            Item { Layout.fillHeight: true }
        }
    }
}
