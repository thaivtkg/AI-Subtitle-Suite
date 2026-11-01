import os
import time
import urllib.request
from typing import Dict, Optional
from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal


class DownloadWorker(QThread):
    progress = Signal(str, int, str, str)  # model_id, percent, speed_str, eta_str
    finished = Signal(str, str)            # model_id, target_file_path
    error = Signal(str, str)               # model_id, error_message

    def __init__(
        self,
        model_id: str,
        download_url: str,
        target_path: str,
        expected_size_bytes: int = 0,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.model_id = model_id
        self.download_url = download_url
        self.target_path = target_path
        self.expected_size_bytes = expected_size_bytes
        self.part_path = target_path + ".part"
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        self.requestInterruption()

    def run(self):
        if not self.download_url:
            self.error.emit(self.model_id, "Không có URL tải về cho model này.")
            return

        # Đảm bảo thư mục cha tồn tại
        parent_dir = os.path.dirname(self.target_path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except OSError as e:
                self.error.emit(self.model_id, f"Không thể tạo thư mục lưu trữ: {e}")
                return

        # Xóa file .part cũ nếu có
        if os.path.exists(self.part_path):
            try:
                os.remove(self.part_path)
            except OSError:
                pass

        bytes_downloaded = 0
        total_bytes = self.expected_size_bytes
        start_time = time.time()
        last_update_time = start_time
        last_bytes = 0

        try:
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "AISubtitleTranslator/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > 0:
                    total_bytes = int(content_length)

                chunk_size = 64 * 1024  # 64 KB
                with open(self.part_path, "wb") as f:
                    while True:
                        if self._is_cancelled or self.isInterruptionRequested():
                            break

                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        bytes_downloaded += len(chunk)

                        now = time.time()
                        if now - last_update_time >= 0.2:  # Cập nhật UI mỗi 200ms
                            duration = now - last_update_time
                            bytes_delta = bytes_downloaded - last_bytes
                            speed_bps = bytes_delta / duration if duration > 0 else 0
                            speed_mbps = speed_bps / (1024 * 1024)
                            speed_str = f"{speed_mbps:.1f} MB/s"

                            if total_bytes > 0:
                                percent = int((bytes_downloaded / total_bytes) * 100)
                                remaining_bytes = total_bytes - bytes_downloaded
                                eta_sec = int(remaining_bytes / speed_bps) if speed_bps > 0 else 0
                                eta_str = f"{eta_sec}s" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s"
                            else:
                                percent = 0
                                eta_str = "--"

                            self.progress.emit(self.model_id, min(percent, 99), speed_str, eta_str)
                            last_update_time = now
                            last_bytes = bytes_downloaded

        except Exception as e:
            self._cleanup_part_file()
            if not self._is_cancelled:
                self.error.emit(self.model_id, f"Lỗi tải file: {str(e)}")
            return

        if self._is_cancelled or self.isInterruptionRequested():
            self._cleanup_part_file()
            return

        # Xác thực dung lượng file khi hoàn tất 100%
        actual_size = os.path.getsize(self.part_path) if os.path.exists(self.part_path) else 0
        if total_bytes > 0 and actual_size != total_bytes:
            self._cleanup_part_file()
            self.error.emit(
                self.model_id,
                f"Kích thước file không khớp (nhận {actual_size} bytes, kỳ vọng {total_bytes} bytes).",
            )
            return

        # Atomic rename từ .part sang .gguf
        try:
            os.replace(self.part_path, self.target_path)
            self.progress.emit(self.model_id, 100, "Hoàn tất", "0s")
            self.finished.emit(self.model_id, self.target_path)
        except OSError as e:
            self._cleanup_part_file()
            self.error.emit(self.model_id, f"Lỗi ghi file vào thư mục models: {e}")

    def _cleanup_part_file(self):
        if os.path.exists(self.part_path):
            try:
                os.remove(self.part_path)
            except OSError:
                pass


class DownloadManager(QObject):
    downloadProgress = Signal(str, int, str, str)  # model_id, percent, speed, eta
    downloadFinished = Signal(str, str)            # model_id, file_path
    downloadFailed = Signal(str, str)              # model_id, error_message

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._workers: Dict[str, DownloadWorker] = {}
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self):
        for worker in list(self._workers.values()):
            if worker.isRunning():
                worker.cancel()
                worker.wait(2000)
        self._workers.clear()

    def start_download(
        self,
        model_id: str,
        download_url: str,
        target_path: str,
        expected_size_bytes: int = 0,
    ) -> bool:
        if self.is_downloading(model_id):
            return False

        worker = DownloadWorker(
            model_id=model_id,
            download_url=download_url,
            target_path=target_path,
            expected_size_bytes=expected_size_bytes,
        )
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        self._workers[model_id] = worker
        worker.start()
        return True

    def cancel_download(self, model_id: str) -> bool:
        worker = self._workers.get(model_id)
        if worker is not None:
            worker.cancel()
            worker.wait(2000)
            self._workers.pop(model_id, None)
            return True
        return False

    def is_downloading(self, model_id: str) -> bool:
        worker = self._workers.get(model_id)
        return worker is not None and worker.isRunning()

    def _on_progress(self, model_id: str, percent: int, speed: str, eta: str):
        self.downloadProgress.emit(model_id, percent, speed, eta)

    def _on_finished(self, model_id: str, file_path: str):
        worker = self._workers.get(model_id)
        if worker is not None:
            worker.wait(2000)
            self._workers.pop(model_id, None)
        self.downloadFinished.emit(model_id, file_path)

    def _on_error(self, model_id: str, error_message: str):
        worker = self._workers.get(model_id)
        if worker is not None:
            worker.wait(2000)
            self._workers.pop(model_id, None)
        self.downloadFailed.emit(model_id, error_message)
