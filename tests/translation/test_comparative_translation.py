"""
Mandatory A/B Comparative Test & Dialogue Continuity Verification.
Ensures that adding Story Summary, Archetype Pronoun Biasing, and Translated Previous Subtitles
strictly modifies the prompt compared to baseline, failing if no difference is detected.
"""

import pytest
from core.translation.core.prompt_builder import PromptBuilder
from core.translation.core.context_engine import ContextEngine
from core.translation.core.context_analyzer import (
    ContextAnalyzer,
    ARCHETYPE_ANCIENT_FANTASY,
    classify_archetype,
)


def test_mandatory_ab_comparative_prompt_difference():
    """
    MANDATORY A/B TEST:
    Compare translation prompt BEFORE vs AFTER adding Summary & Pronoun Biasing.
    MUST fail if enriched prompt does not enforce target pronouns or differs from baseline.
    """
    current_sub = "What do you want from me?"

    # --- 1. BASELINE: No summary, no active pronoun pair, raw previous context ---
    baseline_prev = ["Hello there."]
    baseline_prompt = PromptBuilder.build(
        story_summary="",
        source_lang="English",
        target_lang="Vietnamese",
        prev_context=baseline_prev,
        current_sub=current_sub,
        next_context=[],
        active_pronoun_pair="",
    )

    # --- 2. ENRICHED: Ancient Fantasy summary, Ta - Ngươi detected, translated dialogue ---
    summary = "Phim cổ trang tu tiên kiếm hiệp, hai cao thủ đối đầu sinh tử"
    archetype, pronoun_pair = classify_archetype(summary)
    assert archetype == "pure_model"
    assert pronoun_pair == ""

    # Context continuity
    enriched_prev = ["Ngươi muốn gì ở ta?"]
    enriched_prompt = PromptBuilder.build(
        story_summary=summary,
        source_lang="English",
        target_lang="Vietnamese",
        prev_context=enriched_prev,
        current_sub=current_sub,
        next_context=[],
        active_pronoun_pair=pronoun_pair,
        canonical_names=("Tiêu Viêm",),
    )

    # --- 3. MANDATORY COMPARATIVE ASSERTIONS ---
    # Enriched prompt MUST strictly differ from baseline due to Story Summary and Canonical Names
    assert enriched_prompt != baseline_prompt, (
        "CRITICAL FAILURE: Enriched prompt MUST be strictly different from baseline prompt!"
    )
    assert "STORY SUMMARY" in enriched_prompt
    assert "Tiêu Viêm" in enriched_prompt
    assert "Ngươi muốn gì ở ta?" in enriched_prompt, (
        "CRITICAL FAILURE: Enriched prompt MUST contain preceding translated dialogue for continuity!"
    )

    # Baseline prompt MUST NOT contain these biased rules
    assert "Ta - Ngươi" not in baseline_prompt, (
        "CRITICAL FAILURE: Baseline prompt must NOT contain 'Ta - Ngươi'!"
    )
    assert "Tiêu Viêm" not in baseline_prompt, (
        "CRITICAL FAILURE: Baseline prompt must NOT contain 'Tiêu Viêm'!"
    )


def test_context_engine_dialogue_continuity_statuses():
    """
    ContextEngine must supply translated text for ACCEPTED, TRANSLATED, and EDITED subtitles,
    and fall back to original text for PENDING or untranslated lines.
    """
    subtitles = [
        {"original": "Line 1 original", "translation": "Câu 1 đã duyệt", "status": "ACCEPTED"},
        {"original": "Line 2 original", "translation": "Câu 2 vừa dịch", "status": "TRANSLATED"},
        {"original": "Line 3 original", "translation": "Câu 3 người dùng sửa", "status": "EDITED"},
        {"original": "Line 4 original", "translation": "", "status": "PENDING"},
        {"original": "Line 5 current", "translation": "", "status": "PENDING"},
        {"original": "Line 6 future", "translation": "", "status": "PENDING"},
    ]

    prev_ctx, current_sub, next_ctx = ContextEngine.get_context(subtitles, 4)

    assert current_sub == "Line 5 current"
    # Lines 1, 2, 3 must use translation; Line 4 uses original because translation is empty
    assert "Câu 1 đã duyệt" not in prev_ctx  # window 3 câu trước: index 1, 2, 3
    assert "Câu 2 vừa dịch" in prev_ctx
    assert "Câu 3 người dùng sửa" in prev_ctx
    assert "Line 4 original" in prev_ctx
    # Next subtitles always use original
    assert "Line 6 future" in next_ctx


