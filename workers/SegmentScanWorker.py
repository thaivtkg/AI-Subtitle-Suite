import copy
import dataclasses
import datetime
import math
import re

from PySide6.QtCore import QThread, Signal
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.subtitle_generation.generation_validator import SubtitleGenerationValidator


_SUSPECT_SHORT_CLIP_HALLUCINATIONS = {
    "はいありがとうございます",
    "はいありがとうございました",
    "ありがとうございます",
    "ありがとうございました",
    "どうもありがとうございます",
    "どうもありがとうございました",
    "はいどうもありがとうございました",
    "ごちそうさまでした",
    "はいごちそうさまでした",
    "ご清聴ありがとうございました",
    "次の動画でお会いしましょう",
    "よろしくお願いします",
    "よろしくお願いいたします",
    "お疲れ様でした",
    "お疲れさまでした",
    "おつかれさまでした",
}


def _normalize_ja_phrase(text: str) -> str:
    return re.sub(r"[\s。、.,!?！？・…「」『』()\[\]]+", "", str(text or "")).strip().casefold()


_TWO_BEAT_REPETITION_RE = re.compile(r"^(.{2,5})\1$")
_AUTO_FALLBACK_MIN_LOGPROB = -1.15
_AUTO_FALLBACK_TWO_BEAT_MIN_LOGPROB = -0.95


def _is_short_clip_suspect_hallucination(text: str) -> bool:
    norm = _normalize_ja_phrase(text)
    return bool(norm and norm in _SUSPECT_SHORT_CLIP_HALLUCINATIONS)


def _is_two_beat_repetition(text: str) -> bool:
    norm = _normalize_ja_phrase(text)
    return bool(norm and _TWO_BEAT_REPETITION_RE.match(norm))


def _compute_weighted_avg_logprob(
    segments,
    *,
    target_start_ms: int | None = None,
    target_end_ms: int | None = None,
) -> float | None:
    """Compute text-length-weighted avg_logprob over segments (overlapping target span when specified)."""
    weighted_sum = 0.0
    total_weight = 0
    for seg in segments or ():
        if target_start_ms is not None and target_end_ms is not None:
            seg_start = getattr(seg, "start_ms", None)
            seg_end = getattr(seg, "end_ms", None)
            if (seg_end is not None and seg_end <= target_start_ms) or (
                seg_start is not None and seg_start >= target_end_ms
            ):
                continue
        raw_lp = getattr(seg, "avg_logprob", None)
        if not isinstance(raw_lp, (int, float)) or isinstance(raw_lp, bool):
            continue
        lp = float(raw_lp)
        if not math.isfinite(lp):
            continue
        clean_text = str(getattr(seg, "text", "") or "").strip()
        weight = max(1, len(clean_text))
        weighted_sum += lp * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return weighted_sum / float(total_weight)


def _seg_ms(seg: dict, key_ms: str, key_str: str) -> int | None:
    val = seg.get(key_ms)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val)
    raw = seg.get(key_str)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, str) and raw.strip():
        parts = raw.strip().replace(".", ",").split(":")
        if len(parts) == 3:
            sec_parts = parts[2].split(",")
            try:
                ms = int(sec_parts[1]) if len(sec_parts) > 1 else 0
                return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(sec_parts[0])) * 1000 + ms
            except ValueError:
                return None
    return None


