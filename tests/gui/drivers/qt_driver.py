# -*- coding: utf-8 -*-
"""
Qt Desktop Test Driver (Selenium WebDriver equivalent for PySide6 Desktop Apps).
Provides unified DOM-like element locating, user interaction simulation (click, type),
and assertions across hybrid QWidget and Qt Quick / QML hierarchies.
"""
from __future__ import annotations
from typing import Callable, Optional, Type, TypeVar, Any
from PySide6.QtCore import Qt, QObject, QPoint, QPointF
from PySide6.QtWidgets import QWidget, QLineEdit, QTextEdit, QLabel, QPushButton, QTableWidget, QApplication
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtTest import QTest

T = TypeVar("T", bound=QObject)


class QtDriver:
    """
    Selenium WebDriver equivalent for PySide6 Desktop Applications.
    Wraps qtbot / QTest primitives to provide a clean, declarative automation interface.
    """

    def __init__(self, root_window: QWidget, qtbot: Any = None):
        self.root_window = root_window
        self.qtbot = qtbot

    # =========================================================================
    # 1. ELEMENT LOCATORS (Selenium find_element / find_elements equivalents)
    # =========================================================================

    def find_widget(
        self,
        selector: str,
        parent: Optional[QWidget] = None,
        widget_type: Optional[Type[T]] = None,
    ) -> T:
        """
        Locates a QWidget by objectName (e.g., 'txt_current_sub_content' or '#txt_current_sub_content').
        Raises LookupError if not found (equivalent to NoSuchElementException).
        """
        search_root = parent or self.root_window
        obj_name = selector.lstrip("#")
        target_type = widget_type or QWidget

        found = search_root.findChild(target_type, obj_name)
        if found is None:
            # Fallback: search by accessibility name or custom property
            for child in search_root.findChildren(target_type):
                if (
                    child.objectName() == obj_name
                    or child.accessibleName() == obj_name
                    or child.property("automationId") == obj_name
                ):
                    return child

            raise LookupError(
                f"[QtDriver] Widget not found: selector='{selector}', "
                f"type={target_type.__name__}, search_root={search_root.objectName() or search_root.__class__.__name__}"
            )
        return found

    def find_widgets(
        self,
        selector: str,
        parent: Optional[QWidget] = None,
        widget_type: Optional[Type[T]] = None,
    ) -> list[T]:
        """Locates all QWidgets matching objectName or selector."""
        search_root = parent or self.root_window
        obj_name = selector.lstrip("#")
        target_type = widget_type or QWidget
        return [w for w in search_root.findChildren(target_type) if w.objectName() == obj_name]

    def find_qml_item(
        self,
        object_name: str,
        root_item: Optional[QQuickItem] = None,
        quick_widget: Optional[QQuickWidget] = None,
    ) -> QQuickItem:
        """
        Locates a QQuickItem inside QML scene by objectName.
        Raises LookupError if not found.
        """
        if root_item is None:
            qw = quick_widget or self.root_window.findChild(QQuickWidget)
            if qw is None or qw.rootObject() is None:
                raise LookupError(f"[QtDriver] Cannot find QQuickWidget or root QML object to search for '{object_name}'")
            root_item = qw.rootObject()

        # Qt C++ findChild on QQuickItem
        found = root_item.findChild(QQuickItem, object_name)
        if found is not None:
            return found

        # Recursive traversal through childItems() fallback
        def _search_children(parent_item: QQuickItem) -> Optional[QQuickItem]:
            for child in parent_item.childItems():
                if child.objectName() == object_name:
                    return child
                sub = _search_children(child)
                if sub is not None:
                    return sub
            return None

        found = _search_children(root_item)
        if found is None:
            raise LookupError(f"[QtDriver] QML item '{object_name}' not found in QML Scene Graph")
        return found

    # =========================================================================
    # 2. USER INTERACTIONS (Selenium click, send_keys, clear equivalents)
    # =========================================================================

    def click(self, target: QWidget | QQuickItem, delay_ms: int = 20) -> None:
        """Simulates native user mouse click on QWidget or QQuickItem."""
        if isinstance(target, QWidget):
            if self.qtbot:
                self.qtbot.mouseClick(target, Qt.MouseButton.LeftButton)
            else:
                QTest.mouseClick(target, Qt.MouseButton.LeftButton)
        elif isinstance(target, QQuickItem):
            # Locate enclosing QQuickWidget
            qw = self.root_window.findChild(QQuickWidget)
            if qw is not None:
                center_f = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
                center_p = center_f.toPoint()
                QTest.mouseClick(qw, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center_p)
            elif hasattr(target, "clicked"):
                target.clicked.emit()
            elif hasattr(target, "triggered"):
                target.triggered.emit()

        if delay_ms > 0:
            self.wait_ms(delay_ms)

    def type_text(
        self,
        target: QWidget | QQuickItem,
        text: str,
        clear_first: bool = False,
        delay_ms: int = 20,
    ) -> None:
        """
        Simulates typing text into QLineEdit, QTextEdit, or QML TextInput/TextArea.
        Supports full Unicode text (Vietnamese, Japanese, Chinese) without crashing Qt C++ key mapping.
        """
        if isinstance(target, QLineEdit):
            target.setFocus()
            if clear_first:
                target.clear()
            target.insert(text)
        elif isinstance(target, QTextEdit):
            target.setFocus()
            if clear_first:
                target.clear()
            cursor = target.textCursor()
            cursor.insertText(text)
            target.setTextCursor(cursor)
        elif isinstance(target, QQuickItem):
            # QML TextInput / TextArea
            target.setProperty("focus", True)
            if clear_first:
                target.setProperty("text", "")
            if hasattr(target, "setProperty"):
                target.setProperty("text", text)

        if delay_ms > 0:
            self.wait_ms(delay_ms)

    def get_text(self, target: QWidget | QQuickItem) -> str:
        """Extracts text content uniformly from QWidget or QML item."""
        if isinstance(target, QTextEdit):
            return target.toPlainText()
        elif isinstance(target, (QLineEdit, QLabel, QPushButton)):
            return target.text()
        elif isinstance(target, QQuickItem):
            val = target.property("text")
            return str(val) if val is not None else ""
        elif hasattr(target, "text"):
            return str(target.text())
        elif hasattr(target, "toPlainText"):
            return str(target.toPlainText())
        return ""

    # =========================================================================
    # 3. SYNCHRONIZATION & WAITS (Selenium WebDriverWait equivalents)
    # =========================================================================

    def wait_until(
        self,
        condition_fn: Callable[[], bool],
        timeout_ms: int = 5000,
        poll_interval_ms: int = 50,
        message: str = "Condition not met before timeout",
    ) -> None:
        """Waits until callable returns True, processing Qt events cooperatively."""
        if self.qtbot:
            self.qtbot.waitUntil(condition_fn, timeout=timeout_ms)
        else:
            from PySide6.QtCore import QElapsedTimer
            timer = QElapsedTimer()
            timer.start()
            while not condition_fn():
                if timer.elapsed() > timeout_ms:
                    raise TimeoutError(f"[QtDriver] Timeout ({timeout_ms}ms): {message}")
                QTest.qWait(poll_interval_ms)

    def wait_ms(self, ms: int) -> None:
        """Cooperative wait processing the Qt Event Loop."""
        if self.qtbot:
            self.qtbot.wait(ms)
        else:
            QTest.qWait(ms)

    # =========================================================================
    # 4. ASSERTIONS
    # =========================================================================

    def assert_visible(self, target: QWidget | QQuickItem, expected: bool = True) -> None:
        if isinstance(target, QWidget):
            assert target.isVisible() == expected, f"[QtDriver] Expected {target.objectName()} visible={expected}, got {target.isVisible()}"
        elif isinstance(target, QQuickItem):
            vis = bool(target.property("visible"))
            assert vis == expected, f"[QtDriver] Expected QML item {target.objectName()} visible={expected}, got {vis}"

    def assert_enabled(self, target: QWidget | QQuickItem, expected: bool = True) -> None:
        if isinstance(target, QWidget):
            assert target.isEnabled() == expected, f"[QtDriver] Expected {target.objectName()} enabled={expected}, got {target.isEnabled()}"
        elif isinstance(target, QQuickItem):
            en = bool(target.property("enabled"))
            assert en == expected, f"[QtDriver] Expected QML item {target.objectName()} enabled={expected}, got {en}"

    def assert_text(self, target: QWidget | QQuickItem, expected_text: str) -> None:
        actual = self.get_text(target)
        assert actual == expected_text, f"[QtDriver] Expected text '{expected_text}', got '{actual}' on {target.objectName()}"
