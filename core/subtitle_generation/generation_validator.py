import re
from typing import List

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
        "視聴ありがとうございました",
        "チャンネル登録",
        "thank you for watching",
        "diyorlar",
        "diyorlar.",
        "thank you.",
        "watching!",
    )

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
            if any(
                phrase in text.casefold()
                for phrase in SubtitleGenerationValidator.HALLUCINATIONS
            ):
                continue
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