def resolve_tier3_context(
    all_segments: list | None,
    segment_id: str,
    start_ms: int,
    end_ms: int,
) -> tuple[tuple[int, int], str]:
    """Combine neighboring subtitle span and text around a segment for Tier 3 ASR context."""
    s_ms = max(0, int(start_ms))
    e_ms = max(s_ms + 1, int(end_ms))
    target_dur = e_ms - s_ms

    default_pad = 1500 if target_dur < 3000 else 150
    ctx_start = max(0, s_ms - default_pad)
    ctx_end = e_ms + default_pad
    prompt_parts: list[str] = []

    if not all_segments:
        return (ctx_start, ctx_end), ""

    target_idx = -1
    sid_str = str(segment_id)
    for idx, seg in enumerate(all_segments):
        cur_id = str(seg.get("id") or seg.get("stt") or (idx + 1))
        if cur_id == sid_str:
            target_idx = idx
            break
    if target_idx < 0:
        for idx, seg in enumerate(all_segments):
            ps = _seg_ms(seg, "start_ms", "start")
            pe = _seg_ms(seg, "end_ms", "end")
            if ps == s_ms and pe == e_ms:
                target_idx = idx
                break

    if target_idx < 0:
        return (ctx_start, ctx_end), ""

    max_expand_ms = 4000
    max_gap_ms = 5000

    # Combine preceding subtitle segment into audio window + prompt context
    for prev_idx in range(max(0, target_idx - 2), target_idx):
        p_seg = all_segments[prev_idx]
        p_text = str(p_seg.get("original_text") or p_seg.get("text") or "").strip()
        if p_text and p_text != "[ Chưa có nội dung ]":
            clean_p_text, _ = SubtitleGenerationValidator.sanitize_repetition_text(p_text)
            p_st = _seg_ms(p_seg, "start_ms", "start")
            p_en = _seg_ms(p_seg, "end_ms", "end")
            p_dur_s = ((p_en - p_st) / 1000.0) if (p_st is not None and p_en is not None and p_en > p_st) else None
            is_cjk_high_cps = bool(
                p_dur_s
                and re.search(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]", clean_p_text or "")
                and SubtitleGenerationValidator.is_high_cps_hallucination(
                    clean_p_text, duration_s=p_dur_s, language="ja"
                )
            )
            if (
                clean_p_text
                and not SubtitleGenerationValidator.is_hallucination(clean_p_text)
                and not SubtitleGenerationValidator.is_low_cps_courtesy_hallucination(
                    clean_p_text, duration_s=p_dur_s
                )
                and not is_cjk_high_cps
            ):
                prompt_parts.append(clean_p_text)

    if target_idx > 0:
        prev_seg = all_segments[target_idx - 1]
        p_start = _seg_ms(prev_seg, "start_ms", "start")
        p_end = _seg_ms(prev_seg, "end_ms", "end")
        if p_start is not None and p_end is not None and (s_ms - p_end) <= max_gap_ms:
            ctx_start = max(0, max(s_ms - max_expand_ms, p_start) - 150)

    if target_idx + 1 < len(all_segments):
        next_seg = all_segments[target_idx + 1]
        n_start = _seg_ms(next_seg, "start_ms", "start")
        n_end = _seg_ms(next_seg, "end_ms", "end")
        if n_start is not None and n_end is not None and (n_start - e_ms) <= max_gap_ms:
            ctx_end = max(ctx_end, min(e_ms + max_expand_ms, n_end) + 150)

    return (ctx_start, ctx_end), " ".join(prompt_parts).strip()


_WORD_BOUNDARY_PUNCT = set("、。,.，！？!?・…「」『』()（）[]【】;；:：")
_LEADING_EDGE_PUNCT = "、,，.。・;；:："
_TRAILING_EDGE_PUNCT = "、,，・;；:："


def _group_segment_word_units(words: list) -> list[tuple[int, int, str, list[tuple[int, int]]]]:
    """Group Whisper BPE sub-word tokens into atomic whole-word units without slicing CJK words."""
    units: list[list] = []
    for w in words:
        w_raw = str(w.get("word", "") or "")
        w_s = w_raw.strip()
        if not w_s:
            continue
        ws = int(w.get("start_ms", 0))
        we = int(w.get("end_ms", 0))
        is_punct = all(ch in _WORD_BOUNDARY_PUNCT for ch in w_s)

        if not units:
            units.append([ws, we, [w_raw], [] if is_punct else [(ws, we)]])
            continue

        prev = units[-1]
        prev_raw = prev[2][-1]
        prev_unit_s = "".join(prev[2]).strip()
        gap_ms = ws - prev[1]

        start_new = False
        if w_raw[0].isspace() or prev_raw[-1].isspace() or gap_ms >= 150:
            start_new = True
        elif is_punct:
            start_new = False
        elif prev_unit_s and prev_unit_s[-1] in _WORD_BOUNDARY_PUNCT:
            start_new = True
        elif (
            len(prev_unit_s) >= 2
            and prev_unit_s[-1] == "ー"
            and ("\u3041" <= prev_unit_s[-2] <= "\u3096")
            and w_s[0] != "ー"
        ):
            # Split after hiragana elongation (e.g. あー + やめてー) while preserving katakana words (スーパー).
            start_new = True

        if start_new:
            units.append([ws, we, [w_raw], [] if is_punct else [(ws, we)]])
        else:
            prev[0] = min(prev[0], ws)
            prev[1] = max(prev[1], we)
            prev[2].append(w_raw)
            if not is_punct:
                prev[3].append((ws, we))

    return [(u[0], u[1], "".join(u[2]), u[3] or [(u[0], u[1])]) for u in units]


