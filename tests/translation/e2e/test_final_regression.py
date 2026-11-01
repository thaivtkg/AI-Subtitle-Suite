import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QUrl, Qt

from core.translation.core.srt_parser import SRTParser
from core.translation.core.srt_validator import SRTValidator

from .app_harness import AppHarness
from .deterministic_worker import DeterministicWorkerFactory


FIXTURE = Path(__file__).parent / "fixtures" / "regression.srt"


@pytest.fixture
def harness(request):
    worker_factory = getattr(request, "param", None)
    app_harness = AppHarness(FIXTURE, worker_factory=worker_factory)
    yield app_harness
    app_harness.close()


def wait_for(harness, predicate, timeout_ms=3000):
    harness.driver.wait_until(predicate, timeout_ms)


def accept_first(harness):
    controller = harness.translation_controller
    controller.requestTranslation(0, "Japanese", "Vietnamese", "")
    wait_for(harness, lambda: controller.status == "TRANSLATED")
    wait_for(harness, lambda: not controller.worker.isRunning())
    harness.driver.click("btnAccept")
    wait_for(harness, lambda: controller.acceptedCount == 1)


def test_tc15_01_fresh_launch():
    harness = AppHarness(None)
    try:
        assert harness.window.isVisible()
        assert harness.model.rowCount() == 0
        assert harness.translation_controller.totalSubtitleCount == 0
        assert harness.driver.text("statusProgressText") in ("No project", "Chưa mở dự án")
    finally:
        harness.close()


def test_tc15_02_keyboard_navigation(harness):
    from PySide6.QtTest import QTest
    tabs = harness.driver.find("contextTabs")
    if tabs: tabs.setCurrentIndex(2)
    QTest.qWait(50)
    harness.driver.focus("storySummaryInput")
    harness.driver.key(Qt.Key_Tab)
    wait_for(harness, lambda: not harness.driver.find("storySummaryInput").property("activeFocus"))
    harness.driver.key(Qt.Key_Tab, Qt.ShiftModifier)
    wait_for(harness, lambda: harness.driver.find("storySummaryInput").property("activeFocus"))


def test_tc15_03_search(harness):
    harness.driver.type_text("searchInput", "magic")
    assert harness.driver.text("searchInput") == "magic"
    harness.driver.key(Qt.Key_A, Qt.ControlModifier)
    harness.driver.key(Qt.Key_Backspace)
    assert harness.driver.text("searchInput") == ""


def test_tc15_04_status_filter(harness):
    harness.driver.click("btnToggleFilters")
    combo = harness.driver.find("statusFilterCombo")
    harness.driver.click("statusFilterCombo")
    harness.driver.key(Qt.Key_Home)
    harness.driver.key(Qt.Key_Down)
    harness.driver.key(Qt.Key_Return)
    assert combo.property("currentText") == "Chờ dịch"


def test_tc15_05_import_and_dirty_state():
    harness = AppHarness(None)
    try:
        harness.project_controller.importSrt(QUrl.fromLocalFile(str(FIXTURE)).toString())
        harness.app.processEvents()
        assert harness.project_controller.hasProject is True
        assert harness.project_controller.isDirty is True
    finally:
        harness.close()


def test_tc15_06_subtitle_selection(harness):
    subtitle_list = harness.driver.find("subtitleList")
    harness.driver.click("subtitleRow_0")
    wait_for(harness, lambda: subtitle_list.property("currentIndex") == 0)
    assert harness.translation_controller.currentOriginal == "魔法美少女戦士、ポンテンス"
    harness.driver.click("subtitleRow_1")
    wait_for(harness, lambda: subtitle_list.property("currentIndex") == 1)
    assert harness.translation_controller.currentOriginal == "行くぞ！"


def test_tc15_07_translation_streaming():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        updates = []
        harness.translation_controller.translationUpdated.connect(updates.append)
        harness.driver.click("btnTranslate")
        wait_for(harness, lambda: harness.translation_controller.status == "TRANSLATED")
        wait_for(harness, lambda: not harness.translation_controller.worker.isRunning())
        assert updates[-1] == "Nữ chiến binh phép thuật, Pontens!"
        assert harness.driver.text("translationInput") == updates[-1]
    finally:
        harness.close()


def test_tc15_08_global_busy_guard():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("btnTranslate")
        wait_for(harness, lambda: harness.translation_controller.engineStatus == "Translating")
        harness.driver.click("subtitleRow_1")
        assert harness.driver.is_enabled("btnTranslate") is False
        assert harness.driver.is_enabled("btnRetry") is False
        wait_for(harness, lambda: not harness.translation_controller.worker.isRunning())
    finally:
        harness.close()


