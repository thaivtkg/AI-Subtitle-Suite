from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest


class UserDriver:
    def __init__(self, window, artifact_dir=None):
        self.window = window
        self.artifact_dir = Path(artifact_dir or "artifacts/t15")

    def find(self, object_name):
        item = self.window.findChild(QObject, object_name)
        if item is None:
            item = self._find_visual_child(self.window, object_name)
        if item is None:
            for candidate in self.window.findChildren(QObject):
                item = self._find_visual_child(candidate, object_name)
                if item is not None:
                    break
        if item is None:
            raise AssertionError(f"UI element not found: {object_name}")
        return item

    def _find_visual_child(self, parent, object_name):
        child_items = getattr(parent, "childItems", None)
        if child_items is None:
            return None
        for child in child_items():
            if child.objectName() == object_name:
                return child
            match = self._find_visual_child(child, object_name)
            if match is not None:
                return match
        return None

    def click(self, object_name):
        QTest.qWait(20)
        item = self.find(object_name)
        width = item.property("width")
        height = item.property("height")
        if width is None or height is None:
            raise AssertionError(f"UI element has no width/height: {object_name}")

        center = QPointF(float(width) / 2.0, float(height) / 2.0)
        scene_pos = item.mapToScene(center)
        QTest.mouseClick(
            self.window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(scene_pos.x()), round(scene_pos.y())),
        )
        QCoreApplication.processEvents()

    def focus(self, object_name):
        item = self.find(object_name)
        item.forceActiveFocus()
        QCoreApplication.processEvents()

    def type_text(self, object_name, text):
        self.focus(object_name)
        for character in text:
            self._key_event(Qt.Key_unknown, Qt.NoModifier, character)
        QCoreApplication.processEvents()

    def key(self, key, modifiers=Qt.NoModifier):
        self._key_event(key, modifiers)
        QCoreApplication.processEvents()

    def _key_event(self, key, modifiers, text=""):
        press = QKeyEvent(QEvent.KeyPress, key, modifiers, text)
        release = QKeyEvent(QEvent.KeyRelease, key, modifiers, text)
        QCoreApplication.sendEvent(self.window, press)
        QCoreApplication.sendEvent(self.window, release)

    def wait_until(self, predicate, timeout_ms=2000):
        elapsed = 0
        while elapsed < timeout_ms:
            QCoreApplication.processEvents()
            if predicate():
                return True
            QTest.qWait(20)
            elapsed += 20
        raise AssertionError(f"Timed out after {timeout_ms}ms")

    def is_enabled(self, object_name):
        return bool(self.find(object_name).property("enabled"))

    def is_visible(self, object_name):
        return bool(self.find(object_name).property("visible"))

    def text(self, object_name):
        value = self.find(object_name).property("text")
        return "" if value is None else str(value)

    def snapshot(self, name):
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.artifact_dir / f"{name}.png"
        if not self.window.grabWindow().save(str(path)):
            raise AssertionError(f"Could not save screenshot: {path}")
        return path