def _word_unit_in_span(
    u_start: int,
    u_end: int,
    sub_tokens: list[tuple[int, int]],
    start_ms: int,
    end_ms: int,
) -> bool:
    if u_end <= u_start:
        return start_ms <= u_start < end_ms
    overlap_ms = max(0, min(u_end, end_ms) - max(u_start, start_ms))
    if overlap_ms <= 0:
        return False
    u_mid = (u_start + u_end) / 2.0
    overlap_ratio = overlap_ms / float(u_end - u_start)
    if ((start_ms - 60) <= u_mid <= end_ms) or (overlap_ratio >= 0.50):
        return True
    # Rescue intact word when Whisper DTW stretches its leading sub-token over prior silence.
    if u_end <= end_ms and len(sub_tokens) >= 2:
        inside = sum(1 for tws, twe in sub_tokens if start_ms <= ((tws + twe) / 2.0) <= end_ms)
        if (inside / float(len(sub_tokens))) >= 0.50:
            return True
    return False


def _extract_text_for_target_span(valid_segs: list, start_ms: int, end_ms: int) -> tuple[str, bool]:
    """Extract only whole words belonging to [start_ms, end_ms]; report if outside words exist."""
    any_words = any(getattr(s, "words", None) for s in valid_segs)
    if any_words:
        kept_chunks: list[str] = []
        has_outside_words = False
        for seg in valid_segs:
            words = getattr(seg, "words", None) or []
            if not words:
                if (getattr(seg, "end_ms", None) is None or seg.end_ms > start_ms) and (
                    getattr(seg, "start_ms", None) is None or seg.start_ms < end_ms
                ):
                    txt = (getattr(seg, "text", "") or "").strip()
                    if txt:
                        kept_chunks.append(txt)
                else:
                    has_outside_words = True
                continue
            seg_kept: list[str] = []
            for u_start, u_end, u_text, sub_tokens in _group_segment_word_units(words):
                if _word_unit_in_span(u_start, u_end, sub_tokens, start_ms, end_ms):
                    seg_kept.append(u_text)
                else:
                    has_outside_words = True
            seg_text = "".join(seg_kept).strip()
            if seg_text:
                kept_chunks.append(seg_text)
        extracted = " ".join(kept_chunks).strip()
        extracted = extracted.lstrip(_LEADING_EDGE_PUNCT).rstrip(_TRAILING_EDGE_PUNCT).strip()
        return extracted, has_outside_words

    overlapping = [
        seg.text.strip()
        for seg in valid_segs
        if getattr(seg, "text", None)
        and (getattr(seg, "end_ms", None) is None or seg.end_ms > start_ms)
        and (getattr(seg, "start_ms", None) is None or seg.start_ms < end_ms)
    ]
    has_outside = any(
        getattr(seg, "text", None)
        and not (
            (getattr(seg, "end_ms", None) is None or seg.end_ms > start_ms)
            and (getattr(seg, "start_ms", None) is None or seg.start_ms < end_ms)
        )
        for seg in valid_segs
    )
    return " ".join(overlapping).strip(), has_outside


def _clone_request_with(request: SubtitleGenerationRequest, **updates) -> SubtitleGenerationRequest:
    """Return a shallow copy of request with specific override fields applied."""
    if dataclasses.is_dataclass(request):
        return dataclasses.replace(request, **updates)
    cloned = copy.copy(request)
    for key, value in updates.items():
        setattr(cloned, key, value)
    return cloned


