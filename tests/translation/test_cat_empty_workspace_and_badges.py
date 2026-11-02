# -*- coding: utf-8 -*-
"""
Automated Specs for PLAN-CAT-EMPTY-DEFAULT-001:
- AC-CAT-EMPTY-01: Default empty CAT Studio (0 items) when navigating via tab index 8
- AC-CAT-SELECT-02: Multi-selection transfer from SubEditor imports only selected segments
- AC-CAT-IMPORT-03: Active import from Video Timeline imports all segments
- AC-CAT-BADGE-04: Pending subtitle lifecycle badge is '⏳ CHỜ DỊCH'
- AC-CAT-BADGE-05: AI translated draft lifecycle badge is '⌛ CHỜ DUYỆT'
- AC-CAT-BADGE-06: Accepted subtitle lifecycle badge is '✓ ĐÃ DUYỆT' and syncs to Timeline
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from ui.Gui import MainWindow
from tests.gui.drivers.qt_driver import QtDriver


@pytest.fixture
def main_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    QTest.qWait(100)
    yield win
    win.close()


def test_ac_cat_empty_default_01_and_import_03(main_window):
    """
    AC-CAT-EMPTY-01 & AC-CAT-IMPORT-03:
    Navigating to CAT Studio defaults to 0 rows and shows import action button.
    Triggering import_all_from_timeline populates all items from SubEditor.
    """
    win = main_window
    mock_segments = [
        {"stt": i, "id": f"seg_{i}", "start": f"00:00:{i:02d},000", "end": f"00:00:{i:02d},900", "text": f"Source line #{i}", "translation": ""}
        for i in range(1, 11)
    ]
    win.sub_editor.all_segments = mock_segments

    # 1. Switch to CAT Studio (Nav index 8) without multi-selection
    win.switch_page(8)
    QTest.qWait(200)

    cat_model = win.page_translation.subtitle_model
    # AC-CAT-EMPTY-01: Must start with 0 subtitles!
    assert cat_model.rowCount() == 0, f"Expected 0 subtitles on first navigation, got {cat_model.rowCount()}"

    # Verify QML button btnImportFromTimeline exists
    driver = QtDriver(win)
    root_qml = win.page_translation.quick_widget.rootObject()
    btn_import = driver.find_qml_item("btnImportFromTimeline", root_item=root_qml)
    assert btn_import is not None
    assert btn_import.property("visible") is True

    # 2. AC-CAT-IMPORT-03: Active import from timeline
    win.page_translation.import_all_from_timeline()
    QTest.qWait(200)

    assert cat_model.rowCount() == 10
    item_0 = cat_model.get_item(0)
    assert item_0["original"] == "Source line #1"
    assert item_0["status"] == "PENDING"


def test_ac_cat_select_02_multi_selection_transfer(main_window):
    """
    AC-CAT-SELECT-02:
    Selecting segments #3, #4, #5 in SubEditor and sending to translation
    loads strictly those 3 segments into CAT Studio.
    """
    win = main_window
    mock_segments = [
        {"stt": i, "id": f"seg_{i}", "start": f"00:00:{i:02d},000", "end": f"00:00:{i:02d},900", "text": f"Source line #{i}", "translation": ""}
        for i in range(1, 11)
    ]
    win.sub_editor.all_segments = mock_segments

    # Send segments at indices 2, 3, 4 (stt 3, 4, 5)
    win._on_send_selected_to_translation([2, 3, 4])
    QTest.qWait(200)

    cat_model = win.page_translation.subtitle_model
    assert cat_model.rowCount() == 3
    assert cat_model.get_item(0)["index"] == 3
    assert cat_model.get_item(1)["index"] == 4
    assert cat_model.get_item(2)["index"] == 5


def test_ac_cat_lifecycle_badges_04_05_06(main_window):
    """
    AC-CAT-BADGE-04, 05, 06:
    Lifecycle badges progression:
    PENDING ('⏳ CHỜ DỊCH') -> TRANSLATED ('⌛ CHỜ DUYỆT') -> ACCEPTED ('✓ ĐÃ DUYỆT').
    """
    win = main_window
    mock_segments = [
        {"stt": 1, "id": "seg_1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "English speech", "translation": ""}
    ]
    win.sub_editor.all_segments = mock_segments

    # Load into CAT Studio
    win.page_translation.load_subtitles_from_studio(mock_segments)
    QTest.qWait(150)

    cat_ctrl = win.page_translation.translation_controller
    sub_model = win.page_translation.subtitle_model

    # AC-CAT-BADGE-04: Newly imported subtitle is PENDING
    assert cat_ctrl.status == "PENDING"
    assert sub_model.get_item(0)["status"] == "PENDING"

    # AC-CAT-BADGE-05: AI translation draft generated -> TRANSLATED
    sub_model.update_translation(0, "Bản dịch nháp tiếng Việt", "TRANSLATED")
    cat_ctrl.loadSubtitle(0)
    QTest.qWait(100)
    assert cat_ctrl.status == "TRANSLATED"
    assert sub_model.get_item(0)["status"] == "TRANSLATED"
    # Overwrite Guard check: Draft does not overwrite timeline text
    win.page_translation.export_subtitles_to_studio(win.sub_editor.all_segments)
    assert win.sub_editor.all_segments[0]["text"] == "English speech"

    # AC-CAT-BADGE-06: User accepts translation (Ctrl+Enter) -> ACCEPTED & Timeline sync
    cat_ctrl.acceptTranslation(0, "Bản dịch đã duyệt")
    QTest.qWait(100)
    # Timeline sync check
    assert win.sub_editor.all_segments[0]["text"] == "Bản dịch đã duyệt"
    assert win.sub_editor.all_segments[0]["translation"] == "Bản dịch đã duyệt"
    assert win.sub_editor.all_segments[0]["translation_status"] == "ACCEPTED"
    # Khi đã duyệt, câu biến mất khỏi hàng đợi CAT Studio theo yêu cầu
    assert sub_model.rowCount() == 0
    assert cat_ctrl.status == "IDLE"
