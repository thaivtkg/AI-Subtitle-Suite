import pytest
from unittest.mock import MagicMock
from core.translation.core.context_analyzer import (
    ContextAnalyzer,
    detect_japanese_subject_pronoun,
)
from core.translation.core.prompt_builder import PromptBuilder
from core.translation.models.subtitle import SubtitleModel
from core.translation.controllers.translation_controller import TranslationController


def test_detect_japanese_subject_pronoun_oresama():
    res = detect_japanese_subject_pronoun("「この俺様に一体何の」")
    assert res["pair"] == "Ta - Ngươi"
    assert res["tone"] == "arrogant"
    assert res["source_pronoun"] == "俺様"
    assert "Ta đây" in res["subject"] or "Ta" in res["subject"]

    # Kiểm tra qua static method trên ContextAnalyzer
    res_static = ContextAnalyzer.detect_japanese_subject_pronoun("貴様、何をしている！")
    assert res_static["pair"] == "Ta - Ngươi"
    assert res_static["source_pronoun"] == "貴様"


def test_detect_japanese_sentence_ending_wa():
    res = detect_japanese_subject_pronoun("「そんなの決まってるわ。」")
    assert res["tone"] == "feminine_assertive"
    assert res["is_detected"] is True
    assert "わ" in res["source_pronoun"] or "Nữ" in res["subject"]


def test_prompt_builder_injects_mandatory_pronoun_pair():
    prompt = PromptBuilder.build(
        story_summary="Anime fantasy",
        source_lang="Japanese",
        target_lang="Vietnamese",
        current_sub="「この俺様に一体何の」",
        active_pronoun_pair="Ta - Ngươi",
    )
    assert "MANDATORY PRONOUN PAIR" in prompt
    assert "Ta - Ngươi" in prompt
    assert "First person: 'Ta'" in prompt
    assert "Second person: 'Ngươi'" in prompt


def test_prompt_builder_japanese_anime_rules_present():
    prompt = PromptBuilder.build(
        story_summary="Anime",
        source_lang="Japanese",
        target_lang="Vietnamese",
        current_sub="「この俺様に一体何の」",
        model_family="gemma",
    )
    assert "俺様" in prompt
    assert "Ngươi tìm ta đây rốt cuộc có chuyện gì?" in prompt
    assert "決まってるわ" in prompt
    assert "Chuyện đó còn phải hỏi sao!" in prompt
    assert "đến tớ đây" in prompt  # Nằm trong danh sách cấm cắt vụn từ gốc


def test_translation_controller_current_subject_tag_property(qapp):
    model = SubtitleModel()
    model.load_data([
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:03,000",
            "original": "「この俺様に一体何の」",
            "translation": "",
            "status": "PENDING",
        },
        {
            "index": 2,
            "start_time": "00:00:03,500",
            "end_time": "00:00:05,500",
            "original": "「そんなの決まってるわ。」",
            "translation": "",
            "status": "PENDING",
        },
    ])

    captured_prompts = []

    class DummyWorker:
        def __init__(self, idx, prompt, profile):
            captured_prompts.append(prompt)
            self.progress = MagicMock()
            self.finished = MagicMock()
            self.error = MagicMock()
            self.termsExtracted = MagicMock()

        def isRunning(self):
            return False

        def start(self):
            pass

    tc = TranslationController(model, worker_factory=DummyWorker)
    tc.loadSubtitle(0)

    tag = tc.currentSubjectTag
    assert tag["is_detected"] is True
    assert tag["pair"] == "Ta - Ngươi"
    assert tag["source_pronoun"] == "俺様"

    # Khi dịch câu 0, prompt tự động nhận cặp đại từ phát hiện được ("Ta - Ngươi")
    tc.requestTranslation(0, "Japanese", "Vietnamese", "")
    assert len(captured_prompts) == 1
    assert "MANDATORY PRONOUN PAIR" in captured_prompts[0]
    assert "Ta - Ngươi" in captured_prompts[0]

    # Người dùng click đổi nhanh ngôi xưng trên Thẻ Chủ Ngữ
    tc.setSubjectPronoun("Anh - Em")
    assert tc.currentSubjectTag["pair"] == "Anh - Em"
    assert "Anh ➔ Em" in tc.currentSubjectTag["text"] or "Anh - Em" in tc.currentSubjectTag["text"]


def test_pure_free_mode_omits_context_in_prompt(qapp):
    """Kiểm tra khi chọn 'Tự do', prompt dịch hoàn toàn không chứa ngữ cảnh câu trước/sau để dịch thuần túy."""
    from unittest.mock import MagicMock
    from core.translation.models.subtitle import SubtitleModel
    from core.translation.controllers.translation_controller import TranslationController

    model = SubtitleModel()
    model.load_data([
        {"id": "1", "original": "Câu 1 ngữ cảnh trước", "translation": "Bản dịch 1", "status": "ACCEPTED"},
        {"id": "2", "original": "決まってるわ", "translation": "", "status": "PENDING"},
        {"id": "3", "original": "Câu 3 ngữ cảnh sau", "translation": "", "status": "PENDING"},
    ])

    captured_prompts = []

    class DummyWorker:
        def __init__(self, idx, prompt, profile):
            captured_prompts.append(prompt)
            self.progress = MagicMock()
            self.finished = MagicMock()
            self.error = MagicMock()
            self.termsExtracted = MagicMock()

        def isRunning(self): return False
        def start(self): pass

    tc = TranslationController(model, worker_factory=DummyWorker)
    tc.loadSubtitle(1)

    # Đặt chủ ngữ sang 'Tự do' (Dịch thuần tự do)
    tc.setSubjectPronoun("Tự do")
    tc.requestTranslation(1, "Japanese", "Vietnamese", "")

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # Xác nhận ngữ cảnh trước và sau ĐÃ ĐƯỢC LOẠI BỎ hoàn toàn
    assert "--- PREVIOUS SUBTITLES ---" not in prompt
    assert "--- NEXT SUBTITLES ---" not in prompt
    assert "Câu 1 ngữ cảnh trước" not in prompt
    assert "Câu 3 ngữ cảnh sau" not in prompt
    # Chỉ chứa câu hiện tại để dịch thuần túy
    assert "--- CURRENT SUBTITLE TO TRANSLATE ---" in prompt
    assert "決まってるわ" in prompt


def test_model_catalog_contains_translategemma_q4_and_q5():
    """Kiểm tra danh mục model catalog có cả 2 phiên bản Q4_K_M và Q5_K_M của TranslateGemma."""
    from core.translation.core.model_catalog import MODEL_CATALOG

    assert "translategemma-9b-q4_k_m" in MODEL_CATALOG
    assert "translategemma-9b-q5_k_m" in MODEL_CATALOG

    q4 = MODEL_CATALOG["translategemma-9b-q4_k_m"]
    q5 = MODEL_CATALOG["translategemma-9b-q5_k_m"]

    assert q4.filename == "gemma-2-9b-it-Q4_K_M.gguf"
    assert q5.filename == "gemma-2-9b-it-Q5_K_M.gguf"
    assert "Q5_K_M" in q5.display_name
    assert "Q5_K_M.gguf" in q5.download_url
    assert q5.min_vram_gb > q4.min_vram_gb
