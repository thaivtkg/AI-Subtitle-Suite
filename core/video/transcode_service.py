# -*- coding: utf-8 -*-
"""
core/video/transcode_service.py
Dịch vụ chuyển đổi ngầm sang MP4 Fast-Seek (< 50ms seek latency).
Đặc tả kỹ thuật:
- Chuẩn hóa: H.264 (libx264) + AAC (aac), GOP = 1 giây (-g 25 -keyint_min 25 -sc_threshold 0), +faststart.
- Chạy ngầm qua QThread tách biệt hoàn toàn khỏi Main Thread.
- Tự động nạp cache dựa trên Hash (Path + mtime + size) để đạt tốc độ nạp < 50ms khi mở lại.
- Hỗ trợ Hot-swap nguồn phát tức thì khi chuyển đổi hoàn tất.
"""

import hashlib
import os
import subprocess
import tempfile
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from core.runtime.runtime_paths import RuntimePaths


def is_transcode_needed(video_path: str) -> bool:
    """Kiểm tra video có thuộc định dạng cần tối ưu Fast-Seek hay không."""
    if not video_path:
        return False
    lower = str(video_path).lower()
    # Các định dạng container / codec gặp vấn đề về seek hoặc GOP quá lớn
    problematic_exts = (".wmv", ".asf", ".avi", ".mkv", ".flv", ".ts", ".m2ts", ".vob", ".webm")
    if lower.endswith(problematic_exts):
        return True
    if os.path.isfile(video_path):
        # Kiểm tra magic header của WMV/ASF
        try:
            with open(video_path, "rb") as f:
                header = f.read(16)
                if header == b"\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa\x00\x62\xce\x6c":
                    return True
        except Exception:
            pass
    return False


def get_transcode_cache_path(video_path: str) -> str:
    """Xác định đường dẫn file cache MP4 Fast-Seek tương ứng."""
    if not video_path or not os.path.exists(video_path):
        return ""
    stat = os.stat(video_path)
    key = f"{os.path.abspath(video_path)}:{stat.st_mtime}:{stat.st_size}"
    file_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    cache_dir = os.path.join(tempfile.gettempdir(), "ai_subtitle_suite", "fast_seek_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{base_name}_{file_hash}_fastseek.mp4").replace("\\", "/")


def get_cached_transcode(video_path: str) -> Optional[str]:
    """Kiểm tra xem đã có bản transcode hoàn chỉnh trong cache hay chưa."""
    cache_path = get_transcode_cache_path(video_path)
    if cache_path and os.path.isfile(cache_path) and os.path.getsize(cache_path) > 1024:
        return cache_path
    return None


class TranscodeWorker(QThread):
    """Worker chạy ngầm FFmpeg để chuyển đổi video sang Fast-Seek MP4."""
    transcode_started = Signal(str)
    transcode_finished = Signal(str, str)  # (original_path, transcoded_path)
    transcode_failed = Signal(str, str)    # (original_path, error_message)

    def __init__(self, input_path: str, output_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path or get_transcode_cache_path(input_path)
        self._is_cancelled = False
        self._process: Optional[subprocess.Popen] = None

    def cancel(self):
        self._is_cancelled = True
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass

    def run(self):
        if not self.input_path or not os.path.exists(self.input_path):
            self.transcode_failed.emit(self.input_path, "File không tồn tại")
            return

        # 1. Kiểm tra cache có sẵn
        cached = get_cached_transcode(self.input_path)
        if cached and os.path.abspath(cached) == os.path.abspath(self.output_path):
            self.transcode_finished.emit(self.input_path, cached)
            return

        part_output = self.output_path + ".part"
        ffmpeg_exe = RuntimePaths.get_ffmpeg_exe()

        # Cấu hình FFmpeg: H.264 + AAC, GOP = 1 giây (25 frame), +faststart
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", self.input_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-g", "25",
            "-keyint_min", "25",
            "-sc_threshold", "0",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-f", "mp4",
            part_output,
        ]

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        self.transcode_started.emit(self.input_path)
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
            )
            _, stderr = self._process.communicate()
            if self._is_cancelled:
                if os.path.exists(part_output):
                    try:
                        os.remove(part_output)
                    except Exception:
                        pass
                return

            if self._process.returncode == 0 and os.path.exists(part_output) and os.path.getsize(part_output) > 1024:
                if os.path.exists(self.output_path):
                    try:
                        os.remove(self.output_path)
                    except Exception:
                        pass
                os.rename(part_output, self.output_path)
                self.transcode_finished.emit(self.input_path, self.output_path)
            else:
                err_msg = stderr.decode("utf-8", errors="ignore") if stderr else f"Exit code {self._process.returncode}"
                if os.path.exists(part_output):
                    try:
                        os.remove(part_output)
                    except Exception:
                        pass
                self.transcode_failed.emit(self.input_path, err_msg)
        except Exception as e:
            if os.path.exists(part_output):
                try:
                    os.remove(part_output)
                except Exception:
                    pass
            self.transcode_failed.emit(self.input_path, str(e))
