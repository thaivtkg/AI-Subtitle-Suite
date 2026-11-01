# -*- coding: utf-8 -*-
"""
Test Suite for PLAN-NUDGE-CLAMPING-001:
- AC-NUDGE-01: Nudging start backward clamps strictly at previous segment end
- AC-NUDGE-02: Nudging end forward without ripple clamps strictly at next segment start
- AC-NUDGE-03: Nudging both backward clamps within available gap
- AC-NUDGE-04: Paused video player does not steal SubEditor current_index selection
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from ui.Gui import MainWindow
from ui.SubEditor import SubtitleEditorWidget
from core.subtitle_editing.global_undo_manager import GlobalUndoManager


@pytest.fixture
def sub_editor_widget(qtbot):
    app = QApplication.instance() or QApplication([])
    undo_manager = GlobalUndoManager()
    widget = SubtitleEditorWidget()
    widget.undo_manager = undo_manager
    undo_manager.state_changed.connect(widget.render_page)
    widget.resize(900, 500)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.wait(100)
    yield widget
    widget.close()


def test_nudge_start_clamps_at_previous_segment_end(sub_editor_widget):
    """
    AC-NUDGE-01:
    Câu #1 có end 9,500ms. Câu #2 có start 10,000ms.
    Bấm lùi -1s (-1000ms) ở start câu #2 -> start bị khóa biên chính xác tại 9,500ms, không đè câu #1.
    """
    editor = sub_editor_widget
    editor.all_segments = [
        {"stt": "1", "id": "seg_1", "start": "00:00:08,000", "end": "00:00:09,500", "text": "Câu một"},
        {"stt": "2", "id": "seg_2", "start": "00:00:10,000", "end": "00:00:12,000", "text": "Câu hai"},
    ]
    editor.render_page()
    editor.select_segment(1)

    # Nudge start backward by -1000ms
    editor.nudge_selected_segment(target="start", delta_ms=-1000)

    # Seg #2 start must clamp at 00:00:09,500
    seg_2 = editor.all_segments[1]
    assert seg_2["start"] == "00:00:09,500"
    assert seg_2["end"] == "00:00:12,000"
    assert editor.current_index == 1


def test_nudge_end_clamps_at_next_segment_start_without_ripple(sub_editor_widget):
    """
    AC-NUDGE-02:
    Câu #1 có end 9,500ms. Câu #2 có start 10,000ms.
    Khi ripple_shift_enabled = False, bấm tiến +1s (+1000ms) ở end câu #1
    -> end bị khóa biên chính xác tại start câu #2 (10,000ms).
    """
    editor = sub_editor_widget
    editor.all_segments = [
        {"stt": "1", "id": "seg_1", "start": "00:00:08,000", "end": "00:00:09,500", "text": "Câu một"},
        {"stt": "2", "id": "seg_2", "start": "00:00:10,000", "end": "00:00:12,000", "text": "Câu hai"},
    ]
    editor.ripple_shift_enabled = False
    editor.render_page()
    editor.select_segment(0)

    # Nudge end forward by +1000ms
    editor.nudge_selected_segment(target="end", delta_ms=1000)

    # Seg #1 end must clamp at 00:00:10,000
    seg_1 = editor.all_segments[0]
    assert seg_1["end"] == "00:00:10,000"
    assert seg_1["start"] == "00:00:08,000"


def test_nudge_both_clamps_within_gap(sub_editor_widget):
    """
    AC-NUDGE-03:
    Câu #1 có end 9,800ms. Câu #2 có start 10,000ms, end 12,000ms (khoảng trống 200ms).
    Bấm lùi cả đoạn (both) -1s (-1000ms) -> chỉ được phép dịch lùi tối đa 200ms, dừng ở 9,800ms.
    """
    editor = sub_editor_widget
    editor.all_segments = [
        {"stt": "1", "id": "seg_1", "start": "00:00:08,000", "end": "00:00:09,800", "text": "Câu một"},
        {"stt": "2", "id": "seg_2", "start": "00:00:10,000", "end": "00:00:12,000", "text": "Câu hai"},
    ]
    editor.render_page()
    editor.select_segment(1)

    # Nudge both backward by -1000ms
    editor.nudge_selected_segment(target="both", delta_ms=-1000)

    # Seg #2 must only shift back by 200ms
    seg_2 = editor.all_segments[1]
    assert seg_2["start"] == "00:00:09,800"
    assert seg_2["end"] == "00:00:11,800"
    assert editor.current_index == 1


def test_paused_playback_does_not_steal_editor_selection(qtbot, monkeypatch):
    """
    AC-NUDGE-04:
    Khi Video Player đang TẠM DỪNG (isPlaying() == False), di chuyển kim thời gian
    hoặc phát tín hiệu subtitle_changed tuyệt đối KHÔNG cướp quyền chọn (current_index) của SubEditor.
    """
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1100, 700)
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(100)

    mock_segments = [
        {"stt": "1", "id": "seg_1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Đoạn 1"},
        {"stt": "2", "id": "seg_2", "start": "00:00:05,000", "end": "00:00:07,000", "text": "Đoạn 2"},
        {"stt": "3", "id": "seg_3", "start": "00:00:09,000", "end": "00:00:11,000", "text": "Đoạn 3"},
    ]
    win.sub_editor.all_segments = mock_segments
    win.sub_editor.render_page()

    # Người dùng chọn và đang làm việc ở câu #2 (index 1)
    win.sub_editor.select_segment(1)
    assert win.sub_editor.current_index == 1

    # Đảm bảo video đang dừng
    assert win.video_player.isPlaying() is False

    # Giả lập kim thời gian rơi vào câu #1 và phát tín hiệu subtitle_changed
    win.video_player.sub_controller.subtitle_changed.emit(1, 1000, "Đoạn 1")
    qtbot.wait(100)

    # current_index của SubEditor vẫn phải giữ nguyên là 1 (không bị giật về 0)
    assert win.sub_editor.current_index == 1, (
        f"LỖI GIẬT VÙNG CHỌN: current_index bị đổi thành {win.sub_editor.current_index} trong khi video đang tạm dừng!"
    )

    # Kiểm tra chiều ngược lại: Khi video THỰC SỰ PHÁT (isPlaying() == True)
    monkeypatch.setattr(win.video_player, "isPlaying", lambda: True)
    win.video_player.sub_controller.subtitle_changed.emit(1, 1000, "Đoạn 1")
    qtbot.wait(100)

    # Lúc này do đang phát, sync_playback_highlight được kích hoạt và đồng bộ câu #1 (index 0)
    assert win.sub_editor.current_index == 0
    win.close()
