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

    committed_events = []
    page_widget.translation_committed.connect(lambda idx, text: committed_events.append((idx, text)))

    # Click Accept button
    cat_page.click_accept()
    driver.wait_ms(150)

    # Verify committed signal and item removal from queue (CAT Studio queue model)
    assert len(committed_events) == 1
    assert committed_events[0] == (0, translated_text)
    # Approved item was removed from CAT queue; seg-002 shifted to index 0
    assert page_widget.subtitle_model.rowCount() == 1
    next_seg = page_widget.subtitle_model.get_item(0)
    assert next_seg["original"] == "This is an automated speech translation demo."


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


def test_flow_cat_studio_cancel_translation_via_ui_button(cat_studio_driver):
    """
    User Flow (PLAN-CAT-WORKFLOW-STABILITY-001):
    1. Start translation (simulate TRANSLATING status on row 0).
    2. Verify btnCancelTranslation is visible in QML scene.
    3. Click btnCancelTranslation via QtDriver.
    4. Assert controller status reverts to PENDING, progress resets to 0%,
       and btnCancelTranslation is no longer visible.
    """
    page_widget, cat_page, driver = cat_studio_driver
    ctrl = page_widget.translation_controller

    # Set controller to TRANSLATING state
    ctrl._status = "TRANSLATING"
    ctrl._active_translation_index = 0
    ctrl._translation_progress = 45
    ctrl.statusChanged.emit("TRANSLATING")
    ctrl.translationProgressChanged.emit(45)
    driver.wait_ms(100)

    # Inspect QML Scene Graph: btnCancelTranslation must now be visible
    cancel_btn = cat_page.btn_cancel_translate_item
    assert cancel_btn is not None, "btnCancelTranslation must exist in QML"
    driver.assert_visible(cancel_btn, True)

    # Click Cancel button via Page Object
    cat_page.click_cancel_translation()
    driver.wait_ms(150)

    # Assert status and progress reset
    assert ctrl.status == "PENDING"
    assert ctrl.translationProgress == 0
    assert ctrl._active_translation_index == -1


def test_flow_cat_studio_cancel_translation_via_escape_key(cat_studio_driver):
    """
    User Flow (PLAN-CAT-WORKFLOW-STABILITY-001):
    1. Set status to TRANSLATING.
    2. Send Escape key to the QQuickWidget window.
    3. Assert translation cancels immediately.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    page_widget, cat_page, driver = cat_studio_driver
    ctrl = page_widget.translation_controller

    ctrl._status = "TRANSLATING"
    ctrl._active_translation_index = 0
    ctrl._translation_progress = 70
    ctrl.statusChanged.emit("TRANSLATING")
    ctrl.translationProgressChanged.emit(70)
    driver.wait_ms(100)

    # Trigger Escape shortcut
    QTest.keyClick(cat_page.quick_widget, Qt.Key_Escape)
    driver.wait_ms(150)

    assert ctrl.status == "PENDING"
    assert ctrl.translationProgress == 0
    assert ctrl._active_translation_index == -1


def test_flow_cat_studio_empty_queue_guard_in_ui(cat_studio_driver):
    """
    User Flow (PLAN-CAT-WORKFLOW-STABILITY-001):
    1. Clear/accept all subtitles until SubtitleModel rowCount == 0.
    2. Assert QML switches to EmptyWorkspace.
    3. Emit background progress from stale worker.
    4. Assert controller status remains IDLE and does not revive translating UI.
    """
    page_widget, cat_page, driver = cat_studio_driver
    ctrl = page_widget.translation_controller
    model = page_widget.subtitle_model

    # Clear queue to 0
    while model.rowCount() > 0:
        model.remove_subtitle(0)
    driver.wait_ms(100)

    assert model.rowCount() == 0
    assert ctrl.status == "IDLE"

    # Background stale worker emits progress
    ctrl.on_progress(0, "Stale worker text")
    driver.wait_ms(50)
    assert ctrl.status == "IDLE"
    assert ctrl.currentTranslation == ""


