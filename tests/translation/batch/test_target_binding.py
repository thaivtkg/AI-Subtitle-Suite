from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.hardware_detector import HardwareDetector
from core.translation.models.subtitle import SubtitleModel
from core.translation.services.batch_translation_service import BatchTranslationService
from core.translation.services.translation_pipeline_adapter import TranslationPipelineAdapter

from tests.translation.e2e.deterministic_worker import DeterministicWorkerFactory


def _wait_until(predicate, timeout_ms=3000):
    app = QCoreApplication.instance()
    for _ in range(timeout_ms // 20):
        app.processEvents()
        if predicate():
            return
        QTest.qWait(20)
    raise AssertionError(f"Timed out after {timeout_ms}ms")


def test_tc_p3a2_05_target_binding_survives_selection_change(monkeypatch):
    app = QGuiApplication.instance() or QGuiApplication([])
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "original": "Alpha", "translation": "", "status": "PENDING"},
        {"index": 2, "original": "Bravo", "translation": "", "status": "PENDING"},
        {"index": 3, "original": "Charlie", "translation": "", "status": "PENDING"},
    ])
    monkeypatch.setattr(
        HardwareDetector,
        "get_recommended_profile",
        staticmethod(lambda: {
            "gpu_info": {"name": "T15 test", "vram_gb": 0.0},
            "backend_status": "T15 test profile",
            "model_name": "missing-test-model.gguf",
            "n_ctx": 2048,
            "n_gpu_layers": 0,
        }),
    )
    controller = TranslationController(model, worker_factory=DeterministicWorkerFactory("slow"))
    adapter = TranslationPipelineAdapter(controller)
    service = BatchTranslationService(adapter)
    job = BatchJob.create(
        "p3a2-target-binding",
        {0: BatchItem(target_index=0, source_hash="alpha")},
    )

    controller.loadSubtitle(0)
    service.start(job)
    assert job.items[0].state is BatchItemState.RUNNING
    assert adapter._pending[0] == 0

    controller.loadSubtitle(2)
    assert controller._current_index == 2
    assert job.items[0].target_index == 0

    _wait_until(lambda: job.state is BatchJobState.COMPLETED)
    if controller.worker is not None:
        controller.worker.wait()

    rows = model.get_all_data()
    assert rows[0]["status"] == "TRANSLATED"
    assert rows[0]["translation"] == "Nữ chiến binh phép thuật, Pontens!"
    assert rows[0]["translation"].strip()
    assert rows[1]["status"] == "PENDING"
    assert rows[1]["translation"] == ""
    assert rows[2]["status"] == "PENDING"
    assert rows[2]["translation"] == ""
    assert job.items[0].state is BatchItemState.COMPLETED
    assert controller._current_index == 2
    assert controller.currentOriginal == "Charlie"
    assert controller.currentTranslation == ""
    assert controller.status == "PENDING"
    controller.worker.deleteLater()
    app.processEvents()
    assert app is QCoreApplication.instance()


