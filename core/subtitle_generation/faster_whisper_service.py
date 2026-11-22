import gc
import math
import os
import shutil
import subprocess
import tempfile
import wave
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


def ensure_silero_vad_anti_saturation_patch() -> None:
    """Reset Silero VAD LSTM state on non-speech/saturated windows so BGM cannot mask speech."""
    import numpy as np
    from faster_whisper.vad import SileroVADModel

    if getattr(SileroVADModel, "_anti_saturation_patched", False):
        return

    def _patched_call(
        self, audio: np.ndarray, num_samples: int = 512, context_size_samples: int = 64
    ):
        assert audio.ndim == 1, "Input should be a 1D array"
        assert (
            audio.shape[0] % num_samples == 0
        ), "Input size should be a multiple of num_samples"

        h = np.zeros((1, 1, 128), dtype="float32")
        c = np.zeros((1, 1, 128), dtype="float32")

        batched_audio = audio.reshape(-1, num_samples)
        if batched_audio.shape[0] == 0:
            return np.empty((0, 1), dtype="float32")
        context = batched_audio[..., -context_size_samples:].copy()
        context[-1] = 0
        context = np.roll(context, 1, 0)
        batched_audio = np.concatenate([context, batched_audio], 1)
        batched_audio = batched_audio.reshape(-1, num_samples + context_size_samples)

        encoder_batch_size = 64
        num_segments = batched_audio.shape[0]
        outputs = []
        for i in range(0, num_segments, encoder_batch_size):
            output, h, c = self.session.run(
                None,
                {"input": batched_audio[i : i + encoder_batch_size], "h": h, "c": c},
            )
            outputs.append(output)
            if float(np.max(output)) < 0.25 or float(np.max(np.abs(c))) > 20.0:
                h = np.zeros((1, 1, 128), dtype="float32")
                c = np.zeros((1, 1, 128), dtype="float32")

        return np.concatenate(outputs, axis=0)

    SileroVADModel.__call__ = _patched_call
    SileroVADModel._anti_saturation_patched = True


