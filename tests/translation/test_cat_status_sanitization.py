# -*- coding: utf-8 -*-
"""
Tests for CAT Studio Status Sanitization (PLAN-CAT-TRANSLATE-BUTTON-RESTORE-001).
Ensures subtitle status in SubtitleModel and TranslationController is strictly
within {"PENDING", "TRANSLATING", "TRANSLATED", "EDITED", "ACCEPTED", "ERROR"}
and never contaminated by timeline/ASR statuses ("draft", "final", "timing_only").
"""
import pytest
from core.translation.models.subtitle import SubtitleModel
from ui.pages.translation_studio_page import TranslationStudioPage


def test_load_subtitles_from_studio_sanitizes_draft_status():
    """Segment co status='draft' khi nap phai tro thanh 'PENDING'."""
    page = TranslationStudioPage()
    studio_segments = [
        {
            "id": "seg_001",
            "stt": 1,
            "start": 1000,
            "end": 2000,
            "text": "Kon'nichiwa",
            "original_text": "Kon'nichiwa",
            "status": "draft",
            "translation_status": None,
            "translation": "",
        }
    ]
    page.load_subtitles_from_studio(studio_segments, selected_indices=None)

    assert page.subtitle_model.rowCount() == 1
    item = page.subtitle_model.get_item(0)
    assert item["status"] == "PENDING", f"Expected PENDING, got {item['status']}"
    assert page.translation_controller.status == "PENDING"


def test_load_subtitles_from_studio_sanitizes_final_status():
    """Segment co status='final' khi nap phai tro thanh 'PENDING'."""
    page = TranslationStudioPage()
    studio_segments = [
        {
            "id": "seg_002",
            "stt": 1,
            "start": 1000,
            "end": 2000,
            "text": "Arigatou",
            "original_text": "Arigatou",
            "status": "final",
            "translation_status": None,
            "translation": "",
        }
    ]
    page.load_subtitles_from_studio(studio_segments, selected_indices=None)

    assert page.subtitle_model.rowCount() == 1
    item = page.subtitle_model.get_item(0)
    assert item["status"] == "PENDING", f"Expected PENDING, got {item['status']}"
    assert page.translation_controller.status == "PENDING"


def test_load_subtitles_from_studio_with_existing_translation():
    """Segment co status='draft' nhung da co ban dich phai thanh 'TRANSLATED'."""
    page = TranslationStudioPage()
    studio_segments = [
        {
            "id": "seg_003",
            "stt": 1,
            "start": 1000,
            "end": 2000,
            "text": "Sayonara",
            "original_text": "Sayonara",
            "status": "draft",
            "translation_status": None,
            "translation": "Tạm biệt",
        }
    ]
    page.load_subtitles_from_studio(studio_segments, selected_indices=None)

    assert page.subtitle_model.rowCount() == 1
    item = page.subtitle_model.get_item(0)
    assert item["status"] == "TRANSLATED", f"Expected TRANSLATED, got {item['status']}"
    assert page.translation_controller.status == "TRANSLATED"


def test_subtitle_model_load_data_sanitizes_arbitrary_status():
    """SubtitleModel phai tu dong chuan hoa moi status bat thuong ve tap hop hop le."""
    model = SubtitleModel()
    test_data = [
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:02,000",
            "original": "Test 1",
            "translation": "",
            "status": "draft",
        },
        {
            "index": 2,
            "start_time": "00:00:03,000",
            "end_time": "00:00:04,000",
            "original": "Test 2",
            "translation": "Bản dịch 2",
            "status": "timing_only",
        },
        {
            "index": 3,
            "start_time": "00:00:05,000",
            "end_time": "00:00:06,000",
            "original": "Test 3",
            "translation": "",
            "status": "UNKNOWN_CUSTOM_STATUS",
        },
    ]
    model.load_data(test_data)

    assert model.get_item(0)["status"] == "PENDING"
    assert model.get_item(1)["status"] == "TRANSLATED"
    assert model.get_item(2)["status"] == "PENDING"
