from pathlib import Path

from PySide6.QtCore import Qt

from .app_harness import AppHarness
from .deterministic_worker import DeterministicWorkerFactory


FIXTURE = Path(__file__).parent / "fixtures" / "regression.srt"


def wait_for(harness, predicate, timeout_ms=5000):
    harness.driver.wait_until(predicate, timeout_ms)


def test_tc_p3a7_q01_production_composition_and_start():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        assert harness.driver.find("batchControlBar") is not None
        assert harness.driver.is_enabled("btnBatchStart")
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        assert harness.batch_controller.activeIndex == 0
    finally:
        harness.close()


def test_tc_p3a7_q02_selection_independence():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.find("subtitleList").setProperty("currentIndex", -1)
        assert harness.driver.is_enabled("btnBatchStart")
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        assert harness.batch_controller.activeIndex == 0
    finally:
        harness.close()


def test_tc_p3a7_q03_manual_actions_locked():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        assert not harness.driver.is_enabled("btnTranslate")
        assert not harness.driver.is_enabled("btnRetry")
        assert not harness.driver.is_enabled("btnAccept")
        assert harness.driver.find("translationInput").property("readOnly") is True
    finally:
        harness.close()


def test_tc_p3a7_q04_keyboard_acceptance_is_locked():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("subtitleRow_0")
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        harness.driver.focus("translationInput")
        harness.driver.key(Qt.Key_Return, Qt.ControlModifier)
        assert harness.model.get_all_data()[0]["status"].upper() != "ACCEPTED"
    finally:
        harness.close()


def test_tc_p3a7_q05_project_mutation_locked():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        assert not harness.driver.is_enabled("btnOpenSrt")
        assert not harness.driver.is_enabled("btnOpenProject")
        assert not harness.driver.find("shortcutOpenSrt").property("enabled")
        assert not harness.driver.find("shortcutOpenProject").property("enabled")
    finally:
        harness.close()


def test_tc_p3a7_q06_pause_resume():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        wait_for(
            harness,
            lambda: harness.driver.is_enabled("btnBatchPause")
            and harness.driver.find("btnBatchPause").property("x") > 0,
        )
        harness.driver.click("btnBatchPause")
        wait_for(harness, lambda: harness.batch_controller.state == "PAUSED")
        assert harness.driver.is_enabled("btnBatchResume")
        assert harness.batch_controller.activeIndex == -1
        harness.driver.click("btnBatchResume")
        assert harness.batch_controller.state == "RUNNING"
    finally:
        harness.close()


def test_tc_p3a7_q07_graceful_cancel_presentation():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        harness.driver.click("btnBatchCancel")
        assert harness.batch_controller.cancelPending is True
        assert any(word in harness.driver.text("batchStatusText") for word in ("Cancelling", "Đang hủy"))
        wait_for(harness, lambda: harness.batch_controller.state == "CANCELLED")
        assert harness.batch_controller.executionLocked is False
    finally:
        harness.close()


def test_tc_p3a7_q08_retry_failed():
    factory = DeterministicWorkerFactory("error")
    harness = AppHarness(FIXTURE, worker_factory=factory)
    try:
        harness.model.load_data([
            {"index": 1, "original": "retry me", "translation": "", "status": "PENDING"},
        ])
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "COMPLETED")
        assert harness.driver.is_enabled("btnBatchRetryFailed")
        factory.set_mode("success")
        job = harness.batch_controller._job
        harness.driver.click("btnBatchRetryFailed")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        assert harness.batch_controller._job is job
    finally:
        harness.close()


def test_tc_p3a7_q09_batch_progress_projection():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("slow"))
    try:
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "RUNNING")
        assert harness.batch_controller.totalCount == 3
        assert harness.driver.text("batchProgressText")
    finally:
        harness.close()


def test_tc_p3a7_q10_terminal_unlock():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "COMPLETED")
        assert harness.batch_controller.executionLocked is False
        assert harness.driver.is_enabled("btnOpenSrt")
        assert harness.driver.is_enabled("btnOpenProject")
        assert not harness.driver.is_enabled("btnBatchPause")
        assert not harness.driver.is_enabled("btnBatchCancel")
    finally:
        harness.close()


