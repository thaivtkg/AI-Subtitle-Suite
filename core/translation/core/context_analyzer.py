"""
ContextAnalyzer: 100% Offline Entity & Archetype Classifier.
Analyzes story summaries to extract glossary entities and determine character archetypes
with pronoun biasing using regex and keyword scoring without external dependencies.
"""

from __future__ import annotations

import re
from typing import Any

# --- Archetype Identifiers (Single Pure Model) ---
ARCHETYPE_PURE = "pure_model"
# Backward-compatibility aliases
ARCHETYPE_ANCIENT_FANTASY = "pure_model"
ARCHETYPE_ANIME_SCHOOL = "pure_model"
ARCHETYPE_MODERN_ACTION = "pure_model"
ARCHETYPE_ROMANCE_FAMILY = "pure_model"
ARCHETYPE_CUSTOM = "pure_model"

# --- Default Pronoun Pair Mappings ---
DEFAULT_PRONOUNS: dict[str, str] = {
    ARCHETYPE_PURE: "",
    "custom": "",
}

# --- Archetype Metadata (Used by UI Dropdowns & Inspector) ---
ARCHETYPE_METADATA: dict[str, dict[str, Any]] = {
    ARCHETYPE_PURE: {
        "id": ARCHETYPE_PURE,
        "name": "Dịch Thuần (Pure Model)",
        "pronouns": "Tự do",
        "icon": "🔮",
    },
}

ARCHETYPE_LIST: list[dict[str, Any]] = list(ARCHETYPE_METADATA.values())

# Stopwords to filter out metadata fields or generic noise in summary
STOPWORDS: set[str] = {
    "phim", "tập", "thể loại", "diễn viên", "đạo diễn", "nội dung", "tóm tắt",
    "phần", "tác giả", "nhân vật", "năm", "mùa", "season", "episode", "chapter",
}

# Pair definition pattern:
# Matches: "Source": Target, "Source" -> Target, Source => Target, Source là Target
PAIR_PATTERN = re.compile(
    r'(?:["“]([^"”\n]+)["”]|([\w\-\s\u3040-\u30ff\u4e00-\u9fff]{2,}))\s*(?::|->|=>|→|\blà\b)\s*(?:["“]([^"”\n]+)["”]|([^\n,;.]+))',
    re.IGNORECASE,
)

# Brackets & Quotes pattern:
# Western quotes "...", “...”, CJK brackets 「...」, 『...』, 【...】, 《...》
BRACKET_PATTERN = re.compile(
    r'["“]([^"”\n]{2,})["”]|[「『【《]([^」』】》\n]{2,})[」』】》]'
)

# Katakana pattern (Japanese names/terms, min 2 characters)
KATAKANA_PATTERN = re.compile(r'[\u30A0-\u30FF]{2,}')

# Keyword dictionaries for scoring
ARCHETYPE_KEYWORDS: dict[str, list[str]] = {
    ARCHETYPE_ANCIENT_FANTASY: [
        "tu tiên", "cổ trang", "kiếm hiệp", "võ lâm", "tông môn", "phi kiếm", "sư huynh",
        "sư muội", "sư phụ", "chưởng môn", "hoàng đế", "bệ hạ", "thần tiên", "tiên hiệp",
        "ma giáo", "đạo hữu", "yêu ma", "linh khí", "đan dược", "công pháp", "tiên môn",
    ],
    ARCHETYPE_ANIME_SCHOOL: [
        "học đường", "học sinh", "trường học", "nữ sinh", "nam sinh", "thanh xuân",
        "senpai", "kouhai", "anime", "clb", "manga", "ma pháp", "chuyển sinh", "isekai",
    ],
    ARCHETYPE_MODERN_ACTION: [
        "cảnh sát", "đặc nhiệm", "điệp viên", "bắn tỉa", "trực thăng", "tội phạm",
        "truy kích", "súng", "chiến tranh", "thám tử", "sát thủ", "đặc vụ", "quân đội",
    ],
    ARCHETYPE_ROMANCE_FAMILY: [
        "lãng mạn", "tổng tài", "ngôn tình", "kết hôn", "hôn nhân", "gia đình",
        "yêu đương", "tình cảm", "vợ chồng", "hẹn hò", "bạn gái", "bạn trai",
    ],
}

