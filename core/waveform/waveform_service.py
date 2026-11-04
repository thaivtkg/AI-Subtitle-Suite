import os
import subprocess
import hashlib
import numpy as np
from pathlib import Path
from core.runtime.runtime_paths import RuntimePaths

class WaveformService:
    """[S8-T01 -> T03] Xử lý trích xuất, giảm độ phân giải và lưu Cache Sóng âm"""
    SAMPLE_RATE = 8000  # 8kHz Mono là quá đủ để vẽ biên độ âm thanh
    CHUNK_MS = 10       # Độ phân giải: 10ms mỗi bucket (100 điểm ảnh/giây)

    @staticmethod
    def get_source_fingerprint(file_path: str) -> str:
        """[S8-T11] Băm (Hash) đường dẫn, dung lượng và thời gian sửa đổi để làm Key Cache"""
        if not os.path.exists(file_path):
            raise FileNotFoundError("Không tìm thấy video nguồn.")
        stat = os.stat(file_path)
        unique_string = f"{os.path.abspath(file_path)}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    @staticmethod
    def generate_waveform_peaks(video_path: str, force_rebuild=False) -> np.ndarray:
        """
        Trích xuất PCM qua FFmpeg stdout -> Chuyển đổi thành mảng Min/Max Normalized.
        Trả về: numpy.ndarray shape (N, 2) chứa [min_peak, max_peak] dạng float32 (-1.0 đến 1.0)
        """
        fingerprint = WaveformService.get_source_fingerprint(video_path)
        
        # Lưu cache tại %LOCALAPPDATA%\AI Subtitle Studio\cache\waveforms
        cache_dir = RuntimePaths.get_user_data_dir() / "cache" / "waveforms"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{fingerprint}.npy"

        if cache_file.exists() and not force_rebuild:
            try:
                return np.load(str(cache_file))
            except Exception as e:
                print(f"[Waveform] Cache lỗi ({e}), đang tiến hành tạo lại...")

        ffmpeg_exe = RuntimePaths.get_ffmpeg_exe()
        
        # Trích xuất âm thanh, ép về 16-bit Mono 8000Hz và đẩy thẳng ra Stdout (Không lưu file rác)
        cmd = [
            ffmpeg_exe, "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", str(WaveformService.SAMPLE_RATE),
            "-ac", "1", "-f", "s16le", "-"
        ]

        print("[Waveform] Đang trích xuất và tính toán biên độ âm thanh...")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw_audio, _ = process.communicate()

        if not raw_audio or len(raw_audio) == 0:
            # Fallback an toàn cho video câm (không có audio track) hoặc rỗng
            dummy_peaks = np.zeros((100, 2), dtype=np.float32)
            np.save(str(cache_file), dummy_peaks)
            return dummy_peaks

        # Đọc luồng byte thẳng vào mảng Numpy RAM
        audio_data = np.frombuffer(raw_audio, dtype=np.int16)

        # Tính toán Chunk (Số mẫu trên mỗi 10ms)
        samples_per_chunk = int(WaveformService.SAMPLE_RATE * (WaveformService.CHUNK_MS / 1000.0))
        num_chunks = len(audio_data) // samples_per_chunk

        if num_chunks == 0:
            # Fallback an toàn cho video quá ngắn
            dummy_peaks = np.zeros((100, 2), dtype=np.float32)
            np.save(str(cache_file), dummy_peaks)
            return dummy_peaks

        # Cắt gọt mảng cho vừa khít số lượng Chunk và Reshape thành ma trận 2D
        audio_data = audio_data[:num_chunks * samples_per_chunk]
        audio_chunks = audio_data.reshape(-1, samples_per_chunk)

        # Trích xuất điểm cực tiểu, cực đại trên trục 1 (Rất nhanh nhờ hàm C lõi của Numpy)
        min_peaks = np.min(audio_chunks, axis=1)
        max_peaks = np.max(audio_chunks, axis=1)

        # Gộp lại và Normalize (Chuẩn hóa) biên độ về dạng -1.0 đến 1.0
        peaks = np.column_stack((min_peaks, max_peaks))
        peaks_normalized = (peaks / 32768.0).astype(np.float32)

        # Ghi Cache Binary để tái sử dụng tức thì cho lần mở Project sau
        np.save(str(cache_file), peaks_normalized)
        return peaks_normalized

    @staticmethod
    def build_vad_density_from_intervals(duration_ms: int, speech_intervals: list, chunk_ms: int = 10) -> np.ndarray:
        """FR-04: Xây dựng mảng xác suất giọng nói VAD 10ms từ danh sách intervals"""
        num_chunks = max(1, int(duration_ms / float(chunk_ms)))
        vad_array = np.full(num_chunks, 0.1, dtype=np.float32)
        for interval in speech_intervals:
            s_raw = interval.get("start_ms", interval.get("start", 0))
            e_raw = interval.get("end_ms", interval.get("end", 0))
            start_ms = int(s_raw * 1000 if isinstance(s_raw, float) and s_raw < 10000 else s_raw)
            end_ms = int(e_raw * 1000 if isinstance(e_raw, float) and e_raw < 10000 else e_raw)
            if end_ms <= start_ms:
                continue
            trans_start = max(0, int((start_ms - 100) / chunk_ms))
            trans_end = min(num_chunks, int((end_ms + 100) / chunk_ms))
            vad_array[trans_start:trans_end] = np.maximum(vad_array[trans_start:trans_end], 0.50)
            speech_start = max(0, int(start_ms / chunk_ms))
            speech_end = min(num_chunks, int(end_ms / chunk_ms))
            vad_array[speech_start:speech_end] = 0.85
        return vad_array