def test_tc_p3a7_custom_batch_limit_execution():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        harness.batch_controller.startBatch("English", "Vietnamese", "", 0, 2)
        wait_for(harness, lambda: harness.batch_controller.state == "COMPLETED")
        assert harness.batch_controller.totalCount == 2
        assert harness.batch_controller.completedCount == 2
    finally:
        harness.close()


def test_tc_p3a7_multi_selection_batch_execution():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        harness.batch_controller.startBatchWithIndices("English", "Vietnamese", "", [0, 2])
        wait_for(harness, lambda: harness.batch_controller.state == "COMPLETED")
        assert harness.batch_controller.totalCount == 2
        assert harness.batch_controller.completedCount == 2
        data = harness.model.get_all_data()
        assert data[0]["status"] == "TRANSLATED"
        assert data[1]["status"].upper() == "PENDING"
        assert data[2]["status"] == "TRANSLATED"
    finally:
        harness.close()


def test_tc_p3a7_multi_selection_ui_interaction_and_execution():
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("success"))
    try:
        batch_btn = harness.driver.find("btnBatchStart")
        # 1. Click row 0 normally
        harness.driver.click("subtitleRow_0")
        QTest.qWait(50)
        assert "50 câu" in batch_btn.property("text")

        # 2. Ctrl+Click row 2
        row2 = harness.driver.find("subtitleRow_2")
        p2 = row2.mapToScene(QPoint(10, 10)).toPoint()
        QTest.mouseClick(harness.window, Qt.LeftButton, Qt.ControlModifier, p2)
        QTest.qWait(50)

        # 3. Verify batch button dynamically updates to multi-selection mode
        assert ("2 câu" in batch_btn.property("text") or "(2)" in batch_btn.property("text"))

        # 4. Click batch start button
        harness.driver.click("btnBatchStart")
        wait_for(harness, lambda: harness.batch_controller.state == "COMPLETED")
        assert harness.batch_controller.totalCount == 2
        assert harness.batch_controller.completedCount == 2

        data = harness.model.get_all_data()
        assert data[0]["status"] == "TRANSLATED"
        assert data[1]["status"].upper() == "PENDING"
        assert data[2]["status"] == "TRANSLATED"
    finally:
        harness.close()


def test_tc_p3a7_time_filter_and_language_selector_responsiveness():
    harness = AppHarness(FIXTURE, worker_factory=DeterministicWorkerFactory("fast"))
    try:
        from PySide6.QtTest import QTest

        # 1. Verify initial state: 3 items, filteredCount == 3
        sub_list = harness.driver.find("subtitleList")
        assert sub_list.property("count") == 3
        nav = harness.driver.find("subtitleListView")
        assert nav.property("filteredCount") == 3

        # 2. Activate time filter 1..5 (regression.srt items are all in minute 0)
        time_check = harness.driver.find("timeFilterCheck")
        start_input = harness.driver.find("startMinInput")
        end_input = harness.driver.find("endMinInput")
        assert time_check is not None

        start_input.setProperty("text", "1")
        end_input.setProperty("text", "5")
        time_check.setProperty("checked", True)
        QTest.qWait(50)

        # Count should now be 0 since all are minute 0
        assert nav.property("filteredCount") == 0

        # 3. Change filter to 0..1 (covers minute 0)
        start_input.setProperty("text", "0")
        end_input.setProperty("text", "1")
        QTest.qWait(50)
        assert nav.property("filteredCount") == 3

        # 4. Uncheck time filter
        time_check.setProperty("checked", False)
        QTest.qWait(50)
        assert nav.property("filteredCount") == 3

        # 5. Check LanguageSelector compactness on narrow window
        lang_selector = harness.driver.find("sourceLangCombo")
        assert lang_selector is not None
        harness.window.setWidth(1024)
        QTest.qWait(50)
        assert lang_selector.property("compact") is True
    finally:
        harness.close()

