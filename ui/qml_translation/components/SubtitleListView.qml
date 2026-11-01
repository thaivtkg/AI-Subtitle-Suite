import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import QtQuick.Effects
import "../theme"

ColumnLayout {
    id: root
    objectName: "subtitleListView"
    spacing: 0

    property alias model: subListView.model
    property alias currentIndex: subListView.currentIndex
    property alias count: subListView.count
    property bool isProxyModel: subListView.model && typeof subListView.model.getRawIndex === "function"
    property int currentRawIndex: {
        if (currentIndex < 0 || currentIndex >= count) return -1
        if (isProxyModel) return subListView.model.getRawIndex(currentIndex)
        return currentIndex
    }
    property string currentFilter: "ALL" // "ALL", "PENDING", "TRANSLATING", "TRANSLATED", "EDITED", "ERROR", "ACCEPTED"
    property string searchQuery: ""
    property bool showAdvancedFilters: false
    property int clientFilteredCount: subListView.count
    property int filteredCount: isProxyModel ? (subListView.model ? subListView.model.filteredCount : 0) : clientFilteredCount
    property var selectedIndices: []
    signal selectionChanged(var indices)
    property bool isDraggingLens: false
    property int dragHoverIndex: -1

    property int activeTranslationTarget: {
        if (typeof batchController !== "undefined" && batchController && batchController.activeIndex >= 0) {
            return batchController.activeIndex;
        }
        if (typeof translationController !== "undefined" && translationController && translationController.activeTranslationIndex >= 0) {
            return translationController.activeTranslationIndex;
        }
        return -1;
    }

    function scrollToActiveItem() {
        var target = root.activeTranslationTarget >= 0 ? root.activeTranslationTarget : root.currentRawIndex;
        if (target < 0) return;
        var vIdx = -1;
        if (root.isProxyModel && subListView.model) {
            if (typeof subListView.model.ensureRawIndexVisible === "function") {
                vIdx = subListView.model.ensureRawIndexVisible(target);
            } else if (typeof subListView.model.getViewIndex === "function") {
                vIdx = subListView.model.getViewIndex(target);
            }
        } else {
            vIdx = target;
        }
        if (vIdx >= 0 && vIdx < subListView.count) {
            subListView.currentIndex = vIdx;
            subListView.positionViewAtIndex(vIdx, ListView.Center);
            subListView.forceActiveFocus();
            var rIdx = root.isProxyModel ? subListView.model.getRawIndex(vIdx) : vIdx;
            root.selectedIndices = [rIdx];
            root.selectionChanged(root.selectedIndices);
        }
    }

    function selectNextRowAndFocus() {
        if (subListView.count <= 0) return false;
        var nextIdx = subListView.currentIndex + 1;
        if (nextIdx < subListView.count) {
            subListView.currentIndex = nextIdx;
            subListView.positionViewAtIndex(nextIdx, ListView.Contain);
            return true;
        }
        return false;
    }

    function selectPrevRowAndFocus() {
        if (subListView.count <= 0) return false;
        var prevIdx = subListView.currentIndex - 1;
        if (prevIdx >= 0) {
            subListView.currentIndex = prevIdx;
            subListView.positionViewAtIndex(prevIdx, ListView.Contain);
            return true;
        }
        return false;
    }

    function selectRowAndScroll(rawIdx) {
        if (rawIdx < 0 || subListView.count <= 0) return;
        var vIdx = -1;
        if (root.isProxyModel && subListView.model) {
            if (typeof subListView.model.ensureRawIndexVisible === "function") {
                vIdx = subListView.model.ensureRawIndexVisible(rawIdx);
            } else if (typeof subListView.model.getViewIndex === "function") {
                vIdx = subListView.model.getViewIndex(rawIdx);
            }
        } else {
            vIdx = rawIdx;
        }
        if (vIdx >= 0 && vIdx < subListView.count) {
            subListView.currentIndex = vIdx;
            subListView.positionViewAtIndex(vIdx, ListView.Center);
            subListView.forceActiveFocus();
            var rIdx = (root.isProxyModel && subListView.model && typeof subListView.model.getRawIndex === "function")
                       ? subListView.model.getRawIndex(vIdx) : vIdx;
            root.selectedIndices = [rIdx];
            root.selectionChanged(root.selectedIndices);
        }
    }

    property int currentChunkSize: 0 // 0 = Tất cả câu
    property int currentPage: 1
    property int selectedChunkStart: -1
    property int selectedChunkEnd: -1

    property bool isTimeFilterActive: false
    property int filterStartMin: 0
    property int filterEndMin: 9999

    function updatePagination() {
        if (root.isProxyModel) return
        if (currentChunkSize <= 0 || subListView.count === 0) {
            selectedChunkStart = -1
            selectedChunkEnd = -1
        } else {
            var maxPage = Math.max(1, Math.ceil(subListView.count / currentChunkSize))
            if (currentPage > maxPage) currentPage = maxPage
            if (currentPage < 1) currentPage = 1
            selectedChunkStart = (currentPage - 1) * currentChunkSize
            selectedChunkEnd = Math.min(currentPage * currentChunkSize - 1, subListView.count - 1)
        }
        updateFiltersAndScroll()
    }

    function applyTimeFilter() {
        if (root.isProxyModel) {
            subListView.model.setTimeFilter(root.isTimeFilterActive, root.filterStartMin, root.filterEndMin)
        } else {
            root.updateFiltersAndScroll()
        }
        subListView.positionViewAtIndex(0, ListView.Beginning)
        subListView.contentY = 0
    }

    function updateFiltersAndScroll() {
        updateFilteredCount()
        subListView.positionViewAtIndex(0, ListView.Beginning)
        subListView.contentY = 0
    }

    function updateFilteredCount() {
        if (root.isProxyModel) return
        if (!subListView.model) {
            clientFilteredCount = 0
            return
        }
        if (!root.isTimeFilterActive && root.searchQuery === "" && root.currentFilter === "ALL" && root.currentChunkSize <= 0) {
            clientFilteredCount = subListView.count
            return
        }
        var all = (typeof subtitleModel !== "undefined" && subtitleModel) ? subtitleModel.get_all_data() : []
        if (!all || all.length === 0) {
            clientFilteredCount = 0
            return
        }
        var count = 0
        var sq = root.searchQuery
        var cf = root.currentFilter
        var tf = root.isTimeFilterActive
        var sMin = root.filterStartMin
        var eMin = root.filterEndMin
        var cSize = root.currentChunkSize
        var cStart = root.selectedChunkStart
        var cEnd = root.selectedChunkEnd

        for (var i = 0; i < all.length; i++) {
            var item = all[i]
            if (sq !== "") {
                var orig = (item.original || "").toLowerCase()
                var trans = (item.translation || "").toLowerCase()
                if (orig.indexOf(sq) === -1 && trans.indexOf(sq) === -1) continue
            }
            if (cf !== "ALL") {
                var st = (item.status || "PENDING").toUpperCase()
                if (cf === "PENDING" && st !== "PENDING" && st !== "") continue
                else if (cf !== "PENDING" && st !== cf) continue
            }
            if (tf) {
                var tStr = item.start_time || ""
                var subM = (parseInt(tStr.substring(0, 2), 10) || 0) * 60 + (parseInt(tStr.substring(3, 5), 10) || 0)
                if (subM < sMin || subM > eMin) continue
            }
            if (!tf && cSize > 0 && cStart >= 0) {
                if (i < cStart || i > cEnd) continue
            }
            count++
        }
        clientFilteredCount = count
    }

    // Header controls
    Item {
        id: headerControlsWrapper
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        implicitHeight: headerControlsColumn.implicitHeight + (Theme.spaceSmall * 2)
        Layout.preferredHeight: implicitHeight

        ColumnLayout {
            id: headerControlsColumn
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: Theme.spaceSmall
            spacing: Theme.spaceXs

            // TITLE ROW: DANH SÁCH CÂU + HOLD & DRAG BADGE (MATCHING DESIGN)
            RowLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 8

                Text {
                    text: "📋 DANH SÁCH CÂU"
                    font.pixelSize: 12
                    font.bold: true
                    color: "#FFFFFF"
                    Layout.alignment: Qt.AlignVCenter
                }

                Item {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                }

                // Total count pill
                Rectangle {
                    implicitWidth: countBadgeText.implicitWidth + 14
                    implicitHeight: 20
                    radius: 10
                    color: Theme.badgeEmeraldBg
                    border.color: Theme.badgeEmeraldText
                    border.width: 1
                    Layout.alignment: Qt.AlignVCenter
                    Text {
                        id: countBadgeText
                        anchors.centerIn: parent
                        text: (subListView.count > 0 ? subListView.count : (typeof subtitleModel !== "undefined" && subtitleModel ? subtitleModel.rowCount() : 0)) + " câu"
                        color: Theme.badgeEmeraldText
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                // Filter expand toggle icon button
                Rectangle {
                    objectName: "btnToggleFilters"
                    implicitWidth: 26
                    implicitHeight: 20
                    radius: 10
                    color: root.showAdvancedFilters ? Theme.accentSapphire : Qt.rgba(1.0, 1.0, 1.0, 0.22)
                    border.color: Qt.rgba(1.0, 1.0, 1.0, 0.5)
                    border.width: 1
                    Layout.alignment: Qt.AlignVCenter
                    Text {
                        anchors.centerIn: parent
                        text: "⚙"
                        font.pixelSize: 11
                        color: "#FFFFFF"
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.showAdvancedFilters = !root.showAdvancedFilters
                    }
                }

                // Nút Nạp toàn bộ phụ đề từ Video Timeline
                Rectangle {
                    id: btnImportTimeline
                    objectName: "btnImportTimeline"
                    implicitWidth: 26
                    implicitHeight: 20
                    radius: 10
                    enabled: (typeof batchController === "undefined" || !batchController.executionLocked) &&
                             (typeof translationController === "undefined" || translationController.status !== "TRANSLATING")
                    opacity: enabled ? 1.0 : 0.4
                    color: importTimelineMouse.containsMouse ? Qt.rgba(0.0, 0.5, 1.0, 0.35) : Qt.rgba(1.0, 1.0, 1.0, 0.22)
                    border.color: importTimelineMouse.containsMouse ? Theme.accentSapphire : Qt.rgba(1.0, 1.0, 1.0, 0.5)
                    border.width: 1
                    Layout.alignment: Qt.AlignVCenter
                    Text {
                        anchors.centerIn: parent
                        text: "📥"
                        font.pixelSize: 11
                        font.bold: true
                        color: "#FFFFFF"
                    }
                    ToolTip.visible: importTimelineMouse.containsMouse
                    ToolTip.text: "Nạp toàn bộ phụ đề từ Video Timeline"
                    ToolTip.delay: 300
                    MouseArea {
                        id: importTimelineMouse
                        anchors.fill: parent
                        enabled: btnImportTimeline.enabled
                        hoverEnabled: enabled
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (typeof translationStudioPage !== "undefined" && translationStudioPage !== null) {
                                translationStudioPage.import_all_from_timeline()
                            }
                        }
                    }
                }

                // NÚT ĐÓNG DỰ ÁN & VỀ MÀN HÌNH KHỞI ĐỘNG (THEO PHƯƠNG ÁN 1)
                Rectangle {
                    id: btnCloseSub
                    objectName: "btnCloseSub"
                    implicitWidth: 26
                    implicitHeight: 20
                    radius: 10
                    enabled: (typeof batchController === "undefined" || !batchController.executionLocked) &&
                             (typeof translationController === "undefined" || translationController.status !== "TRANSLATING")
                    opacity: enabled ? 1.0 : 0.4
                    color: closeSubMouse.containsMouse ? Qt.rgba(1.0, 0.2, 0.2, 0.35) : Qt.rgba(1.0, 1.0, 1.0, 0.22)
                    border.color: closeSubMouse.containsMouse ? "#EF4444" : Qt.rgba(1.0, 1.0, 1.0, 0.5)
                    border.width: 1
                    Layout.alignment: Qt.AlignVCenter
                    Text {
                        anchors.centerIn: parent
                        text: "⌂"
                        font.pixelSize: 11
                        font.bold: true
                        color: "#FFFFFF"
                    }
                    ToolTip.visible: closeSubMouse.containsMouse
                    ToolTip.text: "Đóng file phụ đề và quay về màn hình khởi động — Ctrl + W"
                    ToolTip.delay: 300
                    MouseArea {
                        id: closeSubMouse
                        anchors.fill: parent
                        enabled: btnCloseSub.enabled
                        hoverEnabled: enabled
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (typeof mainWindow !== "undefined" && typeof mainWindow.handleCloseProject === "function") {
                                mainWindow.handleCloseProject()
                            } else if (typeof projectController !== "undefined") {
                                projectController.closeProject()
                            }
                        }
                    }
                }
            }

            // Search Row - 100% FULL WIDTH SPACIOUS FROSTED GLASS TUBE
            RowLayout {
                id: searchLayout
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: Theme.spaceSmall

                TextField {
                    objectName: "searchInput"
                    id: searchInput
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 32
                    verticalAlignment: TextInput.AlignVCenter
                    leftPadding: 32
                    rightPadding: 12
                    topPadding: 0
                    bottomPadding: 0
                    placeholderText: "Tìm kiếm nhanh..."
                    placeholderTextColor: Theme.textMuted
                    font.pixelSize: 12
                    color: Theme.textPrimary
                    selectByMouse: true
                    selectionColor: Theme.accentSapphire
                    selectedTextColor: "#FFFFFF"

                    background: Rectangle {
                        color: Theme.glassPodLuminous
                        radius: 16
                        border.color: searchInput.activeFocus ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                        border.width: searchInput.activeFocus ? 1.5 : 1.0

                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            text: "🔍"
                            font.pixelSize: 12
                            opacity: 0.80
                        }
                    }
                    onTextChanged: {
                        root.searchQuery = text.toLowerCase()
                        if (root.isProxyModel) {
                            subListView.model.setSearchQuery(text)
                        } else {
                            root.updateFiltersAndScroll()
                        }
                        subListView.positionViewAtIndex(0, ListView.Beginning)
                        subListView.contentY = 0
                    }
                    Keys.onEscapePressed: function(event) {
                        subListView.forceActiveFocus()
                        event.accepted = true
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Escape) {
                            subListView.forceActiveFocus()
                            event.accepted = true
                        }
                    }
                }
            }

            // ADVANCED FILTERS (COLLAPSED BY DEFAULT TO KEEP MINIMAL CLEAN UI)
            ColumnLayout {
                id: advancedFiltersContainer
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                visible: root.showAdvancedFilters
                spacing: 6

                // Filter Combo
                ComboBox {
                    objectName: "statusFilterCombo"
                    id: filterCombo
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 32
                    font.pixelSize: 12
                    model: ["Tất cả", "Chờ dịch", "Đang dịch", "Đã dịch", "Đã sửa", "Lỗi", "Đã duyệt"]
                    onCurrentIndexChanged: {
                        const filters = ["ALL", "PENDING", "TRANSLATING", "TRANSLATED", "EDITED", "ERROR", "ACCEPTED"]
                        root.currentFilter = filters[currentIndex]
                        if (root.isProxyModel) {
                            subListView.model.setStatusFilter(filters[currentIndex])
                        } else {
                            root.updateFiltersAndScroll()
                        }
                        subListView.positionViewAtIndex(0, ListView.Beginning)
                        subListView.contentY = 0
                    }

                    contentItem: Text {
                        leftPadding: Theme.spaceSmall
                        rightPadding: filterCombo.indicator.width + Theme.spaceSmall
                        text: filterCombo.currentText
                        font.pixelSize: 12
                        font.bold: true
                        color: Theme.textPrimary
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }

                    indicator: Text {
                        x: filterCombo.width - width - Theme.spaceSmall
                        anchors.verticalCenter: parent.verticalCenter
                        text: statusPopup.visible ? "▴" : "▾"
                        color: Theme.accentSapphire
                        font.pixelSize: 12
                        font.bold: true
                    }

                    background: Rectangle {
                        implicitHeight: 32
                        color: Theme.glassPodLuminous
                        radius: 12
                        border.color: filterCombo.activeFocus || statusPopup.visible ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                        border.width: 1
                    }
                    
                    delegate: ItemDelegate {
                        width: filterCombo.width - 12
                        implicitHeight: 34
                        contentItem: RowLayout {
                            spacing: 8
                            Text {
                                text: modelData
                                color: Theme.textPrimary
                                font.pixelSize: 12
                                font.bold: highlighted || filterCombo.currentIndex === index
                                verticalAlignment: Text.AlignVCenter
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            Text {
                                text: "✓"
                                color: Theme.accentSapphire
                                font.pixelSize: 12
                                font.bold: true
                                visible: filterCombo.currentIndex === index
                                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                            }
                        }
                        background: Rectangle {
                            radius: 8
                            color: filterCombo.currentIndex === index ? Qt.rgba(0.0, 0.4, 1.0, 0.12) :
                                   highlighted ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                            border.color: filterCombo.currentIndex === index ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                            border.width: 1
                        }
                    }

                    popup: Popup {
                        id: statusPopup
                        y: filterCombo.height + 4
                        width: filterCombo.width
                        padding: 6
                        implicitHeight: Math.min(contentItem.implicitHeight + padding * 2, 260)

                        contentItem: ListView {
                            clip: true
                            implicitHeight: contentHeight
                            model: statusPopup.visible ? filterCombo.delegateModel : null
                            currentIndex: filterCombo.highlightedIndex
                            ScrollIndicator.vertical: ScrollIndicator { }
                        }

                        background: Rectangle {
                            color: Qt.rgba(0.10, 0.14, 0.22, 0.96)
                            border.color: Theme.glassBorderSpecularUpper
                            border.width: 1.5
                            radius: 14
                        }
                    }
                } // filterCombo

            // Chunk Filter Combo
            ComboBox {
                objectName: "chunkFilterCombo"
                id: chunkFilterCombo
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: 32
                font.pixelSize: 12
                model: [
                    "Tất cả câu",
                    "Hiển thị 5 câu / trang",
                    "Hiển thị 10 câu / trang",
                    "Hiển thị 20 câu / trang",
                    "Hiển thị 50 câu / trang"
                ]
                onCurrentIndexChanged: {
                    var sizes = [0, 5, 10, 20, 50]
                    root.currentChunkSize = sizes[currentIndex]
                    root.currentPage = 1
                    if (root.isProxyModel) {
                        subListView.model.setPageSize(sizes[currentIndex])
                    } else {
                        root.updatePagination()
                    }
                    subListView.positionViewAtIndex(0, ListView.Beginning)
                    subListView.contentY = 0
                }

                contentItem: Text {
                    leftPadding: Theme.spaceSmall
                    rightPadding: chunkFilterCombo.indicator.width + Theme.spaceSmall
                    text: chunkFilterCombo.currentText
                    font.pixelSize: 12
                    font.bold: true
                    color: Theme.textPrimary
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                indicator: Text {
                    x: chunkFilterCombo.width - width - Theme.spaceSmall
                    anchors.verticalCenter: parent.verticalCenter
                    text: chunkPopup.visible ? "▴" : "▾"
                    color: Theme.accentSapphire
                    font.pixelSize: 12
                    font.bold: true
                }

                background: Rectangle {
                    implicitHeight: 32
                    color: Theme.glassPodLuminous
                    radius: 12
                    border.color: chunkFilterCombo.activeFocus || chunkPopup.visible ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                    border.width: 1
                }

                delegate: ItemDelegate {
                    width: chunkFilterCombo.width - 12
                    implicitHeight: 34
                    contentItem: RowLayout {
                        spacing: 8
                        Text {
                            text: modelData
                            color: Theme.textPrimary
                            font.pixelSize: 12
                            font.bold: highlighted || chunkFilterCombo.currentIndex === index
                            verticalAlignment: Text.AlignVCenter
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: "✓"
                            color: Theme.accentSapphire
                            font.pixelSize: 12
                            font.bold: true
                            visible: chunkFilterCombo.currentIndex === index
                            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        }
                    }
                    background: Rectangle {
                        radius: 8
                        color: chunkFilterCombo.currentIndex === index ? Qt.rgba(0.0, 0.4, 1.0, 0.12) :
                               highlighted ? Qt.rgba(0.0, 0.4, 1.0, 0.06) : "transparent"
                        border.color: chunkFilterCombo.currentIndex === index ? Qt.rgba(0.0, 0.4, 1.0, 0.35) : "transparent"
                        border.width: 1
                    }
                }

                popup: Popup {
                    id: chunkPopup
                    y: chunkFilterCombo.height + 4
                    width: chunkFilterCombo.width
                    padding: 6
                    implicitHeight: Math.min(contentItem.implicitHeight + padding * 2, 260)

                    contentItem: ListView {
                        clip: true
                        implicitHeight: contentHeight
                        model: chunkPopup.visible ? chunkFilterCombo.delegateModel : null
                        currentIndex: chunkFilterCombo.highlightedIndex
                        ScrollIndicator.vertical: ScrollIndicator { }
                    }

                    background: Rectangle {
                        color: Qt.rgba(0.10, 0.14, 0.22, 0.96)
                        border.color: Theme.glassBorderSpecularUpper
                        border.width: 1.5
                        radius: 14
                    }
                }
            }


            // Time Filter Row
            RowLayout {
                id: timeFilterLayout
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: Theme.spaceXs

                CheckBox {
                    objectName: "timeFilterCheck"
                    id: timeFilterCheck
                    text: "Lọc phút:"
                    Layout.minimumWidth: 0
                    ToolTip.text: "Lọc hiển thị theo phút bắt đầu. Trình dịch AI sẽ chạy tuần tự từ câu đang chọn."
                    ToolTip.visible: hovered
                    onCheckedChanged: {
                        root.isTimeFilterActive = checked
                        root.applyTimeFilter()
                    }
                    indicator: Rectangle {
                        implicitWidth: 16
                        implicitHeight: 16
                        x: timeFilterCheck.leftPadding
                        anchors.verticalCenter: parent.verticalCenter
                        radius: 5
                        color: timeFilterCheck.checked ? Theme.accentSapphire : Theme.glassPodLuminous
                        border.color: timeFilterCheck.checked ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "✓"
                            color: "#FFFFFF"
                            font.pixelSize: 10
                            font.bold: true
                            visible: timeFilterCheck.checked
                        }
                    }
                    contentItem: Text {
                        text: timeFilterCheck.text
                        font.pixelSize: 11
                        font.bold: true
                        color: "#FFFFFF"
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: timeFilterCheck.indicator.width + Theme.spaceXs
                    }
                }

                TextField {
                    objectName: "startMinInput"
                    id: startMinInput
                    placeholderText: "Từ"
                    placeholderTextColor: Theme.textMuted
                    Layout.preferredWidth: 46
                    Layout.minimumWidth: 35
                    Layout.preferredHeight: 28
                    font.pixelSize: 12
                    font.bold: true
                    color: Theme.textPrimary
                    enabled: timeFilterCheck.checked
                    validator: IntValidator { bottom: 0; top: 9999 }
                    inputMethodHints: Qt.ImhDigitsOnly
                    onTextChanged: {
                        root.filterStartMin = isNaN(parseInt(text, 10)) ? 0 : parseInt(text, 10)
                        root.applyTimeFilter()
                    }
                    background: Rectangle {
                        color: Theme.glassPodLuminous
                        radius: 8
                        border.color: startMinInput.activeFocus ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                        border.width: 1
                    }
                }

                Text {
                    text: "➔"
                    color: "#FFFFFF"
                    font.pixelSize: 11
                    font.bold: true
                    Layout.alignment: Qt.AlignVCenter
                }

                TextField {
                    objectName: "endMinInput"
                    id: endMinInput
                    placeholderText: "Đến"
                    placeholderTextColor: Theme.textMuted
                    Layout.preferredWidth: 46
                    Layout.minimumWidth: 35
                    Layout.preferredHeight: 28
                    font.pixelSize: 12
                    font.bold: true
                    color: Theme.textPrimary
                    enabled: timeFilterCheck.checked
                    validator: IntValidator { bottom: 0; top: 9999 }
                    inputMethodHints: Qt.ImhDigitsOnly
                    onTextChanged: {
                        root.filterEndMin = isNaN(parseInt(text, 10)) ? 9999 : parseInt(text, 10)
                        root.applyTimeFilter()
                    }
                    background: Rectangle {
                        color: Theme.glassPodLuminous
                        radius: 8
                        border.color: endMinInput.activeFocus ? Theme.accentSapphire : Theme.glassBorderSpecularUpper
                        border.width: 1
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                }
            }
        } // advancedFiltersContainer
    } // headerControlsColumn
    } // headerControlsWrapper

    // List View Container (supports FAB Floating Action Button above list without colliding with paginationBar)
    Item {
        id: listViewContainer
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumWidth: 0
        clip: true

        MouseArea {
            anchors.fill: parent
            z: 0
            onClicked: subListView.forceActiveFocus()
        }

        // PHYSICAL LIQUID DROPLET LENS (AC-01, AC-02)
        // Reparented to subListView.contentItem to share native coordinate system with list items
        Rectangle {
            id: subDropletLens
            objectName: "subDropletLens"
            parent: subListView.contentItem
            z: 1
            x: 10
            width: Math.max(0, subListView.width - 20)
            radius: 16

            property real targetY: subListView.currentItem ? subListView.currentItem.y + 4 : 0
            y: root.isDraggingLens ? y : targetY
            height: subListView.currentItem ? (subListView.currentItem.hasTranslation ? 74 : 54) : 54
            visible: subListView.count > 0 && subListView.currentIndex >= 0 && subListView.currentItem !== null

            property real fluidScaleX: 1.0
            property real fluidScaleY: 1.0
            property real fluidOriginY: height / 2

            Behavior on fluidScaleX { enabled: !subLensImpulse.running; NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }
            Behavior on fluidScaleY { enabled: !subLensImpulse.running; NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

            Connections {
                target: subListView
                function onCurrentIndexChanged() {
                    if (!root.isDraggingLens && subListView.currentIndex >= 0) {
                        subLensImpulse.restart()
                    }
                }
            }

            SequentialAnimation {
                id: subLensImpulse
                ParallelAnimation {
                    NumberAnimation { target: subDropletLens; property: "fluidScaleY"; to: 1.14; duration: 90; easing.type: Easing.OutQuad }
                    NumberAnimation { target: subDropletLens; property: "fluidScaleX"; to: 0.90; duration: 90; easing.type: Easing.OutQuad }
                }
                ParallelAnimation {
                    NumberAnimation { target: subDropletLens; property: "fluidScaleY"; to: 0.94; duration: 110; easing.type: Easing.InOutQuad }
                    NumberAnimation { target: subDropletLens; property: "fluidScaleX"; to: 1.03; duration: 110; easing.type: Easing.InOutQuad }
                }
                ParallelAnimation {
                    NumberAnimation { target: subDropletLens; property: "fluidScaleY"; to: 1.0; duration: 100; easing.type: Easing.OutBack }
                    NumberAnimation { target: subDropletLens; property: "fluidScaleX"; to: 1.0; duration: 100; easing.type: Easing.OutBack }
                }
            }

            transform: Scale {
                origin.x: subDropletLens.width / 2
                origin.y: subDropletLens.fluidOriginY
                xScale: subDropletLens.fluidScaleX
                yScale: subDropletLens.fluidScaleY
            }

            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#0066FF" } // Sapphire rực rỡ 92%
                GradientStop { position: 1.0; color: "#0284C7" } // Cyan phát quang 90%
            }

            border.color: Theme.glassBorderSpecularUpper
            border.width: 1.5

            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Qt.rgba(0.0, 0.38, 1.0, 0.45)
                shadowBlur: 0.55
                shadowVerticalOffset: 3
            }

            Behavior on y {
                enabled: !subListView.moving && !subListView.flicking && !root.isDraggingLens
                SpringAnimation {
                    spring: 3.4
                    damping: 0.28
                    epsilon: 0.05
                }
            }

            Behavior on height {
                SpringAnimation {
                    spring: 3.4
                    damping: 0.28
                    epsilon: 0.05
                }
            }
        }

        ListView {
            objectName: "subtitleList"
            id: subListView
            anchors.fill: parent
            anchors.bottomMargin: 8
            clip: true
            focus: true
            keyNavigationEnabled: true
            model: typeof filteredSubtitleModel !== "undefined" && filteredSubtitleModel ? filteredSubtitleModel : (typeof subtitleModel !== "undefined" ? subtitleModel : null)
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { active: true }

            Keys.onPressed: function(event) {
                if (count <= 0) return;
                if (event.key === Qt.Key_Home) {
                    currentIndex = 0;
                    positionViewAtIndex(0, ListView.Beginning);
                    var r0 = root.isProxyModel ? subListView.model.getRawIndex(0) : 0;
                    root.selectedIndices = [r0];
                    root.selectionChanged(root.selectedIndices);
                    event.accepted = true;
                } else if (event.key === Qt.Key_End) {
                    currentIndex = count - 1;
                    positionViewAtIndex(count - 1, ListView.End);
                    var rEnd = root.isProxyModel ? subListView.model.getRawIndex(count - 1) : count - 1;
                    root.selectedIndices = [rEnd];
                    root.selectionChanged(root.selectedIndices);
                    event.accepted = true;
                } else if (event.key === Qt.Key_PageDown) {
                    var nextIdx = Math.min(count - 1, (currentIndex >= 0 ? currentIndex : 0) + 10);
                    currentIndex = nextIdx;
                    positionViewAtIndex(nextIdx, ListView.Contain);
                    var rNext = root.isProxyModel ? subListView.model.getRawIndex(nextIdx) : nextIdx;
                    root.selectedIndices = [rNext];
                    root.selectionChanged(root.selectedIndices);
                    event.accepted = true;
                } else if (event.key === Qt.Key_PageUp) {
                    var prevIdx = Math.max(0, (currentIndex >= 0 ? currentIndex : 0) - 10);
                    currentIndex = prevIdx;
                    positionViewAtIndex(prevIdx, ListView.Contain);
                    var rPrev = root.isProxyModel ? subListView.model.getRawIndex(prevIdx) : prevIdx;
                    root.selectedIndices = [rPrev];
                    root.selectionChanged(root.selectedIndices);
                    event.accepted = true;
                }
            }

            Component.onCompleted: {
                if (count > 0) translationController.loadSubtitle(root.currentRawIndex >= 0 ? root.currentRawIndex : 0)
                root.updateFilteredCount()
            }
            onCountChanged: {
                if (count > 0 && currentIndex < 0) {
                    currentIndex = 0
                }
                if (count === 0) {
                    root.selectedIndices = []
                    root.selectionChanged([])
                    if (typeof translationController !== "undefined") {
                        translationController.loadSubtitle(-1)
                    }
                }
                if (!root.isProxyModel) {
                    root.updatePagination()
                }
            }
            onCurrentIndexChanged: {
                var raw = (root.isProxyModel && subListView.model && typeof subListView.model.getRawIndex === "function")
                          ? subListView.model.getRawIndex(currentIndex)
                          : currentIndex
                if (raw >= 0) {
                    translationController.loadSubtitle(raw)
                    if (!root.selectedIndices || root.selectedIndices.length <= 1) {
                        root.selectedIndices = [raw]
                        root.selectionChanged(root.selectedIndices)
                    }
                } else if (count === 0 && typeof translationController !== "undefined") {
                    translationController.loadSubtitle(-1)
                }
            }

        delegate: Rectangle {
            objectName: "subtitleRow_" + (typeof rawIndex !== "undefined" ? rawIndex : index)
            id: delegateItem
            width: subListView.width
            property int itemRawIndex: root.isProxyModel ? (typeof rawIndex !== "undefined" ? rawIndex : (subListView.model.getRawIndex ? subListView.model.getRawIndex(index) : index)) : index
            property string normalizedStatus: typeof status !== "undefined" && status ? status.toString().toUpperCase() : "PENDING"
            property bool matchSearch: root.isProxyModel ? true : (root.searchQuery === "" ||
                                       (typeof originalText !== "undefined" && originalText.toLowerCase().indexOf(root.searchQuery) !== -1) ||
                                       (typeof translationText !== "undefined" && translationText.toLowerCase().indexOf(root.searchQuery) !== -1))
            property bool matchFilter: root.isProxyModel ? true : (root.currentFilter === "ALL" ||
                                       (root.currentFilter === "PENDING" && (normalizedStatus === "PENDING" || normalizedStatus === "")) ||
                                       normalizedStatus === root.currentFilter)
            property int subStartMin: {
                if (!startTime || startTime.length < 5) return 0;
                return (parseInt(startTime.substring(0, 2), 10) || 0) * 60 + (parseInt(startTime.substring(3, 5), 10) || 0);
            }
            property bool matchTime: root.isProxyModel ? true : (!root.isTimeFilterActive ||
                                     (subStartMin >= root.filterStartMin && subStartMin <= root.filterEndMin))
            property bool matchChunk: root.isProxyModel ? true : (root.selectedChunkStart < 0 ||
                                      root.isTimeFilterActive ||
                                      (index >= root.selectedChunkStart && index <= root.selectedChunkEnd))
            property bool isSelected: (root.selectedIndices && root.selectedIndices.indexOf(itemRawIndex) !== -1) ||
                                      ((!root.selectedIndices || root.selectedIndices.length <= 1) && subListView.currentIndex === index)
            property int activePrimaryIndex: (root.isDraggingLens && root.dragHoverIndex >= 0) ? root.dragHoverIndex : subListView.currentIndex
            property bool isPrimarySelected: activePrimaryIndex === index
            property bool isSecondarySelected: isSelected && !isPrimarySelected
            property bool hasTranslation: typeof translationText !== "undefined" && String(translationText).trim().length > 0
            
            property string durationStr: {
                if (!startTime || !endTime) return ""
                function toSec(t) {
                    var p = t.replace(',', ':').split(':')
                    if (p.length < 4) return 0
                    return parseInt(p[0])*3600 + parseInt(p[1])*60 + parseInt(p[2]) + parseInt(p[3])/1000
                }
                var d = toSec(endTime) - toSec(startTime)
                return d > 0 ? d.toFixed(1) + "s" : ""
            }

            visible: root.isProxyModel ? true : (matchSearch && matchFilter && matchChunk && matchTime)
            height: visible ? (hasTranslation ? 82 : 62) : 0
            color: "transparent"
            z: 2

            MouseArea {
                id: mouseArea
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                anchors.topMargin: 3
                anchors.bottomMargin: 3
                hoverEnabled: true
                cursorShape: (delegateItem.isPrimarySelected && root.isDraggingLens) ? Qt.ClosedHandCursor : Qt.PointingHandCursor
                acceptedButtons: Qt.LeftButton
                z: 20

                property real startPressY: 0
                property real lastPressY: 0
                property real initialLensY: 0
                property bool dragCandidate: false
                property bool hasDragged: false

                onPressed: function(mouse) {
                    subListView.forceActiveFocus()
                    startPressY = mouse.y
                    lastPressY = mouse.y
                    hasDragged = false
                    root.dragHoverIndex = -1
                    dragCandidate = delegateItem.isPrimarySelected
                    initialLensY = subDropletLens.y
                    subDropletLens.fluidScaleX = 1.0
                    subDropletLens.fluidScaleY = 1.0
                }

                onPositionChanged: function(mouse) {
                    if (pressed && dragCandidate) {
                        var dy = mouse.y - startPressY
                        var deltaY = mouse.y - lastPressY
                        lastPressY = mouse.y

                        if (!root.isDraggingLens && Math.abs(dy) > 8) {
                            root.isDraggingLens = true
                            mouseArea.preventStealing = true
                        }
                        if (root.isDraggingLens) {
                            hasDragged = true
                            subDropletLens.y = initialLensY + dy

                            // Fluid Elongation: stretch on Y, squeeze on X, anchor to trailing edge
                            subDropletLens.fluidOriginY = deltaY >= 0 ? 0 : subDropletLens.height
                            subDropletLens.fluidScaleY = 1.0 + Math.min(Math.abs(deltaY) * 0.03, 0.28)
                            subDropletLens.fluidScaleX = Math.max(0.85, 1.0 - (subDropletLens.fluidScaleY - 1.0) * 0.4)

                            var hoverCenterY = subDropletLens.y + subDropletLens.height / 2
                            var hoverTarget = subListView.indexAt(subListView.width / 2, hoverCenterY)
                            if (hoverTarget !== -1) {
                                root.dragHoverIndex = hoverTarget
                            }
                        }
                    }
                }

                onReleased: function(mouse) {
                    subDropletLens.fluidScaleX = 1.0
                    subDropletLens.fluidScaleY = 1.0
                    subDropletLens.fluidOriginY = subDropletLens.height / 2

                    if (root.isDraggingLens) {
                        root.isDraggingLens = false
                        root.dragHoverIndex = -1
                        mouseArea.preventStealing = false
                        dragCandidate = false

                        var lensCenterY = subDropletLens.y + subDropletLens.height / 2
                        var target = subListView.indexAt(subListView.width / 2, lensCenterY)
                        if (target === -1) {
                            target = (lensCenterY < subListView.contentY) ? 0 : (subListView.count - 1)
                        }
                        var targetIndex = Math.max(0, Math.min(subListView.count - 1, target))

                        if (targetIndex !== subListView.currentIndex) {
                            subListView.currentIndex = targetIndex
                            subListView.positionViewAtIndex(targetIndex, ListView.Contain)
                            var rIdx = root.isProxyModel ? subListView.model.getRawIndex(targetIndex) : targetIndex
                            root.selectedIndices = [rIdx]
                            root.selectionChanged(root.selectedIndices)
                        }
                    } else {
                        root.dragHoverIndex = -1
                        dragCandidate = false
                    }
                }

                onClicked: function(mouse) {
                    subListView.forceActiveFocus()
                    if (hasDragged) {
                        hasDragged = false
                        return
                    }
                    var list = []
                    if (mouse.modifiers & Qt.ControlModifier) {
                        list = (root.selectedIndices && root.selectedIndices.length > 0) ? root.selectedIndices.slice() : (root.currentRawIndex >= 0 ? [root.currentRawIndex] : [])
                        var pos = list.indexOf(delegateItem.itemRawIndex)
                        if (pos !== -1) {
                            list.splice(pos, 1)
                        } else {
                            list.push(delegateItem.itemRawIndex)
                        }
                    } else if (mouse.modifiers & Qt.ShiftModifier) {
                        var start = (subListView.currentIndex >= 0) ? subListView.currentIndex : index
                        var minIdx = Math.min(start, index)
                        var maxIdx = Math.max(start, index)
                        for (var i = minIdx; i <= maxIdx; i++) {
                            var rIdx = root.isProxyModel ? subListView.model.getRawIndex(i) : i
                            list.push(rIdx)
                        }
                    } else {
                        list = [delegateItem.itemRawIndex]
                    }
                    root.selectedIndices = list
                    root.selectionChanged(list)
                    if (subListView.currentIndex === index && typeof translationController !== "undefined") {
                        var rIdx = root.isProxyModel ? subListView.model.getRawIndex(index) : index;
                        translationController.loadSubtitle(rIdx);
                    } else {
                        subListView.currentIndex = index;
                    }
                }
            }

            // FLOATING LIQUID GLASS POD
            Rectangle {
                id: cardPod
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                anchors.topMargin: 4
                anchors.bottomMargin: 4
                radius: 16
                clip: true

                // Đổ bóng 3D cho các thẻ không được chọn (Thẻ chọn chính dùng bóng từ subDropletLens)
                layer.enabled: !delegateItem.isPrimarySelected
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: delegateItem.isSecondarySelected ? Qt.rgba(0.0, 0.38, 1.0, 0.20) : Qt.rgba(0.08, 0.04, 0.20, 0.14)
                    shadowBlur: 0.35
                    shadowVerticalOffset: 2
                }

                // Nền thẻ: trong suốt khi được chọn chính (để subDropletLens hiển thị), xanh mờ 20% khi chọn phụ, kính mờ khi chưa chọn
                color: delegateItem.isPrimarySelected ? "transparent" :
                       delegateItem.isSecondarySelected ? Qt.rgba(0.0, 0.4, 1.0, 0.20) :
                       (mouseArea.containsMouse ? Theme.glassPodRaised : Theme.glassPodLuminous)

                border.color: delegateItem.isPrimarySelected ? "transparent" :
                              delegateItem.isSecondarySelected ? Qt.rgba(0.0, 0.4, 1.0, 0.40) :
                              Theme.glassBorderSpecularUpper
                border.width: 1

                scale: mouseArea.pressed ? 0.98 : (mouseArea.containsMouse ? 1.01 : 1.0)
                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                Behavior on color { ColorAnimation { duration: 150 } }
                Behavior on border.color { ColorAnimation { duration: 150 } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    spacing: 4

                    // ROW 1: Index + Timecode + Duration + Status Badge
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        
                        Text {
                            text: "#" + String(subIndex).padStart(3, '0') + " • " + startTime
                            color: delegateItem.isPrimarySelected ? "#FFFFFF" : Theme.accentSapphire
                            font.pixelSize: 11
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                            Behavior on color { ColorAnimation { duration: 150 } }
                        }

                        Text {
                            text: durationStr !== "" ? "(" + durationStr + ")" : ""
                            color: delegateItem.isPrimarySelected ? Qt.rgba(0.88, 0.95, 1.0, 0.75) : Theme.textOnLightPodMuted
                            font.pixelSize: 10
                            Layout.alignment: Qt.AlignVCenter
                            Behavior on color { ColorAnimation { duration: 150 } }
                        }
                        
                        Item {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                        }
                        
                        Text {
                            z: 2
                            visible: typeof qaSeverity !== "undefined" && qaSeverity !== ""
                            text: qaSeverity === "ERROR" ? "🛑" : "⚠️"
                            font.pixelSize: 11
                            Layout.alignment: Qt.AlignVCenter
                            ToolTip.visible: qaHoverArea.containsMouse
                            ToolTip.text: typeof qaTooltip !== "undefined" ? qaTooltip : ""
                            ToolTip.delay: 200
                            MouseArea {
                                id: qaHoverArea
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: subListView.currentIndex = index
                            }
                        }
                        
                        Rectangle {
                            implicitWidth: statusText.implicitWidth + 16
                            implicitHeight: 20
                            radius: 10
                            Layout.alignment: Qt.AlignVCenter
                            color: normalizedStatus === "ACCEPTED" ? Theme.badgeEmeraldBg :
                                   (normalizedStatus === "TRANSLATED" || normalizedStatus === "EDITED") ? Theme.badgeAmberBg :
                                   normalizedStatus === "ERROR" ? Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.15) :
                                   normalizedStatus === "TRANSLATING" ? Qt.rgba(0, 0.4, 1.0, 0.15) : Qt.rgba(0.58, 0.64, 0.72, 0.15)
                            border.color: normalizedStatus === "ACCEPTED" ? Theme.badgeEmeraldText :
                                          (normalizedStatus === "TRANSLATED" || normalizedStatus === "EDITED") ? Theme.badgeAmberText :
                                          normalizedStatus === "ERROR" ? Theme.danger :
                                          normalizedStatus === "TRANSLATING" ? Theme.accentSapphire : "#94A3B8"
                            border.width: 1
                            
                            Text {
                                id: statusText
                                anchors.centerIn: parent
                                leftPadding: 8
                                rightPadding: 8
                                text: normalizedStatus === "ACCEPTED" ? "✓ ĐÃ DUYỆT" : 
                                      (normalizedStatus === "TRANSLATED" || normalizedStatus === "EDITED") ? "⌛ CHỜ DUYỆT" : 
                                      normalizedStatus === "TRANSLATING" ? "⚡ ĐANG DỊCH" : 
                                      normalizedStatus === "ERROR" ? "🛑 LỖI" : "⏳ CHỜ DỊCH"
                                color: normalizedStatus === "ACCEPTED" ? Theme.badgeEmeraldText :
                                       (normalizedStatus === "TRANSLATED" || normalizedStatus === "EDITED") ? Theme.badgeAmberText :
                                       normalizedStatus === "ERROR" ? Theme.danger :
                                       normalizedStatus === "TRANSLATING" ? Theme.accentSapphire : "#94A3B8"
                                font.pixelSize: 10
                                font.bold: true
                            }
                        }
                    }

                    // ROW 2: Subtitle text (Original & Translation)
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            text: originalText
                            color: delegateItem.isPrimarySelected ? "#FFFFFF" : Theme.textOnLightPod
                            font.pixelSize: 12
                            font.bold: true
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            Behavior on color { ColorAnimation { duration: 150 } }
                        }

                        Text {
                            visible: hasTranslation
                            Layout.fillWidth: true
                            text: typeof translationText !== "undefined" ? translationText : ""
                            color: delegateItem.isPrimarySelected ? "#D1FAE5" : "#059669"
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            Behavior on color { ColorAnimation { duration: 150 } }
                        }
                    }
                }
            }
        }

    } // subListView

    // FLOATING ACTION PILL: "👇 Cuộn tới câu đang dịch" (AC-02)
    Rectangle {
        id: scrollToActivePill
        objectName: "btnScrollToActive"
        z: 50
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        anchors.horizontalCenter: parent.horizontalCenter
        implicitHeight: 30
        implicitWidth: pillRow.implicitWidth + 24
        radius: 15
        color: Qt.rgba(15/255, 23/255, 42/255, 0.88)
        border.color: Qt.rgba(1.0, 1.0, 1.0, 0.35)
        border.width: 1

        property bool shouldShow: {
            if (subListView.count <= 0) return false;
            var target = root.activeTranslationTarget;
            if (target >= 0) {
                var vIdx = root.isProxyModel && subListView.model && typeof subListView.model.getViewIndex === "function"
                           ? subListView.model.getViewIndex(target)
                           : target;
                if (vIdx < 0 || vIdx >= subListView.count) return true;
                var item = subListView.itemAtIndex(vIdx);
                if (!item) return true;
                var itemTop = item.y - subListView.contentY;
                var itemBottom = itemTop + item.height;
                return (itemBottom < 0 || itemTop > subListView.height);
            }
            if (subListView.currentIndex >= 0 && subListView.count > 10) {
                var curItem = subListView.itemAtIndex(subListView.currentIndex);
                if (!curItem) return true;
                var curTop = curItem.y - subListView.contentY;
                var curBottom = curTop + curItem.height;
                return (curBottom < 0 || curTop > subListView.height);
            }
            return false;
        }

        visible: shouldShow
        opacity: shouldShow ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        scale: pillMouseArea.pressed ? 0.94 : (pillMouseArea.containsMouse ? 1.05 : 1.0)
        Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutBack } }

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#60000000"
            shadowBlur: 0.6
            shadowVerticalOffset: 3
        }

        RowLayout {
            id: pillRow
            anchors.centerIn: parent
            spacing: 6

            Text {
                text: root.activeTranslationTarget >= 0 ? "⚡" : "👇"
                font.pixelSize: 11
            }

            Text {
                text: root.activeTranslationTarget >= 0
                      ? ("Cuộn tới câu đang dịch (#" + (root.activeTranslationTarget + 1) + ")")
                      : ("Cuộn tới câu đang chọn (#" + (root.currentRawIndex + 1) + ")")
                color: "#FFFFFF"
                font.pixelSize: 11
                font.bold: true
            }
        }

        MouseArea {
            id: pillMouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.scrollToActiveItem()
        }
    }
} // listViewContainer

    // Pagination bar
    Rectangle {
        objectName: "paginationBar"
        id: paginationBar
        Layout.fillWidth: true
        Layout.preferredHeight: 34
        visible: root.isProxyModel ? (subListView.model && subListView.model.pageSize > 0 && subListView.model.filteredCount > 0)
                                   : (root.currentChunkSize > 0 && subListView.count > 0 && !root.isTimeFilterActive)
        color: Qt.rgba(1.0, 1.0, 1.0, 0.16)
        border.color: Theme.glassBorderSubtle
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.spaceSmall
            anchors.rightMargin: Theme.spaceSmall
            spacing: Theme.spaceSmall

            AppButton {
                objectName: "btnPrevPage"
                text: "◀"
                implicitWidth: 32
                implicitHeight: 26
                enabled: root.isProxyModel ? (subListView.model && subListView.model.hasPrevPage) : (root.currentPage > 1)
                onClicked: {
                    if (root.isProxyModel) {
                        subListView.model.prevPage()
                    } else if (root.currentPage > 1) {
                        root.currentPage--
                        root.updatePagination()
                    }
                    subListView.positionViewAtIndex(0, ListView.Beginning)
                    subListView.contentY = 0
                }
            }

            Text {
                objectName: "paginationText"
                text: root.isProxyModel
                      ? (subListView.model ? ("Trang " + subListView.model.currentPage + " / " + subListView.model.totalPages) : "")
                      : ("Trang " + root.currentPage + " / " + Math.max(1, Math.ceil(subListView.count / (root.currentChunkSize > 0 ? root.currentChunkSize : 1))))
                color: "#FFFFFF"
                font.pixelSize: 12
                font.bold: true
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            AppButton {
                objectName: "btnNextPage"
                text: "▶"
                implicitWidth: 32
                implicitHeight: 26
                enabled: root.isProxyModel ? (subListView.model && subListView.model.hasNextPage) : (root.currentPage < Math.ceil(subListView.count / (root.currentChunkSize > 0 ? root.currentChunkSize : 1)))
                onClicked: {
                    if (root.isProxyModel) {
                        subListView.model.nextPage()
                    } else if (root.currentPage < Math.ceil(subListView.count / (root.currentChunkSize > 0 ? root.currentChunkSize : 1))) {
                        root.currentPage++
                        root.updatePagination()
                    }
                    subListView.positionViewAtIndex(0, ListView.Beginning)
                    subListView.contentY = 0
                }
            }
        }
    }

    // Footer stats
    Rectangle {
        visible: false
        Layout.fillWidth: true
        height: 24
        color: Qt.rgba(1.0, 1.0, 1.0, 0.12)
        border.color: Theme.glassBorderSubtle
        border.width: 1
        Text {
            anchors.centerIn: parent
            text: root.isProxyModel ? (subListView.model ? (subListView.model.filteredCount + " / " + subListView.model.totalCount + " câu") : "0 câu")
                                   : (root.filteredCount + " / " + subListView.count + " câu")
            color: Qt.rgba(1.0, 1.0, 1.0, 0.88)
            font.pixelSize: 11
        }
    }
}
