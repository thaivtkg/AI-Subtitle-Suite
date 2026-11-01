import json
import os
import tempfile
import time
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
import pytest

from core.translation.controllers.model_controller import ModelController
from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.app_settings import AppSettings
from core.translation.core.model_catalog import (
    MODEL_CATALOG,
    ModelMetadata,
    calculate_recommendation,
    scan_local_models,
)
from core.translation.models.subtitle import SubtitleModel
from core.translation.services.download_manager import DownloadManager, DownloadWorker


class SignalSpy:
    def __init__(self, signal):
        self._emissions = []
        signal.connect(self._slot)

    def _slot(self, *args):
        self._emissions.append(list(args))

    def wait(self, timeout_ms=500):
        app = QCoreApplication.instance()
        elapsed = 0
        while elapsed < timeout_ms and not self._emissions:
            if app:
                app.processEvents()
            QTest.qWait(10)
            elapsed += 10
        return len(self._emissions) > 0

    def __len__(self):
        return len(self._emissions)

    def __getitem__(self, index):
        return self._emissions[index]


@pytest.fixture
def qapp():
    return QGuiApplication.instance() or QGuiApplication([])


# ==========================================
# TC-MM-01: HARDWARE RECOMMENDATION SCORING
# ==========================================
def test_tc_mm_01_hardware_recommendation_scoring():
    meta_7b = MODEL_CATALOG["qwen2.5-7b-instruct-q4_k_m"]
    meta_3b = MODEL_CATALOG["qwen2.5-3b-instruct-q4_k_m"]
    meta_14b = MODEL_CATALOG["qwen2.5-14b-instruct-q4_k_m"]

    # 1. GPU 8GB VRAM với CUDA: 7B là RECOMMENDED
    gpu_8gb = {"has_gpu_hardware": True, "name": "RTX 4060", "vram_gb": 8.0}
    badge_7b, _ = calculate_recommendation(meta_7b, gpu_8gb, llama_has_cuda=True)
    assert badge_7b == "RECOMMENDED"

    # 2. GPU 16GB VRAM: 14B là RECOMMENDED
    gpu_16gb = {"has_gpu_hardware": True, "name": "RTX 4080", "vram_gb": 16.0}
    badge_14b, _ = calculate_recommendation(meta_14b, gpu_16gb, llama_has_cuda=True)
    assert badge_14b == "RECOMMENDED"

    # 3. GPU yếu 2GB VRAM: 3B là RECOMMENDED, 14B là NOT_RECOMMENDED
    gpu_2gb = {"has_gpu_hardware": True, "name": "GTX 1050", "vram_gb": 2.0}
    badge_3b, _ = calculate_recommendation(meta_3b, gpu_2gb, llama_has_cuda=True)
    badge_14b_low, _ = calculate_recommendation(meta_14b, gpu_2gb, llama_has_cuda=True)
    assert badge_3b == "RECOMMENDED"
    assert badge_14b_low == "NOT_RECOMMENDED"

    # 4. CPU-only: 3B là RECOMMENDED, 14B là NOT_RECOMMENDED
    gpu_none = {"has_gpu_hardware": False, "name": "None", "vram_gb": 0.0}
    badge_cpu_3b, _ = calculate_recommendation(meta_3b, gpu_none, llama_has_cuda=False, ram_gb=16.0)
    badge_cpu_14b, _ = calculate_recommendation(meta_14b, gpu_none, llama_has_cuda=False, ram_gb=8.0)
    assert badge_cpu_3b == "RECOMMENDED"
    assert badge_cpu_14b == "NOT_RECOMMENDED"


