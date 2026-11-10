# -*- coding: utf-8 -*-
"""
tests/ui/test_real_jmsz_project.py
Kiểm thử pháp y thực tế trực tiếp trên dự án: D:\Projects\JMSZ.ai-subtitle
File video: D:\Projects\Video\JMSZ38_02.wmv
Phụ đề: D:\Projects\JMSZ.ai-subtitle\artifacts\timing\JMSZ_timing.srt

Mục tiêu kiểm định:
1. Nạp thành công toàn bộ dự án JMSZ.ai-subtitle (24 câu phụ đề, video WMV2 29m24s).
2. Tái hiện thao tác trong Bugsubtitle.mp4:
   - Điểm tua 21,800ms (nằm trong gap 1.19s giữa câu #2 và #3).
   - Điểm tua 22,500ms (nằm giữa câu #3: 21,850ms - 24,650ms).
   - Kiểm tra: Kim đỏ và player.position() PHẢI GIỮ NGUYÊN mốc chọn, KHÔNG BỊ GIẬT về 21,850ms.
3. Nhấn Space: Playback bắt đầu từ đúng vị trí người dùng đã chọn.
4. Kiểm tra dịch vụ Auto-Transcode nhận diện JMSZ38_02.wmv là container cần tối ưu Fast-Seek.
"""

import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from tests.gui.conftest import timeline_driver
from core.subtitle_editing.selection_controller import SelectionSource
from core.video.transcode_service import (
    is_transcode_needed,
    get_transcode_cache_path,
    get_cached_transcode,
)

PROJECT_DIR = r"D:\Projects\JMSZ.ai-subtitle"
VIDEO_PATH = r"D:\Projects\Video\JMSZ38_02.wmv"
SRT_PATH = r"D:\Projects\JMSZ.ai-subtitle\artifacts\timing\JMSZ_timing.srt"


def test_jmsz_real_project_loading_and_subtitles(timeline_driver, qtbot):
    """Xác minh nạp đầy đủ dự án JMSZ.ai-subtitle và 24 câu phụ đề."""
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    win.activateWindow()
    qtbot.wait(100)

    # 1. Nạp file phụ đề thật của JMSZ
    assert os.path.exists(SRT_PATH), f"Không tìm thấy file phụ đề: {SRT_PATH}"
    win.video_player.load_video(VIDEO_PATH)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=10000)
    win._load_context_subtitles(SRT_PATH)
    qtbot.wait(200)

    # Dự án JMSZ có đúng 24 câu phụ đề
    assert len(win.sub_editor.all_segments) == 24, f"Mong đợi 24 câu, nhận {len(win.sub_editor.all_segments)}"

    # Kiểm tra câu #3: 21,850ms -> 24,650ms
    seg3 = win.sub_editor.all_segments[2]
    assert seg3["stt"] == "3" or seg3.get("id") == "3" or seg3.get("start_ms") == 21850
    assert seg3.get("start_ms") == 21850
    assert seg3.get("end_ms") == 24650
    assert "Sailor Angel" in seg3.get("text", "")


def test_jmsz_real_seek_preservation_inside_sub3(timeline_driver, qtbot):
    """
    Xác minh hiện tượng trong Bugsubtitle.mp4:
    Người dùng tua vào 22,500ms (nửa sau câu #3 [21,850ms - 24,650ms]).
    Trước fix: Kim đỏ và setPosition bị ép giật lùi về 21,850ms.
    Sau fix: Kim đỏ và player GIỮ NGUYÊN tại 22,500ms, Space phát từ 22,500ms.
    """
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    win.activateWindow()
    qtbot.wait(100)

    # Nạp phụ đề và video JMSZ
    win.video_player.load_video(VIDEO_PATH)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=10000)
    win.video_player.load_video(VIDEO_PATH)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=10000)
    win._load_context_subtitles(SRT_PATH)
    qtbot.wait(200)

    vp = win.video_player
    # Đặt duration ảo của video nếu video chưa kịp load đầy đủ duration từ đĩa
    vp._current_pos_ms = 0
    track = win.timeline_widget.container.track
    win.timeline_widget.set_duration(1765000)

    # Người dùng click Timeline tại 22,500ms
    target_ms = 22500
    target_x = (target_ms / 1000.0) * track.pixels_per_second
    win.timeline_controller._do_seek(target_x)
    qtbot.wait(150)

    # 1. Kiểm tra vị trí hiện tại
    current_ms = vp.get_current_time_ms()
    assert abs(current_ms - target_ms) <= 50, (
        f"LỖI TÁI HIỆN: Mong đợi ở mốc tua {target_ms}ms nhưng bị giật về {current_ms}ms!"
    )
    assert current_ms != 21850, "LỖI CƯỚP VỊ TRÍ: Player bị cưỡng chế giật về đầu câu #3 (start_ms=21850ms)!"

    # 2. Kiểm tra Kim đỏ trên Timeline
    playhead_ms = track.playhead_ms
    assert abs(playhead_ms - target_ms) <= 50, (
        f"LỖI KIM ĐỎ: Kim đỏ trên Timeline bị dịch về {playhead_ms}ms thay vì {target_ms}ms!"
    )

    # 3. Kiểm tra bounds tự do
    assert vp._segment_bounds is None, "LỖI BOUNDS: _segment_bounds không được giải phóng!"

    # 4. Nhấn phím Space: Phát video bình thường
    focused = QApplication.focusWidget() or win
    space_ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    handled = win.eventFilter(focused, space_ev)
    assert handled is True
    assert vp.player.isPlaying() is True