def _validate_overlapping_segments(raw_segments: list, start_ms: int, end_ms: int, padded_start: int, padded_end: int) -> list:
    valid_segs = SubtitleGenerationValidator.validate(raw_segments or [], padded_start, padded_end)
    return [
        s for s in valid_segs
        if (getattr(s, "end_ms", None) is None or s.end_ms > start_ms)
        and (getattr(s, "start_ms", None) is None or s.start_ms < end_ms)
    ]


def _format_empty_scan_error(diag_code: str, expected_lang: str | None) -> str:
    base = "Không nhận diện được giọng nói trong đoạn đã chọn"
    if diag_code.startswith("FILTERED_LANGUAGE:"):
        _, lang, sample = diag_code.split(":", 2)
        return (
            f"{base} — Kết quả AI (\"{sample}\") bị lọc do khác ngôn ngữ nguồn "
            f"({lang or expected_lang}). Hãy kiểm tra lại Ngôn ngữ nguồn."
        )
    if diag_code == "HALLUCINATION_FILTERED":
        return f"{base} — Đoạn audio chỉ chứa tạp âm/nhạc nền hoặc ảo giác AI đã bị lọc."
    return f"{base} — Đã thử tăng âm và tắt VAD nhưng không tách được lời thoại rõ ràng."


