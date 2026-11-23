import copy
import re
from typing import List, Optional

from core.subtitle_generation.subtitle_generation_result import WhisperSegmentResult


class SubtitleGenerationValidator:
    """Filters malformed and known hallucinated ASR output."""

    HALLUCINATIONS = (
        "transcription by",
        "castingwords",
        "amara.org",
        "subtitles by",
        "subtitle by",
        "translated by",
        "subs by",
        "đăng ký kênh",
        "ご視聴ありがとうございました",
        "ご視聴ありがとうございます",
        "視聴ありがとうございました",
        "ご清聴ありがとうございました",
        "次の動画でお会いしましょう",
        "チャンネル登録",
        "字幕作成",
        "ご覧いただきありがとうございました",
        "thank you for watching",
        "diyorlar",
        "diyorlar.",
        "thank you.",
        "watching!",
        "♪",
        "♫",
        "🎵",
        "♩",
        "♬",
        "[music]",
        "(music)",
        "[applause]",
        "(applause)",
        "[laughter]",
        "(laughter)",
        "[cheering]",
        "(cheering)",
        "[sound]",
    )

    PURE_COURTESY_HALLUCINATIONS = (
        "ご視聴ありがとうございました",
        "ご視聴ありがとうございます",
        "ご清聴ありがとうございました",
        "次の動画でお会いしましょう",
        "チャンネル登録",
        "字幕作成",
        "ご覧いただきありがとうございました",
    )
    CONTEXTUAL_COURTESY_PHRASES = frozenset(
        {
            "おやすみなさい",
            "お疲れ様でした",
            "お疲れさまでした",
            "ありがとうございました",
            "はいありがとうございました",
            "どうもありがとうございました",
            "はいどうもありがとうございました",
            "ごちそうさまでした",
            "はいごちそうさまでした",
            "また次回",
        }
    )
    CJK_HIGH_CPS_LANGUAGES = frozenset({"ja", "zh", "ko"})
    _CJK_REF_TOKEN_RE = re.compile(
        r"[\u30a0-\u30ffー]{2,}|[\u4e00-\u9fff]{2,}|[\uac00-\ud7af]{2,}|[\u3040-\u309f]{3,}"
    )

    MUSIC_ONLY_PATTERN = re.compile(r"^[\s♪♫🎵♩♬]+$")
    SOUND_TAG_PATTERN = re.compile(
        r"^\s*(?:[\[\(](?:music|applause|laughter|cheering|sound|audio)[\s\-_]*[\]\)]\s*)+$",
        re.IGNORECASE,
    )
    PUNCTUATION_ONLY_PATTERN = re.compile(r"^[\s\W_]+$")
    SINGLE_CHAR_REPEAT_RE = re.compile(r"([^\s.。・…0-9])\1{5,}")
    CLUSTER_REPEAT_RE = re.compile(r"(.{2,4})\1{3,}")
    SEPARATED_CLUSTER_REPEAT_RE = re.compile(
        r"([^\s、。,.!?！？・…]{2,4})[\s、。,.!?！？・…]+(?:\1[\s、。,.!?！？・…]*){3,}"
    )
    SEPARATED_SINGLE_REPEAT_RE = re.compile(
        r"([^\s、。,.!?！？・…0-9])[\s、。,.!?！？・…]+(?:\1[\s、。,.!?！？・…]*){5,}"
    )
    SHORT_FILLER_PREFIX_RE = re.compile(
        r"^(?:[\s、。,.!?！？・…「」『』()（）\[\]]"
        r"|(?:[あいうえおぁぃぅぇぉんっはふほ][あいうえおぁぃぅぇぉんっー]?))*$"
    )
    _ECHO_STRIP_RE = re.compile(r"[\s、。,.!?！？・…「」『』()（）\[\]\-_:;\"'~～]+")
    _JA_CLAUSE_GRAMMAR_RE = re.compile(
        r"(?:ている|てい|ます|です|ない|した|する|くる|から|けど|って|まで|だよ|なの|のか|だった|たい|れる|られる)"
    )

    @classmethod
    def is_prompt_echo(
        cls,
        text: str,
        initial_prompt: Optional[str] = None,
        hotwords: Optional[str] = None,
    ) -> bool:
        """Phát hiện hiệu ứng nhại từ khóa (Prompt Echo) khi ASR chép lại chuỗi Glossary / initial_prompt."""
        raw = str(text or "").strip()
        if not raw:
            return False
        prompt_str = str(initial_prompt or "").strip()
        hw_str = str(hotwords or "").strip()
        if not prompt_str and not hw_str:
            return False

        norm_text = cls._ECHO_STRIP_RE.sub("", raw).casefold()
        if not norm_text:
            return False

        from core.subtitle_generation.language_utils import (
            extract_terminology_terms,
            parse_hotwords_terms,
        )

        terms = parse_hotwords_terms(hw_str, max_terms=128)
        prompt_terms_str = extract_terminology_terms(prompt_str, max_terms=128)
        if prompt_terms_str:
            terms.extend(parse_hotwords_terms(prompt_terms_str, max_terms=128))

        norm_terms = sorted(
            {
                cls._ECHO_STRIP_RE.sub("", t).casefold()
                for t in terms
                if cls._ECHO_STRIP_RE.sub("", t)
            },
            key=len,
            reverse=True,
        )

        match_count = 0
        matched_chars = 0
        remainder_parts: list[str] = []
        pos = 0
        n_len = len(norm_text)
        while pos < n_len:
            matched_term = None
            for nt in norm_terms:
                if norm_text.startswith(nt, pos):
                    matched_term = nt
                    break
            if matched_term:
                match_count += 1
                matched_chars += len(matched_term)
                pos += len(matched_term)
            else:
                remainder_parts.append(norm_text[pos])
                pos += 1
        remainder = "".join(remainder_parts)

        # Rule 1: Khớp hoàn toàn / chuỗi con trực tiếp của initial_prompt hoặc hotwords
        if prompt_str:
            norm_prompt = cls._ECHO_STRIP_RE.sub("", prompt_str).casefold()
            if len(norm_text) >= 4 and norm_text in norm_prompt:
                return True
        if hw_str:
            norm_hw = cls._ECHO_STRIP_RE.sub("", hw_str).casefold()
            if norm_text in norm_hw and match_count >= 2:
                return True

        # Rule 2: >= 70% nội dung là các từ Glossary lặp lại / liệt kê không có cấu trúc vị ngữ bình thường
        raw_parts = [p for p in re.split(r"[\s、,・]+", raw) if cls._ECHO_STRIP_RE.sub("", p)]
        norm_term_set = set(norm_terms)
        part_hits = sum(1 for p in raw_parts if cls._ECHO_STRIP_RE.sub("", p).casefold() in norm_term_set)
        char_ratio = matched_chars / max(1, n_len)
        part_ratio = (part_hits / len(raw_parts)) if len(raw_parts) >= 2 else 0.0

        if match_count >= 2 and (char_ratio >= 0.70 or part_ratio >= 0.70):
            if len(remainder) >= 2 and cls._JA_CLAUSE_GRAMMAR_RE.search(remainder):
                return False
            return True

        return False

    @classmethod
    def sanitize_repetition_text(cls, text: str) -> tuple[str, bool]:
        """Phát hiện và xử lý chuỗi lặp/rên ảo giác: xóa toàn bộ (Case A) hoặc cắt đuôi (Case B)."""
        raw = str(text or "").strip()
        if not raw:
            return "", False

        earliest_start = None
        for pattern in (
            cls.SINGLE_CHAR_REPEAT_RE,
            cls.CLUSTER_REPEAT_RE,
            cls.SEPARATED_CLUSTER_REPEAT_RE,
            cls.SEPARATED_SINGLE_REPEAT_RE,
        ):
            match = pattern.search(raw)
            if match is not None:
                if earliest_start is None or match.start() < earliest_start:
                    earliest_start = match.start()

        if earliest_start is None:
            return raw, False

        prefix = raw[:earliest_start]
        if not prefix.strip() or cls.SHORT_FILLER_PREFIX_RE.match(prefix.strip()):
            return "", True

        cleaned = re.sub(r"[\s、,・]+$", "", prefix).strip()
        if not cleaned or cls.PUNCTUATION_ONLY_PATTERN.match(cleaned):
            return "", True
        if any(phrase in cleaned.casefold() for phrase in cls.HALLUCINATIONS):
            return "", True
        return cleaned, True

    @classmethod
    def clean_repetition_segment(
        cls,
        text: str,
        words: Optional[list] = None,
        start_val: float | int = 0,
        end_val: float | int = 0,
        *,
        words_in_ms: bool = False,
        tail_pad: float | int | None = None,
    ) -> tuple[str, Optional[list], float | int, bool]:
        """Làm sạch segment lặp từ và thu hồi mốc end theo word.end của từ hợp lệ cuối cùng."""
        cleaned, had_rep = cls.sanitize_repetition_text(text)
        if not cleaned:
            return "", None, end_val, had_rep
        if not had_rep or not words:
            return cleaned, words, end_val, had_rep

        target_len = len(re.sub(r"\s+", "", cleaned))
        acc_no_ws = ""
        kept_words = []
        for w in words:
            w_text = w.get("word", "") if isinstance(w, dict) else getattr(w, "word", "")
            if len(acc_no_ws) >= target_len:
                break
            kept_words.append(w)
            acc_no_ws += re.sub(r"\s+", "", str(w_text or ""))

        if not kept_words:
            return cleaned, words, end_val, True

        last_w = kept_words[-1]
        raw_last_end = (
            last_w.get("end_ms") if isinstance(last_w, dict) else getattr(last_w, "end_ms", None)
        ) if words_in_ms else (
            last_w.get("end") if isinstance(last_w, dict) else getattr(last_w, "end", None)
        )
        new_end = end_val
        if isinstance(raw_last_end, (int, float)) and not isinstance(raw_last_end, bool):
            pad = (50 if words_in_ms else 0.05) if tail_pad is None else tail_pad
            min_end = start_val + (10 if words_in_ms else 0.01)
            candidate = float(raw_last_end) + float(pad)
            if words_in_ms:
                new_end = max(int(min_end), min(int(end_val), int(round(candidate))))
            else:
                new_end = max(float(min_end), min(float(end_val), candidate))
        return cleaned, kept_words, new_end, True

    @classmethod
    def is_low_cps_courtesy_hallucination(
        cls,
        text: str,
        duration_s: Optional[float] = None,
        no_speech_prob: Optional[float] = None,
    ) -> bool:
        """Chặn ảo giác câu xã giao kinh điển khi kéo giãn trên đoạn rên/thở (CPS thấp) hoặc xác suất rỗng cao."""
        norm = cls._ECHO_STRIP_RE.sub("", str(text or "").strip()).casefold()
        if not norm:
            return False
        if any(phrase in norm for phrase in cls.PURE_COURTESY_HALLUCINATIONS):
            return True
        if norm in cls.CONTEXTUAL_COURTESY_PHRASES:
            if (
                isinstance(no_speech_prob, (int, float))
                and not isinstance(no_speech_prob, bool)
                and float(no_speech_prob) >= 0.45
            ):
                return True
            if (
                isinstance(duration_s, (int, float))
                and not isinstance(duration_s, bool)
                and float(duration_s) >= 4.5
            ):
                cps = len(norm) / float(duration_s)
                if cps < 1.8:
                    return True
        return False

    @classmethod
    def is_high_cps_hallucination(
        cls,
        text: str,
        duration_s: Optional[float],
        language: Optional[str],
        *,
        hotwords: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        reference_context: Optional[str] = None,
    ) -> bool:
        """Chặn ảo giác nhồi chữ tốc độ bất khả thi (High-CPS > 14.0) cho ngôn ngữ CJK (ja/zh/ko)."""
        from core.subtitle_generation.language_utils import normalize_to_iso_code

        _ = (hotwords, initial_prompt, reference_context)
        iso = normalize_to_iso_code(language)
        if iso not in cls.CJK_HIGH_CPS_LANGUAGES:
            return False
        if not isinstance(duration_s, (int, float)) or isinstance(duration_s, bool):
            return False
        dur = float(duration_s)
        if dur < 1.5:
            return False

        clean_text = cls._ECHO_STRIP_RE.sub("", str(text or "").strip())
        if len(clean_text) < 18:
            return False

        cps = len(clean_text) / dur
        return cps > 14.0

    @classmethod
    def is_hallucination(cls, text: str) -> bool:
        if not text or not text.strip():
            return True
        clean = text.strip()
        clean_lower = clean.casefold()
        if any(phrase in clean_lower for phrase in cls.HALLUCINATIONS):
            return True
        if cls.MUSIC_ONLY_PATTERN.match(clean):
            return True
        if cls.SOUND_TAG_PATTERN.match(clean):
            return True
        if cls.PUNCTUATION_ONLY_PATTERN.match(clean):
            return True
        cleaned_rep, had_rep = cls.sanitize_repetition_text(clean)
        if had_rep and not cleaned_rep:
            return True
        return False

    @classmethod
    def filter_hallucinated_segments(
        cls, segments: List[WhisperSegmentResult]
    ) -> List[WhisperSegmentResult]:
        """Lọc text rỗng / ảo giác / lặp đuôi mà không loại segment theo biên batch."""
        filtered: List[WhisperSegmentResult] = []
        for segment in segments:
            text = (getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            start_ms = getattr(segment, "start_ms", 0)
            end_ms = getattr(segment, "end_ms", 0)
            cleaned_text, kept_words, new_end_ms, had_rep = cls.clean_repetition_segment(
                text,
                words=getattr(segment, "words", None),
                start_val=start_ms,
                end_val=end_ms,
                words_in_ms=True,
            )
            if not cleaned_text or cls.is_hallucination(cleaned_text):
                continue
            try:
                seg_dur_s = max(0.0, (float(end_ms) - float(start_ms)) / 1000.0)
            except (TypeError, ValueError):
                seg_dur_s = 0.0
            if cls.is_low_cps_courtesy_hallucination(cleaned_text, duration_s=seg_dur_s):
                continue
            if had_rep:
                seg_copy = copy.copy(segment)
                seg_copy.text = cleaned_text
                seg_copy.words = kept_words
                seg_copy.end_ms = new_end_ms
                filtered.append(seg_copy)
            else:
                filtered.append(segment)
        return filtered

    @staticmethod
    def validate(
        segments: List[WhisperSegmentResult], batch_start_ms: int, batch_end_ms: int
    ) -> List[WhisperSegmentResult]:
        if batch_start_ms < 0 or batch_end_ms <= batch_start_ms:
            return []

        valid: List[WhisperSegmentResult] = []
        for segment in segments:
            text = (segment.text or "").strip()
            if (
                segment.start_ms < 0
                or segment.end_ms <= segment.start_ms
                or not text
                or segment.start_ms > batch_end_ms
                or segment.end_ms < batch_start_ms
            ):
                continue
            cleaned_text, kept_words, new_end_ms, had_rep = (
                SubtitleGenerationValidator.clean_repetition_segment(
                    text,
                    words=getattr(segment, "words", None),
                    start_val=segment.start_ms,
                    end_val=segment.end_ms,
                    words_in_ms=True,
                )
            )
            if not cleaned_text or SubtitleGenerationValidator.is_hallucination(cleaned_text):
                continue
            seg_dur_s = max(0.0, (segment.end_ms - segment.start_ms) / 1000.0)
            if SubtitleGenerationValidator.is_low_cps_courtesy_hallucination(
                cleaned_text, duration_s=seg_dur_s
            ):
                continue
            if had_rep:
                segment.text = cleaned_text
                segment.words = kept_words
                segment.end_ms = new_end_ms
            valid.append(segment)
        return valid

    @staticmethod
    def filter_inconsistent_language(text: str, expected_lang: str) -> str:
        """
        Nếu expected_lang == 'ja' (hoặc 'japanese') và văn bản chỉ chứa chữ cái Latinh
        (không chứa bất kỳ ký tự tiếng Nhật Hiragana/Katakana/Kanji nào),
        coi đó là ảo giác ASR ngoại lai và trả về chuỗi rỗng.
        """
        if not text:
            return ""
        norm_lang = (expected_lang or "").strip().lower()
        if norm_lang in ("ja", "japanese"):
            has_japanese = bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text))
            has_latin = bool(re.search(r"[a-zA-Z]", text))
            if has_latin and not has_japanese:
                return ""
        return text