def test_tc15_09_target_isolation():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("btnTranslate")
        wait_for(harness, lambda: harness.translation_controller.engineStatus == "Translating")
        harness.driver.click("subtitleRow_1")
        wait_for(harness, lambda: harness.translation_controller.engineStatus == "Ready")
        wait_for(harness, lambda: not harness.translation_controller.worker.isRunning())
        rows = harness.model.get_all_data()
        assert rows[0]["translation"] == "Nữ chiến binh phép thuật, Pontens!"
        assert rows[1]["translation"] == ""
        assert rows[1]["status"].upper() == "PENDING"
    finally:
        harness.close()


def test_tc15_10_translation_restoration():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        harness.driver.click("btnTranslate")
        wait_for(harness, lambda: harness.translation_controller.status == "TRANSLATED")
        wait_for(harness, lambda: not harness.translation_controller.worker.isRunning())
        harness.driver.click("subtitleRow_1")
        harness.driver.click("subtitleRow_0")
        wait_for(harness, lambda: harness.driver.text("translationInput") == "Nữ chiến binh phép thuật, Pontens!")
    finally:
        harness.close()


def test_tc15_11_empty_output_guard():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("empty"))
    try:
        harness.driver.click("btnTranslate")
        wait_for(harness, lambda: harness.translation_controller.status == "ERROR")
        wait_for(harness, lambda: not harness.translation_controller.worker.isRunning())
        assert harness.model.get_all_data()[0]["status"] == "ERROR"
        assert harness.model.get_all_data()[0]["translation"] == "Lỗi: Model trả về bản dịch rỗng."
    finally:
        harness.close()


def test_tc15_12_accept_and_completion():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        accept_first(harness)
        assert harness.translation_controller.acceptedCount == 1
        assert harness.driver.text("statusProgressText").startswith("✓ 1 / 3")
        assert harness.model.get_all_data()[0]["status"] == "ACCEPTED"
    finally:
        harness.close()


def test_tc15_13_save_load_integrity(tmp_path):
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        accept_first(harness)
        project_path = tmp_path / "roundtrip.aisrt"
        file_url = QUrl.fromLocalFile(str(project_path)).toString()
        harness.project_controller.saveProject(file_url, "test story", "Japanese", "Vietnamese")
        assert harness.project_controller.isDirty is False

        harness.project_controller.loadProject(file_url)
        harness.translation_controller.loadSubtitle(0)
        row = harness.model.get_all_data()[0]
        assert row["status"] == "ACCEPTED"
        assert row["translation"] == "Nữ chiến binh phép thuật, Pontens!"
        assert harness.window.property("globalStorySummary") == "test story"
        assert harness.driver.find("sourceLanguageCombo").property("currentText") == "Japanese"
        assert project_path.exists()
    finally:
        harness.close()


def test_tc15_14_responsive_layout(harness):
    required = ("btnOpenSrt", "btnOpenProject", "btnSave", "btnExport", "translationInput", "btnRetry", "btnTranslate", "btnAccept", "engineStatusText", "vramStatusText")
    for width, height in ((1024, 600), (1280, 720), (1366, 768)):
        harness.window.showNormal()
        harness.window.resize(width, height)
        harness.app.processEvents()
        for object_name in required:
            item = harness.driver.find(object_name)
            if not item.property("visible"):
                continue
            top_left = item.mapToScene(QPointF(0, 0))
            bottom_right = item.mapToScene(QPointF(item.property("width"), item.property("height")))
            assert top_left.x() >= 0 and top_left.y() >= 0
            assert bottom_right.x() <= width and bottom_right.y() <= height


def test_tc15_15_export_guard(tmp_path):
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        assert harness.project_controller.validateBeforeExport() is False
        for index in range(3):
            harness.translation_controller.requestTranslation(index, "Japanese", "Vietnamese", "")
            wait_for(harness, lambda: harness.translation_controller.status == "TRANSLATED")
            wait_for(harness, lambda: not harness.translation_controller.worker.isRunning())
            assert harness.translation_controller.acceptTranslation(index, harness.model.get_all_data()[index]["translation"])
        assert harness.project_controller.validateBeforeExport() is True
        output_path = tmp_path / "translated.srt"
        harness.project_controller.exportSrt(QUrl.fromLocalFile(str(output_path)).toString())
        exported_text = output_path.read_text(encoding="utf-8")
        assert "Nữ chiến binh phép thuật, Pontens!" in exported_text
        assert "Đi thôi!" in exported_text
        assert "Mau rời khỏi đây!" in exported_text
    finally:
        harness.close()