def test_jmsz_real_seek_in_gap_before_sub3(timeline_driver, qtbot):
    """
    Xác minh vị trí chính xác trong video Bugsubtitle.mp4:
    Người dùng đậu kim tại 21,800ms (trong khoảng trống gap 1.19s, trước câu #3 đúng 50ms).
    Sau fix: Vị trí 21,800ms được bảo toàn 100%, không bị snap vào 21,850ms.
    """
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    win.activateWindow()
    qtbot.wait(100)

    win.video_player.load_video(VIDEO_PATH)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=10000)
    win._load_context_subtitles(SRT_PATH)
    qtbot.wait(200)

    vp = win.video_player
    track = win.timeline_widget.container.track
    win.timeline_widget.set_duration(1765000)

    # Tua vào khoảng trống 21,800ms
    target_ms = 21800
    target_x = (target_ms / 1000.0) * track.pixels_per_second
    win.timeline_controller._do_seek(target_x)
    qtbot.wait(150)

    current_ms = vp.get_current_time_ms()
    assert abs(current_ms - target_ms) <= 50
    assert current_ms != 21850, "LỖI: Vị trí trong gap bị cưỡng chế nhảy vào đầu câu #3 (21850ms)!"


def test_jmsz_video_transcode_detection_and_cache():
    """Kiểm tra video thật JMSZ38_02.wmv được nhận diện chính xác và sinh cache path hợp lệ."""
    assert os.path.exists(VIDEO_PATH), f"Không tìm thấy file video: {VIDEO_PATH}"
    
    # 1. Nhận diện cần transcode
    assert is_transcode_needed(VIDEO_PATH) is True

    # 2. Cache path tất định
    cache_path = get_transcode_cache_path(VIDEO_PATH)
    assert cache_path.endswith("_fastseek.mp4")
    assert "JMSZ38_02" in cache_path


def test_jmsz_cat_studio_approved_subtitles_pruned(timeline_driver, qtbot):
    """
    BUG-TAB8-APPROVED-AI-PROMPT-RESIDUE-001:
    Kiểm tra các câu phụ đề đã được dịch/duyệt trên Timeline hoặc qua AI Agent
    (ví dụ câu #6, #7 của dự án JMSZ) được tự động loại bỏ khỏi hàng đợi CAT Studio,
    không bị lưu tồn đọng với trạng thái "CHỜ DUYỆT".
    """
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    qtbot.wait(100)

    # 1. Nạp phụ đề của dự án JMSZ
    win._load_context_subtitles(SRT_PATH)
    qtbot.wait(100)

    # Đảm bảo câu #6 và #7 đã có bản dịch tiếng Việt trên Timeline
    seg6 = win.sub_editor.all_segments[5]
    seg7 = win.sub_editor.all_segments[6]
    assert seg6["text"] == "Rốt cuộc ngươi tìm ta có chuyện gì?"
    assert seg7["text"] == "Chuyện đó còn phải hỏi sao!"

    # 2. Giả lập nạp project.aisrt cũ (có 2 câu #6, #7 ở trạng thái TRANSLATED)
    aisrt_path = os.path.join(PROJECT_DIR, "artifacts", "translation", "project.aisrt")
    assert os.path.exists(aisrt_path)
    win.page_translation.load_translation_project(aisrt_path)
    qtbot.wait(50)

    # 3. Kích hoạt đồng bộ từ Studio sang CAT Studio
    win.page_translation.sync_translations_from_studio(win.sub_editor.all_segments)
    qtbot.wait(100)

    # 4. Xác minh: Hàng đợi CAT Studio đã loại bỏ sạch các câu đã duyệt/khớp bản dịch!
    cat_items = win.page_translation.subtitle_model.get_all_data()
    # Không còn câu nào tồn đọng ở trạng thái chờ duyệt
    assert len(cat_items) == 0, f"Kỳ vọng hàng đợi trống nhưng vẫn còn {len(cat_items)} câu: {cat_items}"

    # 5. Kiểm tra Translation Memory đã được cập nhật bản dịch
    tm = getattr(win.page_translation.translation_controller, "translation_memory", None)
    if tm is not None:
        entry1 = tm.get("この俺様に一体何の")
        assert entry1 and getattr(entry1, "target_text", entry1) == "Rốt cuộc ngươi tìm ta có chuyện gì?"
        entry2 = tm.get("そんなの決まってるわ。")
        assert entry2 and getattr(entry2, "target_text", entry2) == "Chuyện đó còn phải hỏi sao!"

    # 6. Kiểm tra chuyển sang Tab 8 (CAT Studio) hiển thị workspace trống (tất cả đã duyệt)
    win.switch_page(8)
    qtbot.wait(100)
    assert win.page_translation.subtitle_model.rowCount() == 0
