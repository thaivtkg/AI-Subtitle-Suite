import pytest
from core.translation.core.context_analyzer import (
    ARCHETYPE_ANCIENT_FANTASY,
    ARCHETYPE_ANIME_SCHOOL,
    ARCHETYPE_MODERN_ACTION,
    ARCHETYPE_ROMANCE_FAMILY,
    ARCHETYPE_CUSTOM,
    DEFAULT_PRONOUNS,
    ARCHETYPE_METADATA,
    extract_entities,
    classify_archetype,
    analyze_context,
)


def test_archetype_constants_and_metadata():
    assert len(ARCHETYPE_METADATA) == 1
    assert ARCHETYPE_METADATA["pure_model"]["name"] == "Dịch Thuần (Pure Model)"
    assert DEFAULT_PRONOUNS[ARCHETYPE_CUSTOM] == ""


def test_extract_pair_definitions():
    text = """
    "Xiao Yan": Tiêu Viêm
    "Master Yao" -> Dược Lão
    Naruto => Uzumaki Naruto
    Aizen là Lam Nhiễm
    """
    entities = extract_entities(text)
    lookup = {e["source_term"]: e["preferred_translation"] for e in entities}
    assert lookup.get("Xiao Yan") == "Tiêu Viêm"
    assert lookup.get("Master Yao") == "Dược Lão"
    assert lookup.get("Naruto") == "Uzumaki Naruto"
    assert lookup.get("Aizen") == "Lam Nhiễm"
    for e in entities:
        assert e["is_auto"] is True


def test_extract_quotes_and_cjk_brackets():
    text = """
    Nhân vật chính "Soul Society" cùng “Kurotsuchi” nghiên cứu 「Bankai」.
    Bảo vật 『Shinigami』 và ấn ký 【Zanpakuto】 được ghi chép trong 《Hokage》.
    """
    entities = extract_entities(text)
    terms = [e["source_term"] for e in entities]
    assert "Soul Society" in terms
    assert "Kurotsuchi" in terms
    assert "Bankai" in terms
    assert "Shinigami" in terms
    assert "Zanpakuto" in terms
    assert "Hokage" in terms
    for e in entities:
        assert e["preferred_translation"] == e["source_term"]


def test_extract_katakana_terms():
    text = "Cuộc phiêu lưu của ナルト trong thế giới サイバーパンク đầy cạm bẫy."
    entities = extract_entities(text)
    terms = [e["source_term"] for e in entities]
    assert "ナルト" in terms
    assert "サイバーパンク" in terms


def test_sanitize_and_stopwords_filtering():
    text = """
    Phim: 123
    Tập: a
    Thể loại: Kiếm hiệp
    "Xiao Yan": Tiêu Viêm
    xiao yan: Tiêu Viêm Nhỏ
    """
    entities = extract_entities(text)
    terms_lower = [e["source_term"].lower() for e in entities]
    # Khử trùng lặp
    assert terms_lower.count("xiao yan") == 1
    # Bỏ qua từ < 2 ký tự hoặc stopwords
    assert "phim" not in terms_lower
    assert "tập" not in terms_lower
    assert "thể loại" not in terms_lower
    assert "a" not in terms_lower


def test_classify_pure_model_defaults():
    text = "Hành trình tu tiên của đệ tử tông môn, luyện phi kiếm cùng sư huynh sư muội trừ yêu ma."
    archetype, pronouns = classify_archetype(text)
    assert archetype == "pure_model"
    assert pronouns == ""


def test_empty_and_whitespace_summary():
    assert classify_archetype("") == ("pure_model", "")
    assert classify_archetype("   \n\t  ") == ("pure_model", "")
    assert extract_entities("") == []
    assert extract_entities("   ") == []


def test_analyze_context_wrapper():
    text = 'Tu tiên tông môn, nhân vật "Xiao Yan": Tiêu Viêm sử dụng phi kiếm.'
    result = analyze_context(text)
    assert result["archetype"] == "pure_model"
    assert result["pronouns"] == ""
    assert any(e["source_term"] == "Xiao Yan" for e in result["entities"])


def test_logic_03_metadata_heading_not_extracted_as_glossary():
    """Kiểm tra LOGIC-03: Không trích xuất tiêu đề tóm tắt thành glossary."""
    from core.translation.core.context_analyzer import extract_entities
    text = "Tóm tắt phim: Nhân vật A là bạn thân của B\nThể loại: Kiếm hiệp"
    entities = extract_entities(text)
    # Không được chứa 'Tóm tắt phim' hay 'Thể loại'
    assert not any(e["source_term"].lower().startswith("tóm tắt") for e in entities)
    assert not any(e["source_term"].lower().startswith("thể loại") for e in entities)


def test_logic_04_witch_does_not_trigger_japanese_origin():
    """Kiểm tra LOGIC-04: Từ tiếng Anh 'witch' không kích hoạt is_ja_origin."""
    from core.translation.core.context_analyzer import detect_ja_translated_en
    result = detect_ja_translated_en("The witch of Salem flew across the dark sky.")
    assert result["is_ja_origin"] is False
    assert "witch" not in result["matched_clues"]


def test_logic_06_word_boundary_glossary_and_entity():
    """Kiểm tra LOGIC-06: Ranh giới từ \b ngăn chặn khớp nhầm chuỗi con."""
    from core.translation.core.glossary import Glossary
    from core.translation.core.entity_dictionary import EntityDictionary

    g = Glossary.from_entries([("cat", "mèo", [])])
    assert len(g.match("communicated with them", word_boundary=True)) == 0
    assert len(g.match("A lovely cat arrived", word_boundary=True)) == 1

    ed = EntityDictionary.from_entries([("Dan", "CHARACTER", "Dan", [])])
    assert len(ed.match("Danger ahead", word_boundary=True)) == 0
    assert len(ed.match("Dan is here", word_boundary=True)) == 1


