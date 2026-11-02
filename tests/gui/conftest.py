# -*- coding: utf-8 -*-
"""
Pytest fixtures for GUI Automation Driver testing (POM Pattern).
Provides isolated and live application drivers for QWidget, QML, and Waveform Timeline testing.
"""
import os
import pytest
from PySide6.QtWidgets import QApplication
from ui.SubEditor import SubtitleEditorWidget
from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from tests.gui.drivers.qt_driver import QtDriver
from tests.gui.pages.sub_editor_page import SubEditorPage
from tests.gui.pages.cat_studio_page import CatStudioPage
from tests.gui.pages.timeline_page import TimelineWidgetPage


@pytest.fixture
def sub_editor_driver(qtbot):
    """
    Provides an isolated SubtitleEditorWidget wrapped in QtDriver and SubEditorPage.
    Configured with standard test subtitle segments and undo manager.
    """
    editor = SubtitleEditorWidget()
    undo_mgr = GlobalUndoManager()
    editor.undo_manager = undo_mgr
    undo_mgr.state_changed.connect(editor.render_page)

    editor.all_segments = [
        {"stt": "1", "start": "00:00:01,000", "end": "00:00:02,500", "text": "Câu thứ nhất ban đầu"},
        {"stt": "2", "start": "00:00:03,000", "end": "00:00:04,500", "text": "Câu thứ hai ban đầu"},
        {"stt": "3", "start": "00:00:05,000", "end": "00:00:07,000", "text": "Câu thứ ba ban đầu"},
    ]
    editor.resize(900, 600)
    qtbot.addWidget(editor)
    editor.show()
    editor.render_page()
    editor.select_segment(0)

    driver = QtDriver(editor, qtbot=qtbot)
    page = SubEditorPage(driver, sub_editor_widget=editor)

    yield editor, page, driver

    editor.close()
    editor.deleteLater()


@pytest.fixture
def cat_studio_driver(qtbot):
    """
    Provides an isolated TranslationStudioPage (QML CAT Studio) wrapped in QtDriver and CatStudioPage.
    Loads standard sample subtitles for testing.
    """
    from ui.pages.translation_studio_page import TranslationStudioPage

    page_widget = TranslationStudioPage()
    page_widget.resize(1024, 600)
    qtbot.addWidget(page_widget)
    page_widget.show()
    qtbot.wait(150)

    # Load initial subtitle segments to populate QML workspace
    page_widget.load_subtitles_from_studio([
        {"segment_id": "seg-001", "start": 1000, "end": 3500, "text": "Good morning, welcome to CAT Studio."},
        {"segment_id": "seg-002", "start": 4000, "end": 6500, "text": "This is an automated speech translation demo."},
    ])
    qtbot.wait(200)

    driver = QtDriver(page_widget, qtbot=qtbot)
    cat_page = CatStudioPage(driver, quick_widget=page_widget.quick_widget)

    yield page_widget, cat_page, driver

    page_widget.close()
    page_widget.deleteLater()


@pytest.fixture
def timeline_driver(qtbot):
    """
    Provides a live MainWindow wrapped in QtDriver, TimelineWidgetPage, and SubEditorPage.
    Equipped with safe video player and eventFilter cleanup.
    """
    from ui.Gui import MainWindow

    win = MainWindow()
    win.timeline_widget.duration_ms = 30000
    win.resize(1280, 720)
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(100)

    driver = QtDriver(win, qtbot=qtbot)
    timeline_page = TimelineWidgetPage(driver, timeline_widget=win.timeline_widget)
    sub_page = SubEditorPage(driver, sub_editor_widget=win.sub_editor)

    yield win, driver, timeline_page, sub_page

    try:
        from dataclasses import is_dataclass
        if hasattr(win, "project_service") and not is_dataclass(getattr(win.project_service, "current_project", None)):
            win.project_service.current_project = None
    except Exception:
        pass
    try:
        if hasattr(win, "video_player") and hasattr(win.video_player, "cleanup"):
            win.video_player.cleanup()
    except Exception:
        pass
    try:
        QApplication.instance().removeEventFilter(win)
    except Exception:
        pass
    win.close()
    win.deleteLater()


@pytest.fixture
def main_window_driver(qtbot, tmp_path):
    """
    Provides a live MainWindow wrapped in QtDriver, with SubEditorPage, CatStudioPage, and TimelineWidgetPage.
    """
    from ui.Gui import MainWindow

    win = MainWindow()
    win.resize(1280, 720)
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(100)

    driver = QtDriver(win, qtbot=qtbot)
    sub_page = SubEditorPage(driver, sub_editor_widget=win.sub_editor)
    cat_page = CatStudioPage(driver, quick_widget=win.page_translation.quick_widget if hasattr(win, "page_translation") else None)
    timeline_page = TimelineWidgetPage(driver, timeline_widget=win.timeline_widget)

    yield win, driver, sub_page, cat_page, timeline_page

    try:
        from dataclasses import is_dataclass
        if hasattr(win, "project_service") and not is_dataclass(getattr(win.project_service, "current_project", None)):
            win.project_service.current_project = None
    except Exception:
        pass
    try:
        if hasattr(win, "video_player") and hasattr(win.video_player, "cleanup"):
            win.video_player.cleanup()
    except Exception:
        pass
    try:
        QApplication.instance().removeEventFilter(win)
    except Exception:
        pass
    win.close()
    win.deleteLater()
