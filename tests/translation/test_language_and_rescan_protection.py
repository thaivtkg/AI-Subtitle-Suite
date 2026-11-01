import pytest
from unittest.mock import MagicMock, patch

from core.translation.models.subtitle import SubtitleModel
from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.context_analyzer import ContextAnalyzer
from ui.pages.translation_studio_page import TranslationStudioPage
from ui.Gui import MainWindow


def test_context_analyzer_detect_native_language():
    assert ContextAnalyzer.detect_native_language("お前はもう死んでいる") == "Japanese"
    assert ContextAnalyzer.detect_native_language("안녕하세요") == "Korean"
    assert ContextAnalyzer.detect_native_language("你吃了没有") == "Chinese (Simplified)"
    assert ContextAnalyzer.detect_native_language("Chào bạn, hôm nay thế nào?") == "Vietnamese"
    assert ContextAnalyzer.detect_native_language("Hello world, this is English.") == "English"
    assert ContextAnalyzer.detect_native_language("") == "English"


def test_translation_controller_language_detection():
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "original": "こんにちは", "translation": "", "status": "PENDING"},
        {"index": 2, "original": "Hello friend", "translation": "", "status": "PENDING"},
        {"index": 3, "original": "안녕하세요", "translation": "", "status": "PENDING"},
    ])
    controller = TranslationController(model)
    assert controller.currentSourceLanguage == "English"

    # Load Japanese subtitle
    controller.loadSubtitle(0)
    assert controller.currentSourceLanguage == "Japanese"

    # Load English subtitle
    controller.loadSubtitle(1)
    assert controller.currentSourceLanguage == "English"

    # Load Korean subtitle
    controller.loadSubtitle(2)
    assert controller.currentSourceLanguage == "Korean"

    # Reset
    controller.loadSubtitle(-1)
    assert controller.currentSourceLanguage == "English"


def test_translation_controller_request_translation_prompt_alignment():
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "original": "おはようございます", "translation": "", "status": "PENDING"},
    ])
    
    mock_worker = MagicMock()
    mock_factory = MagicMock(return_value=mock_worker)
    
    controller = TranslationController(model, worker_factory=mock_factory)
    controller.loadSubtitle(0)
    assert controller.currentSourceLanguage == "Japanese"

    with patch("core.translation.controllers.translation_controller.PromptBuilder.build") as mock_build:
        # UI passed source_lang="English" by default, but currentSourceLanguage is Japanese
        controller.requestTranslation(0, "English", "Vietnamese", "Summary")
        
        # Verify PromptBuilder.build received "Japanese" as source_lang
        assert mock_build.called
        args, kwargs = mock_build.call_args
        # PromptBuilder.build signature: (story_summary, source_lang, target_lang, ...)
        passed_source_lang = args[1]
        assert passed_source_lang == "Japanese"


def test_translation_studio_page_load_and_rescan_update():
    page = TranslationStudioPage()
    
    studio_segments = [
        {"id": "seg_101", "stt": 1, "start": 1000, "end": 2000, "text": "おはよう", "original_text": "おはよう", "translation": ""},
        {"id": "seg_102", "stt": 2, "start": 3000, "end": 4000, "text": "さようなら", "original_text": "さようなら", "translation": ""},
    ]
    
    # 1. Load subtitles from studio
    page.load_subtitles_from_studio(studio_segments)
    data = page.subtitle_model.get_all_data()
    assert len(data) == 2
    assert data[0]["segment_id"] == "seg_101"
    assert data[1]["segment_id"] == "seg_102"
    # Project controller language should be auto-detected as Japanese
    assert page.project_controller._source_language == "Japanese"
    assert page.translation_controller.currentSourceLanguage == "Japanese"

    # Simulate translation done
    page.subtitle_model.update_translation(0, "Chào buổi sáng", "TRANSLATED")
    assert page.subtitle_model.get_all_data()[0]["translation"] == "Chào buổi sáng"
    assert page.subtitle_model.get_all_data()[0]["status"] == "TRANSLATED"

    # 2. Rescan audio for seg_101 with new speech
    page.update_segment_source("seg_101", "こんにちは世界")
    data_after = page.subtitle_model.get_all_data()
    assert data_after[0]["original"] == "こんにちは世界"
    assert data_after[0]["translation"] == ""
    assert data_after[0]["status"] == "PENDING"


def test_export_subtitles_to_studio_overwrite_protection():
    page = TranslationStudioPage()
    
    studio_segments = [
        {
            "id": "seg_1",
            "stt": 1,
            "start": 1000,
            "end": 2000,
            "text": "Old translation",
            "original_text": "Original text A",
            "translation": "Old translation",
            "translation_status": "TRANSLATED",
        },
        {
            "id": "seg_2",
            "stt": 2,
            "start": 3000,
            "end": 4000,
            "text": "Original text B",
            "original_text": "Original text B",
            "translation": "",
            "translation_status": "PENDING",
        }
    ]
    
    page.load_subtitles_from_studio(studio_segments)
    
    # In CAT studio, translate seg_1 and seg_2
    page.subtitle_model.update_translation(0, "New Translation A", "TRANSLATED")
    page.subtitle_model.update_translation(1, "New Translation B", "TRANSLATED")

    # Now simulate: Timeline seg_1 has been re-scanned in Studio with new audio!
    # original_text was updated to "Rescanned text A2"
    studio_segments[0]["original_text"] = "Rescanned text A2"
    studio_segments[0]["text"] = "Rescanned text A2"
    studio_segments[0]["translation"] = ""
    studio_segments[0]["translation_status"] = "PENDING"

    # Export CAT translations back to studio
    page.export_subtitles_to_studio(studio_segments)

    # seg_1 should be protected against overwrite by stale translation!
    assert studio_segments[0]["text"] == "Rescanned text A2"
    assert studio_segments[0]["translation"] == ""
    assert studio_segments[0]["translation_status"] == "PENDING"

    # seg_2 should be updated with new translation
    assert studio_segments[1]["translation"] == "New Translation B"
    assert studio_segments[1]["text"] == "New Translation B"
    assert studio_segments[1]["translation_status"] == "TRANSLATED"


def test_gui_segment_scan_finished_invalidation(qapp):
    win = MainWindow()
    try:
        win.sub_editor.all_segments = [
            {
                "id": "seg_scan_1",
                "stt": "1",
                "start": "00:00:01,000",
                "end": "00:00:04,000",
                "text": "Bản dịch cũ",
                "original_text": "Old Audio Text",
                "translation": "Bản dịch cũ",
                "translation_status": "TRANSLATED",
            }
        ]
        mock_page = MagicMock()
        win.page_translation = mock_page

        win._on_segment_scan_finished("seg_scan_1", "New Audio Text")

        seg = win.sub_editor.all_segments[0]
        assert seg["text"] == "New Audio Text"
        assert seg["original_text"] == "New Audio Text"
        assert seg["translation"] == ""
        assert seg["translation_status"] == "PENDING"
        mock_page.update_segment_source.assert_called_once_with("seg_scan_1", "New Audio Text")
    finally:
        try:
            if hasattr(win, "video_player") and hasattr(win.video_player, "cleanup"):
                win.video_player.cleanup()
        except Exception:
            pass
        win.close()
        win.deleteLater()
