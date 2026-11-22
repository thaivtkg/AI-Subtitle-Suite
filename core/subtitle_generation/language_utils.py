# -*- coding: utf-8 -*-
import re
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

_INITIAL_PROMPTS: dict[str, str] = {}

_DEFAULT_HOTWORDS: dict[str, str] = {}

_JA_CHAR_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_TERMINOLOGY_BLOCK_RE = re.compile(
    r"^\s*Terminology:\s*(?P<terms>.*?)\.(?:\s*Context:\s*(?P<context>.*))?\s*$",
    re.DOTALL,
)
_SENTENCE_END_PUNCT_RE = re.compile(r"[。！？!?]")


def parse_hotwords_terms(hotwords: Optional[str], max_terms: int = 64) -> list[str]:
    """Tách chuỗi hotwords (phân cách bằng dấu cách, phẩy, 、 hoặc xuống dòng) thành danh sách thuật ngữ duy nhất."""
    if not hotwords:
        return []
    raw_str = str(hotwords).strip()
    if not raw_str:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    has_delim = any(d in raw_str for d in (",", "、", "\n"))
    if has_delim:
        chunks = re.split(r"[,、\n]+", raw_str)
    elif "->" in raw_str or "=" in raw_str:
        chunks = [raw_str]
    else:
        chunks = raw_str.split()

    for raw in chunks:
        cleaned = raw.split("->", 1)[0].split("=", 1)[0].strip()
        if not cleaned:
            continue
        sub_tokens = cleaned.split() if (has_delim and _JA_CHAR_RE.search(cleaned) and re.search(r"\s", cleaned)) else [cleaned]
        for token in sub_tokens:
            term = token.strip()
            if not term or term in seen:
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= max_terms:
                return terms
    return terms


def merge_hotwords(*parts: Optional[str], max_terms: int = 64, sep: str = " ") -> str:
    """Gộp nhiều chuỗi hotwords (chuẩn CTranslate2 phân cách bằng dấu cách), loại trùng theo thứ tự ưu tiên."""
    terms: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for term in parse_hotwords_terms(part, max_terms=max_terms):
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= max_terms:
                return sep.join(terms)
    return sep.join(terms)


def get_default_hotwords_for_language(lang_code: Optional[str]) -> str:
    """Không tự ý chèn hotwords ngầm mặc định khi người dùng không cấu hình Từ điển."""
    iso = normalize_to_iso_code(lang_code)
    if not iso:
        return ""
    return _DEFAULT_HOTWORDS.get(iso, "")


def extract_terminology_terms(prompt_text: Optional[str], max_terms: int = 64) -> str:
    """Trích xuất danh sách thuật ngữ từ khối 'Terminology: ...' để chuyển qua hotwords."""
    cleaned = str(prompt_text or "").strip()
    if not cleaned:
        return ""
    match = _TERMINOLOGY_BLOCK_RE.match(cleaned)
    if not match:
        return ""
    raw_terms = match.group("terms") or ""
    return " ".join(parse_hotwords_terms(raw_terms, max_terms=max_terms))


def extract_natural_initial_prompt(
    prompt_text: Optional[str], lang_code: Optional[str] = None
) -> Optional[str]:
    """Chỉ giữ initial_prompt khi thực sự là câu văn / mô tả ngữ cảnh tự nhiên; bỏ qua danh sách từ khóa rời."""
    cleaned = str(prompt_text or "").strip()
    if not cleaned:
        return None
    match = _TERMINOLOGY_BLOCK_RE.match(cleaned)
    if match:
        raw_context = (match.group("context") or "").strip()
        return raw_context or None

    # Nếu chỉ là danh sách từ khóa rời ngắn (ngăn cách bởi dấu phẩy/、, không có dấu kết câu) -> không nhét vào initial_prompt
    if ("," in cleaned or "、" in cleaned) and not _SENTENCE_END_PUNCT_RE.search(cleaned):
        tokens = [t.strip() for t in re.split(r"[,、\n]+", cleaned) if t.strip()]
        if len(tokens) >= 2 and (sum(len(t) for t in tokens) / len(tokens)) <= 6.0:
            return None

    return cleaned


def format_whisper_initial_prompt(prompt_text: Optional[str], lang_code: Optional[str] = None) -> str:
    """Chuẩn hóa initial_prompt cho Whisper: bỏ tiền tố 'Terminology:' và dấu '.' tiếng Anh khi là từ khóa tiếng Nhật."""
    cleaned = str(prompt_text or "").strip()
    if not cleaned:
        return ""
    match = _TERMINOLOGY_BLOCK_RE.match(cleaned)
    if not match:
        return cleaned
    raw_terms = match.group("terms") or ""
    raw_context = (match.group("context") or "").strip()
    iso = normalize_to_iso_code(lang_code)
    is_ja = iso == "ja" or bool(_JA_CHAR_RE.search(raw_terms))
    if not is_ja:
        return cleaned
    terms: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,、\n]+", raw_terms):
        term = raw.split("->", 1)[0].split("=", 1)[0].strip()
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
    ja_terms = "、".join(terms)
    if ja_terms and raw_context:
        return f"{ja_terms}。{raw_context}"
    return ja_terms or raw_context


def extract_glossary_hotwords(transcription_context, max_terms: int = 64) -> str:
    """Trích danh sách thuật ngữ từ TranscriptionContext thành chuỗi hotwords ngăn cách bằng dấu cách cho faster-whisper."""
    if transcription_context is None:
        return ""
    raw_glossary = getattr(transcription_context, "glossary", None)
    if isinstance(raw_glossary, str):
        items = [line.strip() for line in raw_glossary.splitlines() if line.strip()]
    elif isinstance(raw_glossary, (list, tuple, set)):
        items = [str(item).strip() for item in raw_glossary if str(item).strip()]
    else:
        return ""
    terms: list[str] = []
    seen = set()
    for item in items:
        term = item.split("->", 1)[0].split("=", 1)[0].strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return " ".join(terms)


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
