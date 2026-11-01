from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy

from core.translation.batch.batch_state import BatchJobState
from core.translation.controllers.batch_controller import BatchController
from core.translation.controllers.batch_runtime_bridge import BatchRuntimeBridge
from core.translation.models.subtitle import SubtitleModel


class FakeTranslationController(QObject):
    translationCompleted = Signal(int)
    translationFailed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.requests = []

    def requestTranslation(self, target_index, source_lang, target_lang, summary):
        self.requests.append((target_index, source_lang, target_lang, summary))

    def complete(self, target_index):
        self.translationCompleted.emit(target_index)

    def fail(self, target_index, message):
        self.translationFailed.emit(target_index, message)


def make_controller():
    app = QGuiApplication.instance() or QGuiApplication([])
    model = SubtitleModel()
    model.load_data([
        {"index": 10, "original": "alpha", "status": "PENDING", "translation": ""},
        {"index": 20, "original": "bravo", "status": "PENDING", "translation": ""},
    ])
    translation_controller = FakeTranslationController()
    bridge = BatchRuntimeBridge(translation_controller)
    controller = BatchController(model, bridge, project_id="project-1")
    assert app is QGuiApplication.instance()
    return model, translation_controller, bridge, controller


def test_tc_p3a7_w01_real_production_path_dispatches_first_target():
    _, translation, _, controller = make_controller()

    controller.startBatch("English", "Vietnamese", "summary")

    assert controller.state == "RUNNING"
    assert translation.requests == [(0, "English", "Vietnamese", "summary")]
    assert controller.activeIndex == 0


def test_tc_p3a7_w02_start_configuration_is_frozen_for_batch_requests():
    _, translation, _, controller = make_controller()

    controller.startBatch("Japanese", "Vietnamese", "summary A")
    translation.complete(0)

    assert translation.requests == [
        (0, "Japanese", "Vietnamese", "summary A"),
        (1, "Japanese", "Vietnamese", "summary A"),
    ]


def test_tc_p3a7_w03_success_refreshes_after_service_dispatches_next():
    _, translation, bridge, controller = make_controller()
    changes = QSignalSpy(bridge.jobChanged)

    controller.startBatch("English", "Vietnamese", "summary")
    translation.complete(0)

    assert changes.count() == 2
    assert controller.completedCount == 1
    assert controller.activeIndex == 1
    assert controller.state == "RUNNING"


def test_tc_p3a7_w04_failure_is_projected_and_final_success_completes_job():
    _, translation, _, controller = make_controller()

    controller.startBatch("English", "Vietnamese", "summary")
    translation.fail(0, "model failure")

    assert controller.failedCount == 1
    assert controller.activeIndex == 1
    translation.complete(1)

    assert controller.state == "COMPLETED"
    assert controller.failedCount == 1
    assert controller.progressPercent == 100
    assert controller.executionLocked is False


def test_tc_p3a7_w05_pause_resume_cancel_use_production_notifications():
    _, translation, _, controller = make_controller()

    controller.startBatch("English", "Vietnamese", "summary")
    controller.pauseBatch()
    translation.complete(0)

    assert controller.state == "PAUSED"
    assert controller.canResume is True

    controller.resumeBatch()
    assert controller.activeIndex == 1
    controller.cancelBatch()
    assert controller.cancelPending is True
    translation.complete(1)

    assert controller.state == "CANCELLED"
    assert controller.cancelPending is False
    assert controller.executionLocked is False
    assert translation.requests == [(0, "English", "Vietnamese", "summary"), (1, "English", "Vietnamese", "summary")]


def test_tc_p3a7_w06_model_changes_refresh_projection():
    model, _, _, controller = make_controller()
    changes = QSignalSpy(controller.projectionChanged)

    model.load_data([
        {"index": 10, "original": "alpha", "status": "PENDING", "translation": ""},
    ])

    assert changes.count() > 0
    assert controller.canStart is True