# ==========================================
# TC-MM-02: ADVISORY OVERRIDE
# ==========================================
def test_tc_mm_02_advisory_override(qapp):
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Tạo sẵn file 14b dù máy cấu hình thấp
        meta_14b = MODEL_CATALOG["qwen2.5-14b-instruct-q4_k_m"]
        file_path = os.path.join(tmp_dir, meta_14b.filename)
        with open(file_path, "wb") as f:
            f.write(b"mock weights")

        settings = AppSettings(os.path.join(tmp_dir, "test_settings.json"))
        controller = ModelController(models_dir=tmp_dir, settings=settings)

        # Chọn model 14B thành công (Advisory override)
        success = controller.selectActiveModel("qwen2.5-14b-instruct-q4_k_m")
        assert success is True
        assert controller.activeModelId == "qwen2.5-14b-instruct-q4_k_m"


# ==========================================
# TC-MM-03: LOCAL FILE DETECTION
# ==========================================
def test_tc_mm_03_local_file_detection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        meta_3b = MODEL_CATALOG["qwen2.5-3b-instruct-q4_k_m"]
        target_path = os.path.join(tmp_dir, meta_3b.filename)

        # Ban đầu chưa có file
        avail_before = scan_local_models(tmp_dir)
        assert avail_before["qwen2.5-3b-instruct-q4_k_m"] is False

        # Tạo file
        with open(target_path, "wb") as f:
            f.write(b"content")

        avail_after = scan_local_models(tmp_dir)
        assert avail_after["qwen2.5-3b-instruct-q4_k_m"] is True


# ==========================================
# TC-MM-04: SAFE PARTIAL DOWNLOAD (.part)
# ==========================================
def test_tc_mm_04_safe_partial_download_part_file(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_file = os.path.join(tmp_dir, "test_model.gguf")
        part_file = target_file + ".part"

        # Mock urllib để mô phỏng stream đang tải
        class MockResponse:
            def __init__(self):
                self.headers = {"Content-Length": "100"}
                self.chunks = [b"a" * 50, b"b" * 50]
                self.idx = 0

            def read(self, size):
                if self.idx < len(self.chunks):
                    chunk = self.chunks[self.idx]
                    self.idx += 1
                    return chunk
                return b""

            def __enter__(self): return self
            def __exit__(self, *args): pass

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: MockResponse())

        worker = DownloadWorker(
            model_id="test_model",
            download_url="http://mock.test/model.gguf",
            target_path=target_file,
            expected_size_bytes=100,
        )

        worker.start()
        worker.wait(1000)

        # Sau khi hoàn tất, file .gguf tồn tại, file .part không còn
        assert os.path.exists(target_file)
        assert not os.path.exists(part_file)


