import os
import pytest
from PySide6.QtCore import QCoreApplication, QObject
from core.translation.models.subtitle import SubtitleModel
from core.translation.controllers.project_controller import ProjectController
from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.app_settings import AppSettings


@pytest.fixture(autouse=True)
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def test_term_alignment_from_glossary_and_entities():
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "start_time": "00:00:01,000", "end_time": "00:00:03,000", "original": "Sailor Angel và 妖魔王 đang đối đầu.", "translation": "", "status": "PENDING"},
        {"index": 2, "start_time": "00:00:04,000", "end_time": "00:00:06,000", "original": "Xin chào thế giới.", "translation": "", "status": "PENDING"}
    ])

    proj_ctrl = ProjectController(model)
    proj_ctrl.addManualGlossaryTerm("Sailor Angel", "Chiến Binh Thiên Sứ")
    proj_ctrl.addManualGlossaryTerm("妖魔王", "Ma Vương")

    tc = TranslationController(model)
    tc.bind_intelligence(
        glossary=proj_ctrl.glossary,
        entities=proj_ctrl.entity_dictionary,
        translation_memory=proj_ctrl.translation_memory,
        project_controller=proj_ctrl,
    )

    # 1. Load row 0: Should detect both Sailor Angel and 妖魔王
    tc.loadSubtitle(0)
    terms = tc.currentAppliedTerms
    assert len(terms) == 2
    sources = [t["source"] for t in terms]
    targets = [t["target"] for t in terms]
    assert "Sailor Angel" in sources
    assert "妖魔王" in sources
    assert "Chiến Binh Thiên Sứ" in targets
    assert "Ma Vương" in targets

    # 2. Load row 1: No matching terms
    tc.loadSubtitle(1)
    assert tc.currentAppliedTerms == []

    # 3. Add new term to glossary dynamically
    tc.loadSubtitle(1)
    proj_ctrl.addManualGlossaryTerm("thế giới", "World")
    terms_row1 = tc.currentAppliedTerms
    assert len(terms_row1) == 1
    assert terms_row1[0]["source"] == "thế giới"
    assert terms_row1[0]["target"] == "World"


def test_recent_files_settings_and_controller(tmp_path):
    settings_file = tmp_path / "test_settings.json"
    settings = AppSettings(file_path=str(settings_file))
    assert settings.recent_files == []

    f1 = tmp_path / "batch_1.srt"
    f1.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
    f2 = tmp_path / "project.aisrt"
    f2.write_text("{}", encoding="utf-8")

    settings.add_recent_file(str(f1))
    assert len(settings.recent_files) == 1
    assert os.path.normpath(settings.recent_files[0]) == os.path.normpath(str(f1))

    # Add second file: should be at index 0
    settings.add_recent_file(str(f2))
    assert len(settings.recent_files) == 2
    assert os.path.normpath(settings.recent_files[0]) == os.path.normpath(str(f2))

    # Re-adding f1 should move it to the top without duplicates
    settings.add_recent_file(str(f1))
    assert len(settings.recent_files) == 2
    assert os.path.normpath(settings.recent_files[0]) == os.path.normpath(str(f1))

    # Max 5 limit
    for i in range(10):
        dummy = tmp_path / f"dummy_{i}.srt"
        dummy.write_text("", encoding="utf-8")
        settings.add_recent_file(str(dummy), max_items=5)
    assert len(settings.recent_files) == 5

    # Test ProjectController integration
    model = SubtitleModel()
    ctrl = ProjectController(model)
    ctrl._settings = settings

    recent = ctrl.recentFiles
    assert len(recent) <= 5
    for item in recent:
        assert "path" in item
        assert "name" in item
        assert "is_project" in item

    # Test openRecentFile
    ctrl.openRecentFile(str(f1))
    assert ctrl.originalSourcePath == str(f1)
from core.translation.llm.worker import TranslationWorker


def test_worker_auto_terms_extraction_and_visible_shield():
    raw_output = (
        "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương!\n\n"
        "[TỪ GỐC]\n"
        "- 妖魔王 -> Ma Vương\n"
        "* やっと ➔ cuối cùng\n"
        "- 'セーラーエンジェル' -> \"Chiến Binh Thiên Sứ\"\n"
    )

    # 1. Bóc tách từ vựng
    terms = TranslationWorker.extract_auto_terms(raw_output)
    assert len(terms) == 3
    assert terms[0] == {"source": "妖魔王", "target": "Ma Vương"}
    assert terms[1] == {"source": "やっと", "target": "cuối cùng"}
    assert terms[2] == {"source": "セーラーエンジェル", "target": "Chiến Binh Thiên Sứ"}

    # 2. Lá chắn hiển thị: Cắt sạch [TỪ GỐC] khỏi ô nhập liệu
    clean_display = TranslationWorker._visible_translation(raw_output)
    assert clean_display == "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương!"

    # 3. Lá chắn token dở dang khi đang stream
    streaming_chunk_1 = "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương!\n[TỪ"
    assert TranslationWorker._visible_translation(streaming_chunk_1) == "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương!"

    streaming_chunk_2 = "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương!\n[từ gốc"
    assert TranslationWorker._visible_translation(streaming_chunk_2) == "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương!"


