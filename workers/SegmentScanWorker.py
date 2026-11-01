from PySide6.QtCore import QThread, Signal
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
import datetime

class SegmentScanWorker(QThread):
    """
    Worker dng d? chay lai Speech Recognition (Whisper) cho 1 doan subtitle
    d duoc thay doi thoi gian tren Timeline, m khng lm ?nh huong den
    cc ti?n trnh khc ho?c thay doi ID cua subtitle.
    """
    finished_signal = Signal(str, str) # segment_id, new_text
    timing_finished_signal = Signal(str, int, int) # segment_id, new_start_ms, new_end_ms
    error_signal = Signal(str, str) # segment_id, error_msg

    def __init__(
        self,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        request: SubtitleGenerationRequest,
        whisper_service: FasterWhisperService,
        scan_mode: str = "asr",
    ):
        super().__init__()
        self.segment_id = segment_id
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.request = request
        self.whisper_service = whisper_service
        self.scan_mode = scan_mode
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                return

            # T?i model v?i thi?t l?p t? request
            self.whisper_service.load_model(self.request.model_size, self.request.compute_type)
            
            now_iso = datetime.datetime.now().isoformat()
            # T?o 1 batch gi? l?p cho do?n m thanh ny
            batch = SubtitleGenerationBatch(
                batch_id="scan_" + str(self.segment_id),
                start_ms=self.start_ms,
                end_ms=self.end_ms,
                status="RUNNING",
                revision=1,
                created_at=now_iso,
                updated_at=now_iso
            )

            # Ch?y transcribe b?ng api c? s? d? l?y audio clip & ch?y AI
            result = self.whisper_service.transcribe_batch(
                self.request, batch, lambda: self._is_cancelled
            )

            if self._is_cancelled:
                return

            if result.error:
                self.error_signal.emit(self.segment_id, result.error)
            elif self.scan_mode == "timing":
                valid_segs = [
                    s for s in (result.segments or [])
                    if getattr(s, "start_ms", None) is not None and getattr(s, "end_ms", None) is not None
                ]
                if valid_segs:
                    speech_start_ms = min(s.start_ms for s in valid_segs)
                    speech_end_ms = max(s.end_ms for s in valid_segs)
                    self.timing_finished_signal.emit(self.segment_id, speech_start_ms, speech_end_ms)
                else:
                    self.error_signal.emit(self.segment_id, "NO_SPEECH_DETECTED")
            else:
                # Nối văn bản từ các phân đoạn trở về
                text = " ".join([seg.text.strip() for seg in result.segments])
                if not text:
                    text = "[Không nhận diện được giọng nói]"
                self.finished_signal.emit(self.segment_id, text)
                
        except Exception as e:
            self.error_signal.emit(self.segment_id, str(e))


class BatchSegmentScanWorker(QThread):
    """Worker chạy nhận diện âm thanh (Whisper) tuần tự cho danh sách phân đoạn được chọn."""
    progress_signal = Signal(int, int, str)
    segment_completed_signal = Signal(str, str)
    segment_timing_completed_signal = Signal(str, int, int)
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(
        self,
        segments_data: list,
        request: SubtitleGenerationRequest,
        whisper_service: FasterWhisperService,
    ):
        super().__init__()
        self.segments_data = segments_data
        self.request = request
        self.whisper_service = whisper_service
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if not self.segments_data:
                self.finished_signal.emit()
                return

            if hasattr(self.whisper_service, "load_model"):
                self.whisper_service.load_model(self.request.model_size, self.request.compute_type)

            total = len(self.segments_data)
            for idx, seg in enumerate(self.segments_data, 1):
                if self._is_cancelled:
                    return
                seg_id = str(seg.get("id"))
                start_ms = int(seg.get("start_ms", 0))
                end_ms = int(seg.get("end_ms", 0))
                scan_mode = seg.get("scan_mode", "asr")
                self.progress_signal.emit(idx, total, f"Đang nhận diện câu {idx}/{total}...")
                now_iso = datetime.datetime.now().isoformat()
                batch = SubtitleGenerationBatch(
                    batch_id=f"scan_{seg_id}",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    status="RUNNING",
                    revision=1,
                    created_at=now_iso,
                    updated_at=now_iso,
                )
                result = self.whisper_service.transcribe_batch(
                    self.request, batch, lambda: self._is_cancelled
                )
                if self._is_cancelled:
                    return
                if result and not result.error:
                    if scan_mode == "timing":
                        valid_segs = [
                            s for s in (result.segments or [])
                            if getattr(s, "start_ms", None) is not None and getattr(s, "end_ms", None) is not None
                        ]
                        if valid_segs:
                            speech_start_ms = min(s.start_ms for s in valid_segs)
                            speech_end_ms = max(s.end_ms for s in valid_segs)
                            self.segment_timing_completed_signal.emit(seg_id, speech_start_ms, speech_end_ms)
                    else:
                        text = " ".join([s.text.strip() for s in result.segments])
                        if not text:
                            text = "[Không nhận diện được giọng nói]"
                        self.segment_completed_signal.emit(seg_id, text)
                elif result and result.error:
                    self.segment_completed_signal.emit(seg_id, f"[Lỗi nhận diện: {result.error}]")
            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))
