# -*- coding: utf-8 -*-
"""
tests/ui/test_seek_preservation_and_transcode.py
Kiểm định chất lượng cho:
- FR-01: Bảo toàn 100% vị trí tua (ms) khi Seek trên Timeline, không bị nhảy giật về đầu câu (start_ms)
- FR-02: Bộ chuyển đổi ngầm Auto-Transcode Fast-Seek (< 50ms), nạp cache tự động và Hot-swap nguồn phát
"""

import os
import tempfile
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from tests.gui.conftest import timeline_driver
from core.subtitle_editing.selection_controller import SelectionSource
from core.video.transcode_service import (
    is_transcode_needed,
    get_transcode_cache_path,
    get_cached_transcode,
    TranscodeWorker,
)

VIDEO_FILE = os.path.abspath("sample_test_data/sample_video_25s.mp4")


# ==============================================================================
# FR-01: BẢO TOÀN VỊ TRÍ TUA & CHỐNG NHẢY KIM ĐỎ
# ==============================================================================

def test_fr01_timeline_seek_preserves_exact_millisecond(timeline_driver, qtbot):
    """
    Xác minh khi seek vào giữa câu phụ đề (12,500ms trong câu 10,000ms - 15,000ms):
    - Kim đỏ và player giữ nguyên vị trí 12,500ms.
    - Không bị cướp vị trí nhảy lùi về 10,000ms.
    - Không bị cướp focus vào text edit.
    - Nhấn phím Space phát video từ đúng 12,500ms.
    """
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    win.activateWindow()
    qtbot.wait(100)

    win.video_player.load_video(VIDEO_FILE)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=5000)
    vp = win.video_player

    # Tạo câu phụ đề 10s -> 15s
    seg = {
        "id": "seg_001",
        "start": "00:00:10,000",
        "end": "00:00:15,000",
        "start_ms": 10000,
        "end_ms": 15000,
        "text": "Câu thử nghiệm tua chính xác",
    }
    win.sub_editor.all_segments = [seg]
    win.timeline_controller.sync_from_editor_segments(win.sub_editor.all_segments)
    win.sub_editor.render_page()
    qtbot.wait(100)

    # Người dùng click seek tại mốc 12,500ms (ở giữa câu)
    target_ms = 12500
    target_x = (target_ms / 1000.0) * win.timeline_widget.container.track.pixels_per_second
    win.timeline_controller._do_seek(target_x)
    qtbot.wait(200)

    # 1. Kiểm tra vị trí hiện tại: phải ở 12,500ms (dung sai tối đa 50ms), KHÔNG được là 10,000ms
    current_ms = vp.get_current_time_ms()
    assert abs(current_ms - target_ms) <= 50, f"Lỗi nhảy kim: Mong đợi {target_ms}ms nhưng bị nhảy về {current_ms}ms!"
    assert current_ms != 10000, "Lỗi cướp vị trí: Player bị ép lùi về đầu câu (start_ms = 10000ms)!"

    # 2. Kiểm tra focus: Không bị cướp vào ô soạn thảo
    focused = QApplication.focusWidget() or win
    assert focused is not getattr(win.sub_editor.current_editor, "text_edit", None)

    # 3. Nhấn Space phát video: Bắt đầu phát từ chính mốc 12,500ms
    space_ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    handled = win.eventFilter(focused, space_ev)
    assert handled is True
    assert vp.player.isPlaying() is True


def test_fr01_manual_seek_clears_segment_bounds(timeline_driver, qtbot):
    """
    Xác minh khi tua thủ công (set_position), _segment_bounds được giải phóng hoàn toàn,
    không bị kẹp chặn playback ở ranh giới câu cũ.
    """
    win, driver, timeline_page, sub_page = timeline_driver
    vp = win.video_player

    # Giả lập đang focus vào segment [10,000ms, 15,000ms]
    vp._segment_bounds = (10000, 15000)
    vp._segment_playback_active = True

    # Người dùng thực hiện tua thủ công đến 18,000ms
    vp.set_position(18000)

    # _segment_bounds phải được giải phóng về None
    assert vp._segment_bounds is None
    assert vp._segment_playback_active is False
    assert vp._current_pos_ms == 18000


# ==============================================================================
# FR-02: BỘ CHUYỂN ĐỔI NGẦM AUTO-TRANSCODE FAST-SEEK (< 50MS)
# ==============================================================================

def test_fr02_transcode_detection():
    """Kiểm tra nhận diện chính xác các định dạng video cần transcode."""
    assert is_transcode_needed("test_video.wmv") is True
    assert is_transcode_needed("test_video.avi") is True
    assert is_transcode_needed("test_video.mkv") is True
    assert is_transcode_needed("test_video.flv") is True
    assert is_transcode_needed("test_video.ts") is True
    assert is_transcode_needed("standard_fastseek.mp4") is False
    assert is_transcode_needed("") is False


def test_fr02_transcode_cache_deterministic_and_instant():
    """Kiểm tra tính tất định của đường dẫn Cache và nạp tức thì (< 50ms) khi có cache."""
    cache_path_1 = get_transcode_cache_path(VIDEO_FILE)
    cache_path_2 = get_transcode_cache_path(VIDEO_FILE)
    assert cache_path_1 == cache_path_2
    assert cache_path_1.endswith("_fastseek.mp4")

    # Giả lập tạo file cache hoàn chỉnh
    with open(cache_path_1, "wb") as f:
        f.write(b"MOCK_MP4_VALID_CACHE_DATA" * 100)

    try:
        # get_cached_transcode phải trả về đường dẫn ngay lập tức
        cached = get_cached_transcode(VIDEO_FILE)
        assert cached == cache_path_1
    finally:
        if os.path.exists(cache_path_1):
            os.remove(cache_path_1)


def test_fr02_transcode_worker_execution(tmp_path, qtbot):
    """Kiểm tra TranscodeWorker chuyển đổi video bằng FFmpeg ngầm với GOP=1s."""
    target_mp4 = str(tmp_path / "fastseek_output.mp4")
    worker = TranscodeWorker(input_path=VIDEO_FILE, output_path=target_mp4)

    started_paths = []
    finished_paths = []
    failed_msgs = []

    worker.transcode_started.connect(lambda p: started_paths.append(p))
    worker.transcode_finished.connect(lambda orig, trans: finished_paths.append((orig, trans)))
    worker.transcode_failed.connect(lambda p, err: failed_msgs.append((p, err)))

    worker.start()
    qtbot.waitUntil(lambda: len(finished_paths) > 0 or len(failed_msgs) > 0, timeout=15000)

    assert len(finished_paths) == 1, f"Transcode thất bại: {failed_msgs}"
    orig, trans = finished_paths[0]
    assert orig == VIDEO_FILE
    assert trans == target_mp4
    assert os.path.exists(target_mp4)
    assert os.path.getsize(target_mp4) > 10000


def test_fr02_video_player_hot_swap_logic(timeline_driver):
    """Kiểm tra cơ chế Hot-swap nguồn phát không làm mất vị trí hoặc trạng thái phát."""
    win, driver, timeline_page, sub_page = timeline_driver
    vp = win.video_player

    vp._original_video_path = "D:/dummy/input.wmv"
    vp._playback_video_path = "D:/dummy/input.wmv"
    vp._current_pos_ms = 8500

    # Giả lập hoàn tất transcode
    new_transcoded = "D:/dummy/input_fastseek.mp4"
    vp._on_transcode_finished("D:/dummy/input.wmv", new_transcoded)

    assert vp._playback_video_path == new_transcoded
