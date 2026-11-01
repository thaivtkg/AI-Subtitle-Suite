import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import "theme"
import "components"
import "dialogs"

Item {
    id: studioView
    anchors.fill: parent

    property var selectedSubtitleIndices: []
    property string globalStorySummary: ""

    // Nền Dark Obsidian chuẩn Studio
    Rectangle {
        anchors.fill: parent
        color: Theme.colorBackground
    }

    // Lớp ảnh nền Kính lỏng Cyber Mesh
    Image {
        id: bgLiquidMesh
        anchors.fill: parent
        source: "assets/liquid_mesh_bg.jpg"
        fillMode: Image.PreserveAspectCrop
        smooth: true
        asynchronous: false
        opacity: 0.12   // Giảm từ 0.65 xuống 0.12 để tôn nền đen sâu Obsidian #0B0F19
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 1. Thanh điều khiển Dịch Batch & Chọn Mô hình
        HeaderBatchControl {
            id: headerBatch
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            controller: typeof batchController !== "undefined" ? batchController : null
            customModelController: typeof modelController !== "undefined" ? modelController : null
            currentSubtitleIndex: subListView.currentRawIndex
            selectedIndices: studioView.selectedSubtitleIndices
            storySummary: studioView.globalStorySummary
            sourceLanguage: (typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : transWorkspace.getSourceLanguage()
            targetLanguage: "Vietnamese"
            showModelManager: true
            onModelManagerClicked: { if (typeof modelManagerDialog !== "undefined" && modelManagerDialog !== null) modelManagerDialog.open() }
        }

        // 2. Không gian làm việc Dịch thuật 3 cột (Danh sách - Editor - Context Inspector)
        SplitView {
            id: mainSplitView
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.spaceSmall
            orientation: Qt.Horizontal

            handle: Rectangle {
                implicitWidth: 1
                color: Qt.rgba(1, 1, 1, 0.20)
            }

            // CỘT 1: DANH SÁCH CÂU PHỤ ĐỀ
            Rectangle {
                id: subtitleIsland
                SplitView.preferredWidth: 320
                SplitView.minimumWidth: 260
                SplitView.maximumWidth: 450
                color: Theme.glassIslandSurface
                radius: Theme.radiusMedium
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    FindReplaceBar {
                        id: findReplaceBar
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
                        selectedIndices: studioView.selectedSubtitleIndices
                        onSelectionChanged: function(indices) {
                            studioView.selectedSubtitleIndices = indices
                        }
                    }
                }
            }

            // CỘT 2: KHÔNG GIAN LÀM VIỆC DỊCH THUẬT (EDITOR)
            Rectangle {
                id: workspaceIsland
                SplitView.fillWidth: true
                SplitView.minimumWidth: 400
                color: Theme.glassIslandSurface
                radius: Theme.radiusMedium
                clip: true

                TranslationWorkspace {
                    id: transWorkspace
                    anchors.fill: parent
                    anchors.margins: Theme.spaceSmall
                    hasSelection: subListView.currentRawIndex >= 0
                    totalCount: subListView.count
                    executionLocked: typeof batchController !== "undefined" && batchController !== null ? batchController.executionLocked : false

                    onTranslateRequested: (sourceLang) => {
                        if (typeof translationController !== "undefined" && translationController !== null) {
                            translationController.requestTranslation(
                                subListView.currentRawIndex,
                                (translationController.currentSourceLanguage && translationController.currentSourceLanguage !== "") ? translationController.currentSourceLanguage : sourceLang,
                                "Vietnamese",
                                studioView.globalStorySummary
                            )
                        }
                    }

                    onAcceptRequested: (text) => {
                        if (typeof translationController !== "undefined" && translationController !== null) {
                            let isSuccess = translationController.acceptTranslation(subListView.currentRawIndex, text)
                            if (isSuccess) {
                                subListView.selectNextRowAndFocus()
                            }
                        }
                    }

                    onAddGlossaryRequested: (src, tgt) => {
                        contextInspector.openAddTerm(src, tgt)
                    }

                    onHotkeysRequested: hotkeysDialog.open()
                }
            }

            // CỘT 3: CONTEXT INSPECTOR (BẢNG THUẬT NGỮ / TM / THỰC THỂ)
            Rectangle {
                id: contextIsland
                SplitView.preferredWidth: 320
                SplitView.minimumWidth: 280
                SplitView.maximumWidth: 450
                color: Theme.glassIslandSurface
                radius: Theme.radiusMedium
                clip: true

                ContextInspector {
                    id: contextInspector
                    anchors.fill: parent
                    anchors.margins: Theme.spaceSmall
                }
            }
        }
    }

    // 3. Hộp thoại Quản lý Mô hình GGUF (Modal)
    ModelManagerDialog {
        id: modelManagerDialog
        objectName: "modelManagerDialog"
    }

    // 4. Hộp thoại Bảng phím tắt
    HotkeysCheatsheetDialog {
        id: hotkeysDialog
    }

    // 5. Toast Thông báo
    Toast {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height - height - 30
    }

    Connections {
        target: typeof projectController !== "undefined" ? projectController : null
        function onLanguageLoaded(lang) { transWorkspace.setSourceLanguage(lang) }
    }

    // Kết nối thông báo từ Controller
    Connections {
        target: typeof modelController !== "undefined" ? modelController : null
        function onNotify(title, msg) { toast.show(title, msg) }
    }

    Connections {
        target: typeof translationController !== "undefined" ? translationController : null
        function onNotify(title, msg) { toast.show(title, msg) }
    }
}
