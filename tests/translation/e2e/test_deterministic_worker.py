from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication

from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.hardware_detector import HardwareDetector
from core.translation.core.srt_parser import SRTParser
from core.translation.models.subtitle import SubtitleModel

from .deterministic_worker import DeterministicWorkerFactory


FIXTURE = Path(__file__).parent / "fixtures" / "regression.srt"


@pytest.fixture
def qapp():
    return QGuiApplication.instance() or QGuiApplication([])


def make_controller(mode):
    model = SubtitleModel()
    model.load_data(SRTParser.parse(str(FIXTURE)))
    factory = DeterministicWorkerFactory(mode)

    original_profile = HardwareDetector.get_recommended_profile
    HardwareDetector.get_recommended_profile = staticmethod(lambda: {
        "gpu_info": {"name": "T15 test", "vram_gb": 0.0},
        "backend_status": "T15 test profile",
        "model_name": "missing-test-model.gguf",
        "n_ctx": 2048,
        "n_gpu_layers": 0,
    })
    try:
        controller = TranslationController(model, worker_factory=factory)
    finally:
        HardwareDetector.get_recommended_profile = original_profile

    return model, controller, factory


def wait_for(qapp, predicate, timeout_ms=3000):
    elapsed = 0
    while elapsed < timeout_ms:
        qapp.processEvents()
        if predicate():
            return
        qapp.processEvents()
        elapsed += 20
        from PySide6.QtTest import QTest
        QTest.qWait(20)
    raise AssertionError(f"Timed out after {timeout_ms}ms")


def test_success_streams_and_commits_non_empty(qapp):
    model, controller, _ = make_controller("success")
    chunks = []
    controller.translationUpdated.connect(chunks.append)

    controller.requestTranslation(0, "Japanese", "Vietnamese", "")
    wait_for(qapp, lambda: controller.status == "TRANSLATED")
    wait_for(qapp, lambda: not controller.worker.isRunning())

    assert chunks[:3] == ["", "Nữ", "Nữ chiến binh"]
    assert model.get_all_data()[0]["translation"] == "Nữ chiến binh phép thuật, Pontens!"
    assert model.get_all_data()[0]["status"] == "TRANSLATED"


def test_empty_output_becomes_error(qapp):
    model, controller, _ = make_controller("empty")

    controller.requestTranslation(0, "Japanese", "Vietnamese", "")
    wait_for(qapp, lambda: controller.status == "ERROR")
    wait_for(qapp, lambda: not controller.worker.isRunning())

    assert model.get_all_data()[0]["status"] == "ERROR"
    assert model.get_all_data()[0]["translation"] == "Lỗi: Model trả về bản dịch rỗng."


def test_error_mode_is_deterministic(qapp):
    model, controller, _ = make_controller("error")

    controller.requestTranslation(0, "Japanese", "Vietnamese", "")
    wait_for(qapp, lambda: controller.status == "ERROR")
    wait_for(qapp, lambda: not controller.worker.isRunning())

    assert model.get_all_data()[0]["status"] == "ERROR"
    assert model.get_all_data()[0]["translation"] == "Lỗi: Deterministic test error."


def test_slow_mode_allows_selection_switch_without_second_worker(qapp):
    model, controller, _ = make_controller("slow")

    controller.requestTranslation(0, "Japanese", "Vietnamese", "")
    wait_for(qapp, lambda: controller.engineStatus == "Translating")
    first_worker = controller.worker
    controller.loadSubtitle(1)
    assert controller.status == "PENDING"
    assert controller.currentOriginal == "行くぞ！"

    controller.requestTranslation(1, "Japanese", "Vietnamese", "")
    assert controller.worker is first_worker
    wait_for(qapp, lambda: controller.engineStatus == "Ready")
    wait_for(qapp, lambda: not first_worker.isRunning())

    assert model.get_all_data()[0]["status"] == "TRANSLATED"
    assert model.get_all_data()[0]["translation"] == "Nữ chiến binh phép thuật, Pontens!"
    assert model.get_all_data()[1]["status"].upper() == "PENDING"

