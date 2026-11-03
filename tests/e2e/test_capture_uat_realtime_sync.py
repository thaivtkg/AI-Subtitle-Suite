# -*- coding: utf-8 -*-
"""
UAT Acceptance Visual Verification for DEV-SPEC-REALTIME-STRUCTURAL-SYNC-001.
Captures real-time split and merge operations across Studio and CAT Studio.
"""
import os
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

ARTIFACT_DIR = r"C:\Users\Kuroberus\.gemini\antigravity\brain\bc09a4cd-ebe2-4025-ac00-5b4d8c23e82d"


def test_uat_realtime_split_merge_sync(live_studio_app):
    win, watcher, runner = live_studio_app
    win.resize(1366, 768)
    QTest.qWait(300)

    # 1. Setup realistic subtitle project matching the user's video timeline
    segments = [
        {"id": "seg_1", "stt": "1", "start": "00:00:15,199", "end": "00:00:17,339", "start_ms": 15199, "end_ms": 17339, "text": "妖魔王、やっと見つけたわ。", "original_text": "妖魔王、やっと見つけたわ。", "translation": "Yêu ma vương, cuối cùng cũng tìm thấy ngươi rồi."},
        {"id": "seg_2", "stt": "2", "start": "00:00:19,579", "end": "00:00:20,719", "start_ms": 19579, "end_ms": 20719, "text": "お前は誰だ？", "original_text": "お前は誰だ？", "translation": "Ngươi là ai?"},
        {"id": "seg_3", "stt": "3", "start": "00:00:21,539", "end": "00:00:22,839", "start_ms": 21539, "end_ms": 22839, "text": "忘れたのかしら？", "original_text": "忘れたのかしら？", "translation": "Ngươi quên ta rồi sao?"},
        {"id": "seg_4", "stt": "4", "start": "00:00:23,579", "end": "00:00:24,519", "start_ms": 23579, "end_ms": 24519, "text": "セーラーエンジェル！", "original_text": "セーラーエンジェル！", "translation": "Sailor Angel!"},
        {"id": "seg_5", "stt": "5", "start": "00:00:28,179", "end": "00:00:29,339", "start_ms": 28179, "end_ms": 29339, "text": "確かにそうだ。", "original_text": "確かにそうだ。", "translation": "Đúng là như vậy rồi."},
        {"id": "seg_6", "stt": "6", "start": "00:00:33,960", "end": "00:00:37,070", "start_ms": 33960, "end_ms": 37070, "text": "この俺様に 一体何の用だ？", "original_text": "この俺様に 一体何の用だ？", "translation": "Đến gặp bổn vương đây thì có việc gì?"},
        {"id": "seg_7", "stt": "7", "start": "00:00:37,820", "end": "00:00:39,500", "start_ms": 37820, "end_ms": 39500, "text": "それはもう決まってるでしょ。", "original_text": "それはもう決まってるでしょ。", "translation": "Chuyện đó chẳng phải đã rõ rồi sao."},
    ]

    duration_ms = 45000
    win.sub_editor.all_segments = segments
    win.sub_editor.render_page()

    win.timeline_data_provider.load_runtime_data(win.sub_editor.all_segments, duration_ms)
    win.timeline_widget.load_project_data(
        duration_ms,
        win.timeline_data_provider.get_all_segments(),
        None
    )

    track = win.timeline_widget.container.track
    track.set_zoom(65)

    # 2. Nạp phụ đề sang CAT Studio để cả 2 bên cùng lưu giữ câu #6 và #7
    win.page_translation.load_subtitles_from_studio(win.sub_editor.all_segments)
    cat_model = win.page_translation.subtitle_model
    assert cat_model.rowCount() == 7
    QTest.qWait(300)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    # UAT BƯỚC 1: Chụp ảnh hiện trạng ban đầu
    win.switch_page(1) # Studio
    win.timeline_widget.update_playhead(35500)
    win.sub_editor.select_segment(5)
    QTest.qWait(200)
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_01_studio_initial.png"))

    win.switch_page(8) # CAT Studio
    QTest.qWait(200)
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_01_cat_initial.png"))

    # UAT BƯỚC 2: Thực hiện Cắt câu #6 tại 35,500ms ngay trên Studio
    win.switch_page(1)
    win.timeline_widget.update_playhead(35500)
    win.sub_editor.select_segment(5)
    win.sub_editor.trigger_split(35500)
    QTest.qWait(300)

    # Kiểm tra Studio đã tách thành 8 câu
    assert len(win.sub_editor.all_segments) == 8
    assert win.sub_editor.all_segments[5]["text"] == "この俺様に"
    assert win.sub_editor.all_segments[6]["text"] == "一体何の用だ？"
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_02_studio_after_split.png"))

    # Kiểm tra CAT Studio TỰ ĐỘNG TÁCH REALTIME thành 8 câu
    assert cat_model.rowCount() == 8
    item5 = cat_model.get_item(5)
    item6 = cat_model.get_item(6)
    assert item5["original"] == "この俺様に"
    assert item5["status"] == "PENDING"
    assert item6["original"] == "一体何の用だ？"
    assert item6["status"] == "PENDING"
    assert item6["index"] == 7

    win.switch_page(8)
    QTest.qWait(200)
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_02_cat_after_split.png"))

    # UAT BƯỚC 3: Hoàn tác Cắt (Undo Ctrl+Z)
    win.switch_page(1)
    win.undo_manager.undo()
    QTest.qWait(300)

    # Kiểm tra Studio phục hồi 7 câu
    assert len(win.sub_editor.all_segments) == 7
    assert cat_model.rowCount() == 7
    restored_item5 = cat_model.get_item(5)
    assert restored_item5["original"] == "この俺様に 一体何の用だ？"
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_03_studio_after_undo_split.png"))

    # UAT BƯỚC 4: Gộp câu #6 và câu #7 (Merge)
    win.sub_editor.select_segment(5)
    win.sub_editor.trigger_merge()
    QTest.qWait(300)

    # Kiểm tra Studio giảm còn 6 câu
    assert len(win.sub_editor.all_segments) == 6
    merged_seg = win.sub_editor.all_segments[5]
    assert "この俺様に 一体何の用だ？" in merged_seg["text"]
    assert "それはもう決まってるでしょ。" in merged_seg["text"]
    assert "Đến gặp bổn vương đây thì có việc gì?" in merged_seg["translation"]
    assert "Chuyện đó chẳng phải đã rõ rồi sao." in merged_seg["translation"]
    assert merged_seg["translation_status"] == "EDITED"
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_04_studio_after_merge.png"))

    # Kiểm tra CAT Studio TỰ ĐỘNG GỘP REALTIME thành 6 câu
    assert cat_model.rowCount() == 6
    cat_merged = cat_model.get_item(5)
    assert "この俺様に 一体何の用だ？" in cat_merged["original"]
    assert "それはもう決まってるでしょ。" in cat_merged["original"]
    assert "Đến gặp bổn vương đây thì có việc gì?" in cat_merged["translation"]
    assert "Chuyện đó chẳng phải đã rõ rồi sao." in cat_merged["translation"]

    win.switch_page(8)
    QTest.qWait(200)
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_04_cat_after_merge.png"))

    # UAT BƯỚC 5: Hoàn tác Gộp (Undo Ctrl+Z)
    win.switch_page(1)
    win.undo_manager.undo()
    QTest.qWait(300)

    assert len(win.sub_editor.all_segments) == 7
    assert cat_model.rowCount() == 7
    win.grab().save(os.path.join(ARTIFACT_DIR, "uat_05_studio_after_undo_merge.png"))