def test_auto_terms_priority_and_pin_to_glossary():
    model = SubtitleModel()
    model.load_data([
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:03,000",
            "original": "妖魔王やっと見つけたわ",
            "translation": "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương",
            "status": "TRANSLATED",
            "auto_terms": [
                {"source": "妖魔王", "target": "ác quỷ"},
                {"source": "やっと", "target": "cuối cùng"}
            ]
        }
    ])

    proj_ctrl = ProjectController(model)
    tc = TranslationController(model)
    tc.bind_intelligence(
        glossary=proj_ctrl.glossary,
        entities=proj_ctrl.entity_dictionary,
        translation_memory=proj_ctrl.translation_memory,
        project_controller=proj_ctrl,
    )

    tc.loadSubtitle(0)
    terms = tc.currentAppliedTerms
    assert len(terms) == 2
    # Ban đầu là auto_terms: is_glossary = False
    assert terms[0]["source"] == "妖魔王"
    assert terms[0]["target"] == "ác quỷ"
    assert terms[0]["is_glossary"] is False

    # Người dùng nhấn 📌 để ghim vào Glossary vĩnh viễn
    pinned = tc.pinTermToGlossary("妖魔王", "ác quỷ")
    assert pinned is True
    assert proj_ctrl.glossary.get("妖魔王") is not None
    assert proj_ctrl.glossary.get("妖魔王").preferred_translation == "ác quỷ"

    # Sau khi ghim, term chuyển sang is_glossary = True và không bị trùng lặp
    terms_after = tc.currentAppliedTerms
    assert len(terms_after) == 2
    hit_pinned = next(t for t in terms_after if t["source"] == "妖魔王")
    assert hit_pinned["is_glossary"] is True


def test_extract_terms_for_subtitle_on_demand():
    model = SubtitleModel()
    model.load_data([
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:03,000",
            "original": "妖魔王",
            "translation": "Ma Vương\n[TỪ GỐC]\n- 妖魔王 -> Ma Vương",
            "status": "ACCEPTED",
        }
    ])

    proj_ctrl = ProjectController(model)
    tc = TranslationController(model)
    tc.bind_intelligence(
        glossary=proj_ctrl.glossary,
        entities=proj_ctrl.entity_dictionary,
        translation_memory=proj_ctrl.translation_memory,
        project_controller=proj_ctrl,
    )

    # Chạy trích xuất cho câu đã có sẵn
    tc.extractTermsForSubtitle(0)
    tc.loadSubtitle(0)
    terms = tc.currentAppliedTerms
    assert len(terms) == 1
    assert terms[0]["source"] == "妖魔王"
    assert terms[0]["target"] == "Ma Vương"


def test_rogue_vocab_leakage_shield():
    """Kiểm tra lá chắn siêu phòng vệ triệt tiêu hoàn toàn rò rỉ rác (-Tu goc->, -从根源->)."""
    model = SubtitleModel()
    tc = TranslationController(model)

    rogue_output = (
        "LÀ ĐÃ TÌM THẤY NGƯƠI RỐT CUỘC\n"
        "-Tu goc-> 文 -> nghia la\n"
        "-从根源->ai -> người"
    )
    # Lá chắn worker
    clean_worker = TranslationWorker._visible_translation(rogue_output)
    assert clean_worker == "LÀ ĐÃ TÌM THẤY NGƯƠI RỐT CUỘC"

    # Lá chắn controller
    clean_ctrl = tc._clean_translated_text(rogue_output)
    assert clean_ctrl == "LÀ ĐÃ TÌM THẤY NGƯƠI RỐT CUỘC"