# Tech keywords for anti-collision (suppresses ancient fantasy false positives)
TECH_KEYWORDS: list[str] = [
    "lập trình", "lập trình viên", "bug", "code", "máy tính", "server", "hệ thống máy tính",
    "tin học", "phần mềm", "source code", "developer", "cntt", "it",
]

# --- Bảng Nhận Diện Phụ Đề Tiếng Anh Dịch Từ Tiếng Nhật (EN translated from JA) ---
JA_SOURCE_INDICATORS = {
    "romaji_honorifics": [
        "senpai", "kouhai", "sensei", "aniki", "sama", "dono",
        "onii-san", "onii-chan", "onee-san", "onee-chan", "shishou"
    ],
    "anime_keywords": [
        "anime", "manga", "otaku", "kaijin", "magical girl", "mahoushoujo", "isekai"
    ]
}
# 1. Bắt kính ngữ tiếng Nhật có gạch nối trong tiếng Anh (VD: Tanaka-senpai, Sakura-chan)
JA_HONORIFIC_SUFFIX_REGEX = re.compile(
    r"\b[A-Za-z0-9]+-(?:senpai|kouhai|sensei|san|kun|chan|sama|dono)\b", 
    re.IGNORECASE
)
# 2. Bắt Romaji đứng độc lập
JA_STANDALONE_HONORIFIC_REGEX = re.compile(
    r"\b(senpai|kouhai|sensei|aniki|shishou|onii-chan|onee-chan|onii-san|onee-san)\b",
    re.IGNORECASE
)
# 3. Bắt đại từ "senior/seniors" dùng làm danh xưng anime (thay thế cho 先輩)
JA_ANIME_SENIOR_ADDRESS_REGEX = re.compile(
    r"(?:\b(?:my favorite|good|dear)\s+seniors?\b|,\s*seniors?\b|\bsenior\s*,|\bsenior\s+touched\b|\bsenior\s*,\s*are\b)",
    re.IGNORECASE
)