def test_tc15_16_chunk_filter():
    harness = AppHarness(FIXTURE)
    try:
        combo = harness.driver.find("chunkFilterCombo")
        assert combo is not None
        assert combo.property("count") == 5
        assert combo.property("currentText") == "Tất cả câu"

        # Initially, pagination bar is not visible
        assert not harness.driver.find("paginationBar").property("visible")

        # Load 120 items to verify multi-page navigation
        data = [
            {"index": i + 1, "start_time": "00:00:01,000", "end_time": "00:00:02,000", "original": f"Line {i+1}", "status": "PENDING", "translation": ""}
            for i in range(120)
        ]
        harness.model.load_data(data)
        harness.app.processEvents()

        # Select "Hiển thị 5 câu / trang" (index 1)
        combo.setProperty("currentIndex", 1)
        harness.app.processEvents()
        assert harness.driver.find("paginationBar").property("visible")
        assert harness.driver.text("paginationText") == "Trang 1 / 24"
        assert not harness.driver.is_enabled("btnPrevPage")
        assert harness.driver.is_enabled("btnNextPage")

        # Click next page -> Trang 2 / 24
        harness.driver.click("btnNextPage")
        harness.app.processEvents()
        assert harness.driver.text("paginationText") == "Trang 2 / 24"
        assert harness.driver.is_enabled("btnPrevPage")

        # Click prev page -> Trang 1 / 24
        harness.driver.click("btnPrevPage")
        harness.app.processEvents()
        assert harness.driver.text("paginationText") == "Trang 1 / 24"

        # Switch to "Hiển thị 50 câu / trang" (index 4)
        combo.setProperty("currentIndex", 4)
        harness.app.processEvents()
        assert harness.driver.text("paginationText") == "Trang 1 / 3"

        # Switch back to "Tất cả câu" (index 0)
        combo.setProperty("currentIndex", 0)
        harness.app.processEvents()
        assert not harness.driver.find("paginationBar").property("visible")
    finally:
        harness.close()


def test_tc15_17_time_range_filter():
    harness = AppHarness(None)
    try:
        time_check = harness.driver.find("timeFilterCheck")
        start_input = harness.driver.find("startMinInput")
        end_input = harness.driver.find("endMinInput")
        chunk_combo = harness.driver.find("chunkFilterCombo")
        pagination_bar = harness.driver.find("paginationBar")

        assert time_check is not None
        assert start_input is not None
        assert end_input is not None
        assert not time_check.property("checked")
        assert not start_input.property("enabled")
        assert not end_input.property("enabled")

        # Load 4 subtitles across different minutes
        data = [
            {"index": 1, "start_time": "00:02:15,000", "end_time": "00:02:18,000", "original": "Min 2", "status": "PENDING", "translation": ""},
            {"index": 2, "start_time": "00:07:30,000", "end_time": "00:07:35,000", "original": "Min 7", "status": "PENDING", "translation": ""},
            {"index": 3, "start_time": "00:15:45,000", "end_time": "00:15:50,000", "original": "Min 15", "status": "PENDING", "translation": ""},
            {"index": 4, "start_time": "00:25:00,000", "end_time": "00:25:05,000", "original": "Min 25", "status": "PENDING", "translation": ""},
        ]
        harness.model.load_data(data)
        from PySide6.QtTest import QTest
        QTest.qWait(50)
        harness.app.processEvents()

        # All 4 items visible initially
        row0 = harness.driver.find("subtitleRow_0")
        row1 = harness.driver.find("subtitleRow_1")
        row2 = harness.driver.find("subtitleRow_2")
        row3 = harness.driver.find("subtitleRow_3")
        assert row0.property("visible") is True
        assert row1.property("visible") is True
        assert row2.property("visible") is True
        assert row3.property("visible") is True

        # Activate time filter: Min 5 to 20
        time_check.setProperty("checked", True)
        harness.app.processEvents()
        assert start_input.property("enabled") is True
        assert end_input.property("enabled") is True

        start_input.setProperty("text", "5")
        end_input.setProperty("text", "20")
        harness.app.processEvents()

        # Row 0 (min 2) and Row 3 (min 25) are filtered out; Row 1 (min 7) and Row 2 (min 15) are present
        sub_list = harness.driver.find("subtitleList")
        nav = harness.driver.find("subtitleListView")
        assert nav.property("filteredCount") == 2
        assert sub_list.property("count") == 2

        active_row1 = harness.driver.find("subtitleRow_1")
        active_row2 = harness.driver.find("subtitleRow_2")
        assert active_row1.property("visible") is True
        assert active_row2.property("visible") is True

        # Verify Chunking Composition: selecting page size works together with time filter
        chunk_combo.setProperty("currentIndex", 1)  # "Hiển thị 5 câu / trang"
        harness.app.processEvents()
        assert pagination_bar.property("visible") is True
        assert harness.driver.find("subtitleRow_1").property("visible") is True
        assert harness.driver.find("subtitleRow_2").property("visible") is True

        # Deactivate time filter -> Pagination bar and all items restored without losing chunk combo state
        time_check.setProperty("checked", False)
        harness.app.processEvents()
        assert nav.property("filteredCount") == 4
        assert pagination_bar.property("visible") is True
        assert chunk_combo.property("currentIndex") == 1
    finally:
        harness.close()