def test_translation_progress_tracking():
    """Kiểm tra tiến độ dịch % cập nhật chính xác từ 10% -> dynamic % -> 100%."""
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "start_time": "00:00:01,000", "end_time": "00:00:03,000", "original": "妖魔王やっと見つけたわ", "translation": "", "status": "PENDING"}
    ])
    tc = TranslationController(model)
    tc.loadSubtitle(0)
    assert tc.translationProgress == 0

    tc._active_translation_index = 0
    tc._current_original = "妖魔王やっと見つけたわ"
    tc._translation_progress = 10
    tc.translationProgressChanged.emit(10)
    assert tc.translationProgress == 10

    # Giả lập streaming progress
    tc.on_progress(0, "LÀ ĐÃ TÌM THẤY")
    assert 15 <= tc.translationProgress <= 95

    # Giả lập hoàn tất
    tc.on_finished(0, "LÀ ĐÃ TÌM THẤY NGƯƠI RỐT CUỘC")
    assert tc.translationProgress == 100


def test_prompt_builder_translation_and_auto_terms_pipeline():
    """Kiểm tra luồng 1 (Translation Pipeline): PromptBuilder yêu cầu bản dịch + khối [TỪ GỐC]."""
    from core.translation.core.prompt_builder import PromptBuilder
    prompt = PromptBuilder.build(
        story_summary="Chiến tranh Ma Vương",
        source_lang="Japanese",
        target_lang="Vietnamese",
        current_sub="妖魔王やっと見つけたわ",
    )
    assert "[TỪ GỐC]" in prompt
    assert "- original_term -> meaning" in prompt
    assert "STRICT OUTPUT FORMAT" in prompt


def test_original_updated_signal_isolation_during_streaming():
    """Kiểm tra tín hiệu originalUpdated độc lập, không bị kích hoạt trong lúc stream bản dịch."""
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "start_time": "00:00:01,000", "end_time": "00:00:03,000", "original": "妖魔王やっと見つけたわ", "translation": "", "status": "PENDING"}
    ])
    tc = TranslationController(model)

    orig_emits = []
    trans_emits = []
    tc.originalUpdated.connect(lambda s: orig_emits.append(s))
    tc.translationUpdated.connect(lambda s: trans_emits.append(s))

    # 1. loadSubtitle: Cả originalUpdated và translationUpdated đều phát
    tc.loadSubtitle(0)
    assert len(orig_emits) == 1
    assert orig_emits[-1] == "妖魔王やっと見つけたわ"
    assert tc.currentOriginal == "妖魔王やっと見つけたわ"

    # 2. Streaming chunks (on_progress): CHỈ translationUpdated phát, originalUpdated đứng yên tuyệt đối
    orig_count_before = len(orig_emits)
    tc._active_translation_index = 0
    for chunk in ["Cuối", "Cuối cùng", "Cuối cùng đã tìm thấy", "Cuối cùng đã tìm thấy ngươi"]:
        tc.on_progress(0, chunk)

    assert len(orig_emits) == orig_count_before  # originalUpdated đứng yên tuyệt đối!
    assert len(trans_emits) >= 4  # translationUpdated phát đều đặn theo token


def test_bi_directional_unpin_architecture():
    """Kiểm tra cơ chế bỏ ghim hai chiều giữa TranslationWorkspace và ContextInspector."""
    model = SubtitleModel()
    model.load_data([
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:03,000",
            "original": "妖魔王やっと見つけたわ",
            "translation": "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương",
            "status": "TRANSLATED",
            "auto_terms": [
                {"source": "妖魔王", "target": "Ma vương"},
                {"source": "やっと", "target": "cuối cùng"}
            ]
        }
    ])

    proj_ctrl = ProjectController(model)
    tc = TranslationController(model)
    tc.bind_intelligence(
        glossary=proj_ctrl.glossary,
        entities=proj_ctrl.entity_dictionary,
        translation_memory=proj_ctrl.translation_memory,
        project_controller=proj_ctrl,
    )

    tc.loadSubtitle(0)
    # Ban đầu: cả 2 terms đều là auto_terms (is_glossary = False)
    terms = tc.currentAppliedTerms
    assert len(terms) == 2
    assert terms[0]["source"] == "妖魔王"
    assert terms[0]["is_glossary"] is False

    # 1. Ghim từ Workspace: pinTermToGlossary
    pinned = tc.pinTermToGlossary("妖魔王", "Ma vương")
    assert pinned is True
    assert any(item["source_term"] == "妖魔王" for item in proj_ctrl.glossaryTerms)
    terms_pinned = tc.currentAppliedTerms
    term_ymw = next(t for t in terms_pinned if t["source"] == "妖魔王")
    assert term_ymw["is_glossary"] is True

    # 2. Bỏ ghim từ Workspace: unpinTermFromGlossary
    unpinned = tc.unpinTermFromGlossary("妖魔王")
    assert unpinned is True
    assert not any(item["source_term"] == "妖魔王" for item in proj_ctrl.glossaryTerms)
    terms_unpinned = tc.currentAppliedTerms
    term_ymw_reverted = next(t for t in terms_unpinned if t["source"] == "妖魔王")
    assert term_ymw_reverted["is_glossary"] is False  # Tự động trở lại trạng thái auto_term chưa ghim

    # 3. Bỏ ghim từ Intelligence Tab (ProjectController.removeGlossaryTerm)
    tc.pinTermToGlossary("妖魔王", "Ma vương")
    assert any(item["source_term"] == "妖魔王" for item in proj_ctrl.glossaryTerms)
    assert next(t for t in tc.currentAppliedTerms if t["source"] == "妖魔王")["is_glossary"] is True

    removed = proj_ctrl.removeGlossaryTerm("妖魔王")
    assert removed is True
    assert not any(item["source_term"] == "妖魔王" for item in proj_ctrl.glossaryTerms)
    # Thẻ chip ở Workspace tự động đồng bộ về is_glossary: False
    terms_after_intel_remove = tc.currentAppliedTerms
    assert next(t for t in terms_after_intel_remove if t["source"] == "妖魔王")["is_glossary"] is False