class FasterWhisperService:
    """Thin ASR adapter: inference in, segment objects out; no artifact I/O."""

    def __init__(self, device: str = "cuda"):
        self.device = device
        self.model = None
        self.current_model_size: Optional[str] = None
        self.current_compute_type: Optional[str] = None
        self._vram_downgraded: bool = False
        self._batch_progress_callback: Optional[Callable[[int, int], None]] = None

    def set_batch_progress_callback(
        self, callback: Optional[Callable[[int, int], None]]
    ) -> None:
        """Register an optional (segment_count, segment_end_ms) callback for the active batch."""
        self._batch_progress_callback = callback

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

    @staticmethod
    def build_ffmpeg_audio_filter(speech_filter: bool = False, audio_boost: bool = False) -> Optional[str]:
        parts = []
        if speech_filter:
            parts.append("highpass=f=80,lowpass=f=7800,dynaudnorm=f=150:g=15")
        if audio_boost:
            parts.append("volume=2.0")
        return ",".join(parts) if parts else None

    @staticmethod
    def resolve_decode_defaults(
        model_size: Optional[str], language: Optional[str], condition_on_previous_text: bool
    ) -> Tuple[Optional[str], bool]:
        spec = ModelManager.get_specialized_info(model_size or "")
        effective_lang = language or (spec["language"] if spec else None)
        effective_cond = condition_on_previous_text
        if "kotoba" in (model_size or "").lower():
            effective_cond = False
        return effective_lang, effective_cond

    @staticmethod
    def resolve_word_timestamps(
        model_size: Optional[str], requested: bool
    ) -> bool:
        """Disable word-level C++ alignment on distilled models where invalid alignment_heads segfault."""
        return bool(requested) and ModelManager.supports_word_timestamps(model_size)

    @staticmethod
    def is_large_v3_model(model_size: Optional[str]) -> bool:
        lowered = str(model_size or "").strip().lower()
        return (
            "large-v3" in lowered
            and "turbo" not in lowered
            and "kotoba" not in lowered
            and "distil" not in lowered
        )

    @staticmethod
    def is_kotoba_model(model_size: Optional[str]) -> bool:
        return "kotoba" in str(model_size or "").strip().lower()

    @classmethod
    def _enforce_kotoba_guard(cls, model_size: Optional[str], opts: dict) -> dict:
        """Lớp cưỡng chế cứng cho kotoba-whisper ngay trước khi gọi model.transcribe()."""
        if cls.is_kotoba_model(model_size):
            opts["initial_prompt"] = None
            opts["hotwords"] = None
            opts["condition_on_previous_text"] = False
            opts["word_timestamps"] = False
            opts.pop("repetition_penalty", None)
            opts.pop("no_repeat_ngram_size", None)
        return opts

    @staticmethod
    def _slice_wav_segment(
        input_path: str, start_sec: float, end_sec: float, out_path: str
    ) -> bool:
        """Cắt đoạn WAV con [start_sec, end_sec] để retry đơn lẻ khi dính Prompt Echo."""
        if not input_path or not os.path.exists(input_path) or end_sec <= start_sec:
            return False
        try:
            with wave.open(input_path, "rb") as src:
                params = src.getparams()
                rate = int(params.framerate or 16000)
                total_frames = int(src.getnframes())
                start_frame = max(0, min(total_frames, int(round(start_sec * rate))))
                end_frame = max(start_frame, min(total_frames, int(round(end_sec * rate))))
                if end_frame <= start_frame:
                    return False
                src.setpos(start_frame)
                frames = src.readframes(end_frame - start_frame)
            if not frames:
                return False
            with wave.open(out_path, "wb") as dst:
                dst.setparams(params)
                dst.writeframes(frames)
            return True
        except Exception:
            return False

    @classmethod
    def enforce_max_speech_spans(
        cls,
        spans: list[tuple[float, float]],
        max_speech_s: Optional[float],
        *,
        audio=None,
        sampling_rate: int = 16000,
        wav_path: Optional[str] = None,
    ) -> list[tuple[float, float]]:
        """Chia nhỏ mọi khung thoại liên tục vượt ngưỡng max_speech_s tại điểm năng lượng âm thấp nhất gần trần."""
        if not spans or max_speech_s is None or isinstance(max_speech_s, bool):
            return list(spans or [])
        max_s = float(max_speech_s)
        if max_s <= 0.0:
            return list(spans)

        needs_split = any((float(e) - float(s)) > (max_s + 1e-3) for s, e in spans)
        if not needs_split:
            return [(float(s), float(e)) for s, e in spans if float(e) > float(s)]

        waveform = audio
        sr = int(sampling_rate or 16000)
        if waveform is None and wav_path and os.path.exists(wav_path):
            try:
                import numpy as np

                with wave.open(wav_path, "rb") as wf:
                    sr = int(wf.getframerate() or 16000)
                    nchannels = int(wf.getnchannels() or 1)
                    sampwidth = int(wf.getsampwidth() or 2)
                    raw_frames = wf.readframes(wf.getnframes())
                if raw_frames and sampwidth == 2:
                    samples = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
                    if nchannels > 1:
                        samples = samples.reshape(-1, nchannels).mean(axis=1)
                    waveform = samples
            except Exception:
                waveform = None

        result: list[tuple[float, float]] = []
        for raw_s, raw_e in spans:
            start_s = float(raw_s)
            end_s = float(raw_e)
            if end_s <= start_s:
                continue
            cur_s = start_s
            while (end_s - cur_s) > (max_s + 1e-3):
                rem = end_s - cur_s
                n_parts = max(2, int(math.ceil(rem / max_s)))
                ideal_step = min(max_s, rem / n_parts)
                split_t = min(cur_s + max_s, cur_s + ideal_step)

                if waveform is not None and len(waveform) > 0:
                    w_start = cur_s + max(0.5, ideal_step * 0.65)
                    w_end = min(end_s - 0.35, cur_s + max_s)
                    if w_end > w_start + 0.05:
                        i0 = max(0, min(len(waveform) - 1, int(w_start * sr)))
                        i1 = max(i0 + 1, min(len(waveform), int(w_end * sr)))
                        win = max(1, int(0.05 * sr))
                        hop = max(1, int(0.025 * sr))
                        seg_arr = waveform[i0:i1]
                        if len(seg_arr) >= win:
                            best_idx = None
                            best_energy = None
                            for pos in range(0, len(seg_arr) - win + 1, hop):
                                chunk = seg_arr[pos : pos + win]
                                energy = float((chunk * chunk).mean())
                                if best_energy is None or energy < best_energy:
                                    best_energy = energy
                                    best_idx = i0 + pos + (win // 2)
                            if best_idx is not None:
                                cand_t = best_idx / float(sr)
                                if (cur_s + 0.25) < cand_t <= (cur_s + max_s):
                                    split_t = cand_t

                split_t = round(split_t, 3)
                max_bound = round(cur_s + max_s, 3)
                if split_t > max_bound:
                    split_t = max_bound
                if split_t <= cur_s + 0.05:
                    split_t = round(min(end_s, cur_s + max_s), 3)
                result.append((round(cur_s, 3), split_t))
                cur_s = split_t
            if end_s > cur_s:
                result.append((round(cur_s, 3), round(end_s, 3)))
        return result

    @classmethod
    def build_bounded_vad_windows(
        cls,
        speech_chunks: list,
        max_speech_s: float,
        min_silence_ms: int = 300,
        *,
        audio=None,
        sampling_rate: int = 16000,
    ) -> list[tuple[float, float]]:
        """Gom các chunk VAD liền kề thành các cửa sổ <= max_speech_s để ngăn faster-whisper nối gộp thành khối 30s."""
        if not speech_chunks or max_speech_s <= 0:
            return []
        sr = float(max(1, int(sampling_rate or 16000)))
        raw_spans: list[tuple[float, float]] = []
        for ch in speech_chunks:
            if isinstance(ch, dict):
                c_s = float(ch.get("start", 0.0)) / sr
                c_e = float(ch.get("end", 0.0)) / sr
            else:
                c_s = float(ch[0])
                c_e = float(ch[1])
            if c_e > c_s:
                raw_spans.append((c_s, c_e))
        if not raw_spans:
            return []

        split_spans = cls.enforce_max_speech_spans(
            raw_spans,
            float(max_speech_s),
            audio=audio,
            sampling_rate=int(sr),
        )
        max_group_gap_s = max(1.2, float(min_silence_ms or 300) / 1000.0)
        windows: list[tuple[float, float]] = []
        for sp_s, sp_e in split_spans:
            if not windows:
                windows.append((round(sp_s, 3), round(sp_e, 3)))
                continue
            prev_s, prev_e = windows[-1]
            if (sp_s - prev_e) <= max_group_gap_s and (sp_e - prev_s) <= (float(max_speech_s) + 1e-3):
                windows[-1] = (prev_s, round(max(prev_e, sp_e), 3))
            else:
                windows.append((round(sp_s, 3), round(sp_e, 3)))
        return windows

    @staticmethod
    def _shift_raw_segment(seg, offset_sec: float):
        from types import SimpleNamespace

        if offset_sec == 0.0:
            return seg
        raw_words = getattr(seg, "words", None)
        shifted_words = None
        if raw_words:
            shifted_words = [
                SimpleNamespace(
                    word=getattr(w, "word", ""),
                    start=(float(w.start) + offset_sec) if getattr(w, "start", None) is not None else None,
                    end=(float(w.end) + offset_sec) if getattr(w, "end", None) is not None else None,
                    probability=getattr(w, "probability", 1.0),
                )
                for w in raw_words
            ]
        return SimpleNamespace(
            start=float(getattr(seg, "start", 0.0) or 0.0) + offset_sec,
            end=float(getattr(seg, "end", 0.0) or 0.0) + offset_sec,
            text=getattr(seg, "text", ""),
            no_speech_prob=getattr(seg, "no_speech_prob", 0.0),
            avg_logprob=getattr(seg, "avg_logprob", 0.0),
            compression_ratio=getattr(seg, "compression_ratio", None),
            temperature=getattr(seg, "temperature", None),
            words=shifted_words,
        )

    @staticmethod
    def is_high_compression_hallucination(segment) -> bool:
        cr = getattr(segment, "compression_ratio", None)
        return isinstance(cr, (int, float)) and not isinstance(cr, bool) and float(cr) > 2.4

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
            if model_path == model_size or model_path == ModelManager.resolve_repo_id(model_size):
                models_dir = ModelManager.prepare_models_storage("load model")
            ModelManager.ensure_windows_hf_no_symlink()
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
        on_progress: Optional[Callable[[int, int], None]] = None,
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
            effective_model_size = self.current_model_size or getattr(request, "model_size", "")
            effective_lang, effective_cond_prev = self.resolve_decode_defaults(
                effective_model_size,
                request.language,
                getattr(request, "condition_on_previous_text", True),
            )
            effective_word_ts = self.resolve_word_timestamps(
                effective_model_size,
                getattr(request, "word_timestamps", False),
            )
            is_japanese = (effective_lang or "").strip().lower() in ("ja", "japanese")
            has_custom_vad = (
                getattr(request, "vad_threshold", None) is not None
                or getattr(request, "vad_speech_pad_ms", None) is not None
                or getattr(request, "vad_max_speech_duration_s", None) is not None
            )
            effective_min_silence = request.min_silence_ms
            if is_japanese and effective_min_silence == 500 and not has_custom_vad:
                effective_min_silence = 2000

            req_log_prob = getattr(request, "log_prob_threshold", None)
            req_no_speech = getattr(request, "no_speech_threshold", None)
            req_patience = getattr(request, "patience", None)
            transcribe_options = {
                "language": effective_lang,
                "beam_size": 5,
                "best_of": 5,
                "patience": float(req_patience) if req_patience is not None else 1.0,
                "temperature": (0.0, 0.2, 0.4),
                "log_prob_threshold": float(req_log_prob) if req_log_prob is not None else -1.0,
                "no_speech_threshold": float(req_no_speech) if req_no_speech is not None else 0.6,
                "compression_ratio_threshold": 2.4,
                "condition_on_previous_text": effective_cond_prev,
                "word_timestamps": effective_word_ts,
            }
            from core.subtitle_generation.language_utils import (
                extract_natural_initial_prompt,
                extract_terminology_terms,
                format_whisper_initial_prompt,
                merge_hotwords,
            )

            is_large_v3 = self.is_large_v3_model(effective_model_size)
            is_kotoba = self.is_kotoba_model(effective_model_size)
            if is_large_v3:
                transcribe_options["repetition_penalty"] = 1.1
                transcribe_options["no_repeat_ngram_size"] = 3
                transcribe_options["initial_prompt"] = extract_natural_initial_prompt(
                    request.prompt_context, effective_lang
                )
                merged_hotwords = merge_hotwords(
                    getattr(request, "hotwords", ""),
                    extract_terminology_terms(request.prompt_context),
                    sep=" ",
                )
                transcribe_options["hotwords"] = merged_hotwords or None
            elif not is_kotoba:
                supports_word_ts = ModelManager.supports_word_timestamps(effective_model_size)
                if request.prompt_context.strip():
                    formatted_prompt = (
                        format_whisper_initial_prompt(request.prompt_context, effective_lang)
                        if supports_word_ts
                        else request.prompt_context
                    )
                    if formatted_prompt:
                        transcribe_options["initial_prompt"] = formatted_prompt
                raw_hw = getattr(request, "hotwords", "")
                merged_hotwords = merge_hotwords(raw_hw, sep=" ") if supports_word_ts else str(raw_hw or "").strip()
                if merged_hotwords:
                    transcribe_options["hotwords"] = merged_hotwords
            # Every batch is an independent, zero-based audio input.  This
            # keeps VAD compatible with batch processing and makes the offset
            # contract unambiguous for both VAD and non-VAD transcription.
            input_path, temp_dir = self._extract_batch_audio(request, batch)
            timestamp_offset_ms = batch.start_ms
            if request.use_vad:
                ensure_silero_vad_anti_saturation_patch()
                transcribe_options["vad_filter"] = True
                req_hst = getattr(request, "hallucination_silence_threshold", None)
                effective_hst = 1.0 if req_hst is None else float(req_hst)
                if effective_hst > 0:
                    transcribe_options["hallucination_silence_threshold"] = effective_hst
                vad_params = {
                    "min_silence_duration_ms": effective_min_silence,
                    "min_speech_duration_ms": int(getattr(request, "min_speech_duration_ms", None) or 500),
                }
                if getattr(request, "vad_threshold", None) is not None:
                    vad_params["threshold"] = float(request.vad_threshold)
                if getattr(request, "vad_speech_pad_ms", None) is not None:
                    vad_params["speech_pad_ms"] = int(request.vad_speech_pad_ms)
                if getattr(request, "vad_max_speech_duration_s", None) is not None:
                    vad_params["max_speech_duration_s"] = float(request.vad_max_speech_duration_s)
                transcribe_options["vad_parameters"] = vad_params
            else:
                transcribe_options["vad_filter"] = False

            progress_cb = (
                on_progress if on_progress is not None else self._batch_progress_callback
            )

            def _consume_segments(segments_iter):
                collected = []
                valid_count = 0
                for seg in segments_iter:
                    if is_cancelled():
                        return collected, True
                    collected.append(seg)
                    seg_text = str(getattr(seg, "text", "") or "").strip()
                    if (
                        seg_text
                        and not self.is_high_compression_hallucination(seg)
                        and not SubtitleGenerationValidator.is_hallucination(seg_text)
                    ):
                        valid_count += 1
                    if callable(progress_cb):
                        seg_end_ms = max(
                            0, int(float(getattr(seg, "end", 0.0) or 0.0) * 1000)
                        )
                        progress_cb(valid_count or len(collected), seg_end_ms)
                return collected, False

            batch_dur_s = max(0.0, (batch.end_ms - batch.start_ms) / 1000.0)

            def _run_model_with_oom_guard(target_audio: str, opts: dict):
                self._enforce_kotoba_guard(effective_model_size, opts)
                try:
                    segments, info_obj = self.model.transcribe(target_audio, **opts)
                    seg_list, was_cancelled = _consume_segments(segments)
                    return seg_list, info_obj, was_cancelled
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
                        self._enforce_kotoba_guard(effective_model_size, opts)
                        segments, info_obj = self.model.transcribe(target_audio, **opts)
                        seg_list, was_cancelled = _consume_segments(segments)
                        return seg_list, info_obj, was_cancelled
                    raise

            raw_seg_list = None
            max_speech_cap = (
                transcribe_options.get("vad_parameters", {}).get("max_speech_duration_s")
                if request.use_vad and not is_kotoba
                else None
            )
            if (
                isinstance(max_speech_cap, (int, float))
                and not isinstance(max_speech_cap, bool)
                and float(max_speech_cap) > 0.0
                and batch_dur_s > (float(max_speech_cap) + 1e-3)
                and os.path.exists(input_path)
            ):
                try:
                    from faster_whisper.audio import decode_audio
                    from faster_whisper.vad import VadOptions, get_speech_timestamps

                    vad_audio = decode_audio(input_path, sampling_rate=16000)
                    vad_opts = VadOptions(**transcribe_options["vad_parameters"])
                    speech_chunks = get_speech_timestamps(vad_audio, vad_opts)
                    if speech_chunks:
                        total_vad_span_s = (
                            float(speech_chunks[-1]["end"]) - float(speech_chunks[0]["start"])
                        ) / 16000.0
                        if total_vad_span_s > (float(max_speech_cap) + 1e-3):
                            bounded_spans = self.build_bounded_vad_windows(
                                speech_chunks,
                                float(max_speech_cap),
                                effective_min_silence,
                                audio=vad_audio,
                                sampling_rate=16000,
                            )
                            collected_bounded = []
                            for cap_idx, (sp_start, sp_end) in enumerate(bounded_spans, start=1):
                                if is_cancelled():
                                    return SubtitleGenerationResult(batch.batch_id, [], "Cancelled.")
                                slice_wav = os.path.join(temp_dir or "", f"vad_cap_{cap_idx}.wav")
                                if slice_wav and self._slice_wav_segment(input_path, sp_start, sp_end, slice_wav):
                                    slice_opts = dict(transcribe_options)
                                    part_segs, _part_info, part_cancelled = _run_model_with_oom_guard(
                                        slice_wav, slice_opts
                                    )
                                    if part_cancelled:
                                        return SubtitleGenerationResult(batch.batch_id, [], "Cancelled.")
                                    for p_seg in part_segs:
                                        collected_bounded.append(self._shift_raw_segment(p_seg, sp_start))
                            raw_seg_list = collected_bounded
                except Exception:
                    raw_seg_list = None

            if raw_seg_list is None:
                raw_seg_list, _info, cancelled = _run_model_with_oom_guard(input_path, transcribe_options)
                if cancelled:
                    return SubtitleGenerationResult(batch.batch_id, [], "Cancelled.")
                if (
                    not raw_seg_list
                    and not ModelManager.supports_word_timestamps(effective_model_size)
                    and (not request.use_vad or float(getattr(_info, "duration_after_vad", 0.0) or 0.0) >= 0.3)
                ):
                    clean_opts = dict(transcribe_options)
                    clean_opts.pop("initial_prompt", None)
                    clean_opts.pop("hotwords", None)
                    clean_opts["no_speech_threshold"] = None
                    clean_opts["log_prob_threshold"] = None
                    raw_seg_list, _info, cancelled = _run_model_with_oom_guard(input_path, clean_opts)
                    if cancelled:
                        return SubtitleGenerationResult(batch.batch_id, [], "Cancelled.")

            used_prompt = str(transcribe_options.get("initial_prompt") or "").strip()
            used_hotwords = str(transcribe_options.get("hotwords") or "").strip()
            has_glossary_bias = bool(used_prompt or used_hotwords)
            clean_batch_cache: Optional[list] = None
            consumed_clean_indices: set[int] = set()
            retry_counter = 0

            def _convert_segment(
                segment, seg_offset_ms: int, allow_echo_retry: bool
            ) -> Tuple[list[WhisperSegmentResult], bool]:
                nonlocal clean_batch_cache, retry_counter
                if is_cancelled():
                    return [], True
                if self.is_high_compression_hallucination(segment):
                    return [], False

                raw_text = str(getattr(segment, "text", "") or "").strip()
                raw_words = getattr(segment, "words", None) if effective_word_ts else None
                orig_start = float(getattr(segment, "start", 0.0) or 0.0)
                orig_end = float(getattr(segment, "end", 0.0) or 0.0)
                cleaned_text, kept_raw_words, new_end_sec, _had_rep = (
                    SubtitleGenerationValidator.clean_repetition_segment(
                        raw_text,
                        words=raw_words,
                        start_val=orig_start,
                        end_val=orig_end,
                        words_in_ms=False,
                    )
                )
                if not cleaned_text:
                    return [], False
                if SubtitleGenerationValidator.is_low_cps_courtesy_hallucination(
                    cleaned_text,
                    duration_s=max(0.0, new_end_sec - orig_start),
                    no_speech_prob=getattr(segment, "no_speech_prob", None),
                ):
                    return [], False

                is_echo = has_glossary_bias and (
                    SubtitleGenerationValidator.is_prompt_echo(
                        raw_text, initial_prompt=used_prompt, hotwords=used_hotwords
                    )
                    or SubtitleGenerationValidator.is_prompt_echo(
                        cleaned_text, initial_prompt=used_prompt, hotwords=used_hotwords
                    )
                )
                if is_echo:
                    if not allow_echo_retry:
                        return [], False
                    retry_opts = dict(transcribe_options)
                    retry_opts["initial_prompt"] = None
                    retry_opts["hotwords"] = None
                    retry_opts["condition_on_previous_text"] = False
                    self._enforce_kotoba_guard(effective_model_size, retry_opts)

                    seg_dur_s = max(0.0, orig_end - orig_start)
                    slice_retry_threshold_s = float(max_speech_cap) if (
                        isinstance(max_speech_cap, (int, float))
                        and not isinstance(max_speech_cap, bool)
                        and float(max_speech_cap) > 0.0
                    ) else 30.0
                    if (
                        batch_dur_s > (slice_retry_threshold_s + 1e-3)
                        and 0.0 < seg_dur_s <= 30.0
                        and os.path.exists(input_path)
                    ):
                        retry_counter += 1
                        slice_path = os.path.join(
                            temp_dir or "", f"echo_retry_{retry_counter}.wav"
                        )
                        if slice_path and self._slice_wav_segment(
                            input_path, orig_start, orig_end, slice_path
                        ):
                            slice_opts = dict(retry_opts)
                            self._enforce_kotoba_guard(effective_model_size, slice_opts)
                            r_segs, _ = self.model.transcribe(slice_path, **slice_opts)
                            r_list, r_cancelled = _consume_segments(r_segs)
                            if r_cancelled:
                                return [], True
                            rescued: list[WhisperSegmentResult] = []
                            slice_offset_ms = seg_offset_ms + int(round(orig_start * 1000))
                            for r_seg in r_list:
                                sub_items, sub_cancelled = _convert_segment(
                                    r_seg, slice_offset_ms, allow_echo_retry=False
                                )
                                if sub_cancelled:
                                    return [], True
                                rescued.extend(sub_items)
                            return rescued, False

                    if clean_batch_cache is None:
                        r_segs, _ = self.model.transcribe(input_path, **retry_opts)
                        clean_batch_cache, r_cancelled = _consume_segments(r_segs)
                        if r_cancelled:
                            return [], True
                    rescued = []
                    for idx, r_seg in enumerate(clean_batch_cache):
                        if idx in consumed_clean_indices:
                            continue
                        r_start = float(getattr(r_seg, "start", 0.0) or 0.0)
                        r_end = float(getattr(r_seg, "end", 0.0) or 0.0)
                        if r_end <= orig_start - 0.15 or r_start >= orig_end + 0.15:
                            continue
                        consumed_clean_indices.add(idx)
                        sub_items, sub_cancelled = _convert_segment(
                            r_seg, seg_offset_ms, allow_echo_retry=False
                        )
                        if sub_cancelled:
                            return [], True
                        rescued.extend(sub_items)
                    return rescued, False

                words = None
                if effective_word_ts and kept_raw_words:
                    words = [
                        {
                            "word": word.word,
                            "start_ms": self._shift_ms(word.start, seg_offset_ms),
                            "end_ms": self._shift_ms(word.end, seg_offset_ms),
                        }
                        for word in kept_raw_words
                        if word.start is not None and word.end is not None
                    ]
                    words = words or None

                return [
                    WhisperSegmentResult(
                        start_ms=self._shift_ms(orig_start, seg_offset_ms),
                        end_ms=self._shift_ms(new_end_sec, seg_offset_ms),
                        text=cleaned_text,
                        words=words,
                    )
                ], False

            results = []
            for segment in raw_seg_list:
                converted, cancelled = _convert_segment(
                    segment, timestamp_offset_ms, allow_echo_retry=True
                )
                if cancelled:
                    return SubtitleGenerationResult(batch.batch_id, [], "Cancelled.")
                results.extend(converted)
            results = SubtitleGenerationValidator.validate(results, batch.start_ms, batch.end_ms)
            if effective_lang and effective_lang != "auto":
                filtered_results = []
                for res in results:
                    filtered_text = SubtitleGenerationValidator.filter_inconsistent_language(
                        res.text, effective_lang
                    )
                    if filtered_text:
                        res.text = filtered_text
                        filtered_results.append(res)
                results = filtered_results
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
        audio_filter = FasterWhisperService.build_ffmpeg_audio_filter(
            speech_filter=bool(getattr(request, "speech_filter", False)),
            audio_boost=bool(getattr(request, "audio_boost", False)),
        )
        if audio_filter:
            command.extend(["-af", audio_filter])
        command.extend([
            "-c:a",
            "pcm_s16le",
            "-y",
            output_path,
        ])
        try:
            for attempt in range(2):
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                with wave.open(output_path, "rb") as audio:
                    audio_duration = audio.getnframes() / audio.getframerate()
                if attempt == 0 and audio_duration < duration_s - 0.1:
                    # Some ASF/WMV indexes seek past short clips; decode from the start instead.
                    seek_index = command.index("-ss")
                    seek_args = command[seek_index:seek_index + 2]
                    del command[seek_index:seek_index + 2]
                    input_end = command.index("-i") + 2
                    command[input_end:input_end] = seek_args
                    continue
                if audio_duration == 0:
                    raise RuntimeError("FFmpeg returned empty audio for the selected time range")
                break
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to extract audio batch: {exc}") from exc
        return output_path, temp_dir

    @staticmethod
    def _shift_ms(seconds: float, offset_ms: int) -> int:
        return max(0, int(round(seconds * 1000)) + offset_ms)

    def run(
        self,
        input_file: str,
        model_size: str = "tiny",
        language: Optional[str] = None,
        artifact_store: Optional[object] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Transcribe full media file and register resulting SRT artifact."""
        if not input_file or not os.path.exists(input_file):
            raise FileNotFoundError(f"Media file not found: {input_file}")

        target_size = model_size or self.current_model_size or "tiny"
        compute_type = "float16" if self.device == "cuda" else "int8"
        if not self.is_loaded(target_size, compute_type):
            self.load_model(target_size, compute_type)

        if self.model is None:
            raise RuntimeError(f"Failed to load Faster-Whisper model: {target_size}")

        ensure_silero_vad_anti_saturation_patch()
        transcribe_kwargs = {
            "vad_filter": True,
            "vad_parameters": {"min_speech_duration_ms": 500},
            "hallucination_silence_threshold": 1.0,
            "compression_ratio_threshold": 2.4,
            "no_speech_threshold": 0.6,
        }
        if self.is_large_v3_model(target_size):
            transcribe_kwargs["repetition_penalty"] = 1.1
            transcribe_kwargs["no_repeat_ngram_size"] = 3
            transcribe_kwargs["vad_parameters"]["max_speech_duration_s"] = 6.0
        if language and language != "auto":
            transcribe_kwargs["language"] = language
        self._enforce_kotoba_guard(target_size, transcribe_kwargs)

        segments_gen, _info = self.model.transcribe(input_file, **transcribe_kwargs)

        lines = []
        srt_idx = 0
        for seg in segments_gen:
            if self.is_high_compression_hallucination(seg):
                continue
            nsp = getattr(seg, "no_speech_prob", None)
            if isinstance(nsp, (int, float)) and not isinstance(nsp, bool) and float(nsp) >= 0.75:
                continue
            cleaned_text, _kw, new_end_sec, _rep = SubtitleGenerationValidator.clean_repetition_segment(
                str(getattr(seg, "text", "") or "").strip(),
                words=getattr(seg, "words", None),
                start_val=float(getattr(seg, "start", 0.0) or 0.0),
                end_val=float(getattr(seg, "end", 0.0) or 0.0),
                words_in_ms=False,
            )
            if not cleaned_text or SubtitleGenerationValidator.is_hallucination(cleaned_text):
                continue
            seg_dur_s = max(0.0, new_end_sec - float(getattr(seg, "start", 0.0) or 0.0))
            if SubtitleGenerationValidator.is_low_cps_courtesy_hallucination(
                cleaned_text, duration_s=seg_dur_s, no_speech_prob=nsp
            ):
                continue
            if language and language != "auto":
                cleaned_text = SubtitleGenerationValidator.filter_inconsistent_language(cleaned_text, language)
                if not cleaned_text:
                    continue
            srt_idx += 1
            s_ms = self._shift_ms(seg.start, 0)
            e_ms = self._shift_ms(new_end_sec, 0)
            s_str = f"{s_ms // 3600000:02d}:{(s_ms % 3600000) // 60000:02d}:{(s_ms % 60000) // 1000:02d},{s_ms % 1000:03d}"
            e_str = f"{e_ms // 3600000:02d}:{(e_ms % 3600000) // 60000:02d}:{(e_ms % 60000) // 1000:02d},{e_ms % 1000:03d}"
            lines.append(f"{srt_idx}\n{s_str} --> {e_str}\n{cleaned_text}\n\n")

        from datetime import datetime
        import uuid
        from core.utils.file_utils import atomic_save_text
        from core.artifacts.artifact import Artifact
        from core.artifacts.artifact_types import ArtifactType, ArtifactStatus

        video_dir = os.path.dirname(input_file)
        video_name = os.path.splitext(os.path.basename(input_file))[0]
        srt_path = os.path.join(video_dir, f"{video_name}.srt")
        atomic_save_text(srt_path, "".join(lines))

        artifact_id = uuid.uuid4().hex
        if artifact_store:
            art = Artifact(
                artifact_id=artifact_id,
                artifact_type=ArtifactType.SUBTITLE,
                path=srt_path,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                source_project_id=session_id or "batch_session",
                status=ArtifactStatus.READY,
            )
            artifact_store.register(art)

        return artifact_id
