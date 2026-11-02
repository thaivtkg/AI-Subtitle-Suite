import gc
import os
import shutil
import subprocess
import tempfile
from typing import Callable, Optional, Tuple

from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
from core.subtitle_generation.subtitle_generation_result import (
    SubtitleGenerationResult,
    WhisperSegmentResult,
)
from core.runtime.runtime_paths import RuntimePaths
from core.services.model_manager import ModelManager, ModelStorageError


def should_downgrade_to_int8_float16(threshold: float = 0.65) -> Tuple[bool, float]:
    """Kiểm tra mức sử dụng VRAM qua nvcuda.dll (<0.05ms); trả về (True, ratio) khi vượt threshold hoặc GPU <= 4.5GB VRAM."""
    try:
        from core.translation.core.hardware_detector import HardwareDetector

        used_gb, total_gb = HardwareDetector.get_vram_usage()
        if total_gb and total_gb > 0:
            ratio = float(used_gb) / float(total_gb)
            if float(total_gb) <= 4.5 or ratio > threshold:
                return (True, ratio)
    except Exception:
        pass
    return (False, 0.0)


class FasterWhisperService:
    """Thin ASR adapter: inference in, segment objects out; no artifact I/O."""

    def __init__(self, device: str = "cuda"):
        self.device = device
        self.model = None
        self.current_model_size: Optional[str] = None
        self.current_compute_type: Optional[str] = None
        self._vram_downgraded: bool = False

    def is_loaded(self, model_size: str, compute_type: str) -> bool:
        if self.model is None:
            return False
        if self.current_model_size is not None and self.current_model_size != model_size:
            return False
        if self.current_compute_type is not None and self.current_compute_type != compute_type:
            if (
                compute_type == "float16"
                and self.current_compute_type == "int8_float16"
                and self._vram_downgraded
            ):
                return True
            return False
        return True

    def load_model(self, model_size: str, compute_type: str) -> None:
        effective_compute = compute_type
        if self.device == "cuda" and compute_type == "float16":
            downgrade, ratio = should_downgrade_to_int8_float16(0.65)
            if downgrade:
                effective_compute = "int8_float16"
                self._vram_downgraded = True
                msg = (
                    f"[ASR] VRAM đạt {ratio * 100:.0f}% (>65%) ➔ Tự động chuyển sang int8_float16."
                    if ratio > 0.65
                    else f"[ASR] GPU VRAM <= 4.5GB (RTX 3050) ➔ Tự động tối ưu sang int8_float16."
                )
                print(msg, flush=True)
            else:
                self._vram_downgraded = False

        if self.is_loaded(model_size, effective_compute):
            return

        self.unload_model()
        try:
            from faster_whisper import WhisperModel

            model_path = ModelManager.get_model_path_for_inference(model_size)
            models_dir = RuntimePaths.get_models_dir()
            if model_path == model_size:
                models_dir = ModelManager.prepare_models_storage("load model")
            self.model = WhisperModel(
                model_path,
                device=self.device,
                compute_type=effective_compute,
                download_root=str(models_dir),
            )
            self.current_model_size = model_size
            self.current_compute_type = effective_compute
        except ModelStorageError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to load Faster-Whisper model: {exc}") from exc

    def unload_model(self) -> None:
        had_model = self.model is not None
        self.model = None
        self.current_model_size = None
        self.current_compute_type = None
        if had_model:
            try:
                gc.collect()
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def transcribe_batch(
        self,
        request: SubtitleGenerationRequest,
        batch: SubtitleGenerationBatch,
        is_cancelled: Callable[[], bool],
    ) -> SubtitleGenerationResult:
        if self.model is None:
            return SubtitleGenerationResult(
                batch_id=batch.batch_id,
                segments=[],
                error="Faster-Whisper model is not loaded.",
            )
        if batch.start_ms < 0 or batch.end_ms <= batch.start_ms:
            return SubtitleGenerationResult(
                batch_id=batch.batch_id,
                segments=[],
                error="Invalid batch time range.",
            )
        if is_cancelled():
            return SubtitleGenerationResult(batch.batch_id, [], "Cancelled.")

        # Kiểm tra áp lực VRAM động trước mỗi batch nếu đang chạy float16
        if self.device == "cuda" and self.current_compute_type == "float16":
            downgrade, ratio = should_downgrade_to_int8_float16(0.65)
            if downgrade:
                target_size = self.current_model_size or request.model_size
                self._vram_downgraded = True
                print(
                    f"[ASR] VRAM đạt {ratio * 100:.0f}% (>65%) ➔ Tự động chuyển sang int8_float16.",
                    flush=True,
                )
                self.unload_model()
                self.load_model(target_size, "int8_float16")
                self._vram_downgraded = True

        temp_dir = None
        try:
            is_japanese = (request.language or "").strip().lower() in ("ja", "japanese")
            effective_min_silence = request.min_silence_ms
            if is_japanese and effective_min_silence <= 500:
                effective_min_silence = 2000

            transcribe_options = {
                "language": request.language,
                "beam_size": 5,
                "best_of": 5,
                "patience": 1.0,
                "temperature": (0.0, 0.2, 0.4),
                "log_prob_threshold": -1.0,
                "no_speech_threshold": 0.6,
                "compression_ratio_threshold": 2.4,
                "condition_on_previous_text": getattr(request, "condition_on_previous_text", True),
                "word_timestamps": request.word_timestamps,
            }
            if request.prompt_context.strip():
                transcribe_options["initial_prompt"] = request.prompt_context
            # Every batch is an independent, zero-based audio input.  This
            # keeps VAD compatible with batch processing and makes the offset
            # contract unambiguous for both VAD and non-VAD transcription.
            input_path, temp_dir = self._extract_batch_audio(request, batch)
            timestamp_offset_ms = batch.start_ms
            if request.use_vad:
                transcribe_options["vad_filter"] = True
                transcribe_options["vad_parameters"] = {
                    "min_silence_duration_ms": effective_min_silence
                }
            else:
                transcribe_options["vad_filter"] = False

            try:
                segments, _info = self.model.transcribe(
                    input_path, **transcribe_options
                )
                raw_seg_list = list(segments)
            except RuntimeError as oom_exc:
                if (
                    "out of memory" in str(oom_exc).lower()
                    and self.device == "cuda"
                    and self.current_compute_type == "float16"
                ):
                    target_size = self.current_model_size or request.model_size
                    print(
                        "[ASR] Phát hiện tràn VRAM (OOM) ➔ Tự động chuyển sang int8_float16.",
                        flush=True,
                    )
                    self.unload_model()
                    self.load_model(target_size, "int8_float16")
                    self._vram_downgraded = True
                    segments, _info = self.model.transcribe(
                        input_path, **transcribe_options
                    )
                    raw_seg_list = list(segments)
                else:
                    raise

            results = []
            for segment in raw_seg_list:
                if is_cancelled():
                    return SubtitleGenerationResult(batch.batch_id, [], "Cancelled.")

                words = None
                if request.word_timestamps and getattr(segment, "words", None):
                    words = [
                        {
                            "word": word.word,
                            "start_ms": self._shift_ms(word.start, timestamp_offset_ms),
                            "end_ms": self._shift_ms(word.end, timestamp_offset_ms),
                        }
                        for word in segment.words
                        if word.start is not None and word.end is not None
                    ]
                    words = words or None

                results.append(
                    WhisperSegmentResult(
                        start_ms=self._shift_ms(segment.start, timestamp_offset_ms),
                        end_ms=self._shift_ms(segment.end, timestamp_offset_ms),
                        text=segment.text.strip(),
                        words=words,
                    )
                )
            results = SubtitleGenerationValidator.validate(results, batch.start_ms, batch.end_ms)
            return SubtitleGenerationResult(batch.batch_id, results)
        except Exception as exc:
            return SubtitleGenerationResult(batch.batch_id, [], str(exc))
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _extract_batch_audio(
        request: SubtitleGenerationRequest, batch: SubtitleGenerationBatch
    ) -> Tuple[str, str]:
        """Crop one batch to a temporary 16 kHz mono WAV for VAD + ASR."""
        temp_dir = tempfile.mkdtemp(prefix="subtitle_generation_batch_")
        output_path = os.path.join(temp_dir, "audio.wav")
        duration_s = (batch.end_ms - batch.start_ms) / 1000
        # AUD-PERF-001: Chuyển -ss lên trước -i (Fast Input Seeking) kết hợp -vn (audio PCM giải mã mẫu chuẩn xác).
        # Nhảy trực tiếp đến vị trí audio cần lấy, giảm độ phức tạp từ O(N^2) xuống O(1) cho mỗi batch.
        command = [
            RuntimePaths.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{batch.start_ms / 1000:.3f}",
            "-i",
            request.video_path,
            "-t",
            f"{duration_s:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
        ]
        # Tăng âm lượng gốc 2x (+6dB) nếu request yêu cầu boost
        if getattr(request, "audio_boost", False):
            command.extend(["-af", "volume=2.0"])
        command.extend([
            "-c:a",
            "pcm_s16le",
            "-y",
            output_path,
        ])
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to extract audio batch: {exc}") from exc
        return output_path, temp_dir

    @staticmethod
    def _shift_ms(seconds: float, offset_ms: int) -> int:
        return max(0, int(round(seconds * 1000)) + offset_ms)
