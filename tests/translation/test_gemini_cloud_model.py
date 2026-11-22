import io
import json
import urllib.error
from unittest.mock import patch

from PySide6.QtQuick import QQuickItem

from core.translation.controllers.model_controller import ModelController
from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.app_settings import AppSettings
from core.translation.core.backends.gemini_backend import GeminiBackend
from core.translation.core.prompt_builder import format_chat
from core.translation.llm.worker import TranslationWorker
from core.translation.models.subtitle import SubtitleModel
from ui.pages.translation_studio_page import TranslationStudioPage


class _FakeHTTPResponse:
    def __init__(self, lines):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return b"".join(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        pass


def test_gemini_backend_list_models_test_connection_and_streaming():
    ok, msg = GeminiBackend.test_connection("")
    assert ok is False
    assert "API Key" in msg

    models_payload = json.dumps({
        "models": [
            {
                "name": "models/gemini-3.8-flash",
                "displayName": "Gemini 3.8 Flash",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-3.1-pro-preview",
                "displayName": "Gemini 3.1 Pro Preview",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/text-embedding-004",
                "displayName": "Embedding",
                "supportedGenerationMethods": ["embedContent"],
            },
        ]
    }).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse([models_payload])):
        ok, msg = GeminiBackend.test_connection("AIzaSecretKey123", "gemini-3.8-flash")
        assert ok is True
        assert "Gemini 3.8 Flash" in msg
        assert "2 model khả dụng" in msg

    err = urllib.error.HTTPError(
        "https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSecretKey123",
        403,
        "Forbidden",
        {},
        io.BytesIO(b'{"error": {"message": "API key not valid"}}'),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        ok, msg = GeminiBackend.test_connection("AIzaSecretKey123")
        assert ok is False
        assert "AIzaSecretKey123" not in msg
        assert "không hợp lệ" in msg

    sse_lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"Internal thought","thought":true}]}}]}\n',
        b'data: {"candidates":[{"content":{"parts":[{"text":"Xin "}]}}]}\n',
        b'data: {"candidates":[{"content":{"parts":[{"text":"ch\xc3\xa0o!"}]}}]}\n',
        b"data: [DONE]\n",
    ]
    backend = GeminiBackend()
    assert backend.load_model("gemini-3.8-flash", api_key="AIzaTest") is True
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(sse_lines)):
        chunks = list(backend.stream("Translate Hello"))
    assert "".join(chunks) == "Xin chào!"


def test_prompt_builder_gemini_plain_format():
    out = format_chat("SYS", "USR", model_family="gemini")
    assert out == "SYS\n\nUSR"
    assert "<|im_start|>" not in out
    assert "<start_of_turn>" not in out


