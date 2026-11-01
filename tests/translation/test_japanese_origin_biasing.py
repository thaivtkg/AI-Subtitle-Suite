"""
Unit tests for Japanese Origin Detection & Pronoun Biasing.
"""
import pytest
from core.translation.core.context_analyzer import (
    ContextAnalyzer,
    detect_ja_translated_en,
    ARCHETYPE_ANIME_SCHOOL,
)
from core.translation.core.prompt_builder import PromptBuilder


def test_detect_ja_translated_en_romaji_honorifics():
    text = "Please listen to me, senpai! Tanaka-sensei is waiting."
    res = detect_ja_translated_en(text)
    assert res["is_ja_origin"] is True
    assert any("senpai" in c for c in res["matched_clues"])
    assert any("sensei" in c for c in res["matched_clues"])


def test_detect_ja_translated_en_hyphenated_suffixes():
    text = "Hello Taro-kun, have you seen Hanako-chan today?"
    res = detect_ja_translated_en(text)
    assert res["is_ja_origin"] is True
    assert any("Taro-kun" in c or "Hanako-chan" in c for c in res["matched_clues"])


def test_detect_ja_translated_en_senior_address():
    # Câu đặc trưng trích từ file ghpm98.srt thực tế
    text = "What's wrong, senior, are you giving up? Because my favorite senior touched me."
    res = detect_ja_translated_en(text)
    assert res["is_ja_origin"] is True
    assert "anime_senior_address" in res["matched_clues"]


def test_native_english_not_detected_as_ja():
    text = "The senior software engineer submitted a pull request for the quarterly report."
    res = detect_ja_translated_en(text)
    assert res["is_ja_origin"] is False
    assert res["confidence"] == 0.0


def test_prompt_builder_pure_model_omits_japanese_artifacts():
    prompt = PromptBuilder.build(
        story_summary="Anime romance school",
        source_lang="English",
        target_lang="Vietnamese",
        current_sub="What's wrong, senior, are you giving up?",
        active_pronoun_pair="Em - Tiền bối",
        is_ja_origin=True,
    )
    # The Ponytail Purge: Pure translation mode omits forced anime artifact and pronoun rules
    assert "JAPANESE TRANSLATION ARTIFACTS" not in prompt
    assert "PRONOUN RELATIONSHIP" not in prompt
    assert "Anime romance school" in prompt
    assert "STRICT OUTPUT FORMAT" in prompt


def test_senior_pure_mode_no_forced_pronoun_artifacts():
    current_sub = "What's wrong, senior, are you giving up?"
    unmarked_prompt = PromptBuilder.build(
        current_sub=current_sub,
        source_lang="English",
        target_lang="Vietnamese",
        is_ja_origin=False,
    )
    assert "JAPANESE TRANSLATION ARTIFACTS" not in unmarked_prompt
    assert "NEVER translate as 'người lớn tuổi'" not in unmarked_prompt

    marked_prompt = PromptBuilder.build(
        current_sub=current_sub,
        source_lang="English",
        target_lang="Vietnamese",
        is_ja_origin=True,
    )
    # Pure mode does not force 'tiền bối' or artifacts
    assert "JAPANESE TRANSLATION ARTIFACTS" not in marked_prompt
    assert "NEVER translate as 'người lớn tuổi'" not in marked_prompt


def test_pure_mode_prev_context_handling():
    prompt = PromptBuilder.build(
        story_summary="Anime học đường",
        source_lang="English",
        target_lang="Vietnamese",
        prev_context=["Chuyện gì vậy tiền bối, tiền bối định bỏ cuộc sao?"],
        current_sub="I will not give up.",
        active_pronoun_pair="Em - Tiền bối",
        is_ja_origin=True,
    )
    # Pure mode includes context and strict output format, but no alternating speaker forced rules
    assert "Chuyện gì vậy tiền bối" in prompt
    assert "STRICT OUTPUT FORMAT" in prompt
    assert "ALTERNATING SPEAKERS" not in prompt

