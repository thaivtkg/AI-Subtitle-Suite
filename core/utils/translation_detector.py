# -*- coding: utf-8 -*-
import re
from typing import Optional, Union

# 1. Ký tự CJK (Nhật Bản Hiragana, Katakana, Kanji, Hàn Quốc Hangul)
CJK_REGEX = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")

# 2. Ký tự Cyrillic (Tiếng Nga)
CYRILLIC_REGEX = re.compile(r"[\u0400-\u04FF]")

# 3. Ký tự nguyên âm và dấu thanh đặc trưng của Tiếng Việt
VIETNAMESE_DIACRITICS_REGEX = re.compile(
    r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ"
    r"ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]"
)

# 4. Các từ tiếng Anh phổ biến (dùng để nhận diện câu tiếng Anh không có dấu)
ENGLISH_STOP_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not",
    "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from",
    "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would",
    "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which",
    "go", "me", "when", "make", "can", "like", "time", "no", "just", "him", "know",
    "take", "people", "into", "year", "your", "good", "some", "could", "them", "see",
    "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first", "well",
    "way", "even", "new", "want", "because", "any", "these", "give", "day", "most", "us"
}

CONVERSATIONAL_PARTICLES = {
    "ok", "oke", "okey", "alo", "bye", "ha", "wow", "haha", "hihi", "huhu",
}


def is_vietnamese_translated(text_or_segment: Union[dict, str, None]) -> bool:
    """
    Xác định câu phụ đề đã được dịch sang Tiếng Việt hay chưa.
    Trả về True NẾU VÀ CHỈ NẾU là Tiếng Việt.
    Trả về False nếu là Tiếng Nhật, Tiếng Anh, Tiếng Nga, rỗng hoặc placeholder.
    """
    if isinstance(text_or_segment, dict):
        text = str(text_or_segment.get("text", "")).strip()
    else:
        text = str(text_or_segment or "").strip()

    # Tiêu chí 1: Rỗng hoặc placeholder
    if not text or text == "[ Chưa có nội dung ]":
        return False

    # Tiêu chí 2: Chứa ký tự CJK (Tiếng Nhật, Tiếng Hàn)
    if CJK_REGEX.search(text):
        return False

    # Tiêu chí 2 phụ: Chứa ký tự tiếng Nga
    if CYRILLIC_REGEX.search(text):
        return False

    # Tiêu chí 3: Chứa dấu thanh Tiếng Việt (chắc chắn là Tiếng Việt)
    if VIETNAMESE_DIACRITICS_REGEX.search(text):
        return True

    # Đối chiếu với original_text nếu có: nếu text giống hệt text gốc nhận diện -> chưa dịch
    if isinstance(text_or_segment, dict):
        orig = str(text_or_segment.get("original_text", "")).strip()
        if orig and orig.lower() == text.lower():
            return False

    # Tiêu chí 4: Xử lý chữ Latinh không dấu (phân biệt Tiếng Anh vs Tiếng Việt không dấu)
    words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    if words and words.intersection(ENGLISH_STOP_WORDS):
        # Chứa các từ tiếng Anh (ví dụ: "what is this", "lord help my world", "you know")
        return False

    # Các câu cảm thán ngắn quốc tế thông dụng được chấp nhận trong sub Việt: ok, alo, bye, wow...
    if words and words.issubset(CONVERSATIONAL_PARTICLES):
        return True

    # Mặc định: Nếu là câu dài hoàn toàn không có dấu tiếng Việt nào -> Coi là chưa dịch
    return len(words) <= 1


def find_first_untranslated_index(segments: list) -> Optional[int]:
    """
    Tìm chỉ mục 1-based của câu đầu tiên chưa được dịch sang Tiếng Việt.
    Trả về None nếu toàn bộ danh sách đã được dịch.
    """
    if not segments:
        return None
    for i, s in enumerate(segments, 1):
        if not is_vietnamese_translated(s):
            return i
    return None


def count_translated_segments(segments: list) -> tuple[int, int]:
    """
    Trả về tuple (số câu đã dịch sang Tiếng Việt, tổng số câu).
    """
    if not segments:
        return 0, 0
    translated = sum(1 for s in segments if is_vietnamese_translated(s))
    return translated, len(segments)
