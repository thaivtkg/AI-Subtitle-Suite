# -*- coding: utf-8 -*-
"""
Chụp ảnh thực tế thao tác Cắt Subtitle (Split) trên ứng dụng Desktop AI Subtitle Suite.
Lưu ảnh trực tiếp vào thư mục artifact để báo cáo cho người dùng.
"""
import os
import pytest
from PIL import Image
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtTest import QTest

ARTIFACT_DIR = os.environ.get(
    "AI_SUBTITLE_ARTIFACT_DIR",
    r"C:\Users\Kuroberus\.gemini\antigravity\brain\d7d2d74d-59ec-4d54-8751-7d91438bdf1d"
)


def test_capture_real_split_screenshots(live_studio_app):
    win, watcher, runner = live_studio_app
    win.resize(1366, 768)
    QTest.qWait(200)

    # 1. Chuẩn bị dữ liệu phụ đề thực tế (Anime JA từ project của người dùng)
    segments = [
        {"id": "seg_1", "stt": "1", "start": "00:00:15,199", "end": "00:00:17,339", "start_ms": 15199, "end_ms": 17339, "text": "妖魔王、やっと見つけたわ。", "translation": "Yêu ma vương, cuối cùng cũng tìm thấy ngươi rồi."},
        {"id": "seg_2", "stt": "2", "start": "00:00:19,579", "end": "00:00:20,719", "start_ms": 19579, "end_ms": 20719, "text": "お前は誰だ？", "translation": "Ngươi là ai?"},
        {"id": "seg_3", "stt": "3", "start": "00:00:21,539", "end": "00:00:22,839", "start_ms": 21539, "end_ms": 22839, "text": "忘れたのかしら？", "translation": "Ngươi quên ta rồi sao?"},
        {"id": "seg_4", "stt": "4", "start": "00:00:23,579", "end": "00:00:24,519", "start_ms": 23579, "end_ms": 24519, "text": "セーラーエンジェル！", "translation": "Sailor Angel!"},
        {"id": "seg_5", "stt": "5", "start": "00:00:28,179", "end": "00:00:29,339", "start_ms": 28179, "end_ms": 29339, "text": "確かにそうだ。", "translation": "Đúng là như vậy rồi."},
        {"id": "seg_6", "stt": "6", "start": "00:00:33,960", "end": "00:00:37,070", "start_ms": 33960, "end_ms": 37070, "text": "この俺様に 一体何の用だ？", "translation": "Đến gặp bổn vương đây thì có việc gì?"},
        {"id": "seg_7", "stt": "7", "start": "00:00:37,820", "end": "00:00:38,920", "start_ms": 37820, "end_ms": 38920, "text": "それはもう決まってるでしょ。", "translation": "Chuyện đó chẳng phải đã rõ rồi sao."},
    ]

    duration_ms = 45000 # 45 giây
    win.sub_editor.all_segments = segments
    win.sub_editor.render_page()

    win.timeline_data_provider.load_runtime_data(win.sub_editor.all_segments, duration_ms)
    win.timeline_widget.load_project_data(
        duration_ms,
        win.timeline_data_provider.get_all_segments(),
        None
    )

    # Đặt zoom timeline để khối hiển thị rõ ràng dễ đọc (~70 pixel / giây)
    track = win.timeline_widget.container.track
    track.set_zoom(70)

    # Đưa kim thời gian đến giữa câu #006: 35,500ms
    split_point_ms = 35500
    win.timeline_widget.update_playhead(split_point_ms)
    win.video_player.position_changed(split_point_ms)
    win.sub_editor.select_segment(5) # Chọn câu #006
    QTest.qWait(300)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    # --- ẢNH 1: Toàn cảnh trước khi cắt ---
    path_before_full = os.path.join(ARTIFACT_DIR, "split_before_full.png")
    win.grab().save(path_before_full)

    # --- ẢNH 2: Cận cảnh Timeline Widget trước khi cắt ---
    path_tl_before = os.path.join(ARTIFACT_DIR, "split_timeline_before.png")
    win.timeline_widget.grab().save(path_tl_before)

    path_track_before = os.path.join(ARTIFACT_DIR, "split_track_before.png")
    track.grab().save(path_track_before)

    # ========================================================
    # THỰC HIỆN CẮT SUBTITLE TẠI VỊ TRÍ 35,500ms (Split / Ctrl+K)
    # ========================================================
    win.sub_editor.trigger_split(split_point_ms)

    # Đồng bộ sang Timeline và Video Player
    win.timeline_data_provider.load_runtime_data(win.sub_editor.all_segments, duration_ms)
    win.timeline_widget.load_project_data(
        duration_ms,
        win.timeline_data_provider.get_all_segments(),
        None
    )
    win.timeline_widget.update_playhead(split_point_ms)
    win.video_player.position_changed(split_point_ms)
    win.sub_editor.render_page()
    QTest.qWait(400)

    # --- ẢNH 3: Toàn cảnh sau khi cắt ---
    path_after_full = os.path.join(ARTIFACT_DIR, "split_after_full.png")
    win.grab().save(path_after_full)

    # --- ẢNH 4: Cận cảnh Timeline Widget sau khi cắt ---
    path_tl_after = os.path.join(ARTIFACT_DIR, "split_timeline_after.png")
    win.timeline_widget.grab().save(path_tl_after)

    # --- ẢNH 4B: Cận cảnh Track (Thanh phụ đề) sau khi cắt ---
    path_track_after = os.path.join(ARTIFACT_DIR, "split_track_after.png")
    track.grab().save(path_track_after)

    # --- ẢNH 5: Cận cảnh Bảng SubEditor (danh sách câu #006 và #007) ---
    path_table = os.path.join(ARTIFACT_DIR, "split_subeditor_table.png")
    win.sub_editor.table.grab().save(path_table)

    # --- ẢNH 6: Cận cảnh Video Player (Overlay hiển thị 1 câu duy nhất) ---
    path_player = os.path.join(ARTIFACT_DIR, "split_video_overlay.png")
    win.video_player.grab().save(path_player)

    # Crop cận cảnh vùng cắt trước và sau
    im_b = Image.open(path_track_before)
    im_a = Image.open(path_track_after)
    crop_b = im_b.crop((2800, 0, 3450, 63))
    crop_a = im_a.crop((2800, 0, 3450, 63))
    crop_b.save(os.path.join(ARTIFACT_DIR, "split_track_zoom_before.png"))
    crop_a.save(os.path.join(ARTIFACT_DIR, "split_track_zoom_after.png"))

    # Assertions để đảm bảo dữ liệu đúng
    assert len(win.sub_editor.all_segments) == 8, "Cắt 1 câu từ 7 câu phải thành 8 câu"
    seg6 = win.sub_editor.all_segments[5]
    seg7 = win.sub_editor.all_segments[6]
    assert seg6["end_ms"] == split_point_ms
    assert seg7["start_ms"] == split_point_ms
    assert seg6["end_ms"] <= seg7["start_ms"], "Không được chồng lấn thời gian"
    print("\n[SUCCESS] Đã chụp và lưu thành công tất cả ảnh thực tế vào Artifacts directory!")