def _transcribe_segment_with_fallback(
    whisper_service: FasterWhisperService,
    request: SubtitleGenerationRequest,
    seg_id: str,
    start_ms: int,
    end_ms: int,
    is_cancelled_fn,
    force_no_vad: bool = False,
    on_tier_callback=None,
    context_window: tuple[int, int] | None = None,
    context_prompt: str = "",
) -> tuple[str, str]:
    """Run per-segment ASR with short-clip tuning and 3-tier context-expanded fallback."""
    # Giữ đệm trái gọn (60ms) để tránh hút tiếng hít thở trước câu vào Tier 2; giữ đệm phải 150ms cho đuôi câu
    padded_start = max(0, int(start_ms) - 60)
    padded_end = max(int(start_ms) + 1, int(end_ms) + 150)
    supports_word_ts = FasterWhisperService.resolve_word_timestamps(
        getattr(request, "model_size", ""), True
    )
    if supports_word_ts:
        tier3_start, tier3_end = context_window if context_window else (padded_start, padded_end)
        tier3_start = max(0, min(int(tier3_start), padded_start))
        tier3_end = max(padded_end, int(tier3_end))
        has_expanded_context = (tier3_end - tier3_start) > (padded_end - padded_start)
        base_prompt = getattr(request, "prompt_context", "") or ""
        use_prev_ctx = bool(getattr(request, "condition_on_previous_text", True))
        clean_ctx_prompt = (
            SubtitleGenerationValidator.sanitize_repetition_text(context_prompt)[0]
            if (use_prev_ctx and context_prompt and context_prompt.strip())
            else ""
        )
        combined_prompt = (
            f"{base_prompt.strip()} {clean_ctx_prompt}".strip()
            if clean_ctx_prompt
            else base_prompt
        )
    else:
        # Distilled models (kotoba/distil) run with word_timestamps=False and degrade with prompt conditioning;
        # keep Tier 3 focused on the padded segment window without neighbor bleed or prompt tokens.
        tier3_start, tier3_end = padded_start, padded_end
        has_expanded_context = False
        combined_prompt = ""
    target_duration_ms = max(0, int(end_ms) - int(start_ms))

    expected_lang = getattr(request, "language", None)
    base_min_speech = getattr(request, "min_speech_duration_ms", None) or 150
    base_threshold = getattr(request, "vad_threshold", None)

    if force_no_vad:
        tier3_overrides = {
            "use_vad": False,
            "audio_boost": True,
            "no_speech_threshold": 0.85,
            "log_prob_threshold": -1.5,
            "prompt_context": "",
            "hotwords": "",
        }
        if has_expanded_context:
            tier3_overrides["word_timestamps"] = True
        tiers = [
            {
                "tier_name": "Tầng 1/1: Quét sâu kết hợp ngữ cảnh (No VAD)" if has_expanded_context else "Tầng 1/1: Quét sâu không VAD (Deep Scan)",
                "window": (tier3_start, tier3_end),
                "is_context_tier": has_expanded_context,
                "overrides": tier3_overrides,
            },
        ]
    else:
        tier3_overrides = {
            "use_vad": False,
            "audio_boost": True,
            "no_speech_threshold": 0.85,
            "log_prob_threshold": -1.5,
            "prompt_context": "",
            "hotwords": "",
        }
        if has_expanded_context:
            tier3_overrides["word_timestamps"] = True
        tiers = [
            {
                "tier_name": "Tầng 1/3: Nhận diện tiêu chuẩn (VAD)",
                "window": (int(start_ms), max(int(start_ms) + 1, int(end_ms))),
                "is_context_tier": False,
                "overrides": {
                    "min_speech_duration_ms": base_min_speech,
                    "prompt_context": "",
                    "hotwords": "",
                },
            },
            {
                "tier_name": "Tầng 2/3: Tăng âm & Hạ ngưỡng VAD",
                "window": (padded_start, padded_end),
                "is_context_tier": False,
                "overrides": {
                    "min_speech_duration_ms": min(base_min_speech, 100),
                    "vad_threshold": min(float(base_threshold), 0.2) if base_threshold is not None else 0.2,
                    "audio_boost": True,
                    "prompt_context": "",
                    "hotwords": "",
                },
            },
            {
                "tier_name": "Tầng 3/3: Kết hợp ngữ cảnh & Quét sâu (No VAD)" if has_expanded_context else "Tầng 3/3: Quét sâu không VAD (Deep Scan)",
                "window": (tier3_start, tier3_end),
                "is_context_tier": has_expanded_context,
                "overrides": tier3_overrides,
            },
        ]

    saw_hallucination = False
    for tier_idx, tier in enumerate(tiers, 1):
        if is_cancelled_fn():
            return "", "CANCELLED"
        if on_tier_callback:
            on_tier_callback(tier_idx, len(tiers), tier.get("tier_name", f"Tầng {tier_idx}/{len(tiers)}"))
        batch_start, batch_end = tier["window"]
        now_iso = datetime.datetime.now().isoformat()
        batch = SubtitleGenerationBatch(
            batch_id=f"scan_{seg_id}",
            start_ms=batch_start,
            end_ms=batch_end,
            status="RUNNING",
            revision=1,
            created_at=now_iso,
            updated_at=now_iso,
        )
        tier_req = _clone_request_with(request, **tier["overrides"])
        result = whisper_service.transcribe_batch(tier_req, batch, is_cancelled_fn)
        if is_cancelled_fn():
            return "", "CANCELLED"
        if not result:
            continue
        if result.error:
            return "", f"ERROR:{result.error}"

        raw_segments = result.segments or []
        overlapping_raw_text = " ".join(
            [
                seg.text.strip()
                for seg in raw_segments
                if getattr(seg, "text", None)
                and (getattr(seg, "end_ms", None) is None or seg.end_ms > start_ms)
                and (getattr(seg, "start_ms", None) is None or seg.start_ms < end_ms)
            ]
        ).strip()
        if tier["is_context_tier"]:
            valid_segs = SubtitleGenerationValidator.validate(raw_segments, batch_start, batch_end)
            raw_text, has_outside = _extract_text_for_target_span(valid_segs, int(start_ms), int(end_ms))
        else:
            has_outside = False
            valid_segs = _validate_overlapping_segments(
                raw_segments, start_ms, end_ms, batch_start, batch_end
            )
            raw_text = " ".join([seg.text.strip() for seg in valid_segs if getattr(seg, "text", None)]).strip()

        if raw_segments and not valid_segs:
            if (
                expected_lang
                and overlapping_raw_text
                and not SubtitleGenerationValidator.MUSIC_ONLY_PATTERN.match(overlapping_raw_text)
                and not SubtitleGenerationValidator.SOUND_TAG_PATTERN.match(overlapping_raw_text)
                and not SubtitleGenerationValidator.PUNCTUATION_ONLY_PATTERN.match(overlapping_raw_text)
                and not SubtitleGenerationValidator.filter_inconsistent_language(overlapping_raw_text, expected_lang)
            ):
                return "", f"FILTERED_LANGUAGE:{expected_lang}:{overlapping_raw_text[:40]}"
            saw_hallucination = True
            continue

        raw_text_before_san = raw_text
        raw_text, _had_rep = SubtitleGenerationValidator.sanitize_repetition_text(raw_text)
        if not raw_text:
            saw_hallucination = True
            continue

        req_prompt = getattr(tier_req, "prompt_context", None)
        req_hotwords = getattr(tier_req, "hotwords", None)
        if SubtitleGenerationValidator.is_prompt_echo(
            raw_text_before_san, initial_prompt=req_prompt, hotwords=req_hotwords
        ) or SubtitleGenerationValidator.is_prompt_echo(
            raw_text, initial_prompt=req_prompt, hotwords=req_hotwords
        ):
            saw_hallucination = True
            continue

        span_dur_s = (
            max(
                max(0, int(getattr(s, "end_ms", 0) or 0) - int(getattr(s, "start_ms", 0) or 0))
                for s in valid_segs
            ) / 1000.0
            if valid_segs
            else (target_duration_ms / 1000.0)
        )
        if SubtitleGenerationValidator.is_low_cps_courtesy_hallucination(
            raw_text, duration_s=span_dur_s
        ):
            saw_hallucination = True
            continue

        if SubtitleGenerationValidator.is_high_cps_hallucination(
            raw_text,
            duration_s=span_dur_s,
            language=expected_lang,
            hotwords=req_hotwords,
            initial_prompt=req_prompt,
            reference_context=getattr(tier_req, "reference_context", None),
        ):
            saw_hallucination = True
            continue

        # Short-clip Whisper phantom guard: defer/reject zero-context phrases like "はい、ありがとうございます。"
        if target_duration_ms <= 3500 and _is_short_clip_suspect_hallucination(raw_text):
            if not (tier["is_context_tier"] and has_outside):
                saw_hallucination = True
                continue

        # Auto fallback Tier 2/3 (audio_boost / No-VAD) low-confidence & 2-beat hallucination guard.
        # Never applied to Tier 1 or explicit user-triggered force_no_vad rescue scans.
        if (not force_no_vad) and (tier_idx >= 2):
            weighted_lp = _compute_weighted_avg_logprob(
                valid_segs,
                target_start_ms=int(start_ms) if tier["is_context_tier"] else None,
                target_end_ms=int(end_ms) if tier["is_context_tier"] else None,
            )
            if weighted_lp is not None and (
                weighted_lp < _AUTO_FALLBACK_MIN_LOGPROB
                or (_is_two_beat_repetition(raw_text) and weighted_lp < _AUTO_FALLBACK_TWO_BEAT_MIN_LOGPROB)
            ):
                saw_hallucination = True
                continue

        text = SubtitleGenerationValidator.filter_inconsistent_language(raw_text, expected_lang)
        if text:
            return text, "OK"

        # Text was emitted by Whisper but stripped strictly by language consistency check.
        return "", f"FILTERED_LANGUAGE:{expected_lang or 'auto'}:{raw_text[:40]}"

    diag = "HALLUCINATION_FILTERED" if saw_hallucination else "NO_SPEECH_ASR"
    return "", diag