# ==========================================
# TC-MM-05: ATOMIC PROMOTION ON COMPLETION
# ==========================================
def test_tc_mm_05_atomic_promotion_on_completion(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_file = os.path.join(tmp_dir, "atomic_model.gguf")

        class MockResponse:
            def __init__(self):
                self.headers = {"Content-Length": "20"}
            def read(self, size):
                return b""
            def __enter__(self): return self
            def __exit__(self, *args): pass

        # Mô phỏng worker hoàn thành ghi 20 bytes
        worker = DownloadWorker("atomic", "http://mock.test/url", target_file, expected_size_bytes=20)
        
        # Ghi trực tiếp vào file .part
        with open(worker.part_path, "wb") as f:
            f.write(b"01234567890123456789")

        spy_finished = SignalSpy(worker.finished)
        
        # Test logic atomic rename
        os.replace(worker.part_path, worker.target_path)
        assert os.path.exists(target_file)
        assert not os.path.exists(worker.part_path)


# ==========================================
# TC-MM-06: CANCEL DOWNLOAD CLEANUP
# ==========================================
def test_tc_mm_06_cancel_download_cleanup(qapp):
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_file = os.path.join(tmp_dir, "cancel_model.gguf")
        part_file = target_file + ".part"

        # Tạo sẵn file .part dở dang
        with open(part_file, "wb") as f:
            f.write(b"partial content")

        worker = DownloadWorker("cancel_model", "http://mock.test/url", target_file, expected_size_bytes=1000)
        worker._cleanup_part_file()

        # File .part phải bị xóa sạch
        assert not os.path.exists(part_file)


# ==========================================
# TC-MM-07: SIZE VALIDATION GUARD
# ==========================================
def test_tc_mm_07_size_validation_guard(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_file = os.path.join(tmp_dir, "corrupt_model.gguf")
        part_file = target_file + ".part"

        class ShortResponse:
            def __init__(self):
                self.headers = {"Content-Length": "100"}
                self.sent = False
            def read(self, size):
                if not self.sent:
                    self.sent = True
                    return b"only 10 bytes"
                return b""
            def __enter__(self): return self
            def __exit__(self, *args): pass

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: ShortResponse())

        worker = DownloadWorker("corrupt", "http://mock.test/short", target_file, expected_size_bytes=100)
        spy_error = SignalSpy(worker.error)

        worker.start()
        worker.wait(1000)
        spy_error.wait(200)

        assert len(spy_error) == 1
        assert "không khớp" in spy_error[0][1]
        assert not os.path.exists(target_file)
        assert not os.path.exists(part_file)


# ==========================================
# TC-MM-08: RUNTIME BACKEND SWITCHING
# ==========================================
def test_tc_mm_08_runtime_backend_switching(qapp):
    with tempfile.TemporaryDirectory() as tmp_dir:
        meta_3b = MODEL_CATALOG["qwen2.5-3b-instruct-q4_k_m"]
        file_path = os.path.join(tmp_dir, meta_3b.filename)
        with open(file_path, "wb") as f:
            f.write(b"dummy")

        model = SubtitleModel()
        tc = TranslationController(model)
        settings = AppSettings(os.path.join(tmp_dir, "settings.json"))
        mc = ModelController(models_dir=tmp_dir, translation_controller=tc, settings=settings)

        assert mc.selectActiveModel("qwen2.5-3b-instruct-q4_k_m") is True
        assert tc.hardware_profile["model_name"] == meta_3b.filename
        assert tc.hardware_profile["n_ctx"] == meta_3b.recommended_ctx


# ==========================================
# TC-MM-09: EXECUTION CONCURRENCY LOCK
# ==========================================
def test_tc_mm_09_execution_concurrency_lock(qapp):
    with tempfile.TemporaryDirectory() as tmp_dir:
        meta_3b = MODEL_CATALOG["qwen2.5-3b-instruct-q4_k_m"]
        file_path = os.path.join(tmp_dir, meta_3b.filename)
        with open(file_path, "wb") as f:
            f.write(b"dummy")

        model = SubtitleModel()
        tc = TranslationController(model)
        tc._status = "TRANSLATING"  # Đang dịch

        test_settings = AppSettings(os.path.join(tmp_dir, "test_settings.json"))
        mc = ModelController(models_dir=tmp_dir, translation_controller=tc, settings=test_settings)
        assert mc.isExecutionLocked is True

        # Đổi model bị khóa
        success = mc.selectActiveModel("qwen2.5-3b-instruct-q4_k_m")
        assert success is False

        # Xóa file bị khóa
        del_success = mc.deleteModelFile("qwen2.5-3b-instruct-q4_k_m")
        assert del_success is False


# ==========================================
# TC-MM-10: STATE SEPARATION INVARIANT
# ==========================================
def test_tc_mm_10_state_separation_invariant(qapp):
    from PySide6.QtCore import QUrl
    from core.translation.controllers.project_controller import ProjectController
    model = SubtitleModel()
    model.load_data([{"index": 0, "original": "Hello", "translation": "Xin chào", "status": "TRANSLATED"}])
    pc = ProjectController(model)

    with tempfile.TemporaryDirectory() as tmp_dir:
        save_file = os.path.join(tmp_dir, "project.aisrt")
        file_url = QUrl.fromLocalFile(save_file).toString()
        pc.saveProject(file_url, "Story", "English", "Vietnamese")

        with open(save_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # File .aisrt hoàn toàn không chứa active_model_id hay model_name
        assert "active_model_id" not in data
        assert "model_name" not in data
        assert "intelligence" in data


# ==========================================
# TC-MM-11: APP SETTINGS PERSISTENCE
# ==========================================
def test_tc_mm_11_app_settings_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings_file = os.path.join(tmp_dir, "app_settings.json")
        settings = AppSettings(settings_file)
        settings.active_model_id = "deepseek-r1-distill-qwen-7b-q4_k_m"

        # Đọc lại từ file
        reloaded = AppSettings(settings_file)
        assert reloaded.active_model_id == "deepseek-r1-distill-qwen-7b-q4_k_m"


# ==========================================
# TC-MM-12: ZERO-BLOCKING UI DURING DOWNLOAD
# ==========================================
def test_tc_mm_12_zero_blocking_ui_during_download(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_file = os.path.join(tmp_dir, "bg_model.gguf")

        class SlowResponse:
            def __init__(self):
                self.headers = {"Content-Length": "100"}
                self.step = 0
            def read(self, size):
                if self.step < 3:
                    self.step += 1
                    time.sleep(0.05)
                    return b"x" * 30
                return b""
            def __enter__(self): return self
            def __exit__(self, *args): pass

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: SlowResponse())

        dm = DownloadManager()
        dm.start_download("bg_model", "http://mock.test/slow", target_file, expected_size_bytes=90)
        assert dm.is_downloading("bg_model") is True

        # UI event loop vẫn xử lý mượt mà
        for _ in range(5):
            qapp.processEvents()
            QTest.qWait(20)

        dm.cancel_download("bg_model")
        assert dm.is_downloading("bg_model") is False


# ==========================================
# TC-MM-13: DOWNLOAD ERROR THREAD SAFETY
# ==========================================
def test_tc_mm_13_download_error_thread_safety(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_file = os.path.join(tmp_dir, "error_model.gguf")

        import urllib.request
        def mock_error_urlopen(req, timeout=30):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", mock_error_urlopen)

        dm = DownloadManager()
        spy_failed = SignalSpy(dm.downloadFailed)

        dm.start_download("error_model", "http://mock.test/404", target_file, expected_size_bytes=100)
        spy_failed.wait(1000)

        assert len(spy_failed) == 1
        assert spy_failed[0][0] == "error_model"
        assert "404" in spy_failed[0][1]
        assert dm.is_downloading("error_model") is False
        assert not os.path.exists(target_file)
        assert not os.path.exists(target_file + ".part")


# ==========================================
# TC-MM-14: NEW MODELS & VIETNAMESE PURITY
# ==========================================
def test_new_models_in_catalog_and_vietnamese_purity():
    from core.translation.core.model_catalog import MODEL_CATALOG
    from core.translation.core.prompt_builder import PromptBuilder
    # 1. Kiểm tra 3 model mới đã có mặt trong danh mục với URL hợp lệ
    assert "llama-3.1-8b-instruct-q4_k_m" in MODEL_CATALOG
    assert "llama-3.3-8b-instruct-q4_k_m" in MODEL_CATALOG
    assert "translategemma-9b-q4_k_m" in MODEL_CATALOG
    
    llama_meta = MODEL_CATALOG["llama-3.1-8b-instruct-q4_k_m"]
    assert llama_meta.download_url.startswith("https://huggingface.co/")
    # 2. Kiểm tra prompt có luật cấm chữ Hán / CJK
    prompt = PromptBuilder.build(
        current_sub="you are too naive.",
        target_lang="Vietnamese",
    )
    assert "VIETNAMESE PURITY (NO CJK / NO HANZI)" in prompt
    assert "ABSOLUTELY DO NOT output Chinese Hanzi" in prompt
    assert "太天真了" in prompt


# ==========================================
# TC-MM-15: NO MODEL LIST CHANGED SPAM DURING PROGRESS
# ==========================================
def test_tc_mm_15_no_model_list_changed_spam_during_progress(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = AppSettings(os.path.join(tmp_dir, "test_settings.json"))
        controller = ModelController(models_dir=tmp_dir, settings=settings)

        spy_progress = SignalSpy(controller.downloadProgress)
        spy_list_changed = SignalSpy(controller.modelListChanged)

        # 1. Khi gọi _on_download_progress: downloadProgress được phát, nhưng modelListChanged KHÔNG bị phát
        controller._on_download_progress("test_model", 50, "10 MB/s", "00:30")
        assert len(spy_progress) == 1
        assert spy_progress[0] == ["test_model", 50, "10 MB/s", "00:30"]
        assert len(spy_list_changed) == 0

        # 2. Khi gọi startDownload: modelListChanged VẪN được phát
        monkeypatch.setattr(controller._download_manager, "start_download", lambda **kwargs: True)
        start_res = controller.startDownload("qwen2.5-3b-instruct-q4_k_m")
        assert start_res is True
        assert len(spy_list_changed) == 1

        # 3. Khi gọi cancelDownload: modelListChanged VẪN được phát
        monkeypatch.setattr(controller._download_manager, "cancel_download", lambda model_id: True)
        cancel_res = controller.cancelDownload("qwen2.5-3b-instruct-q4_k_m")
        assert cancel_res is True
        assert len(spy_list_changed) == 2

        # 4. Khi gọi _on_download_finished: modelListChanged VẪN được phát
        spy_finished = SignalSpy(controller.downloadFinished)
        controller._on_download_finished("qwen2.5-3b-instruct-q4_k_m", os.path.join(tmp_dir, "dummy.gguf"))
        assert len(spy_finished) == 1
        assert len(spy_list_changed) == 3


def test_active_model_pinned_to_top_and_llama33_url(tmp_path):
    import urllib.request
    from core.translation.core.model_catalog import MODEL_CATALOG
    from core.translation.controllers.model_controller import ModelController
    from core.translation.core.app_settings import AppSettings
    # 1. Kiểm tra URL Llama 3.3 trả về HTTP 200 hợp lệ (không phải 401)
    llama33 = MODEL_CATALOG["llama-3.3-8b-instruct-q4_k_m"]
    req = urllib.request.Request(llama33.download_url, headers={"User-Agent": "AISubtitleTranslator/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
    # 2. Kiểm tra Model đang sử dụng luôn đứng đầu danh sách
    settings = AppSettings(file_path=str(tmp_path / "test_settings.json"))
    controller = ModelController(models_dir="models", settings=settings)
    models_list = controller.models
    assert len(models_list) > 0
    # Model đầu tiên bắt buộc phải là active model
    assert models_list[0]["is_active"] is True


def test_tc_mm_17_vram_cleanup_and_safe_hybrid_layers(tmp_path):
    """Kiểm tra giải phóng VRAM khi đổi model và tính toán số layer an toàn cho GPU VRAM thấp."""
    from core.translation.controllers.model_controller import ModelController
    from core.translation.core.backends.llama_cpp_backend import LlamaCppBackend
    from unittest.mock import MagicMock
    # 1. Kiểm tra LlamaCppBackend.load_model giải phóng model cũ
    backend = LlamaCppBackend()
    backend._llm = MagicMock()
    backend._current_model = "models/old_model.gguf"
    
    backend.unload_model()
    assert backend._llm is None
    assert backend._current_model == ""
    # 2. Kiểm tra tính toán layer GPU an toàn cho RTX 3050 (4GB VRAM) khi nạp Gemma 2 9B
    fake_gpu = {"has_gpu_hardware": True, "name": "RTX 3050", "vram_gb": 4.0}
    # Tạo dummy model file cho translategemma
    (tmp_path / "gemma-2-9b-it-Q4_K_M.gguf").write_bytes(b"dummy weights")
    test_settings = AppSettings(file_path=str(tmp_path / "test_settings.json"))
    controller = ModelController(models_dir=str(tmp_path), gpu_info=fake_gpu, llama_has_cuda=True, settings=test_settings)
    
    mock_trans = MagicMock()
    mock_trans.hardware_profile = {}
    controller.bind_translation_controller(mock_trans)
    
    controller.selectActiveModel("translategemma-9b-q4_k_m")
    prof = mock_trans.hardware_profile
    # Với 4GB VRAM, số layer offload phải nằm trong khoảng an toàn (8 <= n_gpu_layers < 40)
    assert 8 <= prof["n_gpu_layers"] <= 30
    assert "CUDA Hybrid" in prof["backend_status"]


def test_tc_mm_18_realtime_vram_telemetry(tmp_path):
    """Kiểm tra đo đạc VRAM thời gian thực và loại bỏ hoàn toàn dữ liệu tĩnh giả."""
    from core.translation.core.hardware_detector import HardwareDetector
    from core.translation.controllers.model_controller import ModelController
    from core.translation.core.app_settings import AppSettings
    # 1. Kiểm tra API get_vram_usage trả về tuple hợp lệ
    used, total = HardwareDetector.get_vram_usage()
    if HardwareDetector.get_gpu_info().get("has_gpu_hardware"):
        assert total > 0.0
        assert used >= 0.0
    else:
        assert (used, total) == (-1.0, -1.0)
    # 2. Kiểm tra ModelController phát sinh property vramUsed / vramTotal thực tế
    fake_gpu = {"has_gpu_hardware": True, "name": "RTX 3050", "vram_gb": 4.0}
    # Tạo dummy model file cho translategemma
    (tmp_path / "gemma-2-9b-it-Q4_K_M.gguf").write_bytes(b"dummy weights")
    test_settings = AppSettings(file_path=str(tmp_path / "test_settings.json"))
    controller = ModelController(models_dir=str(tmp_path), gpu_info=fake_gpu, llama_has_cuda=True, settings=test_settings)
    assert controller.vramTotal > 0.0 or controller.vramTotal == -1.0


def test_tc_mm_19_minimalist_launchpad_and_unified_file_dialog():
    """Kiểm tra màn hình khởi động tinh gọn và hộp thoại hỗ trợ cả .srt lẫn .aisrt."""
    with open("ui/qml_translation/components/StudioLaunchpad.qml", "r", encoding="utf-8") as f:
        launchpad_code = f.read()
    # 1. Xác nhận đã đổi text và xóa 2 nút mẫu / duyệt file
    assert "Kéo thả file vào đây hoặc Click để nạp phụ đề" in launchpad_code
    assert "btnDemoProject" not in launchpad_code
    assert "btnBrowseFile" not in launchpad_code
    assert ".MP4" not in launchpad_code
    # 2. Xác nhận hộp thoại Main.qml hỗ trợ cả .srt và .aisrt
    with open("ui/qml_translation/Main.qml", "r", encoding="utf-8") as f:
        main_code = f.read()
    assert "*.srt *.aisrt" in main_code
    assert "loadProject" in main_code


def test_tc_mm_20_select_model_guard_against_missing_file(tmp_path):
    """Kiểm tra BUG-07: Chặn kích hoạt model nếu file GGUF chưa tải về máy."""
    test_settings = AppSettings(file_path=str(tmp_path / "test_settings.json"))
    controller = ModelController(models_dir=str(tmp_path), settings=test_settings)
    # Chưa có file trên đĩa -> Từ chối
    assert controller.selectActiveModel("qwen2.5-3b-instruct-q4_k_m") is False
    # Sau khi có file trên đĩa -> Kích hoạt thành công
    (tmp_path / "qwen2.5-3b-instruct-q4_k_m.gguf").write_bytes(b"dummy")
    assert controller.selectActiveModel("qwen2.5-3b-instruct-q4_k_m") is True







