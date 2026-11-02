# -*- coding: utf-8 -*-
from typing import Optional

_LANGUAGE_MAP = {
    "japanese": "ja",
    "english": "en",
    "vietnamese": "vi",
    "korean": "ko",
    "chinese": "zh",
    "ja": "ja",
    "en": "en",
    "vi": "vi",
    "ko": "ko",
    "zh": "zh",
}

_INITIAL_PROMPTS = {
    "ja": "こんにちは。はい、そうですね。うん、あの、ええと、よし、では、違う、わかった、なるほど。",
}


def normalize_to_iso_code(lang: Optional[str]) -> Optional[str]:
    """
    Chuẩn hóa tên hoặc mã ngôn ngữ về mã chuẩn ISO-639-1 (2 ký tự) tương thích Faster-Whisper.
    Trả về None nếu là chế độ Auto Detect hoặc không xác định.
    """
    if not lang or lang.strip().lower() in ("auto detect", "none", ""):
        return None
    cleaned = lang.strip().lower()
    return _LANGUAGE_MAP.get(cleaned, cleaned)


def get_initial_prompt_for_language(lang_code: Optional[str]) -> str:
    """
    Cung cấp đoạn văn bản ngữ cảnh mồi (initial_prompt) để định hướng Whisper decoder,
    đặc biệt đối với các từ cảm thán / đệm ngắn 1-4 âm tiết trong hội thoại tự nhiên.
    """
    if not lang_code:
        return ""
    return _INITIAL_PROMPTS.get(lang_code.lower(), "")