def test_active_pronoun_pair_only_injected_for_vietnamese():
    """
    Active pronoun pair instructions are specific to Vietnamese localization.
    Targeting other languages (e.g. English, French) should not inject Vietnamese pronoun rules.
    """
    prompt_en = PromptBuilder.build(
        story_summary="Some summary",
        source_lang="Vietnamese",
        target_lang="English",
        prev_context=[],
        current_sub="Xin chào",
        next_context=[],
        active_pronoun_pair="Ta - Ngươi",
    )
    assert "VIETNAMESE LOCALIZATION RULES" not in prompt_en
    assert "PRONOUN RELATIONSHIP" not in prompt_en


def test_custom_archetype_omits_mandatory_pronoun_rule():
    """
    When active_pronoun_pair is 'Tự do (Theo ngữ cảnh)' or empty,
    mandatory pronoun constraint is omitted, falling back to general natural pronoun guidelines.
    """
    prompt = PromptBuilder.build(
        story_summary="Modern story",
        source_lang="English",
        target_lang="Vietnamese",
        prev_context=[],
        current_sub="Hello",
        next_context=[],
        active_pronoun_pair="Tự do (Theo ngữ cảnh)",
    )
    assert "VIETNAMESE LOCALIZATION RULES" in prompt
    assert "PRONOUN RELATIONSHIP" not in prompt
    assert "NATURAL DIALOGUE" in prompt


def test_request_and_apply_alternative_translation():
    from core.translation.controllers.translation_controller import TranslationController
    from core.translation.models.subtitle import SubtitleModel
    from PySide6.QtCore import QObject, Signal

    class MockWorker(QObject):
        finished = Signal(int, str)
        error = Signal(int, str)
        progress = Signal(int, str)

        def __init__(self, index, prompt, profile):
            super().__init__()
            self.index = index
            self.prompt = prompt
            self.profile = profile

        def start(self):
            assert self.profile.get("temperature") == 0.7
            assert "phóng khoáng" in self.prompt
            self.finished.emit(self.index, "Tôi rất khỏe, cảm ơn bạn nhiều nhé!")

    model = SubtitleModel()
    model.load_data([{"index": 1, "original": "How are you?", "translation": "Bạn khỏe không?", "status": "TRANSLATED"}])
    controller = TranslationController(model, worker_factory=MockWorker)

    received_alt = []
    controller.alternativeTranslationReady.connect(lambda idx, text, mode: received_alt.append((idx, text, mode)))

    controller.requestAlternativeTranslation(0, "English", "CREATIVE")
    assert len(received_alt) == 1
    assert received_alt[0] == (0, "Tôi rất khỏe, cảm ơn bạn nhiều nhé!", "CREATIVE")

    controller.applyAlternativeTranslation(0, received_alt[0][1])
    assert model.get_all_data()[0]["translation"] == "Tôi rất khỏe, cảm ơn bạn nhiều nhé!"
    assert model.get_all_data()[0]["status"] == "EDITED"


