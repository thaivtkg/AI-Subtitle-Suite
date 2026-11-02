import os
import pytest
from PySide6.QtWidgets import QApplication

from ui.Gui import MainWindow


@pytest.fixture
def main_window(qtbot):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1280, 720)
    qtbot.addWidget(win)

    # Nạp 2 câu phụ đề mẫu và đồng bộ data provider
    segments = [
        {
            "id": "seg_sync_1",
            "stt": "1",
            "start": "00:00:01,000",
            "end": "00:00:03,000",
            "start_ms": 1000,
            "end_ms": 3000,
            "text": "Câu một ban đầu",
            "original_text": "Original text 1",
            "translation": "",
            "translation_status": "PENDING",
        },
        {
            "id": "seg_sync_2",
            "stt": "2",
            "start": "00:00:04,000",
            "end": "00:00:06,000",
            "start_ms": 4000,
            "end_ms": 6000,
            "text": "Câu hai ban đầu",
            "original_text": "Original text 2",
            "translation": "",
            "translation_status": "PENDING",
        },
    ]
    win.timeline_widget.duration_ms = 20000
    win.sub_editor.all_segments = list(segments)
    win.timeline_data_provider.load_runtime_data(segments, 20000)
    win.timeline_widget.load_project_data(20000, win.timeline_data_provider.get_all_segments())
    win.timeline_controller.sync_from_editor_segments(segments)
    win.sub_editor.render_page()
    win.sub_editor.select_segment(0)

    # Đặt vị trí video tại 1500ms (nằm trọn trong câu 1)
    win.video_player.set_position(1500)
    yield win
    win.close()
    win.deleteLater()


def test_ac_live_01_current_subtitle_editor_syncs_realtime_to_video_player(main_window, qtbot):
    """
    AC-LIVE-01: Khi gõ nội dung vào ô CurrentSubtitleEditor (txt_current_sub_content),
    text trên màn hình Video Player phải thay đổi theo thời gian thực (sau debounce).
    """
    win = main_window
    assert win.video_player.subtitle_overlay.render_input is not None
    assert win.video_player.subtitle_overlay.render_input.text == "Câu một ban đầu"

    # Người dùng gõ text mới vào ô soạn thảo
    win.sub_editor.current_editor.text_edit.setPlainText("Câu một đã sửa realtime")
    win.sub_editor.current_editor.commit_pending_edit()

    # Xác nhận Video Player đã render lại ngay lập tức text mới
    assert win.video_player.subtitle_overlay.render_input.text == "Câu một đã sửa realtime"


def test_ac_live_02_table_cell_edit_syncs_realtime_to_video_player(main_window, qtbot):
    """
    AC-LIVE-02: Khi sửa nội dung trực tiếp tại ô trong bảng SubEditor (table_subtitles),
    chữ trên Video Player phải đổi ngay khi hoàn tất sửa cell.
    """
    win = main_window
    assert win.video_player.subtitle_overlay.render_input.text == "Câu một ban đầu"

    # Sửa cell trực tiếp trên bảng
    item = win.sub_editor.table.item(0, win.sub_editor.COL_TEXT)
    assert item is not None
    item.setText("Câu một sửa trực tiếp từ Table")

    # Xác nhận Video Player cập nhật text từ bảng ngay lập tức
    assert win.video_player.subtitle_overlay.render_input.text == "Câu một sửa trực tiếp từ Table"


def test_ac_live_03_undo_redo_syncs_realtime_to_video_player(main_window, qtbot):
    """
    AC-LIVE-03: Khi bấm Ctrl+Z (Undo) hoặc Ctrl+Y (Redo) thao tác gõ chữ,
    chữ hiển thị trên Video Player phải lập tức đổi theo trạng thái hoàn tác/làm lại.
    """
    win = main_window
    assert win.video_player.subtitle_overlay.render_input.text == "Câu một ban đầu"

    # Sửa lần 1
    win.sub_editor.current_editor.text_edit.setPlainText("Sửa lần 1")
    win.sub_editor.current_editor.commit_pending_edit()
    assert win.video_player.subtitle_overlay.render_input.text == "Sửa lần 1"

    # Hoàn tác (Undo)
    assert win.undo_manager.can_undo if hasattr(win.undo_manager, "can_undo") else win.undo_manager.undo_stack.canUndo()
    win.undo_manager.undo()
    assert win.video_player.subtitle_overlay.render_input.text == "Câu một ban đầu"

    # Làm lại (Redo)
    assert win.undo_manager.can_redo if hasattr(win.undo_manager, "can_redo") else win.undo_manager.undo_stack.canRedo()
    win.undo_manager.redo()
    assert win.video_player.subtitle_overlay.render_input.text == "Sửa lần 1"


def test_ac_live_04_tm_and_asr_scan_sync_realtime_to_video_player(main_window, qtbot):
    """
    AC-LIVE-04: Áp dụng gợi ý TM hoặc quét lại ASR đoạn đơn lập tức phản ánh
    nội dung mới lên Video Player mà không cần bấm Play video.
    """
    win = main_window
    assert win.video_player.subtitle_overlay.render_input.text == "Câu một ban đầu"

    # 1. Quét lại giọng nói ASR đoạn đơn hoàn tất
    win._on_segment_scan_finished("seg_sync_1", "Nội dung nhận diện mới từ ASR")
    assert win.video_player.subtitle_overlay.render_input.text == "Nội dung nhận diện mới từ ASR"

    # 2. Áp dụng gợi ý TM
    win.sub_editor.select_segment(0)
    win._on_tm_match_applied("Bản dịch gợi ý từ TM")
    assert win.video_player.subtitle_overlay.render_input.text == "Bản dịch gợi ý từ TM"