def _run_segment_timing_scan(
    whisper_service: FasterWhisperService,
    request: SubtitleGenerationRequest,
    seg_id: str,
    start_ms: int,
    end_ms: int,
    is_cancelled_fn,
    on_tier_callback=None,
) -> tuple[tuple[int, int] | None, str | None]:
    if on_tier_callback:
        on_tier_callback(1, 1, "Tầng 1/1: Căn chỉnh mốc Timing")
    padded_start = max(0, int(start_ms) - 150)
    padded_end = max(int(start_ms) + 1, int(end_ms) + 150)
    now_iso = datetime.datetime.now().isoformat()
    batch = SubtitleGenerationBatch(
        batch_id=f"scan_{seg_id}",
        start_ms=padded_start,
        end_ms=padded_end,
        status="RUNNING",
        revision=1,
        created_at=now_iso,
        updated_at=now_iso,
    )
    timing_req = _clone_request_with(
        request,
        min_speech_duration_ms=getattr(request, "min_speech_duration_ms", None) or 150,
    )
    result = whisper_service.transcribe_batch(timing_req, batch, is_cancelled_fn)
    if is_cancelled_fn():
        return None, "CANCELLED"
    if not result:
        return None, "Không nhận được kết quả ASR"
    if result.error:
        return None, result.error

    valid_segs = _validate_overlapping_segments(
        result.segments or [], start_ms, end_ms, padded_start, padded_end
    )
    valid_segs = [
        s for s in valid_segs
        if getattr(s, "start_ms", None) is not None and getattr(s, "end_ms", None) is not None
    ]
    if valid_segs:
        speech_start_ms = max(int(start_ms), min(s.start_ms for s in valid_segs))
        speech_end_ms = min(int(end_ms), max(s.end_ms for s in valid_segs))
        if speech_end_ms > speech_start_ms:
            return (speech_start_ms, speech_end_ms), None
    return None, "NO_SPEECH_DETECTED"


