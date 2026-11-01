import os
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

from core.translation.core.app_settings import AppSettings
from core.translation.core.hardware_detector import HardwareDetector
from core.translation.core.model_catalog import (
    MODEL_CATALOG,
    ModelMetadata,
    calculate_recommendation,
    scan_local_models,
)
from core.translation.services.download_manager import DownloadManager


class ModelController(QObject):
    modelListChanged = Signal()
    activeModelChanged = Signal(str)
    downloadProgress = Signal(str, int, str, str)  # model_id, percent, speed, eta
    downloadFinished = Signal(str)                 # model_id
    downloadFailed = Signal(str, str)              # model_id, error_message
    notify = Signal(str, str)                      # type, message
    vramChanged = Signal()

    def __init__(
        self,
        models_dir: Optional[str] = None,
        translation_controller: Optional[QObject] = None,
        batch_controller: Optional[QObject] = None,
        settings: Optional[AppSettings] = None,
        download_manager: Optional[DownloadManager] = None,
        parent: Optional[QObject] = None,
        gpu_info: Optional[dict] = None,
        llama_has_cuda: Optional[bool] = None,
    ):
        super().__init__(parent)
        self.models_dir = models_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models"
        )
        self._translation_controller = translation_controller
        self._batch_controller = batch_controller
        self._settings = settings or AppSettings()
        self._download_manager = download_manager or DownloadManager(self)

        # Trạng thái tải động {model_id: (percent, speed, eta)}
        self._download_states: Dict[str, tuple] = {}

        # Thông tin phần cứng
        self._gpu_info = gpu_info if gpu_info is not None else HardwareDetector.get_gpu_info()
        self._llama_has_cuda = llama_has_cuda if llama_has_cuda is not None else HardwareDetector.check_llama_cuda_backend()

        # Giám sát VRAM thời gian thực
        self._vram_used = -1.0
        self._vram_total = -1.0
        if self._gpu_info.get("has_gpu_hardware"):
            self._update_vram_usage()
            self._vram_timer = QTimer(self)
            self._vram_timer.setInterval(2000)
            self._vram_timer.timeout.connect(self._update_vram_usage)
            self._vram_timer.start()

        # Kết nối sự kiện DownloadManager
        self._download_manager.downloadProgress.connect(self._on_download_progress)
        self._download_manager.downloadFinished.connect(self._on_download_finished)
        self._download_manager.downloadFailed.connect(self._on_download_failed)

        # Khởi tạo active model id từ settings hoặc fallback thông minh
        self._active_model_id = self._determine_initial_active_model()
        if self._settings.active_model_id != self._active_model_id:
            self._settings.active_model_id = self._active_model_id
        self._apply_active_model_profile()

    def bind_translation_controller(self, controller: QObject) -> None:
        self._translation_controller = controller
        self._apply_active_model_profile()

    def _determine_initial_active_model(self) -> str:
        saved_id = self._settings.active_model_id
        local_models = scan_local_models(self.models_dir)

        # Nếu model đã lưu có sẵn trên đĩa -> dùng luôn
        if saved_id in MODEL_CATALOG and local_models.get(saved_id, False):
            return saved_id

        # Tìm model có sẵn trên đĩa phù hợp nhất
        for model_id, exists in local_models.items():
            if exists and model_id in MODEL_CATALOG:
                return model_id

        # Fallback về recommendation chuẩn nếu chưa tải model nào
        rec_profile = HardwareDetector.get_recommended_profile()
        target_name = rec_profile.get("model_name", "")
        for m_id, meta in MODEL_CATALOG.items():
            if meta.filename == target_name:
                return m_id

        return "qwen2.5-7b-instruct-q4_k_m"

    def _apply_active_model_profile(self) -> None:
        """Cập nhật hardware_profile trong TranslationController khi đổi active model."""
        if not self._translation_controller:
            return

        meta = MODEL_CATALOG.get(self._active_model_id)
        if not meta:
            return

        full_model_path = os.path.join(self.models_dir, meta.filename)

        has_gpu = bool(self._gpu_info.get("has_gpu_hardware")) and self._llama_has_cuda
        vram_gb = float(self._gpu_info.get("vram_gb", 0.0))
        if not has_gpu:
            n_gpu_layers = 0
            backend_status = "CPU Backend"
        elif vram_gb >= meta.min_vram_gb:
            n_gpu_layers = -1
            backend_status = "CUDA Enabled (Full Offload)"
        else:
            # Dynamic layer offloading cho GPU VRAM thấp (RTX 3050 4GB chạy model 8B/9B)
            safe_vram = max(0.5, vram_gb - 0.8)
            model_size_gb = meta.size_bytes / (1024 ** 3)
            ratio = min(1.0, safe_vram / max(1.0, model_size_gb))
            n_gpu_layers = max(8, int(ratio * 40))
            backend_status = f"CUDA Hybrid ({n_gpu_layers} layers on GPU)"

        profile = getattr(self._translation_controller, "hardware_profile", {})
        profile.update({
            "model_name": meta.filename,
            "model_path": full_model_path,
            "n_ctx": meta.recommended_ctx,
            "n_gpu_layers": n_gpu_layers,
            "gpu_info": self._gpu_info,
            "backend_status": backend_status,
        })
        self._translation_controller.hardware_profile = profile

    @Property(bool, notify=modelListChanged)
    def isExecutionLocked(self) -> bool:
        if self._translation_controller and str(getattr(self._translation_controller, "status", "")).upper() == "TRANSLATING":
            return True
        if self._batch_controller and str(getattr(self._batch_controller, "state", "")).upper() == "RUNNING":
            return True
        return False

    @Property(str, notify=activeModelChanged)
    def activeModelId(self) -> str:
        return self._active_model_id

    @Property(str, notify=activeModelChanged)
    def activeModelDisplayName(self) -> str:
        meta = MODEL_CATALOG.get(self._active_model_id)
        return meta.display_name if meta else self._active_model_id

    @Property("QVariantMap", constant=True)
    def hardwareSummary(self) -> dict:
        vram = self._gpu_info.get("vram_gb", 0.0)
        gpu_name = self._gpu_info.get("name", "Unknown")
        return {
            "gpu_name": gpu_name,
            "vram_gb": vram,
            "has_cuda": self._llama_has_cuda,
            "backend_status": "CUDA Acceleration" if self._llama_has_cuda else "CPU Only",
        }

    @Slot()
    def _update_vram_usage(self) -> None:
        used, total = HardwareDetector.get_vram_usage()
        if used >= 0 and total > 0:
            if self._vram_used != used or self._vram_total != total:
                self._vram_used = used
                self._vram_total = total
                self.vramChanged.emit()

    @Property(float, notify=vramChanged)
    def vramUsed(self) -> float:
        return self._vram_used

    @Property(float, notify=vramChanged)
    def vramTotal(self) -> float:
        return self._vram_total

    @Property("QVariantList", notify=modelListChanged)
    def models(self) -> list:
        local_availability = scan_local_models(self.models_dir)
        is_locked = self.isExecutionLocked

        result = []
        for model_id, meta in MODEL_CATALOG.items():
            badge, reason = calculate_recommendation(
                meta, self._gpu_info, self._llama_has_cuda
            )
            is_downloaded = local_availability.get(model_id, False)
            is_downloading = self._download_manager.is_downloading(model_id)
            is_active = (model_id == self._active_model_id)

            download_info = self._download_states.get(model_id, (0, "", ""))

            if is_active:
                status = "ACTIVE"
            elif is_downloading:
                status = "DOWNLOADING"
            elif is_downloaded:
                status = "DOWNLOADED"
            else:
                status = "NOT_DOWNLOADED"

            result.append({
                "model_id": meta.model_id,
                "display_name": meta.display_name,
                "filename": meta.filename,
                "size_gb_formatted": meta.size_gb_formatted,
                "size_formatted": meta.size_gb_formatted,
                "description": meta.description,
                "recommendation": badge,
                "badge": badge,
                "recommendation_reason": reason,
                "reason": reason,
                "status": status,
                "is_downloaded": is_downloaded,
                "is_downloading": is_downloading,
                "is_active": is_active,
                "progress_percent": download_info[0],
                "download_percent": download_info[0],
                "speed": download_info[1],
                "download_speed": download_info[1],
                "eta": download_info[2],
                "download_eta": download_info[2],
                "can_select": is_downloaded and not is_active and not is_locked,
                "can_download": not is_downloaded and not is_downloading and bool(meta.download_url),
                "can_delete": is_downloaded and not is_active and not is_locked,
            })

        # Ghim model đang sử dụng lên đầu tiên, kế đến là đang tải và đã tải về
        result.sort(key=lambda m: (
            0 if m["is_active"] else (
                1 if m["is_downloading"] else (
                    2 if m["is_downloaded"] else (
                        3 if m["recommendation"] == "RECOMMENDED" else 4
                    )
                )
            )
        ))
        return result

    @Slot(str)
    def startDownload(self, model_id: str) -> bool:
        meta = MODEL_CATALOG.get(model_id)
        if not meta or not meta.download_url:
            self.notify.emit("ERROR", "Model không có URL tải trực tiếp.")
            return False

        target_file = os.path.join(self.models_dir, meta.filename)
        success = self._download_manager.start_download(
            model_id=model_id,
            download_url=meta.download_url,
            target_path=target_file,
            expected_size_bytes=meta.size_bytes,
        )
        if success:
            self._download_states[model_id] = (0, "Bắt đầu...", "--")
            self.modelListChanged.emit()
            self.notify.emit("INFO", f"Đang bắt đầu tải: {meta.display_name}")
            return True
        return False

    @Slot(str)
    def cancelDownload(self, model_id: str) -> bool:
        success = self._download_manager.cancel_download(model_id)
        if success:
            self._download_states.pop(model_id, None)
            self.modelListChanged.emit()
            self.notify.emit("WARNING", "Đã hủy tiến trình tải file.")
            return True
        return False

    @Slot(str, result=bool)
    def selectActiveModel(self, model_id: str) -> bool:
        if self.isExecutionLocked:
            self.notify.emit("ERROR", "Không thể đổi model khi tiến trình dịch đang chạy.")
            return False

        meta = MODEL_CATALOG.get(model_id)
        if not meta:
            self.notify.emit("ERROR", "Không tìm thấy thông tin model.")
            return False

        local_models = scan_local_models(self.models_dir)
        if not local_models.get(model_id, False):
            self.notify.emit("ERROR", "Model này chưa được tải về máy.")
            return False

        self._settings.active_model_id = model_id
        if self._active_model_id != model_id:
            # Thu hồi VRAM của model cũ ngay khi người dùng bấm chọn model khác
            try:
                from core.translation.llm.model_manager import ModelManager
                ModelManager.get_instance("llama_cpp").unload_model()
            except Exception:
                pass
            self._active_model_id = model_id
            self._apply_active_model_profile()
            self.activeModelChanged.emit(model_id)
            self.modelListChanged.emit()
            self.notify.emit("SUCCESS", f"Đã chuyển sang mô hình: {meta.display_name}")
        return True

    @Slot(str, result=bool)
    def deleteModelFile(self, model_id: str) -> bool:
        if self.isExecutionLocked:
            self.notify.emit("ERROR", "Không thể xóa file khi tiến trình dịch đang chạy.")
            return False

        if model_id == self._active_model_id:
            self.notify.emit("ERROR", "Không thể xóa model đang được sử dụng làm mặc định.")
            return False

        meta = MODEL_CATALOG.get(model_id)
        if not meta:
            return False

        target_file = os.path.join(self.models_dir, meta.filename)
        if os.path.exists(target_file):
            try:
                os.remove(target_file)
                self.modelListChanged.emit()
                self.notify.emit("SUCCESS", f"Đã xóa file model: {meta.display_name}")
                return True
            except OSError as e:
                self.notify.emit("ERROR", f"Lỗi khi xóa file: {e}")
                return False
        return False

    def _on_download_progress(self, model_id: str, percent: int, speed: str, eta: str):
        self._download_states[model_id] = (percent, speed, eta)
        self.downloadProgress.emit(model_id, percent, speed, eta)

    def _on_download_finished(self, model_id: str, file_path: str):
        self._download_states.pop(model_id, None)
        self.downloadFinished.emit(model_id)
        # Tự động kích hoạt model vừa tải về làm model mặc định
        self.selectActiveModel(model_id)
        self.modelListChanged.emit()
        meta = MODEL_CATALOG.get(model_id)
        name = meta.display_name if meta else model_id
        self.notify.emit("SUCCESS", f"Tải hoàn tất: {name}")

    def _on_download_failed(self, model_id: str, error_message: str):
        self._download_states.pop(model_id, None)
        self.downloadFailed.emit(model_id, error_message)
        self.modelListChanged.emit()
        self.notify.emit("ERROR", f"Tải thất bại: {error_message}")

