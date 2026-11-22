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
    # Không còn hardcode prompt mồi tiếng Nhật ẩn trong mã nguồn
    assert get_initial_prompt_for_language("ja") == ""
    assert get_initial_prompt_for_language(None) == ""
    assert get_initial_prompt_for_language("") == ""
    assert get_initial_prompt_for_language("unknown") == ""