class SegmentScanWorker(QThread):
    """
    Worker dùng để chạy lại Speech Recognition (Whisper) cho 1 đoạn subtitle
    hoặc căn chỉnh lại mốc timing mà không làm thay đổi ID phụ đề.
    """
    finished_signal = Signal(str, str)  # segment_id, new_text
    timing_finished_signal = Signal(str, int, int)  # segment_id, new_start_ms, new_end_ms
    error_signal = Signal(str, str)  # segment_id, error_msg
    progress_signal = Signal(int, str)  # percent, tier_name

    def __init__(
        self,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        request: SubtitleGenerationRequest,
        whisper_service: FasterWhisperService,
        scan_mode: str = "asr",
        force_no_vad: bool = False,
        context_window: tuple[int, int] | None = None,
        context_prompt: str = "",
    ):
        super().__init__()
        self.segment_id = segment_id
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.request = request
        self.whisper_service = whisper_service
        self.scan_mode = scan_mode
        self.force_no_vad = force_no_vad
        self.context_window = context_window
        self.context_prompt = context_prompt
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                return

            self.whisper_service.load_model(self.request.model_size, self.request.compute_type)
            if self._is_cancelled:
                return

            def _tier_cb(tier_idx, total_tiers, tier_name):
                if self._is_cancelled:
                    return
                percent = int(((tier_idx - 1) / max(1, total_tiers)) * 100)
                self.progress_signal.emit(percent, tier_name)

            if self.scan_mode == "timing":
                _tier_cb(1, 1, "Tầng 1/1: Căn chỉnh mốc Timing")
                span, err = _run_segment_timing_scan(
                    self.whisper_service,
                    self.request,
                    self.segment_id,
                    self.start_ms,
                    self.end_ms,
                    lambda: self._is_cancelled,
                    on_tier_callback=_tier_cb,
                )
                if err == "CANCELLED" or self._is_cancelled:
                    return
                if span is not None:
                    self.timing_finished_signal.emit(self.segment_id, span[0], span[1])
                else:
                    self.error_signal.emit(self.segment_id, err or "NO_SPEECH_DETECTED")
                return

            fallback_kwargs = {}
            if self.context_window is not None:
                fallback_kwargs["context_window"] = self.context_window
            if self.context_prompt:
                fallback_kwargs["context_prompt"] = self.context_prompt

            text, diag = _transcribe_segment_with_fallback(
                self.whisper_service,
                self.request,
                self.segment_id,
                self.start_ms,
                self.end_ms,
                lambda: self._is_cancelled,
                force_no_vad=self.force_no_vad,
                on_tier_callback=_tier_cb,
                **fallback_kwargs,
            )
            if diag == "CANCELLED" or self._is_cancelled:
                return
            if diag.startswith("ERROR:"):
                self.error_signal.emit(self.segment_id, diag[len("ERROR:"):])
            elif text:
                self.finished_signal.emit(self.segment_id, text)
            else:
                expected_lang = getattr(self.request, "language", None)
                self.error_signal.emit(
                    self.segment_id, _format_empty_scan_error(diag, expected_lang)
                )
        except Exception as e:
            self.error_signal.emit(self.segment_id, str(e))


