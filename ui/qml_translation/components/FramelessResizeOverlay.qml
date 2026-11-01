import QtQuick 2.15
import QtQuick.Window 2.15

Item {
    id: root
    z: 99999

    property int edgeSize: 6

    MouseArea {
        anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: root.edgeSize; rightMargin: root.edgeSize }
        height: root.edgeSize
        cursorShape: Qt.SizeVerCursor
        onPressed: Window.window.startSystemResize(Qt.TopEdge)
    }

    MouseArea {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: root.edgeSize; rightMargin: root.edgeSize }
        height: root.edgeSize
        cursorShape: Qt.SizeVerCursor
        onPressed: Window.window.startSystemResize(Qt.BottomEdge)
    }

    MouseArea {
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: root.edgeSize; bottomMargin: root.edgeSize }
        width: root.edgeSize
        cursorShape: Qt.SizeHorCursor
        onPressed: Window.window.startSystemResize(Qt.LeftEdge)
    }

    MouseArea {
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom; topMargin: root.edgeSize; bottomMargin: root.edgeSize }
        width: root.edgeSize
        cursorShape: Qt.SizeHorCursor
        onPressed: Window.window.startSystemResize(Qt.RightEdge)
    }

    MouseArea {
        anchors { left: parent.left; top: parent.top }
        width: root.edgeSize
        height: root.edgeSize
        cursorShape: Qt.SizeFDiagCursor
        onPressed: Window.window.startSystemResize(Qt.TopEdge | Qt.LeftEdge)
    }

    MouseArea {
        anchors { right: parent.right; top: parent.top }
        width: root.edgeSize
        height: root.edgeSize
        cursorShape: Qt.SizeBDiagCursor
        onPressed: Window.window.startSystemResize(Qt.TopEdge | Qt.RightEdge)
    }

    MouseArea {
        anchors { left: parent.left; bottom: parent.bottom }
        width: root.edgeSize
        height: root.edgeSize
        cursorShape: Qt.SizeBDiagCursor
        onPressed: Window.window.startSystemResize(Qt.BottomEdge | Qt.LeftEdge)
    }

    MouseArea {
        anchors { right: parent.right; bottom: parent.bottom }
        width: root.edgeSize
        height: root.edgeSize
        cursorShape: Qt.SizeFDiagCursor
        onPressed: Window.window.startSystemResize(Qt.BottomEdge | Qt.RightEdge)
    }
}
