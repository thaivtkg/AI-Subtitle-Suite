# -*- coding: utf-8 -*-
import pytest
from core.subtitle_generation.language_utils import normalize_to_iso_code, get_initial_prompt_for_language


def test_normalize_to_iso_code():
    assert normalize_to_iso_code("Japanese") == "ja"
    assert normalize_to_iso_code("japanese") == "ja"
    assert normalize_to_iso_code("ja") == "ja"
    assert normalize_to_iso_code("Vietnamese") == "vi"
    assert normalize_to_iso_code("vietnamese") == "vi"
    assert normalize_to_iso_code("English") == "en"
    assert normalize_to_iso_code("Korean") == "ko"
    assert normalize_to_iso_code("Chinese") == "zh"
    assert normalize_to_iso_code("Auto Detect") is None
    assert normalize_to_iso_code("auto detect") is None
    assert normalize_to_iso_code("none") is None
    assert normalize_to_iso_code("") is None
    assert normalize_to_iso_code(None) is None


def test_get_initial_prompt_for_japanese():
    prompt = get_initial_prompt_for_language("ja")
    assert prompt != ""
    # Chứa các từ cảm thán / đệm thông dụng trong tiếng Nhật
    for token in ["はい", "うん", "そう", "あの", "よし", "では", "違う"]:
        assert token in prompt, f"Kỳ vọng từ đệm '{token}' có trong initial prompt tiếng Nhật!"

    assert get_initial_prompt_for_language(None) == ""
    assert get_initial_prompt_for_language("") == ""
    assert get_initial_prompt_for_language("unknown") == ""
