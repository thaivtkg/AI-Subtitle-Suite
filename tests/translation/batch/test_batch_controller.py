import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.controllers.batch_controller import BatchController
from core.translation.models.subtitle import SubtitleModel


class FakeBatchService(QObject):
    jobChanged = Signal()

    def __init__(self):
        super().__init__()
        self.job = None
        self.calls = []

    def start(self, job):
        self.calls.append(("start", job))
        self.job = job
        job.state = BatchJobState.RUNNING
        job.items[min(job.items)].state = BatchItemState.RUNNING
        self.jobChanged.emit()

    def request_pause(self, job):
        self.calls.append(("pause", job))
        job.state = BatchJobState.PAUSING
        self.jobChanged.emit()

    def resume(self, job):
        self.calls.append(("resume", job))
        job.state = BatchJobState.RUNNING
        self.jobChanged.emit()

    def request_cancel(self, job):
        self.calls.append(("cancel", job))
        self.jobChanged.emit()

    def retry_failed(self, job):
        self.calls.append(("retry_failed", job))
        job.state = BatchJobState.RUNNING
        self.jobChanged.emit()

    def finish(self, state=BatchJobState.COMPLETED):
        self.job.state = state
        self.jobChanged.emit()


@pytest.fixture
def model():
    app = QGuiApplication.instance() or QGuiApplication([])
    subtitle_model = SubtitleModel()
    subtitle_model.load_data([
        {"index": 10, "original": "ten", "status": "TRANSLATED", "translation": "10"},
        {"index": 20, "original": "twenty", "status": "PENDING", "translation": ""},
        {"index": 30, "original": "thirty", "status": "PENDING", "translation": ""},
        {"index": 40, "original": "forty", "status": "ERROR", "translation": "bad"},
    ])
    assert app is QGuiApplication.instance()
    return subtitle_model


def test_tc_p3a7_01_start_snapshots_only_pending_targets(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")

    controller.startBatch("English", "Vietnamese", "summary")

    job = service.job
    assert sorted(job.items) == [1, 2]
    assert [item.target_index for item in job.items.values()] == [1, 2]
    assert controller.activeIndex == 1


def test_tc_p3a7_02_start_mapping_and_counts(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")

    assert controller.canStart is True
    controller.startBatch("English", "Vietnamese", "summary")

    assert controller.state == "RUNNING"
    assert controller.canStart is False
    assert controller.canPause is True
    assert controller.canCancel is True
    assert controller.totalCount == 2
    assert controller.pendingCount == 1


def test_tc_p3a7_03_progress_uses_batch_states_not_acceptance_count(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")

    service.job.items[1].state = BatchItemState.COMPLETED
    service.job.items[2].state = BatchItemState.FAILED
    service.finish()

    assert controller.completedCount == 1
    assert controller.failedCount == 1
    assert controller.progressPercent == 100


def test_tc_p3a7_04_pause_resume_button_mapping(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")

    controller.pauseBatch()
    assert controller.state == "PAUSING"
    assert controller.canPause is False
    assert controller.canResume is False

    service.job.items[1].state = BatchItemState.COMPLETED
    service.job.state = BatchJobState.PAUSED
    service.jobChanged.emit()
    assert controller.canResume is True
    controller.resumeBatch()
    assert controller.state == "RUNNING"


def test_tc_p3a7_05_cancel_is_presentation_pending_until_terminal(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")

    controller.cancelBatch()

    assert controller.state == "RUNNING"
    assert controller.cancelPending is True
    assert controller.executionLocked is True

    service.finish(BatchJobState.CANCELLED)
    assert controller.cancelPending is False
    assert controller.executionLocked is False


def test_tc_p3a7_06_retry_failed_uses_same_job(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")
    job = service.job
    job.items[2].state = BatchItemState.FAILED
    job.state = BatchJobState.COMPLETED
    service.jobChanged.emit()

    assert controller.canRetryFailed is True
    controller.retryFailed()
    assert service.calls[-1] == ("retry_failed", job)


def test_tc_p3a7_07_execution_lock_covers_active_batch(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")

    for state in (BatchJobState.RUNNING, BatchJobState.PAUSING, BatchJobState.PAUSED):
        service.job.state = state
        service.jobChanged.emit()
        assert controller.executionLocked is True


def test_tc_p3a7_08_terminal_state_releases_controls(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")

    service.finish(BatchJobState.COMPLETED)

    assert controller.executionLocked is False
    assert controller.canPause is False
    assert controller.canCancel is False
    assert controller.canStart is True


def test_tc_p3a7_09_selection_does_not_change_target_snapshot(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")
    job = service.job

    model.load_data(model.get_all_data()[::-1])

    assert job.items[1].target_index == 1
    assert job.items[2].target_index == 2


def test_tc_p3a7_10_action_calls_are_forwarded_to_service(model):
    service = FakeBatchService()
    controller = BatchController(model, service, project_id="project-1")
    controller.startBatch("English", "Vietnamese", "summary")
    job = service.job

    controller.pauseBatch()
    service.job.items[1].state = BatchItemState.COMPLETED
    service.job.state = BatchJobState.PAUSED
    service.jobChanged.emit()
    controller.resumeBatch()
    controller.cancelBatch()

    assert [name for name, _ in service.calls] == [
        "start", "pause", "resume", "cancel"
    ]
    assert all(call_job is job for _, call_job in service.calls)


def test_batch_start_with_limit_and_circular_rollover():
    model = SubtitleModel()
    data = [
        {"index": i, "original": f"Line {i}", "status": "TRANSLATED"} for i in range(10)
    ]
    data[8]["status"] = "PENDING"
    data[9]["status"] = "PENDING"
    data[0]["status"] = "PENDING"
    data[1]["status"] = "PENDING"
    model.load_data(data)

    service = FakeBatchService()
    controller = BatchController(model, service, "test_proj")

    controller.startBatch("English", "Vietnamese", "", start_index=8, limit=4)

    assert controller.totalCount == 4
    assert list(controller._job.items.keys()) == [8, 9, 0, 1]


def test_batch_start_backward_compatible_signature():
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "Line 0", "status": "PENDING"}])
    service = FakeBatchService()
    controller = BatchController(model, service, "test_proj")

    controller.startBatch("English", "Vietnamese", "")
    assert controller.state == "RUNNING"


def test_batch_start_with_specific_indices():
    model = SubtitleModel()
    data = [
        {"index": i, "original": f"Line {i}", "status": "PENDING"} for i in range(10)
    ]
    model.load_data(data)
    service = FakeBatchService()
    controller = BatchController(model, service, "test_proj")

    controller.startBatchWithIndices("English", "Vietnamese", "", [1, 3, 4, 5])

    assert controller.totalCount == 4
    assert list(controller._job.items.keys()) == [1, 3, 4, 5]



