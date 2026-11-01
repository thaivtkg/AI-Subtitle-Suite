import QtQuick 2.15
import QtQuick.Controls.Basic
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../theme"

Item {
    id: root

    signal dismissRequested()
    property bool dismissed: false
    property int lastValidPresetIndex: 0
    readonly property var presets: [
        { label: "1024×600", width: 1024, height: 600 },
        { label: "1280×720", width: 1280, height: 720 },
        { label: "1366×768", width: 1366, height: 768 },
        { label: "1600×900", width: 1600, height: 900 },
        { label: "1920×1080", width: 1920, height: 1080 }
    ]
    readonly property int availableWidth: Screen.desktopAvailableWidth
    readonly property int availableHeight: Screen.desktopAvailableHeight

    property bool toolVisible: false
    visible: !dismissed && toolVisible && Window.window !== null
    implicitWidth: 460
    implicitHeight: 42
    z: 1000

    function applyPreset(index) {
        const preset = root.presets[index]
        if (!preset || !root.isPresetAvailable(index) || !Window.window) return

        if (Window.window.visibility === Window.Maximized)
            Window.window.showNormal()

        Window.window.width = preset.width
        Window.window.height = preset.height

        if (root.availableWidth > 0 && root.availableHeight > 0) {
            Window.window.x = Math.max(0, Math.round((root.availableWidth - preset.width) / 2))
            Window.window.y = Math.max(0, Math.round((root.availableHeight - preset.height) / 2))
        }
    }

    function isPresetAvailable(index) {
        const preset = root.presets[index]
        return !!preset && preset.width <= root.availableWidth && preset.height <= root.availableHeight
    }

    function presetLabel(index) {
        const preset = root.presets[index]
        return preset.label + (root.isPresetAvailable(index) ? "" : " ⚠")
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.bgSurfaceElevated
        border.color: Theme.border
        radius: Theme.radius

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.spaceSmall
            anchors.rightMargin: Theme.spaceSmall
            spacing: Theme.spaceSmall

            Text {
                text: Window.window
                      ? "Viewport: " + Math.round(Window.window.width) + " × " + Math.round(Window.window.height)
                      : "Viewport: —"
                color: Theme.textSecondary
                font.family: "Segoe UI"
                font.pixelSize: 12
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            Text {
                text: "Screen: " + root.availableWidth + " × " + root.availableHeight
                color: Theme.textMuted
                font.family: "Segoe UI"
                font.pixelSize: 11
            }

            ComboBox {
                id: presetSelector
                model: root.presets.map(function(preset, index) { return root.presetLabel(index) })
                Layout.preferredWidth: 105
                Layout.minimumWidth: 105
                onActivated: {
                    if (root.isPresetAvailable(currentIndex)) {
                        root.lastValidPresetIndex = currentIndex
                        root.applyPreset(currentIndex)
                    } else {
                        currentIndex = root.lastValidPresetIndex
                    }
                }
            }

            Button {
                text: "×"
                implicitWidth: 28
                implicitHeight: 28
                onClicked: {
                    root.dismissed = true
                    root.dismissRequested()
                }
            }
        }
    }
}