def test_model_controller_gemini_discovery_selection_and_connection_test(qapp, qtbot, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = AppSettings(file_path=str(tmp_path / "settings.json"))
    sub_model = SubtitleModel()
    tc = TranslationController(sub_model)
    mc = ModelController(
        models_dir=str(tmp_path / "models"),
        translation_controller=tc,
        settings=settings,
        gpu_info={"has_gpu_hardware": False, "vram_gb": 0.0, "name": "CPU"},
        llama_has_cuda=False,
    )

    flash_entry = next(m for m in mc.models if m["model_id"] == "gemini-3.8-flash")
    assert flash_entry["is_cloud"] is True
    assert flash_entry["can_download"] is False
    assert flash_entry["can_delete"] is False
    assert flash_entry["can_select"] is False
    assert mc.selectActiveModel("gemini-3.8-flash") is False

    live_models = [
        {"model_id": "gemini-3.8-flash", "display_name": "Gemini 3.8 Flash", "description": "Fast"},
        {"model_id": "gemini-3.1-pro-preview", "display_name": "Gemini 3.1 Pro Preview", "description": "Pro"},
    ]
    with patch.object(GeminiBackend, "list_available_models", return_value=(True, live_models, "")):
        mc.testGeminiConnection("AIzaLiveValidKey")
        qtbot.waitUntil(lambda: not mc.isTestingGemini, timeout=3000)

    assert mc.geminiTestOk is True
    assert mc.geminiApiKey == "AIzaLiveValidKey"
    assert mc.selectActiveModel("gemini-3.1-pro-preview") is True
    assert mc.hasValidModel is True
    assert tc.hardware_profile["backend_type"] == "gemini"
    assert tc.hardware_profile["cloud_model_name"] == "gemini-3.1-pro-preview"
    assert tc._resolve_model_family() == "gemini"


def test_translation_worker_runs_gemini_without_gguf_file():
    sse_lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"Ch\xc3\xa0o bu\xc3\xb4i s\xc3\xa1ng\\n[T\xe1\xbb\xaa G\xe1\xbb\x90C]\\n- Good morning -> Ch\xc3\xa0o bu\xc3\xb4i s\xc3\xa1ng"}]}}]}\n',
    ]
    worker = TranslationWorker(
        0,
        "Translate Good morning",
        {
            "backend_type": "gemini",
            "cloud_model_name": "gemini-3.8-flash",
            "api_key": "AIzaKey",
            "model_path": "",
        },
    )
    finished = []
    errors = []
    worker.finished.connect(lambda idx, txt: finished.append((idx, txt)))
    worker.error.connect(lambda idx, err: errors.append((idx, err)))
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(sse_lines)):
        worker.run()
    assert errors == []
    assert finished == [(0, "Chào buôi sáng")]
    assert worker.extracted_terms == [{"source": "Good morning", "target": "Chào buôi sáng"}]


def test_qml_model_manager_dialog_has_masked_key_and_test_button(qapp, qtbot, tmp_path, monkeypatch):
    page = TranslationStudioPage()
    qtbot.addWidget(page)
    page.resize(1024, 600)
    page.show()
    qtbot.wait(150)

    assert page.quick_widget.errors() == []
    root_obj = page.quick_widget.rootObject()

    def _find(obj, name):
        if obj is None:
            return None
        if obj.objectName() == name:
            return obj
        for child in obj.children():
            found = _find(child, name)
            if found is not None:
                return found
        if isinstance(obj, QQuickItem):
            for child in obj.childItems():
                found = _find(child, name)
                if found is not None:
                    return found
        return None

    panel_obj = _find(root_obj, "geminiApiPanel")
    key_field = _find(root_obj, "geminiApiKeyField")
    toggle_btn = _find(root_obj, "btnToggleGeminiKeyVisibility")
    test_btn = _find(root_obj, "btnTestGeminiConnection")
    assert panel_obj is not None
    assert key_field is not None
    assert toggle_btn is not None
    assert test_btn is not None

    assert panel_obj.property("showApiKey") is False
    assert toggle_btn.property("text") == "Hiện"
    toggle_btn.clicked.emit()
    qtbot.wait(20)
    assert panel_obj.property("showApiKey") is True
    assert toggle_btn.property("text") == "Ẩn"
    toggle_btn.clicked.emit()
    qtbot.wait(20)
    assert panel_obj.property("showApiKey") is False

    isolated_settings = AppSettings(file_path=str(tmp_path / "qml_settings.json"))
    monkeypatch.setattr(page.model_controller, "_settings", isolated_settings)
    key_field.setProperty("text", "AIzaTestQmlKey")
    qtbot.wait(20)

    live_models = [
        {"model_id": "gemini-3.8-flash", "display_name": "Gemini 3.8 Flash", "description": "Fast"},
    ]
    with patch.object(GeminiBackend, "list_available_models", return_value=(True, live_models, "")):
        test_btn.clicked.emit()
        qtbot.waitUntil(lambda: not page.model_controller.isTestingGemini, timeout=3000)

    assert page.model_controller.geminiTestOk is True
    assert "Gemini 3.8 Flash" in page.model_controller.geminiTestStatus
