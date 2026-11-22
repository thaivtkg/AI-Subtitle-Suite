from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, Signal

from core.translation.controllers.translation_controller import TranslationController
from core.translation.llm.worker import TranslationWorker
from core.translation.models.subtitle import SubtitleModel


class PendingWorker(QObject):
    progress = Signal(int, str)
    activity = Signal(int)
    finished = Signal(int, str)
    error = Signal(int, str)

    def __init__(self, index, prompt, profile):
        super().__init__()
        self._running = False

    def start(self):
        self._running = True

    def isRunning(self):
        return self._running

    def cancel(self):
        self._running = False

    def wait(self, timeout):
        return not self._running


@pytest.fixture
def controller(qapp, monkeypatch):
    monkeypatch.setattr(
        "core.translation.core.hardware_detector.HardwareDetector.get_recommended_profile",
        lambda: {"model_name": "qa.gguf"},
    )
    monkeypatch.setattr(
        "core.translation.llm.model_manager.ModelManager.get_instance",
        MagicMock(return_value=MagicMock()),
    )
    model = SubtitleModel()
    model.load_data([
        {"original": "Hello", "translation": "Xin chào", "status": "TRANSLATED"},
        {"original": "Goodbye", "translation": "Tạm biệt", "status": "TRANSLATED"},
    ])
    ctrl = TranslationController(model, worker_factory=PendingWorker)
    ctrl.loadSubtitle(0)
    ctrl.requestTranslation(0, "English", "Vietnamese", "")
    yield ctrl, model
    ctrl.shutdown()


def test_first_response_allows_model_loading_and_prompt_processing(controller):
    ctrl, _ = controller
    assert ctrl._watchdog_timer.isActive()
    assert ctrl._watchdog_timer.interval() == 300_000


def test_visible_progress_refreshes_inactivity_deadline(controller):
    ctrl, model = controller
    ctrl._watchdog_timer.start(50)
    ctrl.worker.progress.emit(0, "Xin chào bạn")
    assert ctrl._watchdog_timer.remainingTime() > 80_000
    assert model.get_item(0)["translation"] == "Xin chào bạn"


def test_hidden_token_activity_refreshes_deadline_without_showing_reasoning(controller):
    ctrl, model = controller
    ctrl._watchdog_timer.start(50)
    ctrl.worker.activity.emit(0)
    assert ctrl._watchdog_timer.remainingTime() > 80_000
    assert model.get_item(0)["translation"] == ""
    assert ctrl.currentTranslation == ""


def test_animated_progress_does_not_refresh_inactivity_deadline(controller):
    ctrl, _ = controller
    ctrl._watchdog_timer.start(50)
    ctrl._on_thinking_progress_tick()
    assert ctrl._watchdog_timer.interval() == 50


def test_timeout_applies_to_active_row_after_selecting_another_row(controller):
    ctrl, model = controller
    ctrl.loadSubtitle(1)
    ctrl._watchdog_timer.start(90_000)
    ctrl._on_translation_timeout()
    assert model.get_item(0)["status"] == "ERROR"
    assert model.get_item(0)["translation"] == "Xin chào"
    assert "90s" in model.get_item(0)["translation_error"]
    assert model.get_item(1)["translation"] == "Tạm biệt"
    assert ctrl.status == "TRANSLATED"
    assert ctrl.currentTranslation == "Tạm biệt"
    assert ctrl._active_translation_index == -1
    assert not ctrl._watchdog_timer.isActive()


def test_first_response_timeout_reports_actual_wait_without_blame_on_gpu(controller):
    ctrl, model = controller
    ctrl._on_translation_timeout()
    assert "300s" in ctrl.currentError
    assert "GPU" not in ctrl.currentError
    assert model.get_item(0)["translation"] == "Xin chào"


def test_activity_from_replaced_worker_or_wrong_row_is_ignored(controller):
    ctrl, _ = controller
    old_worker = ctrl.worker
    old_worker.error.emit(0, "failed")
    old_worker.cancel()
    ctrl.requestTranslation(0, "English", "Vietnamese", "")
    ctrl._watchdog_timer.start(50)
    old_worker.activity.emit(0)
    ctrl.worker.activity.emit(1)
    assert ctrl._watchdog_timer.interval() == 50
    ctrl.worker.activity.emit(0)
    assert ctrl._watchdog_timer.remainingTime() > 80_000


@pytest.mark.parametrize("signal_name", ["finished", "error"])
def test_late_result_does_not_stop_new_workers_watchdog(controller, signal_name):
    ctrl, _ = controller
    old_worker = ctrl.worker
    old_worker.error.emit(0, "failed")
    old_worker.cancel()
    ctrl.requestTranslation(0, "English", "Vietnamese", "")
    getattr(old_worker, signal_name).emit(0, "stale result")
    assert ctrl._watchdog_timer.isActive()
    assert ctrl._active_translation_index == 0
    assert ctrl.status == "TRANSLATING"


def test_worker_reports_hidden_reasoning_and_vocab_as_activity(tmp_path, monkeypatch):
    model_path = tmp_path / "qa.gguf"
    model_path.touch()
    manager = MagicMock()
    manager.generate_stream.return_value = iter([
        "<think>", "I need to translate this", "</think>", "Xin chào",
        "\n[TỪ GỐC]\nHello -> Xin chào", "",
    ])
    monkeypatch.setattr(
        "core.translation.llm.worker.ModelManager.get_instance",
        MagicMock(return_value=manager),
    )
    worker = TranslationWorker(0, "Translate this", {"model_path": str(model_path)})
    activities, visible, finished = [], [], []
    worker.activity.connect(activities.append)
    worker.progress.connect(lambda idx, text: visible.append(text))
    worker.finished.connect(lambda idx, text: finished.append(text))
    worker.run()
    assert activities == [0] * 5
    assert finished == ["Xin chào"]
    assert all("<think>" not in text and "TỪ GỐC" not in text for text in visible)


@pytest.mark.parametrize("load_fails", [False, True])
def test_cancel_during_model_load_does_not_start_generation_or_cpu_retry(tmp_path, monkeypatch, load_fails):
    model_path = tmp_path / "qa.gguf"
    model_path.touch()
    worker = TranslationWorker(0, "Translate this", {"model_path": str(model_path)})
    manager = MagicMock()

    def load_model(*args, **kwargs):
        worker.cancel()
        if load_fails:
            raise RuntimeError("GPU load failed while cancelling")

    manager.load_model.side_effect = load_model
    monkeypatch.setattr(
        "core.translation.llm.worker.ModelManager.get_instance",
        MagicMock(return_value=manager),
    )
    worker.run()
    manager.generate_stream.assert_not_called()
    assert manager.load_model.call_count == 1
