import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import QtQuick.Dialogs
import QtQuick.Effects
import "theme"
import "components"
import "dialogs"

ApplicationWindow {
    id: mainWindow
    visible: true
    width: 1280
    height: 720
    minimumWidth: 1024
    minimumHeight: 600
    flags: Qt.FramelessWindowHint | Qt.Window
    title: "AI Subtitle Translator - Professional Workspace"
    color: "transparent"

    property string pendingCloseAction: ""
    property bool forceClose: false

    onClosing: (close) => {
        if (forceClose) {
            close.accepted = true
            return
        }
        if (typeof projectController !== "undefined" && projectController.hasProject && projectController.isDirty) {
            close.accepted = false
            pendingCloseAction = "EXIT_APP"
            dirtyCloseConfirmDialog.open()
        }
    }

    // THÊM MỚI: Biến toàn cục hứng Story Summary (đặt ở cấp cao nhất)
    property string globalStorySummary: ""
    property var selectedSubtitleIndices: []
    // P2.5-T13-D0: manual responsive acceptance only.
    property bool responsiveTestToolsEnabled: Qt.application.arguments.indexOf("--dev-tools") >= 0

    // Mask for rounded liquid glass window frame
    Item {
        id: windowMaskContainer
        anchors.fill: windowRootContainer
        layer.enabled: true
        visible: false
        Rectangle {
            anchors.fill: parent
            radius: windowRootContainer.radius
            color: "white"
        }
    }

    // ==========================================
    // P2.5-T2: PROJECT HEADER
    // ==========================================
    // ==========================================
    // SEAMLESS LIQUID GLASS ROOT WINDOW CONTAINER (ROUNDED & LUMINOUS)
    // ==========================================
    Rectangle {
        id: windowRootContainer
        anchors.fill: parent
        anchors.margins: 0
        radius: (mainWindow.visibility === Window.Maximized) ? 0 : 16
        clip: true
        border.color: Qt.rgba(1.0, 1.0, 1.0, 0.75)
        border.width: 1.5
        layer.enabled: mainWindow.visibility !== Window.Maximized
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: windowMaskContainer
        }

        // LAYER 1: Fluid Liquid Mesh Wallpaper (100% 1:1 match with web design mockup)
        Image {
            id: bgLiquidMesh
            anchors.fill: parent
            source: "../assets/liquid_mesh_bg.jpg"
            fillMode: Image.PreserveAspectCrop
            smooth: true
            asynchronous: false
        }

        // LAYER 2: Ultra-Gloss Liquid Glass Frost Sheen
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: Qt.rgba(1.0, 1.0, 1.0, 0.12) } // Giảm từ 0.28 xuống 0.12
                GradientStop { position: 0.5; color: Qt.rgba(1.0, 1.0, 1.0, 0.03) } // Giảm từ 0.12 xuống 0.03
                GradientStop { position: 1.0; color: Qt.rgba(1.0, 1.0, 1.0, 0.08) } // Giảm từ 0.20 xuống 0.08
            }
        }


        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            AppHeader {
                id: appHeader
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                projectName: "Workspace"
                hasProject: projectController.hasProject || subListView.count > 0
                isSaved: (projectController.hasProject || subListView.count > 0) && !projectController.isDirty
                hasProjectData: subListView.count > 0
                projectMutationLocked: batchController.executionLocked
                sourceLanguage: transWorkspace.getSourceLanguage()
                targetLanguage: "Vietnamese"
                storySummary: mainWindow.globalStorySummary
                currentSubtitleIndex: subListView.currentRawIndex
                selectedIndices: mainWindow.selectedSubtitleIndices
                onOpenSrtClicked: {
                    if (!batchController.executionLocked) importSrtDialog.open()
                }
                onOpenProjectClicked: {
                    if (!batchController.executionLocked) loadProjectDialog.open()
                }
                onSaveClicked: saveProjectDialog.open()
                onExportClicked: {
                    if (projectController.validateBeforeExport()) {
                        exportSrtDialog.open()
                    }
                }
                isBatchMode: typeof projectController !== "undefined" && projectController.isBatchMode
                batchLabel: typeof projectController !== "undefined" ? projectController.batchLabel : ""
                originalSourcePath: typeof projectController !== "undefined" ? projectController.originalSourcePath : ""
                onModelManagerClicked: modelManagerDialog.open()
                onArchetypeClicked: {
                    contextInspector.switchToTab(1)
                }
                onCloseProjectClicked: handleCloseProject()
                onSyncStudioClicked: {
                    if (typeof projectController !== "undefined") {
                        projectController.quickSyncToOriginal()
                    }
                }
                onAppendBatchClicked: {
                    if (!batchController.executionLocked) {
                        appendBatchDialog.open()
                    }
                }
                onHotkeysClicked: hotkeysDialog.open()
            }

            StudioLaunchpad {
                id: studioLaunchpad
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: subListView.count === 0
                onOpenSrtClicked: {
                    if (!batchController.executionLocked) importSrtDialog.open()
                }
                onOpenProjectClicked: {
                    if (!batchController.executionLocked) loadProjectDialog.open()
                }
            }

            SplitView {
                id: mainSplitView
                objectName: "mainSplitView"
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: subListView.count > 0
                orientation: Qt.Horizontal

                handle: Rectangle {
                    implicitWidth: 1
                    color: Qt.rgba(1, 1, 1, 0.32) // Tăng từ 0.24 lên 0.32 cho sắc nét như bản mẫu
                }

                // PANEL 1: SUBTITLE NAVIGATOR (SEAMLESS DOCKED)
                Rectangle {
                    id: subtitleIsland
                    SplitView.preferredWidth: 320
                    SplitView.minimumWidth: 260
                    SplitView.maximumWidth: 450
                    radius: 0
                    color: Theme.glassIslandSurface
                    border.color: "transparent"
                    border.width: 0
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        FindReplaceBar {
                            id: findReplaceBar
                            objectName: "findReplaceBar"
                            visible: false
                            Layout.fillWidth: true
                            Layout.margins: 6
                            onCloseRequested: visible = false
                        }

                        SubtitleListView {
                            id: subListView
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            model: typeof filteredSubtitleModel !== "undefined" && filteredSubtitleModel ? filteredSubtitleModel : subtitleModel
                            selectedIndices: mainWindow.selectedSubtitleIndices
                            onSelectionChanged: function(indices) {
                                mainWindow.selectedSubtitleIndices = indices
                            }
                        }
                    }
                }

                // PANEL 2: TRANSLATION WORKSPACE (SEAMLESS DOCKED)
                Rectangle {
                    id: workspaceIsland
                    SplitView.fillWidth: true
                    SplitView.minimumWidth: 400
                    radius: 0
                    color: Theme.glassIslandSurface
                    border.color: "transparent"
                    border.width: 0
                    clip: true

                    TranslationWorkspace {
                        id: transWorkspace
                        anchors.fill: parent
                        anchors.margins: Theme.spaceMedium
                        hasSelection: subListView.currentRawIndex >= 0
                        totalCount: subListView.count
                        executionLocked: batchController.executionLocked

                        onTranslateRequested: (sourceLang) => {
                            translationController.requestTranslation(subListView.currentRawIndex, sourceLang, "Vietnamese", globalStorySummary)
                        }

                        onAcceptRequested: (text) => {
                            let isSuccess = translationController.acceptTranslation(subListView.currentRawIndex, text)
                            if (isSuccess) {
                                subListView.selectNextRowAndFocus()
                            }
                        }
                        onAddGlossaryRequested: (src, tgt) => {
                            contextInspector.openAddTerm(src, tgt)
                        }
                        onOpenSrtRequested: {
                            if (!batchController.executionLocked) importSrtDialog.open()
                        }
                        onOpenProjectRequested: {
                            if (!batchController.executionLocked) loadProjectDialog.open()
                        }
                        onHotkeysRequested: hotkeysDialog.open()
                    }
                }

                // PANEL 3: CONTEXT INSPECTOR (SEAMLESS DOCKED)
                Rectangle {
                    id: contextIsland
                    SplitView.preferredWidth: 300
                    SplitView.minimumWidth: 280
                    SplitView.maximumWidth: 400
                    radius: 0
                    color: Theme.glassIslandSurface
                    border.color: "transparent"
                    border.width: 0
                    clip: true

                    ContextInspector {
                        id: contextInspector
                        anchors.fill: parent
                        anchors.margins: Theme.spaceMedium
                    }
                }
            }

            AppStatusBar {
                id: appStatusBar
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                totalCount: translationController.totalSubtitleCount
                acceptedCount: translationController.acceptedCount
                engineStatus: {
                    return translationController.engineStatus
                }
                vramUsed: typeof modelController !== "undefined" ? modelController.vramUsed : -1.0
                vramTotal: typeof modelController !== "undefined" ? modelController.vramTotal : -1.0
                gpuName: typeof modelController !== "undefined" && modelController.hardwareSummary ? modelController.hardwareSummary.gpu_name : ""
                backendStatus: typeof modelController !== "undefined" && modelController.hardwareSummary ? modelController.hardwareSummary.backend_status : ""
            }
        }
    }


    // ==========================================
    // DIALOGS & CONNECTIONS
    // ==========================================
    // Đưa Toast vào lớp Overlay trên cùng để không bị che bởi các Dialog modal
    Shortcut {
        sequence: "Ctrl+H"
        onActivated: {
            findReplaceBar.visible = !findReplaceBar.visible
            if (findReplaceBar.visible) {
                findReplaceBar.focusFind()
            }
        }
    }

    Toast {
        id: appToast
        parent: Overlay.overlay
        z: 99999
    }
    FileDialog {
        id: importSrtDialog
        title: "Chọn file phụ đề hoặc dự án"
        nameFilters: [
            "Tất cả định dạng phụ đề (*.srt *.aisrt)",
            "File phụ đề SRT (*.srt)",
            "File dự án AISRT (*.aisrt)"
        ]
        onAccepted: {
            var path = selectedFile.toString().toLowerCase()
            if (path.endsWith(".aisrt")) {
                projectController.loadProject(selectedFile)
            } else {
                projectController.importSrt(selectedFile)
            }
        }
    }
    FileDialog { id: loadProjectDialog; title: "Mở file dự án"; nameFilters: ["AI Subtitle Project (*.aisrt)"]; onAccepted: projectController.loadProject(selectedFile) }

    FileDialog {
        id: saveProjectDialog;
        title: "Lưu dự án";
        fileMode: FileDialog.SaveFile;
        nameFilters: ["AI Subtitle Project (*.aisrt)"];
        defaultSuffix: "aisrt";
        // ĐÃ FIX: Xóa onAccepted bị lặp
        onAccepted: {
            projectController.saveProject(selectedFile, globalStorySummary, transWorkspace.getSourceLanguage(), "Vietnamese")
            if (pendingCloseAction === "EXIT_APP_SAVING") {
                forceClose = true
                Qt.quit()
                mainWindow.close()
            } else if (pendingCloseAction === "CLOSE_PROJECT_SAVING") {
                projectController.closeProject()
            }
            pendingCloseAction = ""
        }
        onRejected: {
            pendingCloseAction = ""
        }
    }

    FileDialog { id: exportSrtDialog; title: "Xuất file SRT đã dịch"; fileMode: FileDialog.SaveFile; nameFilters: ["Subtitle files (*.srt)"]; defaultSuffix: "srt"; onAccepted: projectController.exportSrt(selectedFile) }
    FileDialog { id: appendBatchDialog; title: "Chọn file đợt dịch tiếp theo (.srt)"; fileMode: FileDialog.OpenFile; nameFilters: ["File phụ đề SRT (*.srt)"]; defaultSuffix: "srt"; onAccepted: projectController.appendNextBatch(selectedFile) }

    Connections {
        target: translationController
        function onNotify(title, msg) { appToast.show(title, msg) }
    }

    Connections {
        target: projectController
        function onNotify(title, msg) { appToast.show(title, msg) }
        function onLanguageLoaded(lang) { transWorkspace.setSourceLanguage(lang) }
        function onProjectLoaded(summary) { globalStorySummary = summary }
        function onBatchAppended(firstNewIndex) {
            subListView.selectRowAndScroll(firstNewIndex)
        }
        function onQaExportWarningRequired(filePath, errorCount) {
            qaConfirmDialog.targetFilePath = filePath
            qaConfirmDialog.errorCount = errorCount
            qaConfirmDialog.open()
        }
    }

    Dialog {
        id: qaConfirmDialog
        title: ""
        anchors.centerIn: parent
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        width: 460

        property string targetFilePath: ""
        property int errorCount: 0

        background: Rectangle {
            color: Qt.rgba(0.97, 0.96, 0.99, 0.96)
            radius: 20
            border.color: Theme.glassBorderSpecularUpper
            border.width: 1.5

            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowBlur: 0.8
                shadowColor: Qt.rgba(0, 0, 0, 0.35)
            }
        }

        contentItem: ColumnLayout {
            spacing: 0

            // Header
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 48
                color: Qt.rgba(1.0, 1.0, 1.0, 0.70)
                radius: 20

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 16
                    color: Qt.rgba(1.0, 1.0, 1.0, 0.70)
                }
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Qt.rgba(0, 0, 0, 0.08)
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 16

                    Text {
                        text: "🛡️ Cảnh Báo Chất Lượng Phụ Đề (QA)"
                        color: Theme.textOnLightPod
                        font.pixelSize: 14
                        font.bold: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Item { Layout.fillWidth: true }

                    Rectangle {
                        width: 28
                        height: 28
                        radius: 14
                        color: closeArea.containsMouse ? Qt.rgba(0.94, 0.27, 0.27, 0.15) : "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: "✕"
                            color: closeArea.containsMouse ? "#EF4444" : Theme.textOnLightPodMuted
                            font.pixelSize: 13
                        }

                        MouseArea {
                            id: closeArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: qaConfirmDialog.reject()
                        }
                    }
                }
            }

            // Body
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 20
                spacing: 16

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: warningCol.implicitHeight + 20
                    color: Qt.rgba(0.94, 0.27, 0.27, 0.08)
                    radius: 12
                    border.color: Qt.rgba(0.94, 0.27, 0.27, 0.25)
                    border.width: 1

                    RowLayout {
                        id: warningCol
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 12

                        Text {
                            text: "⚠️"
                            font.pixelSize: 22
                            Layout.alignment: Qt.AlignVCenter
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text {
                                text: "Có " + qaConfirmDialog.errorCount + " dòng phụ đề vi phạm quy tắc (Lỗi đỏ)"
                                color: "#DC2626"
                                font.pixelSize: 13
                                font.bold: true
                            }
                            Text {
                                text: "Các câu vượt giới hạn độ dài hoặc tốc độ đọc quá nhanh có thể gây khó chịu cho người xem."
                                color: Theme.textOnLightPodMuted
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                Text {
                    text: "Bạn có chắc chắn muốn bỏ qua cảnh báo và tiếp tục xuất file SRT không?"
                    color: Theme.textOnLightPod
                    font.pixelSize: 13
                    font.bold: true
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                // Action buttons
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    spacing: 12

                    Item { Layout.fillWidth: true }

                    AppButton {
                        id: btnCancelExport
                        text: "Hủy bỏ"
                        isDarkGlass: true
                        onClicked: qaConfirmDialog.reject()
                    }

                    AppButton {
                        id: btnConfirmExport
                        text: "Tiếp tục xuất ➔"
                        isPrimary: true
                        onClicked: qaConfirmDialog.accept()
                    }
                }
            }
        }

        onAccepted: {
            if (targetFilePath !== "") {
                projectController.exportSrt(targetFilePath, true)
            }
        }
    }

    function handleCloseProject() {
        if (typeof batchController !== "undefined" && batchController.executionLocked) return
        if (typeof projectController !== "undefined" && projectController.hasProject) {
            if (projectController.isDirty) {
                pendingCloseAction = "CLOSE_PROJECT"
                dirtyCloseConfirmDialog.open()
            } else {
                projectController.closeProject()
            }
        }
    }

    Dialog {
        id: dirtyCloseConfirmDialog
        objectName: "dirtyCloseConfirmDialog"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 440
        padding: 0
        closePolicy: Dialog.CloseOnEscape
        onClosed: {
            if (pendingCloseAction !== "EXIT_APP_SAVING" && pendingCloseAction !== "CLOSE_PROJECT_SAVING") {
                pendingCloseAction = ""
            }
        }

        background: Rectangle {
            color: Qt.rgba(0.97, 0.96, 0.99, 0.96)
            radius: 20
            border.color: Theme.glassBorderSpecularUpper
            border.width: 1.5

            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowBlur: 0.8
                shadowColor: Qt.rgba(0, 0, 0, 0.35)
            }
        }

        contentItem: ColumnLayout {
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 48
                color: Qt.rgba(1.0, 1.0, 1.0, 0.70)
                radius: 20

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 16
                    color: Qt.rgba(1.0, 1.0, 1.0, 0.70)
                }
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Qt.rgba(0, 0, 0, 0.08)
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 16

                    Text {
                        text: "💾 Lưu Thay Đổi Trước Khi Đóng?"
                        color: Theme.textOnLightPod
                        font.pixelSize: 14
                        font.bold: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Item { Layout.fillWidth: true }

                    Rectangle {
                        width: 28
                        height: 28
                        radius: 14
                        color: closeDirtyArea.containsMouse ? Qt.rgba(0.94, 0.27, 0.27, 0.15) : "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: "✕"
                            color: closeDirtyArea.containsMouse ? "#EF4444" : Theme.textOnLightPodMuted
                            font.pixelSize: 13
                        }

                        MouseArea {
                            id: closeDirtyArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                pendingCloseAction = ""
                                dirtyCloseConfirmDialog.close()
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 20
                spacing: 16

                Text {
                    text: "Dự án hiện tại có các thay đổi chưa được lưu. Nếu đóng bây giờ, toàn bộ bản dịch và chỉnh sửa chưa lưu sẽ bị mất."
                    color: Theme.textOnLightPodMuted
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    spacing: 10

                    AppButton {
                        text: "Hủy"
                        isDarkGlass: true
                        onClicked: {
                            pendingCloseAction = ""
                            dirtyCloseConfirmDialog.close()
                        }
                    }

                    Item { Layout.fillWidth: true }

                    AppButton {
                        text: "Đóng không lưu"
                        isDarkGlass: true
                        onClicked: {
                            var action = pendingCloseAction
                            dirtyCloseConfirmDialog.close()
                            pendingCloseAction = ""
                            if (action === "EXIT_APP") {
                                forceClose = true
                                Qt.quit()
                                mainWindow.close()
                            } else {
                                projectController.closeProject()
                            }
                        }
                    }

                    AppButton {
                        text: "Lưu dự án"
                        isPrimary: true
                        onClicked: {
                            var action = pendingCloseAction
                            dirtyCloseConfirmDialog.close()
                            if (action === "EXIT_APP") {
                                pendingCloseAction = "EXIT_APP_SAVING"
                            } else {
                                pendingCloseAction = "CLOSE_PROJECT_SAVING"
                            }
                            saveProjectDialog.open()
                        }
                    }
                }
            }
        }
    }

    ModelManagerDialog {
        id: modelManagerDialog
    }

    HotkeysCheatsheetDialog {
        id: hotkeysDialog
    }

    Connections {
        target: typeof modelController !== "undefined" ? modelController : null
        function onNotify(title, msg) { appToast.show(title, msg) }
    }
    // ==========================================
    // S2-T16: GLOBAL KEYBOARD SHORTCUTS
    // ==========================================
    Shortcut {
        objectName: "shortcutOpenSrt"
        sequence: "Ctrl+O"
        enabled: !batchController.executionLocked
        onActivated: {
            if (!batchController.executionLocked) importSrtDialog.open()
        }
    }

    Shortcut {
        objectName: "shortcutOpenProject"
        sequence: "Ctrl+Shift+O"
        enabled: !batchController.executionLocked
        onActivated: {
            if (!batchController.executionLocked) loadProjectDialog.open()
        }
    }

    Shortcut {
        objectName: "shortcutCloseProject"
        sequence: "Ctrl+W"
        enabled: appHeader.hasProject && !batchController.executionLocked
        onActivated: handleCloseProject()
    }

    Shortcut {
        sequence: "Ctrl+S"
        onActivated: {
            if (typeof projectController !== "undefined" && projectController.isBatchMode && projectController.originalSourcePath !== "") {
                projectController.quickSyncToOriginal()
            } else {
                saveProjectDialog.open()
            }
        }
    }

    Shortcut {
        sequence: "Ctrl+Shift+S"
        onActivated: {
            if (projectController.validateBeforeExport()) {
                exportSrtDialog.open()
            }
        }
    }

    Shortcut {
        objectName: "shortcutHotkeys"
        sequence: "F1"
        onActivated: {
            if (hotkeysDialog.visible) hotkeysDialog.close()
            else hotkeysDialog.open()
        }
    }

    DropArea {
        id: workspaceDropArea
        anchors.fill: parent
        enabled: subListView.count > 0 && !batchController.executionLocked

        onEntered: (drag) => {
            if (!drag.hasUrls) {
                drag.accepted = false
                return
            }
            var hasValid = false
            for (var i = 0; i < drag.urls.length; i++) {
                var url = drag.urls[i].toString().toLowerCase()
                if (url.endsWith(".srt")) {
                    hasValid = true
                    break
                }
            }
            drag.accepted = hasValid
        }

        onDropped: (drop) => {
            if (drop.hasUrls && drop.urls.length > 0) {
                for (var i = 0; i < drop.urls.length; i++) {
                    var urlStr = drop.urls[i].toString()
                    if (urlStr.toLowerCase().endsWith(".srt")) {
                        if (typeof projectController !== "undefined") {
                            projectController.appendNextBatch(urlStr)
                        }
                        break
                    }
                }
            }
        }
    }

    FramelessResizeOverlay {
        anchors.fill: parent
    }

    Shortcut {
        sequence: "Ctrl+Alt+R"
        context: Qt.ApplicationShortcut
        onActivated: {
            mainWindow.responsiveTestToolsEnabled = !mainWindow.responsiveTestToolsEnabled
            responsiveTestToolbar.dismissed = false
        }
    }

    ResponsiveTestToolbar {
        id: responsiveTestToolbar
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: Theme.spaceMedium
        anchors.bottomMargin: Theme.spaceMedium
        toolVisible: mainWindow.responsiveTestToolsEnabled
        onDismissRequested: mainWindow.responsiveTestToolsEnabled = false
    }
}