def test_settings_singleton_and_anti_overwrite_between_controllers(tmp_path):
    """Kiểm tra chống ghi đè dữ liệu chéo (Race Condition / Split-Brain) giữa ProjectController và ModelController."""
    import json
    from core.translation.controllers.model_controller import ModelController

    settings_file = str(tmp_path / "app_settings.json")
    s_proj = AppSettings(file_path=settings_file)
    s_model = AppSettings(file_path=settings_file)
    assert s_proj is s_model  # Cùng trỏ vào 1 singleton instance

    dummy_model_file = tmp_path / "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
    dummy_model_file.write_bytes(b"dummy")

    model = SubtitleModel()
    pc = ProjectController(model, settings=s_proj)
    mc = ModelController(models_dir=str(tmp_path), settings=s_model)

    # 1. ModelController chọn model Llama 3.1
    mc.selectActiveModel("llama-3.1-8b-instruct-q4_k_m")
    assert s_model.active_model_id == "llama-3.1-8b-instruct-q4_k_m"
    assert s_proj.active_model_id == "llama-3.1-8b-instruct-q4_k_m"

    # 2. ProjectController ghi file recent
    dummy_srt = tmp_path / "test.srt"
    dummy_srt.write_text("dummy", encoding="utf-8")
    pc._add_recent_file(str(dummy_srt))

    # 3. Đọc trực tiếp từ đĩa: active_model_id vẫn phải nguyên vẹn là llama 3.1
    with open(settings_file, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["active_model_id"] == "llama-3.1-8b-instruct-q4_k_m"
    assert any("test.srt" in f for f in disk_data["recent_files"])

    # 4. Tạo instance mới sau khi xóa cache bộ nhớ: không bị reset về mặc định
    AppSettings._instances.clear()
    s_reloaded = AppSettings(file_path=settings_file)
    assert s_reloaded.active_model_id == "llama-3.1-8b-instruct-q4_k_m"


def test_deepseek_r1_reasoning_shield_and_stop_tokens():
    """Kiểm tra triệt tiêu rò rỉ suy luận (Chain of Thought / Monologue) của DeepSeek R1."""
    # 1. Output có thẻ </think>
    r1_output = (
        "Wait, let's think carefully about this sentence.\n"
        "The Japanese is: 身も心もすべてを捧げるためです\n"
        "So it means to dedicate both body and soul.\n"
        "</think>\n"
        "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn.\n"
        "[TỪ GỐC]\n"
        "- 捧げる -> dâng hiến"
    )
    clean_display = TranslationWorker._visible_translation(r1_output)
    assert clean_display == "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."

    clean_ctrl = TranslationController._clean_translated_text(r1_output)
    assert clean_ctrl == "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."

    # 2. Output độc thoại thô khi bị cấm thẻ <think>
    r1_raw_monologue = (
        "Wait, that can't be right. Let's think carefully.\n"
        "Final output: Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."
    )
    assert TranslationWorker._visible_translation(r1_raw_monologue) == "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."
    assert TranslationController._clean_translated_text(r1_raw_monologue) == "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."

    # 3. Output prompt echo
    r1_echo = (
        "--- CURRENT SUBTITLE TO TRANSLATE ---\n"
        "身も心もすべてを捧げるためです\n"
        "--- Output ---\n"
        "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."
    )
    assert TranslationWorker._visible_translation(r1_echo) == "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."
    assert TranslationController._clean_translated_text(r1_echo) == "Để dâng hiến trọn vẹn cả thể xác lẫn tâm hồn."





