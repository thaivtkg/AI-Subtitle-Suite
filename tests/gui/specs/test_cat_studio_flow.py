# -*- coding: utf-8 -*-
"""
E2E GUI Flow Specs for QML CAT Translation Studio using Page Object Model (POM) and QtDriver.
Verifies QML Scene Graph element inspection, source text extraction, translation input simulation,
and action button execution.
"""
import pytest


def test_flow_cat_studio_qml_introspection_and_source_reading(cat_studio_driver):
    """
    User Flow:
    1. Verify CAT Studio QQuickWidget is loaded and displaying.
    2. Read source sentence from QML origTextArea.
    3. Assert source matches segment #1.
    """
    page_widget, cat_page, driver = cat_studio_driver

    cat_page.assert_workspace_visible()
    source_text = cat_page.get_source_text()
    assert "Good morning, welcome to CAT Studio." in source_text


def test_flow_cat_studio_manual_translation_and_accept(cat_studio_driver):
    """
    User Flow:
    1. Enter target translation into QML translationInput.
    2. Click ✓ Lưu & Tiếp tục (Accept).
    3. Verify segment status in SubtitleModel is updated to ACCEPTED.
    """
    page_widget, cat_page, driver = cat_studio_driver

    translated_text = "Chào buổi sáng, chào mừng đến với CAT Studio."
    cat_page.type_translation(translated_text, clear_first=True)
    assert cat_page.get_translation_text() == translated_text

    # Click Accept button
    cat_page.click_accept()
    driver.wait_ms(150)

    # Verify model state
    seg = page_widget.subtitle_model.get_item(0)
    assert seg is not None
    assert seg.get("translation") == translated_text
    assert seg.get("status") == "ACCEPTED"


def test_flow_cat_studio_action_buttons_visibility(cat_studio_driver):
    """
    User Flow:
    1. Inspect QML Scene Graph elements (Translate, Accept, ModelManager).
    2. Assert all critical workflow buttons are visible and active.
    """
    page_widget, cat_page, driver = cat_studio_driver

    driver.assert_visible(cat_page.btn_translate_item, True)
    driver.assert_visible(cat_page.btn_accept_item, True)

    btn_model = cat_page.btn_model_manager_item
    assert btn_model is not None, "btnModelManager must be present in QML Header"
    driver.assert_visible(btn_model, True)


def test_flow_cat_studio_hotkeys_button(cat_studio_driver):
    """
    AUD-UX-003: Verify btnHotkeys exists and is clickable in CAT Studio action bar.
    """
    page_widget, cat_page, driver = cat_studio_driver

    btn_hotkeys = cat_page.btn_hotkeys_item
    assert btn_hotkeys is not None, "btnHotkeys must be present in QML Workspace footer"
    driver.assert_visible(btn_hotkeys, True)
    cat_page.click_hotkeys()
    driver.wait_ms(100)

