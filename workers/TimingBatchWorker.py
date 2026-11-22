import gc
import os
import tempfile
import subprocess
import traceback
import wave
from PySide6.QtCore import QThread, Signal

from core.subtitle_generation.faster_whisper_service import (
    FasterWhisperService,
    ensure_silero_vad_anti_saturation_patch,
    should_downgrade_to_int8_float16,
)
from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
from core.timing.timing_run_request import TimingRunRequest

class TimingBatchWorker(QThread):
    progress_signal = Signal(int, str)
    log_signal = Signal(str)
    finished_signal = Signal(list, bool) 
    error_signal = Signal(str)
    effective_compute_signal = Signal(str)

    def __init__(self, request: TimingRunRequest):
        super().__init__()
        self.request = request
        self.is_cancelled = False
        self._active_chunk_wav = None

    @staticmethod
    def effective_compute_type(device: str, configured: str) -> str:
        return configured if device == "cuda" else "int8"

    @staticmethod
    def split_segment_by_word_gaps(seg, split_gap_sec: float = 1.0) -> list:
        words = [
            w for w in (getattr(seg, "words", None) or [])
            if getattr(w, "start", None) is not None and getattr(w, "end", None) is not None
        ]
        if len(words) >= 2:
            sub_ranges = []
            c_start = words[0].start
            c_end = words[0].end
            for i in range(1, len(words)):
                w = words[i]
                if (w.start - c_end) >= split_gap_sec:
                    sub_ranges.append((c_start, c_end))
                    c_start = w.start
                    c_end = w.end
                else:
                    c_end = max(c_end, w.end)
            sub_ranges.append((c_start, c_end))
            return sub_ranges
        elif words:
            return [(words[0].start, words[-1].end)]
        return [(seg.start, seg.end)]

    @staticmethod
    def clip_segment_to_speech_spans(
        seg_start: float,
        seg_end: float,
        speech_spans: list[tuple[float, float]] | None,
        min_piece_sec: float = 0.20,
        merge_gap_sec: float = 1.0,
    ) -> list[tuple[float, float]]:
        """Split coarse segments at significant VAD silence gaps (>= merge_gap_sec) without chopping short pauses."""
        if not speech_spans or seg_end <= seg_start:
            return [(seg_start, seg_end)]
        merged_spans: list[tuple[float, float]] = []
        for sp_start, sp_end in speech_spans:
            if merged_spans and (sp_start - merged_spans[-1][1]) < merge_gap_sec:
                prev_start, prev_end = merged_spans[-1]
                merged_spans[-1] = (prev_start, max(prev_end, sp_end))
            else:
                merged_spans.append((sp_start, sp_end))
        overlaps: list[tuple[float, float]] = []
        for sp_start, sp_end in merged_spans:
            if sp_end <= seg_start:
                continue
            if sp_start >= seg_end:
                break
            o_start = max(seg_start, sp_start)
            o_end = min(seg_end, sp_end)
            if o_end > o_start:
                overlaps.append((o_start, o_end))
        if not overlaps:
            return [(seg_start, seg_end)]
        significant = [pair for pair in overlaps if (pair[1] - pair[0]) >= min_piece_sec]
        return significant or overlaps

    @staticmethod
    def _compute_vad_speech_spans(
        chunk_wav: str, vad_parameters: dict
    ) -> list[tuple[float, float]] | None:
        if not chunk_wav or not os.path.exists(chunk_wav):
            return None
        try:
            from faster_whisper.audio import decode_audio
            from faster_whisper.vad import VadOptions, get_speech_timestamps

            audio = decode_audio(chunk_wav, sampling_rate=16000)
            chunks = get_speech_timestamps(audio, VadOptions(**vad_parameters))
            spans = [(c["start"] / 16000.0, c["end"] / 16000.0) for c in chunks]
            max_speech = vad_parameters.get("max_speech_duration_s")
            if (
                isinstance(max_speech, (int, float))
                and not isinstance(max_speech, bool)
                and float(max_speech) > 0.0
            ):
                spans = FasterWhisperService.enforce_max_speech_spans(
                    spans, float(max_speech), audio=audio, sampling_rate=16000
                )
            return spans
        except Exception:
            return None

    def _extract_valid_sub_ranges(
        self, seg, actual_start_ms: int, current_start_ms: int
    ) -> list[tuple[int, int]]:
        """Apply speech/language filters and return shifted valid timing ranges."""
        if FasterWhisperService.is_high_compression_hallucination(seg):
            return []
        no_speech_prob = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
        is_distilled = not FasterWhisperService.resolve_word_timestamps(
            getattr(self.request, "model_size", ""), True
        )
        max_no_speech = 0.85 if is_distilled else 0.75
        if no_speech_prob >= max_no_speech:
            return []
        avg_logprob = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
        if avg_logprob <= -1.2 and no_speech_prob >= (0.65 if is_distilled else 0.5):
            return []
        text = str(getattr(seg, "text", "") or "").strip()
        target_seg = seg
        if text:
            req_prompt = getattr(self.request, "initial_prompt", None)
            req_hotwords = getattr(self.request, "hotwords", None)
            if SubtitleGenerationValidator.is_prompt_echo(
                text, initial_prompt=req_prompt, hotwords=req_hotwords
            ):
                return []
            cleaned_text, kept_words, new_end_sec, had_rep = (
                SubtitleGenerationValidator.clean_repetition_segment(
                    text,
                    words=getattr(seg, "words", None),
                    start_val=float(getattr(seg, "start", 0.0) or 0.0),
                    end_val=float(getattr(seg, "end", 0.0) or 0.0),
                    words_in_ms=False,
                )
            )
            if not cleaned_text or SubtitleGenerationValidator.is_hallucination(cleaned_text):
                return []
            if SubtitleGenerationValidator.is_prompt_echo(
                cleaned_text, initial_prompt=req_prompt, hotwords=req_hotwords
            ):
                return []
            seg_dur_s = max(0.0, new_end_sec - float(getattr(seg, "start", 0.0) or 0.0))
            if SubtitleGenerationValidator.is_low_cps_courtesy_hallucination(
                cleaned_text, duration_s=seg_dur_s, no_speech_prob=no_speech_prob
            ):
                return []
            req_lang = getattr(self.request, "language", None)
            if req_lang and req_lang != "Auto Detect":
                if not SubtitleGenerationValidator.filter_inconsistent_language(cleaned_text, req_lang):
                    return []
            if had_rep:
                from types import SimpleNamespace
                target_seg = SimpleNamespace(
                    start=float(getattr(seg, "start", 0.0) or 0.0),
                    end=new_end_sec,
                    words=kept_words,
                )

        split_gap_sec = max(1.0, self.request.min_silence_ms / 1000.0)
        has_words = bool(
            [
                w for w in (getattr(target_seg, "words", None) or [])
                if getattr(w, "start", None) is not None and getattr(w, "end", None) is not None
            ]
        )
        if has_words:
            sub_ranges = self.split_segment_by_word_gaps(target_seg, split_gap_sec)
        else:
            sub_ranges = self.clip_segment_to_speech_spans(
                target_seg.start,
                target_seg.end,
                getattr(self, "_active_vad_speech_spans", None),
                merge_gap_sec=split_gap_sec,
            )
        max_speech = getattr(self.request, "vad_max_speech_duration_s", None)
        if (
            isinstance(max_speech, (int, float))
            and not isinstance(max_speech, bool)
            and float(max_speech) > 0.0
        ):
            sub_ranges = FasterWhisperService.enforce_max_speech_spans(
                sub_ranges,
                float(max_speech),
                wav_path=getattr(self, "_active_chunk_wav", None),
            )
        valid_ranges = []
        for s_start, s_end in sub_ranges:
            abs_start_ms = int(s_start * 1000) + actual_start_ms
            abs_end_ms = int(s_end * 1000) + actual_start_ms
            if abs_end_ms <= current_start_ms + 250 and current_start_ms > 0:
                continue
            valid_ranges.append((abs_start_ms, abs_end_ms))
        return valid_ranges

    def _emit_timing_progress(
        self, done_count: int, stage: str = "", min_pct: int = 0
    ) -> None:
        """Emit strictly non-decreasing progress bar percentage and generated count for Timing Draft."""
        target = max(1, int(self.request.target_segment_count or 1))
        done = max(0, min(target, int(done_count)))
        seg_pct = int(done * 100 / target)
        floor_pct = int(getattr(self, "_last_emitted_pct", 0) or 0)
        bar_pct = max(floor_pct, min(99, max(int(min_pct), seg_pct)))
        self._last_emitted_pct = bar_pct
        start_idx = max(1, int(getattr(self.request, "start_segment_index", 1) or 1))
        if start_idx > 1:
            count_text = f"Đã gen {done}/{target} câu ({bar_pct}%) · Tổng {(start_idx - 1) + done} câu"
        else:
            count_text = f"Đã gen {done}/{target} câu ({bar_pct}%)"
        prefix = stage or (
            f"Đang tiếp tục từ câu {start_idx}" if start_idx > 1 else "Đang tạo Timing"
        )
        self.progress_signal.emit(bar_pct, f"{prefix} · {count_text}")

    @staticmethod
    def _shift_segment(seg, offset_sec: float):
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

    def _collect_segments(self, segments_generator, on_segment=None) -> list:
        """Consume Whisper generator segment-by-segment for live progress and cancellation."""
        raw_segments = []
        for seg in segments_generator:
            if self.is_cancelled:
                break
            raw_segments.append(seg)
            if callable(on_segment) and on_segment(seg):
                break
        return raw_segments

    def _transcribe_progressive_slices(
        self, model, chunk_wav: str, kwargs: dict, on_segment=None
    ) -> tuple[list, object]:
        """Transcribe long WAVs in <=25s sub-slices so small batches & Cancel return in ~1-3s instead of blocking C++."""
        from types import SimpleNamespace

        wav_duration = None
        if chunk_wav and os.path.exists(chunk_wav):
            try:
                with wave.open(chunk_wav, "rb") as wf:
                    n_frames = wf.getnframes()
                    fps = wf.getframerate()
                    params = wf.getparams()
                if (
                    isinstance(n_frames, int)
                    and not isinstance(n_frames, bool)
                    and isinstance(fps, int)
                    and not isinstance(fps, bool)
                    and isinstance(getattr(params, "nchannels", None), int)
                    and not isinstance(getattr(params, "nchannels", None), bool)
                    and isinstance(getattr(params, "sampwidth", None), int)
                    and not isinstance(getattr(params, "sampwidth", None), bool)
                    and n_frames > 0
                    and fps > 0
                ):
                    wav_duration = n_frames / float(fps)
            except Exception:
                wav_duration = None

        if wav_duration is None or wav_duration <= 30.0:
            vad_params = kwargs.get("vad_parameters") if kwargs.get("vad_filter") else None
            max_speech_cap = (vad_params or {}).get("max_speech_duration_s")
            model_size = getattr(self.request, "model_size", "")
            if (
                wav_duration is not None
                and isinstance(max_speech_cap, (int, float))
                and not isinstance(max_speech_cap, bool)
                and float(max_speech_cap) > 0.0
                and wav_duration > (float(max_speech_cap) + 1e-3)
                and not FasterWhisperService.is_kotoba_model(model_size)
                and chunk_wav
                and os.path.exists(chunk_wav)
            ):
                try:
                    from faster_whisper.audio import decode_audio
                    from faster_whisper.vad import VadOptions, get_speech_timestamps

                    vad_audio = decode_audio(chunk_wav, sampling_rate=16000)
                    speech_chunks = get_speech_timestamps(vad_audio, VadOptions(**vad_params))
                    if speech_chunks:
                        total_vad_span_s = (
                            float(speech_chunks[-1]["end"]) - float(speech_chunks[0]["start"])
                        ) / 16000.0
                        if total_vad_span_s > (float(max_speech_cap) + 1e-3):
                            bounded_spans = FasterWhisperService.build_bounded_vad_windows(
                                speech_chunks,
                                float(max_speech_cap),
                                int((vad_params or {}).get("min_silence_duration_ms", 300)),
                                audio=vad_audio,
                                sampling_rate=16000,
                            )
                            collected = []
                            last_info = SimpleNamespace(
                                duration=wav_duration,
                                duration_after_vad=total_vad_span_s,
                                language=kwargs.get("language") or "ja",
                                language_probability=1.0,
                            )
                            sub_wav = os.path.join(tempfile.gettempdir(), f"timing_vad_cap_{id(self)}.wav")
                            try:
                                for sp_start, sp_end in bounded_spans:
                                    if self.is_cancelled:
                                        break
                                    if FasterWhisperService._slice_wav_segment(chunk_wav, sp_start, sp_end, sub_wav):
                                        part_gen, part_info = model.transcribe(sub_wav, **dict(kwargs))
                                        last_info = part_info or last_info
                                        for p_seg in part_gen:
                                            if self.is_cancelled:
                                                break
                                            shifted = self._shift_segment(p_seg, sp_start)
                                            collected.append(shifted)
                                            if callable(on_segment) and on_segment(shifted):
                                                return collected, last_info
                                return collected, last_info
                            finally:
                                if os.path.exists(sub_wav):
                                    try:
                                        os.remove(sub_wav)
                                    except OSError:
                                        pass
                except Exception:
                    pass
            segments_generator, info = model.transcribe(chunk_wav, **kwargs)
            return self._collect_segments(segments_generator, on_segment=on_segment), info

        slice_sec = 25.0
        overlap_sec = 2.0
        step_sec = slice_sec - overlap_sec
        fps = params.framerate or 16000
        total_frames = params.nframes
        slice_frames = int(slice_sec * fps)
        step_frames = int(step_sec * fps)
        sub_wav = os.path.join(tempfile.gettempdir(), f"timing_slice_{id(self)}.wav")

        all_segments = []
        total_speech_sec = 0.0
        detected_lang = kwargs.get("language") or "?"
        detected_prob = 0.0
        last_seen_end_s = None

        try:
            with wave.open(chunk_wav, "rb") as src_wf:
                frame_pos = 0
                while frame_pos < total_frames:
                    if self.is_cancelled:
                        break
                    read_count = min(slice_frames, total_frames - frame_pos)
                    src_wf.setpos(frame_pos)
                    raw_bytes = src_wf.readframes(read_count)
                    if not raw_bytes:
                        break
                    with wave.open(sub_wav, "wb") as dst_wf:
                        dst_wf.setnchannels(params.nchannels)
                        dst_wf.setsampwidth(params.sampwidth)
                        dst_wf.setframerate(fps)
                        dst_wf.writeframes(raw_bytes)

                    offset_sec = frame_pos / float(fps)
                    seg_gen, slice_info = model.transcribe(sub_wav, **kwargs)
                    total_speech_sec += float(getattr(slice_info, "duration_after_vad", 0.0) or 0.0)
                    if getattr(slice_info, "language", None):
                        detected_lang = slice_info.language
                    detected_prob = max(
                        detected_prob,
                        float(getattr(slice_info, "language_probability", 0.0) or 0.0),
                    )

                    reached_target = False
                    for raw_seg in seg_gen:
                        if self.is_cancelled:
                            break
                        shifted = self._shift_segment(raw_seg, offset_sec)
                        if last_seen_end_s is not None and shifted.end <= last_seen_end_s + 0.25:
                            continue
                        if last_seen_end_s is not None and shifted.start < last_seen_end_s + 0.05:
                            shifted = self._shift_segment(
                                shifted, 0.0
                            )
                            from types import SimpleNamespace
                            clamped_start = last_seen_end_s + 0.05
                            if getattr(shifted, "words", None):
                                shifted_words = [
                                    w for w in shifted.words
                                    if getattr(w, "end", None) is None or float(w.end) > clamped_start
                                ]
                            else:
                                shifted_words = None
                            shifted = SimpleNamespace(
                                start=clamped_start,
                                end=float(shifted.end),
                                text=getattr(shifted, "text", ""),
                                no_speech_prob=getattr(shifted, "no_speech_prob", 0.0),
                                avg_logprob=getattr(shifted, "avg_logprob", 0.0),
                                compression_ratio=getattr(shifted, "compression_ratio", None),
                                temperature=getattr(shifted, "temperature", None),
                                words=shifted_words,
                            )
                        last_seen_end_s = max(last_seen_end_s or 0.0, float(shifted.end))
                        all_segments.append(shifted)
                        if callable(on_segment) and on_segment(shifted):
                            reached_target = True
                            break

                    if self.is_cancelled or reached_target:
                        break
                    if frame_pos + read_count >= total_frames:
                        break
                    frame_pos += step_frames
        finally:
            if os.path.exists(sub_wav):
                try:
                    os.remove(sub_wav)
                except OSError:
                    pass

        merged_info = SimpleNamespace(
            duration=wav_duration,
            duration_after_vad=total_speech_sec,
            language=detected_lang,
            language_probability=detected_prob,
        )
        return all_segments, merged_info

    def _build_transcribe_kwargs(self, language: str | None, *, vad_filter: bool, word_timestamps: bool, vad_parameters: dict | None = None) -> dict:
        model_size = getattr(self.request, "model_size", "")
        req_cond = getattr(self.request, "condition_on_previous_text", True)
        effective_lang, effective_cond = FasterWhisperService.resolve_decode_defaults(
            model_size,
            language,
            True if req_cond is None else bool(req_cond),
        )
        effective_word_ts = FasterWhisperService.resolve_word_timestamps(
            model_size,
            word_timestamps,
        )
        req_hst = getattr(self.request, "hallucination_silence_threshold", None)
        effective_hst = 1.0 if req_hst is None else float(req_hst)
        kwargs = {
            "vad_filter": vad_filter,
            "word_timestamps": effective_word_ts,
            "temperature": (0.0, 0.2),
            "best_of": 2,
            "no_speech_threshold": 0.6,
            "log_prob_threshold": -1.0,
            "compression_ratio_threshold": 2.4,
            "condition_on_previous_text": bool(effective_cond),
        }
        if FasterWhisperService.is_large_v3_model(model_size):
            kwargs["repetition_penalty"] = 1.1
            kwargs["no_repeat_ngram_size"] = 3
        if vad_parameters is not None:
            kwargs["vad_parameters"] = vad_parameters
        if effective_word_ts and effective_hst > 0:
            kwargs["hallucination_silence_threshold"] = effective_hst
        if effective_lang:
            kwargs["language"] = effective_lang
        req_patience = getattr(self.request, "patience", None)
        if req_patience is not None:
            # Cap beam patience at 1.0 for Timing Draft so slow high-patience beams never stall cancel/progress.
            kwargs["patience"] = min(1.0, float(req_patience))
        # Distilled models (kotoba/distil) degrade/drop segments when fed Whisper prompt/hotwords tokens.
        if FasterWhisperService.is_large_v3_model(model_size):
            from core.subtitle_generation.language_utils import (
                extract_natural_initial_prompt,
                extract_terminology_terms,
                merge_hotwords,
            )

            req_prompt = str(getattr(self.request, "initial_prompt", "") or "").strip()
            req_hotwords = str(getattr(self.request, "hotwords", "") or "").strip()
            kwargs["initial_prompt"] = extract_natural_initial_prompt(req_prompt, effective_lang)
            merged_hw = merge_hotwords(
                req_hotwords,
                extract_terminology_terms(req_prompt),
                sep=" ",
            )
            kwargs["hotwords"] = merged_hw or None
        elif FasterWhisperService.resolve_word_timestamps(model_size, True):
            req_prompt = str(getattr(self.request, "initial_prompt", "") or "").strip()
            if req_prompt:
                kwargs["initial_prompt"] = req_prompt
            req_hotwords = str(getattr(self.request, "hotwords", "") or "").strip()
            if req_hotwords:
                kwargs["hotwords"] = req_hotwords
        FasterWhisperService._enforce_kotoba_guard(model_size, kwargs)
        return kwargs

    def _transcribe_with_vad_retry(self, model, chunk_wav, language=None, on_segment=None):
        """Retry one empty VAD result at a lower, still-VAD threshold."""
        ensure_silero_vad_anti_saturation_patch()
        self._active_chunk_wav = chunk_wav
        vad_preset = getattr(self.request, "vad_preset", None)
        vad_threshold = getattr(self.request, "vad_threshold", None)
        is_explicit_preset = (
            vad_preset not in (None, "standard")
            or (vad_threshold is not None and vad_threshold != 0.5)
        )
        if is_explicit_preset:
            target_threshold = float(vad_threshold if vad_threshold is not None else 0.35)
            thresholds = (target_threshold,)
        else:
            thresholds = (0.5, 0.35)

        min_speech = int(getattr(self.request, "min_speech_duration_ms", None) or 500)
        speech_pad = int(getattr(self.request, "vad_speech_pad_ms", None) or 400)
        max_speech = getattr(self.request, "vad_max_speech_duration_s", None)

        info = None
        for attempt, threshold in enumerate(thresholds, start=1):
            vad_parameters = {
                "min_silence_duration_ms": self.request.min_silence_ms,
                "threshold": threshold,
                "min_speech_duration_ms": min_speech,
                "speech_pad_ms": speech_pad,
            }
            if max_speech is not None:
                vad_parameters["max_speech_duration_s"] = float(max_speech)

            kwargs = self._build_transcribe_kwargs(
                language,
                vad_filter=True,
                word_timestamps=True,
                vad_parameters=vad_parameters,
            )
            self._active_vad_speech_spans = (
                None
                if kwargs.get("word_timestamps", False)
                else self._compute_vad_speech_spans(chunk_wav, vad_parameters)
            )
            raw_segments, info = self._transcribe_progressive_slices(
                model, chunk_wav, kwargs, on_segment=on_segment
            )
            if self.is_cancelled:
                return raw_segments, info
            duration = float(getattr(info, "duration", 0.0) or 0.0)
            duration_after_vad = float(
                getattr(info, "duration_after_vad", 0.0) or 0.0
            )
            detected_language = getattr(info, "language", "?")
            probability = float(
                getattr(info, "language_probability", 0.0) or 0.0
            )
            self.log_signal.emit(
                "[Batch Worker] VAD "
                f"attempt={attempt}, threshold={threshold:.2f}, "
                f"audio={duration:.2f}s, speech={duration_after_vad:.2f}s, "
                f"language={detected_language} ({probability:.2f}), "
                f"raw_segments={len(raw_segments)}."
            )
            if raw_segments or attempt == len(thresholds):
                if (not raw_segments) and (not self.is_cancelled) and duration_after_vad >= 0.5:
                    # Silero VAD confirmed speech, yet Whisper skipped chunks on no_speech/log_prob thresholds.
                    relaxed_kwargs = dict(kwargs)
                    relaxed_kwargs["no_speech_threshold"] = None
                    relaxed_kwargs["log_prob_threshold"] = None
                    self.log_signal.emit(
                        f"[Batch Worker] VAD phát hiện {duration_after_vad:.2f}s thoại nhưng model trả 0 segment; thử lại với ngưỡng nới lỏng."
                    )
                    return self._transcribe_progressive_slices(
                        model, chunk_wav, relaxed_kwargs, on_segment=on_segment
                    )
                return raw_segments, info
            next_threshold = thresholds[attempt]
            self.log_signal.emit(
                f"[Batch Worker] VAD trả về 0 segment; retry với threshold {next_threshold:.2f}."
            )
        return [], info

    def run(self):
        chunk_wav = None
        self._last_emitted_pct = 0
        empty_scan_windows = 0
        try:
            from faster_whisper import WhisperModel
            import torch
            from core.runtime.runtime_paths import RuntimePaths
            from core.services.model_manager import ModelManager

            # [TỐI ƯU HÓA HIỆU NĂNG]
            # Chỉ nạp Whisper Model vào RAM/VRAM đúng 1 lần duy nhất cho toàn bộ Batch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = self.effective_compute_type(device, self.request.compute_type)
            if device == "cuda" and compute_type == "float16":
                downgrade, ratio = should_downgrade_to_int8_float16(0.65)
                if downgrade:
                    compute_type = "int8_float16"
                    self.log_signal.emit(
                        f"[ASR] VRAM đạt {ratio * 100:.0f}% (>65%) ➔ Tự động chuyển sang int8_float16."
                    )
            self.effective_compute_signal.emit(compute_type)
            
            self.log_signal.emit(f"[Batch Worker] Đang tải Model Whisper ({self.request.model_size})...")
            if not ModelManager.supports_word_timestamps(self.request.model_size):
                self.log_signal.emit(
                    f"[Batch Worker] Model {self.request.model_size} (distilled) không hỗ trợ word alignment; tự động tắt word_timestamps."
                )
            self._emit_timing_progress(
                0,
                f"Đang tải Model ({self.request.model_size})",
                min_pct=2,
            )
            # [S7.2-T14] Ép Model Manager quyết định đường dẫn tải
            ModelManager.ensure_windows_hf_no_symlink()
            safe_model_path = ModelManager.get_model_path_for_inference(self.request.model_size)
            model = WhisperModel(
                safe_model_path,
                device=device, 
                compute_type=compute_type,
                download_root=str(RuntimePaths.get_models_dir())
            )

            vad_filter = self.request.use_vad

            all_final_segments = []
            current_start_ms = self.request.start_ms
            is_end_of_source = False
            
            temp_dir = tempfile.gettempdir()
            chunk_wav = os.path.join(temp_dir, f"timing_chunk_{id(self)}.wav")

            # [S7.1-FIX-11] VÒNG LẶP TRƯỢT THỜI GIAN THÔNG MINH
            # Liên tục trượt cửa sổ thời gian cắt audio cho đến khi lấy đủ target_count
            while len(all_final_segments) < self.request.target_segment_count:
                if self.is_cancelled:
                    return

                # Giám sát VRAM thời gian thực (>65%) giữa các cửa sổ trượt
                if device == "cuda" and compute_type == "float16":
                    downgrade, ratio = should_downgrade_to_int8_float16(0.65)
                    if downgrade:
                        compute_type = "int8_float16"
                        self.log_signal.emit(
                            f"[ASR] VRAM đạt {ratio * 100:.0f}% (>65%) ➔ Tự động chuyển sang int8_float16."
                        )
                        del model
                        gc.collect()
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        model = WhisperModel(
                            safe_model_path,
                            device=device,
                            compute_type=compute_type,
                            download_root=str(RuntimePaths.get_models_dir()),
                        )
                        self.effective_compute_signal.emit(compute_type)

                overlap = self.request.overlap_ms if current_start_ms > 0 else 0
                actual_start_ms = max(0, current_start_ms - overlap)
                
                start_sec = actual_start_ms / 1000.0
                duration_sec = self.request.max_window_ms / 1000.0

                self.log_signal.emit(f"[Batch Worker] Trích xuất audio từ {start_sec:.2f}s, window {duration_sec}s...")
                self._emit_timing_progress(
                    len(all_final_segments),
                    "Đang trích xuất âm thanh",
                    min_pct=5,
                )

                audio_filter = FasterWhisperService.build_ffmpeg_audio_filter(
                    speech_filter=bool(getattr(self.request, "speech_filter", False)),
                )
                cmd = [
                    RuntimePaths.get_ffmpeg_exe(), "-y",
                    "-ss", str(start_sec),
                    "-t", str(duration_sec),
                    "-i", self.request.video_path,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                ]
                if audio_filter:
                    cmd.extend(["-af", audio_filter])
                cmd.append(chunk_wav)
                
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
                if self.is_cancelled:
                    return

                stderr_lines = [
                    line.strip()
                    for line in (process.stderr or "").splitlines()
                    if any(
                        marker in line.casefold()
                        for marker in ("error", "invalid", "corrupt", "failed")
                    )
                ]
                chunk_size = (
                    os.path.getsize(chunk_wav) if os.path.exists(chunk_wav) else 0
                )
                self.log_signal.emit(
                    "[Batch Worker] FFmpeg "
                    f"exit={process.returncode}, wav_bytes={chunk_size}, "
                    f"decode_warnings={len(stderr_lines)}."
                )
                for line in stderr_lines[:3]:
                    self.log_signal.emit(f"[Batch Worker] FFmpeg warning: {line}")

                if process.returncode != 0:
                    detail = stderr_lines[-1] if stderr_lines else "unknown error"
                    raise RuntimeError(
                        f"FFmpeg không thể trích xuất audio (exit {process.returncode}): {detail}"
                    )

                # Fast seeking can truncate WMV audio well before the video ends.
                try:
                    with wave.open(chunk_wav, "rb") as wav:
                        audio_duration = wav.getnframes() / wav.getframerate()
                except (OSError, EOFError, wave.Error):
                    audio_duration = None
                if (audio_duration is None and chunk_size < 1024) or (
                    audio_duration is not None and audio_duration < duration_sec - 5.0
                ):
                    accurate_cmd = [
                        RuntimePaths.get_ffmpeg_exe(), "-y", "-i", self.request.video_path,
                        "-ss", str(start_sec), "-t", str(duration_sec),
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    ]
                    if audio_filter:
                        accurate_cmd.extend(["-af", audio_filter])
                    accurate_cmd.append(chunk_wav)
                    retry = subprocess.run(
                        accurate_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        text=True, errors="replace",
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    )
                    if self.is_cancelled:
                        return
                    if retry.returncode != 0:
                        raise RuntimeError(f"FFmpeg cắt chính xác audio thất bại: {retry.stderr}")
                    with wave.open(chunk_wav, "rb") as wav:
                        audio_duration = wav.getnframes() / wav.getframerate()
                    self.log_signal.emit(
                        f"[Batch Worker] Cắt chính xác sau seek ngắn: audio={audio_duration:.2f}s."
                    )

                if not os.path.exists(chunk_wav) or os.path.getsize(chunk_wav) < 1024:
                    self.log_signal.emit("[Batch Worker] Trích xuất trả về rỗng (Đã đến cuối video).")
                    is_end_of_source = True
                    break

                self.log_signal.emit("[Batch Worker] Đang nhận diện (Infer) âm thanh...")
                self._emit_timing_progress(len(all_final_segments), "", min_pct=8)

                live_chunk_valid_count = 0

                def _on_live_segment(seg) -> bool:
                    nonlocal live_chunk_valid_count
                    ranges = self._extract_valid_sub_ranges(
                        seg, actual_start_ms, current_start_ms
                    )
                    if not ranges:
                        return False
                    live_chunk_valid_count += len(ranges)
                    done_now = min(
                        self.request.target_segment_count,
                        len(all_final_segments) + live_chunk_valid_count,
                    )
                    self._emit_timing_progress(done_now, "", min_pct=10)
                    return done_now >= self.request.target_segment_count

                is_music = getattr(self.request, "music_mode", False)
                lang = getattr(self.request, "language", None)
                if lang == "Auto Detect":
                    lang = None
                if is_music:
                    self._active_vad_speech_spans = None
                    # Chế độ Nhạc: Bỏ qua Silero VAD (tránh nuốt câu do nhạc nền), 
                    # kích hoạt word_timestamps để Whisper tự tách nhịp câu tự nhiên
                    kwargs = self._build_transcribe_kwargs(
                        lang,
                        vad_filter=False,
                        word_timestamps=True,
                    )
                    segments_generator, info = model.transcribe(chunk_wav, **kwargs)
                    raw_segments = self._collect_segments(
                        segments_generator, on_segment=_on_live_segment
                    )
                elif vad_filter:
                    raw_segments, info = self._transcribe_with_vad_retry(
                        model, chunk_wav, language=lang, on_segment=_on_live_segment
                    )
                else:
                    self._active_vad_speech_spans = None
                    kwargs = self._build_transcribe_kwargs(
                        lang,
                        vad_filter=False,
                        word_timestamps=False,
                    )
                    segments_generator, info = model.transcribe(chunk_wav, **kwargs)
                    raw_segments = self._collect_segments(
                        segments_generator, on_segment=_on_live_segment
                    )

                if self.is_cancelled:
                    return

                # Decoder warnings can shorten a nominal 120s WAV slightly.
                # Let the next extraction prove EOF instead of ending early.
                chunk_end_of_source = (audio_duration if audio_duration is not None else info.duration) < (duration_sec - 5.0)

                added_in_chunk = 0
                last_end_ms_in_chunk = current_start_ms
                tail_pad_ms = max(0, int(getattr(self.request, "tail_pad_ms", 0) or 0))
                overlap_gap = max(0, int(getattr(self.request, "overlap_gap_ms", 50) or 0))
                for seg in raw_segments:
                    if self.is_cancelled:
                        return
                    for abs_start_ms, abs_end_ms in self._extract_valid_sub_ranges(
                        seg, actual_start_ms, current_start_ms
                    ):
                        if tail_pad_ms > 0:
                            # Đệm nhẹ hai đầu câu để không xén mất phụ âm đầu / trợ từ cuối câu (わ, よ, ね)
                            abs_start_ms = max(0, abs_start_ms - min(60, abs_start_ms))
                            abs_end_ms = abs_end_ms + tail_pad_ms
                            if all_final_segments and getattr(self.request, "fix_overlap", True):
                                prev_seg = all_final_segments[-1]
                                min_allowed_start = prev_seg["end_ms"] + overlap_gap
                                if abs_start_ms < min_allowed_start:
                                    # Giảm phần tail_pad của câu trước trước khi đẩy mốc đầu câu hiện tại
                                    reclaimed = min(tail_pad_ms, min_allowed_start - abs_start_ms)
                                    prev_seg["end_ms"] = max(prev_seg["start_ms"] + 1, prev_seg["end_ms"] - reclaimed)
                                    abs_start_ms = max(abs_start_ms, prev_seg["end_ms"] + overlap_gap)
                                if abs_end_ms <= abs_start_ms:
                                    abs_end_ms = abs_start_ms + 1
                        all_final_segments.append({
                            "start_ms": abs_start_ms,
                            "end_ms": abs_end_ms,
                            "text": ""
                        })
                        added_in_chunk += 1
                        last_end_ms_in_chunk = abs_end_ms
                        if len(all_final_segments) >= self.request.target_segment_count:
                            break
                    if len(all_final_segments) >= self.request.target_segment_count:
                        break

                if chunk_end_of_source and len(all_final_segments) < self.request.target_segment_count:
                    is_end_of_source = True
                    break
                    
                # Chống kẹt vòng lặp vô hạn ở những vùng video tĩnh lặng hoàn toàn
                if added_in_chunk == 0:
                    empty_scan_windows += 1
                    advance_ms = max(1000, int(info.duration * 1000) - self.request.overlap_ms)
                    current_start_ms += advance_ms
                    if not all_final_segments:
                        mm, ss = divmod(int(current_start_ms // 1000), 60)
                        hh, mm = divmod(mm, 60)
                        ts_text = f"{hh:02d}:{mm:02d}:{ss:02d}" if hh else f"{mm:02d}:{ss:02d}"
                        self._emit_timing_progress(
                            0,
                            f"Đang quét qua vùng chưa có thoại ({ts_text})",
                            min_pct=min(18, 8 + empty_scan_windows),
                        )
                else:
                    # Trượt cửa sổ tiến đến cuối câu phân tích vừa rồi
                    current_start_ms = last_end_ms_in_chunk

            if len(all_final_segments) > self.request.target_segment_count:
                all_final_segments = all_final_segments[:self.request.target_segment_count]
                is_end_of_source = False 

            self.progress_signal.emit(
                100,
                f"Hoàn tất Batch Timing · Đã gen {len(all_final_segments)}/{self.request.target_segment_count} câu (100%)",
            )
            self.finished_signal.emit(all_final_segments, is_end_of_source)

        except Exception as e:
            self.error_signal.emit(str(e))
            print(traceback.format_exc())
            
        finally:
            if chunk_wav and os.path.exists(chunk_wav):
                try:
                    os.remove(chunk_wav)
                except:
                    pass

    def cancel(self):
        self.is_cancelled = True