class BatchSegmentScanWorker(QThread):
    """Worker chạy nhận diện âm thanh (Whisper) tuần tự cho danh sách phân đoạn được chọn."""
    progress_signal = Signal(int, int, str)
    detailed_progress_signal = Signal(int, str)
    segment_completed_signal = Signal(str, str)
    segment_error_signal = Signal(str, str)
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
            expected_lang = getattr(self.request, "language", None)
            clean_text_by_index: dict[int, str] = {}
            dropped_indices: set[int] = set()
            for idx, seg in enumerate(self.segments_data, 1):
                if self._is_cancelled:
                    return
                seg_id = str(seg.get("id"))
                start_ms = int(seg.get("start_ms", 0))
                end_ms = int(seg.get("end_ms", 0))
                scan_mode = seg.get("scan_mode", "asr")
                self.progress_signal.emit(idx, total, f"Đang nhận diện câu {idx}/{total}...")

                def _tier_cb(tier_idx, total_tiers, tier_name):
                    if self._is_cancelled:
                        return
                    unit = (idx - 1) + (tier_idx - 1) / max(1, total_tiers)
                    percent = min(99, max(0, int((unit / total) * 100)))
                    msg = f"Đang nhận diện câu {idx}/{total} ({percent}%)\n➔ {tier_name}"
                    self.detailed_progress_signal.emit(percent, msg)

                if scan_mode == "timing":
                    _tier_cb(1, 1, "Tầng 1/1: Căn chỉnh mốc Timing")
                    span, err = _run_segment_timing_scan(
                        self.whisper_service,
                        self.request,
                        seg_id,
                        start_ms,
                        end_ms,
                        lambda: self._is_cancelled,
                        on_tier_callback=_tier_cb,
                    )
                    if err == "CANCELLED" or self._is_cancelled:
                        return
                    if span is not None:
                        self.segment_timing_completed_signal.emit(seg_id, span[0], span[1])
                    else:
                        self.segment_error_signal.emit(seg_id, err or "NO_SPEECH_DETECTED")
                    done_percent = min(100, int((idx / total) * 100))
                    self.detailed_progress_signal.emit(done_percent, f"Đã hoàn thành câu {idx}/{total} ({done_percent}%)")
                    continue

                fallback_kwargs = {}
                if seg.get("context_window") is not None:
                    fallback_kwargs["context_window"] = seg.get("context_window")
                seg_row_idx = seg.get("index")
                if isinstance(seg_row_idx, int) and (seg_row_idx - 1) in dropped_indices:
                    # Ngắt truyền ngữ cảnh khi phân đoạn liền trước bị xóa do ảo giác/rỗng
                    fallback_kwargs["context_prompt"] = ""
                elif isinstance(seg_row_idx, int) and (seg_row_idx - 1) in clean_text_by_index:
                    fallback_kwargs["context_prompt"] = clean_text_by_index[seg_row_idx - 1]
                elif seg.get("context_prompt"):
                    fallback_kwargs["context_prompt"] = str(seg.get("context_prompt"))

                text, diag = _transcribe_segment_with_fallback(
                    self.whisper_service,
                    self.request,
                    seg_id,
                    start_ms,
                    end_ms,
                    lambda: self._is_cancelled,
                    force_no_vad=bool(seg.get("force_no_vad", False)),
                    on_tier_callback=_tier_cb,
                    **fallback_kwargs,
                )
                if diag == "CANCELLED" or self._is_cancelled:
                    return
                if diag.startswith("ERROR:"):
                    if isinstance(seg_row_idx, int):
                        dropped_indices.add(seg_row_idx)
                    self.segment_error_signal.emit(seg_id, diag[len("ERROR:"):])
                elif text:
                    if isinstance(seg_row_idx, int):
                        clean_text_by_index[seg_row_idx] = text
                    self.segment_completed_signal.emit(seg_id, text)
                else:
                    if isinstance(seg_row_idx, int):
                        dropped_indices.add(seg_row_idx)
                    self.segment_error_signal.emit(
                        seg_id, _format_empty_scan_error(diag, expected_lang)
                    )
                done_percent = min(100, int((idx / total) * 100))
                self.detailed_progress_signal.emit(done_percent, f"Đã hoàn thành câu {idx}/{total} ({done_percent}%)")

            if not self._is_cancelled:
                self.detailed_progress_signal.emit(100, f"Đã hoàn thành nhận diện {total}/{total} câu (100%)")
                self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))