VI_ACCENTS = re.compile(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', re.IGNORECASE)

def detect_native_language(text: str) -> str:
    """
    Tự động nhận diện ngôn ngữ gốc dựa trên dải mã Unicode chuẩn:
    - Chứa Hiragana [\u3040-\u309F] hoặc Katakana [\u30A0-\u30FF] -> 100% Japanese
    - Chứa Hangul [\uAC00-\uD7AF] -> Korean
    - Chứa chữ Hán [\u4E00-\u9FFF] (không có Kana) -> Chinese (Simplified)
    - Chứa dấu tiếng Việt -> Vietnamese
    - Mặc định -> English
    """
    if not text:
        return "English"
    if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
        return "Japanese"
    if re.search(r'[\uac00-\ud7af]', text):
        return "Korean"
    if re.search(r'[\u4e00-\u9fff]', text):
        return "Chinese (Simplified)"
    if VI_ACCENTS.search(text):
        return "Vietnamese"
    return "English"


def detect_japanese_subject_pronoun(text: str) -> dict[str, Any]:
    """
    Nhận diện đại từ nhân xưng và khẩu khí anime trong câu tiếng Nhật.
    Trả về dict: {"subject": str, "pair": str, "tone": str, "source_pronoun": str, "is_detected": bool, "text": str}
    """
    if not text or not text.strip():
        return {
            "subject": "Tự do",
            "pair": "",
            "tone": "neutral",
            "source_pronoun": "",
            "is_detected": False,
            "text": "Tự do",
        }

    clean = text.strip()

    # 1. Ngôi 1 ngạo mạn / bề trên (俺様, 我輩, 吾輩, わらわ)
    arrogant_m = re.search(r"(俺様|おれさま|オレサマ|我輩|吾輩|わらわ)", clean)
    if arrogant_m:
        pron = arrogant_m.group(1)
        return {
            "subject": f"Ta đây ({pron})",
            "pair": "Ta - Ngươi",
            "tone": "arrogant",
            "source_pronoun": pron,
            "is_detected": True,
            "text": f"Ta ➔ Ngươi ({pron})",
        }

    # 2. Ngôi 2 đối địch / trịch thượng (貴様, お前, てめえ, あんた, お主)
    hostile_m = re.search(r"(貴様|きさま|お前|おまえ|てめえ|てめぇ|あんた|お主)", clean)
    if hostile_m:
        pron = hostile_m.group(1)
        return {
            "subject": f"Ngươi ({pron})",
            "pair": "Ta - Ngươi",
            "tone": "hostile",
            "source_pronoun": pron,
            "is_detected": True,
            "text": f"Ta ➔ Ngươi ({pron})",
        }

    # 3. Kính ngữ Senpai (先輩)
    senpai_m = re.search(r"(先輩|せんぱい|\bsenpai\b)", clean, re.IGNORECASE)
    if senpai_m:
        pron = senpai_m.group(1)
        return {
            "subject": f"Tiền bối ({pron})",
            "pair": "Em - Tiền bối",
            "tone": "respectful",
            "source_pronoun": pron,
            "is_detected": True,
            "text": f"Em ➔ Tiền bối ({pron})",
        }

    # 4. Ngôi 1 thông dụng (あたし, 僕, 俺, 私)
    first_person_rules = [
        (r"(あたし|アタシ|わたくし)", "Tớ - Cậu", "feminine", "Tớ/Em"),
        (r"(僕|ぼく|ボク)", "Tôi - Cậu", "polite", "Tôi/Tớ"),
        (r"(俺|おれ|オレ)", "Tôi - Cậu", "casual_male", "Tôi/Ta"),
        (r"(私|わたし|ワタシ)", "Tôi - Cậu", "polite", "Tôi"),
    ]
    for pattern, pair, tone, label in first_person_rules:
        m = re.search(pattern, clean)
        if m:
            pron = m.group(1)
            return {
                "subject": f"{label} ({pron})",
                "pair": pair,
                "tone": tone,
                "source_pronoun": pron,
                "is_detected": True,
                "text": f"{pair.replace(' - ', ' ➔ ')} ({pron})",
            }

    # 5. Đuôi câu nữ tính / khẳng định (〜わ, 〜わよ, 〜わね, 〜かしら)
    ending_m = re.search(
        r"(わよ|わね|かしら|(?:だ|る|く|う|つ|ぬ|む|ぶ|ぐ|す|ない|たい)わ)[。！!？?」』\s]*$",
        clean,
    )
    if ending_m:
        return {
            "subject": "Nữ tính (〜わ)",
            "pair": "Tớ - Cậu",
            "tone": "feminine_assertive",
            "source_pronoun": "〜わ",
            "is_detected": True,
            "text": "Tớ ➔ Cậu (〜わ)",
        }

    return {
        "subject": "Tự do",
        "pair": "",
        "tone": "neutral",
        "source_pronoun": "",
        "is_detected": False,
        "text": "Tự do",
    }


def detect_ja_translated_en(subtitles_text_sample: str, summary: str = "") -> dict[str, Any]:
    """
    Phát hiện phụ đề tiếng Anh có phải được dịch từ tiếng Nhật hay không
    dựa trên Romaji honorifics, hậu tố gạch nối và hiện tượng 'senior/seniors' làm đại xưng hô.
    """
    sample = f"{subtitles_text_sample}\n{summary}"
    sample_lower = sample.lower()
    clues: list[str] = []
    # 0. Quét ký tự Hiragana / Katakana trực tiếp
    if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', sample):
        clues.append("native_japanese_script")
    # 1. Quét kính ngữ Romaji độc lập
    for term in JA_SOURCE_INDICATORS["romaji_honorifics"]:
        if re.search(rf"\b{re.escape(term)}\b", sample_lower):
            clues.append(f"romaji:{term}")
    # 2. Quét kính ngữ có gạch nối
    suffix_matches = JA_HONORIFIC_SUFFIX_REGEX.findall(sample)
    if suffix_matches:
        clues.extend([f"suffix:{m}" for m in suffix_matches[:3]])
    # 3. Quét đại từ xưng hô "senior/seniors"
    senior_matches = JA_ANIME_SENIOR_ADDRESS_REGEX.findall(sample)
    if senior_matches:
        clues.append("anime_senior_address")
    # 4. Quét từ khóa thể loại anime
    for kw in JA_SOURCE_INDICATORS["anime_keywords"]:
        if re.search(rf"\b{re.escape(kw)}\b", sample_lower):
            clues.append(f"anime_kw:{kw}")
    is_ja = len(clues) > 0
    if "native_japanese_script" in clues:
        confidence = 1.0
    else:
        confidence = min(1.0, len(clues) * 0.3) if is_ja else 0.0
    return {
        "is_ja_origin": is_ja,
        "confidence": confidence,
        "matched_clues": list(set(clues))
    }


def extract_entities(text: str, source_lang: str = "") -> list[dict[str, Any]]:
    """
    Extracts terms and definitions from story summary offline.
    Returns list of dicts with keys: source_term, preferred_translation, is_auto.
    """
    if not text or not text.strip():
        return []

    results: list[dict[str, Any]] = []
    seen_terms_lower: set[str] = set()

    def _is_valid_term(term: str) -> bool:
        t = term.strip()
        if len(t) < 2 or len(t.split()) > 4:
            return False
        if t.isdigit():
            return False
        if t.lower() in STOPWORDS:
            return False
        if any(t.lower().startswith(sw) for sw in ("tóm tắt", "nội dung", "thể loại", "diễn viên", "đạo diễn")):
            return False
        return True

    def _add_entity(src: str, target: str):
        cleaned_src = src.strip().strip('"“\'')
        cleaned_target = target.strip().strip('"“\'')
        if not _is_valid_term(cleaned_src):
            return
        if not cleaned_target:
            cleaned_target = cleaned_src

        src_key = cleaned_src.lower()
        if src_key not in seen_terms_lower:
            seen_terms_lower.add(src_key)
            results.append({
                "source_term": cleaned_src,
                "preferred_translation": cleaned_target,
                "is_auto": True,
            })

    # 1. Extract Explicit Pair Definitions (Line by Line for accuracy)
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        for match in PAIR_PATTERN.finditer(line_clean):
            src = match.group(1) or match.group(2)
            target = match.group(3) or match.group(4)
            if src and target:
                _add_entity(src, target)

    # 2. Extract Quoted or CJK Bracketed Single Entities
    for match in BRACKET_PATTERN.finditer(text):
        term = match.group(1) or match.group(2)
        if term:
            _add_entity(term, term)

    # 3. Extract Katakana Entities
    for match in KATAKANA_PATTERN.finditer(text):
        term = match.group(0)
        if term:
            _add_entity(term, term)

    return results


def classify_archetype(text: str) -> tuple[str, str]:
    """
    Classifies summary text into a character archetype and default pronoun pair.
    Default and only supported mode is Pure Model (Dịch thuần).
    Returns: (ARCHETYPE_PURE, "")
    """
    return ARCHETYPE_PURE, ""


def analyze_context(text: str, source_lang: str = "") -> dict[str, Any]:
    """
    Convenience wrapper returning archetype, pronouns, and extracted entities.
    """
    entities = extract_entities(text, source_lang)
    return {
        "archetype": ARCHETYPE_PURE,
        "pronouns": "",
        "entities": entities,
    }


class ContextAnalyzer:
    """Class wrapper providing static access to analysis methods."""
    ARCHETYPE_PURE = ARCHETYPE_PURE
    ARCHETYPE_ANCIENT_FANTASY = ARCHETYPE_ANCIENT_FANTASY
    ARCHETYPE_ANIME_SCHOOL = ARCHETYPE_ANIME_SCHOOL
    ARCHETYPE_MODERN_ACTION = ARCHETYPE_MODERN_ACTION
    ARCHETYPE_ROMANCE_FAMILY = ARCHETYPE_ROMANCE_FAMILY
    ARCHETYPE_CUSTOM = ARCHETYPE_CUSTOM

    DEFAULT_PRONOUNS = DEFAULT_PRONOUNS
    ARCHETYPE_METADATA = ARCHETYPE_METADATA
    ARCHETYPE_LIST = ARCHETYPE_LIST

    @staticmethod
    def extract_entities(text: str, source_lang: str = "") -> list[dict[str, Any]]:
        return extract_entities(text, source_lang)

    @staticmethod
    def classify_archetype(text: str) -> tuple[str, str]:
        return classify_archetype(text)

    @staticmethod
    def analyze_context(text: str, source_lang: str = "") -> dict[str, Any]:
        return analyze_context(text, source_lang)

    @staticmethod
    def detect_native_language(text: str) -> str:
        return detect_native_language(text)

    @staticmethod
    def detect_ja_translated_en(subtitles_text_sample: str, summary: str = "") -> dict[str, Any]:
        return detect_ja_translated_en(subtitles_text_sample, summary)

    @staticmethod
    def detect_japanese_subject_pronoun(text: str) -> dict[str, Any]:
        return detect_japanese_subject_pronoun(text)