def test_detect_native_language():
    assert ContextAnalyzer.detect_native_language("邪魔王やっと見つけたわ") == "Japanese"
    assert ContextAnalyzer.detect_native_language("こんにちは世界") == "Japanese"
    assert ContextAnalyzer.detect_native_language("안녕하세요") == "Korean"
    assert ContextAnalyzer.detect_native_language("你好世界") == "Chinese (Simplified)"
    assert ContextAnalyzer.detect_native_language("Hello, how are you today?") == "English"
    assert ContextAnalyzer.detect_native_language("Cuối cùng đã tìm thấy ngươi rồi Ma Vương") == "Vietnamese"
    assert ContextAnalyzer.detect_native_language("Tôi là học sinh") == "Vietnamese"
    assert ContextAnalyzer.detect_native_language("") == "English"


def test_alternative_prompt_placement_in_gemma():
    style = "Dịch bám sát từng từ ngữ gốc (literal)."
    prompt = PromptBuilder.build(
        current_sub="What is that?",
        model_family="gemma",
        style_instruction=style,
    )
    # style must be in user prompt before model turn
    assert f"STYLE INSTRUCTION:\n{style}" in prompt
    assert prompt.endswith("<start_of_turn>model\n")
    # Verify model turn has no appended text
    after_model = prompt.split("<start_of_turn>model\n")[-1]
    assert after_model == ""


def test_clean_translated_text_chatter_removal():
    from core.translation.controllers.translation_controller import TranslationController

    raw1 = "Nữ chiến binh phép thuật.\nCuối cùng, nếu bạn có thể cho tôi biết thêm về ngữ cảnh, tôi có thể dịch chuẩn xác hơn."
    assert TranslationController._clean_translated_text(raw1) == "Nữ chiến binh phép thuật."

    raw2 = "Cuối cùng, nếu bạn có thể cho tôi biết thêm về ngữ cảnh của bộ phim."
    assert TranslationController._clean_translated_text(raw2) == ""

    raw3 = "Thanh gươm diệt quỷ Nếu bạn có thể cho tôi biết nhân vật là ai"
    assert TranslationController._clean_translated_text(raw3) == "Thanh gươm diệt quỷ"


def test_project_controller_auto_detect_japanese_on_import(tmp_path):
    from core.translation.controllers.project_controller import ProjectController
    from core.translation.models.subtitle import SubtitleModel

    srt_content = """1
00:00:01,000 --> 00:00:03,000
邪魔王やっと見つけたわ
"""
    srt_file = tmp_path / "japanese_sub.srt"
    srt_file.write_text(srt_content, encoding="utf-8")

    model = SubtitleModel()
    controller = ProjectController(model)

    emitted_langs = []
    controller.languageLoaded.connect(lambda l: emitted_langs.append(l))

    controller.importSrt(str(srt_file))

    assert "Japanese" in emitted_langs
    assert controller.isJaOrigin is True
    # Không tự động ép sang anime_school / Em - Tiền bối khi nhận diện tiếng Nhật
    assert controller.activeArchetype == "pure_model"
    assert "Tiền bối" not in controller.activePronounPair


def test_project_controller_auto_detect_japanese_on_load_project(tmp_path):
    import json
    from core.translation.controllers.project_controller import ProjectController
    from core.translation.models.subtitle import SubtitleModel

    aisrt_data = {
        "version": "1.0",
        "metadata": {
            "source_file": "sample.srt",
            "source_language": "English",
            "target_language": "Vietnamese"
        },
        "subtitles": [
            {
                "index": 1,
                "start_time": "00:00:15,350",
                "end_time": "00:00:17,540",
                "original": "妖魔王やっと見つけたわ",
                "translation": "",
                "status": "PENDING"
            }
        ]
    }
    aisrt_file = tmp_path / "legacy_project.aisrt"
    aisrt_file.write_text(json.dumps(aisrt_data), encoding="utf-8")

    model = SubtitleModel()
    controller = ProjectController(model)

    emitted_langs = []
    controller.languageLoaded.connect(lambda l: emitted_langs.append(l))

    controller.loadProject(str(aisrt_file))

    assert "Japanese" in emitted_langs
    assert controller.isJaOrigin is True
    # Không tự động ép sang anime_school khi nhận diện tiếng Nhật
    assert controller.activeArchetype == "pure_model"

