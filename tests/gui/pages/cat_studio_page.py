# -*- coding: utf-8 -*-
"""
Page Object for AI Subtitle Translation CAT Studio (Qt Quick / QML).
Encapsulates UI interactions with QML Scene Graph components:
source text area, translation input, action buttons (translate, accept, retry).
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickWidgets import QQuickWidget
from tests.gui.pages.base_page import BasePage
from tests.gui.drivers.qt_driver import QtDriver


class CatStudioPage(BasePage):
    """Page Object for QML CAT Translation Studio."""

    # Locators (QML objectName identifiers)
    LOC_ORIG_TEXT = "origTextArea"
    LOC_TRANSLATION_INPUT = "translationInput"
    LOC_BTN_TRANSLATE = "btnTranslate"
    LOC_BTN_ACCEPT = "btnAccept"
    LOC_BTN_RETRY = "btnRetry"
    LOC_BTN_HOTKEYS = "btnHotkeys"
    LOC_BTN_MODEL_MANAGER = "btnModelManager"
    LOC_SOURCE_LANG_COMBO = "sourceLangCombo"

    def __init__(self, driver: QtDriver, quick_widget: Optional[QQuickWidget] = None):
        super().__init__(driver)
        self.quick_widget = quick_widget or self.window.findChild(QQuickWidget)

    @property
    def root_qml(self) -> QQuickItem:
        assert self.quick_widget is not None, "QQuickWidget not found on window"
        root = self.quick_widget.rootObject()
        assert root is not None, "QML Root Object is None"
        return root

    # -------------------------------------------------------------------------
    # Element Getters (QML Components via QQuickItem)
    # -------------------------------------------------------------------------

    @property
    def orig_text_item(self) -> QQuickItem:
        return self.driver.find_qml_item(self.LOC_ORIG_TEXT, root_item=self.root_qml)

    @property
    def translation_input_item(self) -> QQuickItem:
        return self.driver.find_qml_item(self.LOC_TRANSLATION_INPUT, root_item=self.root_qml)

    @property
    def btn_translate_item(self) -> QQuickItem:
        return self.driver.find_qml_item(self.LOC_BTN_TRANSLATE, root_item=self.root_qml)

    @property
    def btn_accept_item(self) -> QQuickItem:
        return self.driver.find_qml_item(self.LOC_BTN_ACCEPT, root_item=self.root_qml)

    @property
    def btn_hotkeys_item(self) -> Optional[QQuickItem]:
        try:
            return self.driver.find_qml_item(self.LOC_BTN_HOTKEYS, root_item=self.root_qml)
        except LookupError:
            return None

    @property
    def btn_model_manager_item(self) -> Optional[QQuickItem]:
        try:
            return self.driver.find_qml_item(self.LOC_BTN_MODEL_MANAGER, root_item=self.root_qml)
        except LookupError:
            return None

    # -------------------------------------------------------------------------
    # User Actions
    # -------------------------------------------------------------------------

    def get_source_text(self) -> str:
        """Returns the source sentence text in the CAT Studio workspace."""
        return self.driver.get_text(self.orig_text_item)

    def get_translation_text(self) -> str:
        """Returns current translation text in translationInput."""
        return self.driver.get_text(self.translation_input_item)

    def type_translation(self, text: str, clear_first: bool = True) -> CatStudioPage:
        """Enters translation text into the QML translation editor."""
        self.driver.type_text(self.translation_input_item, text, clear_first=clear_first)
        self.wait_ms(50)
        return self

    def click_translate(self) -> CatStudioPage:
        """Clicks the ⚡ Dịch câu này button."""
        self.driver.click(self.btn_translate_item)
        self.wait_ms(100)
        return self

    def click_accept(self) -> CatStudioPage:
        """Clicks the ✓ Lưu & Tiếp tục (Ctrl+Enter) button."""
        self.driver.click(self.btn_accept_item)
        self.wait_ms(100)
        return self

    def click_hotkeys(self) -> CatStudioPage:
        """Clicks the ⌨ Phím tắt (F1) button."""
        assert self.btn_hotkeys_item is not None, "btnHotkeys not found in QML"
        self.driver.click(self.btn_hotkeys_item)
        self.wait_ms(100)
        return self

    def assert_workspace_visible(self) -> None:
        """Asserts that QQuickWidget is loaded and displaying."""
        assert self.quick_widget is not None and self.quick_widget.isVisible()
        assert self.root_qml is not None
