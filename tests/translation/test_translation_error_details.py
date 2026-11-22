from unittest.mock import MagicMock, patch

import pytest

from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel


@pytest.fixture
def controller(qapp):
    model = SubtitleModel()
    model.load_data([
        {"original": "Hello", "translation": "Xin chào", "status": "TRANSLATED"},
        {"original": "Goodbye", "translation": "Tạm biệt", "status": "TRANSLATED"},
    ])
    ctrl = TranslationController(model)
    ctrl.loadSubtitle(0)
    ctrl._active_translation_index = 0
    ctrl._translation_before_request = "Xin chào"
    ctrl._status = "TRANSLATING"
    yield ctrl, model
    ctrl.shutdown()


@pytest.mark.parametrize("partial", ["", "Bản dịch đang viết"])
def test_inference_error_keeps_translation_and_exposes_reason(controller, partial):
    ctrl, model = controller
    model.update_translation(0, partial, "TRANSLATING")
    failures = []
    ctrl.translationFailed.connect(lambda idx, message: failures.append((idx, message)))
    ctrl.on_error(0, "Requested tokens exceed context window of 2048")
    expected = partial or "Xin chào"
    assert model.get_item(0)["translation"] == expected
    assert ctrl.currentTranslation == expected
    assert ctrl.status == "ERROR"
    assert "context window of 2048" in ctrl.currentError
    assert failures == [(0, ctrl.currentError)]
    ctrl.loadSubtitle(1)
    assert ctrl.currentError == ""
    ctrl.loadSubtitle(0)
    assert "context window of 2048" in ctrl.currentError


def test_empty_result_keeps_old_translation_and_exposes_reason(controller):
    ctrl, model = controller
    model.update_translation(0, "", "TRANSLATING")
    ctrl.on_finished(0, "")
    assert model.get_item(0)["translation"] == "Xin chào"
    assert "bản dịch rỗng" in ctrl.currentError
    assert ctrl._active_translation_index == -1


def test_timeout_exposes_actual_reason(controller):
    ctrl, model = controller
    model.update_translation(0, "Bản nháp", "TRANSLATING")
    with patch("core.translation.llm.model_manager.ModelManager.get_instance"):
        ctrl._on_translation_timeout()
    assert "90s" in ctrl.currentError
    assert model.get_item(0)["translation"] == "Bản nháp"


def test_late_errors_do_not_change_other_rows_or_success(controller):
    ctrl, model = controller
    ctrl.on_error(1, "wrong row")
    assert model.get_item(1)["status"] == "TRANSLATED"
    ctrl.on_error(0, "failed once")
    ctrl._active_translation_index = 0
    ctrl._status = "TRANSLATING"
    ctrl.on_finished(0, "Chào bạn")
    assert ctrl.currentError == ""
    assert not model.get_item(0).get("translation_error")
    ctrl.on_error(0, "stale error")
    assert model.get_item(0)["translation"] == "Chào bạn"
    assert ctrl.status == "TRANSLATED"


def test_retry_clears_error_before_notifying_ui(controller):
    ctrl, model = controller
    ctrl.on_error(0, "failed once")
    worker = MagicMock()
    worker.isRunning.return_value = False
    ctrl._worker_factory = lambda *args: worker
    statuses = []
    ctrl.statusChanged.connect(lambda status: statuses.append((status, ctrl.currentError)))
    ctrl.requestTranslation(0, "English", "Vietnamese", "")
    assert statuses == [("TRANSLATING", "")]
    assert not model.get_item(0).get("translation_error")
    worker.start.assert_called_once()


def test_workspace_displays_error_details_as_plain_wrapped_text(qapp):
    from PySide6.QtCore import QObject
    from ui.pages.translation_studio_page import TranslationStudioPage

    page = TranslationStudioPage()
    try:
        assert not page.quick_widget.errors()
        page.subtitle_model.load_data([
            {"original": "Hello", "translation": "Xin chào", "status": "TRANSLATED"},
            {"original": "Goodbye", "translation": "Tạm biệt", "status": "TRANSLATED"},
        ])
        ctrl = page.translation_controller
        ctrl.loadSubtitle(0)
        ctrl._active_translation_index = 0
        ctrl._status = "TRANSLATING"
        ctrl.on_error(0, "<b>Requested tokens exceed context window</b>")
        qapp.processEvents()
        details = page.quick_widget.rootObject().findChild(QObject, "translationErrorDetails")
        assert details is not None
        assert details.property("text") == ctrl.currentError
        script_object = page.quick_widget.engine().newQObject(details)
        assert script_object.property("textFormat").toInt() == 0  # Text.PlainText
        assert script_object.property("wrapMode").toInt() == 4  # Text.Wrap
        ctrl.loadSubtitle(1)
        assert not details.property("visible")
        ctrl.loadSubtitle(0)
        assert details.property("text") == ctrl.currentError
        assert "context window" in details.property("text")
    finally:
        page.translation_controller.shutdown()
        page.close()
        page.deleteLater()
        qapp.processEvents()
