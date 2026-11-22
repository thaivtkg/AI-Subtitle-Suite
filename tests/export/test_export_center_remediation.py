import os
import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.Gui import MainWindow

@pytest.fixture
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])

def test_import_batch_preserves_original_text(app, tmp_path):
    """
    Tác vụ 4 (PLAN-EXPORT-DELIVERY-REMEDIATION-001):
    Nạp bản dịch từ app ngoài phải kích hoạt Overwrite Guard bảo vệ original_text.
    """
    win = MainWindow()
    win.sub_editor.all_segments = [
        {"stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "こんにちは", "original_text": ""}
    ]
    
    # Tạo file SRT bản dịch tiếng Việt
    trans_srt = tmp_path / "translated.srt"
    trans_srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào các bạn\n", encoding="utf-8")
    
    with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(trans_srt), "SRT Files (*.srt)")):
        win._on_import_batch_translation_requested()
        
    seg = win.sub_editor.all_segments[0]
    assert seg["text"] == "Xin chào các bạn"
    assert seg["original_text"] == "こんにちは" # Phải bảo tồn câu gốc!

def test_export_batch_prioritizes_original_text(app, tmp_path):
    """
    Tác vụ 5 (PLAN-EXPORT-DELIVERY-REMEDIATION-001):
    Xuất đợt dịch phải ưu tiên lấy original_text thay vì câu tiếng Việt đã dịch.
    """
    win = MainWindow()
    win.sub_editor.all_segments = [
        {
            "stt": "1",
            "start": "00:00:01,000",
            "end": "00:00:03,000",
            "text": "Chào thế giới",
            "original_text": "Hello world"
        }
    ]
    
    out_srt = tmp_path / "batch_out.srt"
    with patch("PySide6.QtWidgets.QMessageBox.warning", return_value=QMessageBox.Yes):
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(out_srt), "SRT Files (*.srt)")):
            win._on_export_batch_translation_requested(1, 1)
        
    assert out_srt.exists()
    content = out_srt.read_text(encoding="utf-8")
    assert "Hello world" in content
    assert "Chào thế giới" not in content

def test_softsub_auto_fallback_to_video_directory(app, tmp_path):
    """
    Tác vụ 2 (PLAN-EXPORT-DELIVERY-REMEDIATION-001):
    Khi out_edit để trống, xuất Softsub tự động fallback về thư mục video an toàn.
    """
    win = MainWindow()
    fake_video = tmp_path / "my_video.mp4"
    fake_video.write_bytes(b"dummy")
    
    win.queue_mgr.add_video(str(fake_video))
    win.queue_mgr.set_active(str(fake_video))
    win.page_export.out_edit.setText("")
    win.out_input.setText("")
    
    win.sub_editor.all_segments = [
        {"stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu test"}
    ]
    win.page_export.chk_srt.setChecked(True)
    win.page_export.chk_hardsub.setChecked(False)
    
    win._trigger_export_softsub()
    
    expected_srt = tmp_path / "my_video.srt"
    assert expected_srt.exists()
    assert "Câu test" in expected_srt.read_text(encoding="utf-8")

def test_hardsub_in_memory_auto_generates_srt_when_missing_on_disk(app, tmp_path):
    """
    Tác vụ 1 (PLAN-EXPORT-DELIVERY-REMEDIATION-001):
    Khi chưa có SRT trên đĩa nhưng RAM có sub_editor.all_segments,
    _trigger_export_hardsub() tự động sinh SRT và khởi tạo HardsubWorker.
    """
    win = MainWindow()
    fake_video = tmp_path / "my_video.mp4"
    fake_video.write_bytes(b"dummy")
    
    win.queue_mgr.add_video(str(fake_video))
    win.queue_mgr.set_active(str(fake_video))
    # Đảm bảo srt_path rỗng
    win.queue_mgr._items[win.queue_mgr.active_item_key]["srt_path"] = None
    
    win.sub_editor.all_segments = [
        {"stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu test hardsub"}
    ]
    win.page_export.out_edit.setText(str(tmp_path))
    
    with patch("ui.Gui.HardsubWorker") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        win._trigger_export_hardsub()
        assert mock_worker_cls.called
        assert mock_worker.start.called
        # Xác nhận srt đã được tự động sinh ra đĩa
        generated_srt = tmp_path / "my_video.srt"
        assert generated_srt.exists()

def test_softsub_chains_hardsub_when_chk_hardsub_checked(app, tmp_path):
    """
    Tác vụ 3 (PLAN-EXPORT-DELIVERY-REMEDIATION-001):
    Khi chk_hardsub được tích, bấm xuất Softsub sẽ tự động kích hoạt tiếp _trigger_export_hardsub.
    """
    win = MainWindow()
    fake_video = tmp_path / "chain_video.mp4"
    fake_video.write_bytes(b"dummy")
    
    win.queue_mgr.add_video(str(fake_video))
    win.queue_mgr.set_active(str(fake_video))
    win.page_export.out_edit.setText(str(tmp_path))
    win.sub_editor.all_segments = [
        {"stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu chuỗi"}
    ]
    win.page_export.chk_srt.setChecked(True)
    win.page_export.chk_hardsub.setChecked(True)
    
    with patch.object(win, "_trigger_export_hardsub") as mock_hardsub:
        with patch("PySide6.QtCore.QTimer.singleShot", side_effect=lambda ms, cb: cb()):
            win._trigger_export_softsub()
            assert mock_hardsub.called

def test_chk_hardsub_is_unchecked_by_default(app):
    """
    Verify chk_hardsub is unchecked by default to prevent unwanted hardsub burn on softsub export.
    """
    win = MainWindow()
    assert win.page_export.chk_hardsub.isChecked() is False

def test_softsub_does_not_chain_hardsub_by_default(app, tmp_path):
    """
    Verify softsub export does NOT chain hardsub by default.
    """
    win = MainWindow()
    fake_video = tmp_path / "softsub_only.mp4"
    fake_video.write_bytes(b"dummy")
    
    win.queue_mgr.add_video(str(fake_video))
    win.queue_mgr.set_active(str(fake_video))
    win.page_export.out_edit.setText(str(tmp_path))
    win.sub_editor.all_segments = [
        {"stt": "1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu test softsub only"}
    ]
    win.page_export.chk_srt.setChecked(True)
    # Ensure default is kept (False)
    assert win.page_export.chk_hardsub.isChecked() is False
    
    with patch.object(win, "_trigger_export_hardsub") as mock_hardsub:
        with patch("PySide6.QtCore.QTimer.singleShot", side_effect=lambda ms, cb: cb()):
            win._trigger_export_softsub()
            assert not mock_hardsub.called

def test_clear_files_cancels_running_worker(app):
    """
    Verify that clear_files() safely cancels active worker and resets UI status.
    """
    win = MainWindow()
    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    win.worker = mock_worker
    win.page_dashboard.card_status_val.setText("Processing")

    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Discard):
        win.clear_files()

    assert mock_worker.cancel.called
    assert win.page_dashboard.card_status_val.text() == "Idle"

def test_on_queue_item_removed_cancels_running_worker(app):
    """
    Verify that removing the video item being processed cancels the worker.
    """
    win = MainWindow()
    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    mock_worker.video_path = "D:/dummy/active.mp4"
    win.worker = mock_worker

    win.on_queue_item_removed_handler("D:/dummy/active.mp4")

    assert mock_worker.cancel.called

def test_burn_hardsub_cancel_check_prevents_cpu_fallback(tmp_path):
    """
    Verify burn_hardsub aborts immediately when cancel_check returns True,
    and does NOT fall back to CPU libx264.
    """
    from core.Backend import burn_hardsub
    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy")
    srt = tmp_path / "test.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    output = tmp_path / "out.mp4"

    with patch("core.Backend.detect_video_encoder", return_value=("h264_nvenc", "NVIDIA NVENC")):
        with patch("subprocess.Popen") as mock_popen:
            # cancel_check returns True immediately
            burn_hardsub(
                str(video),
                str(srt),
                str(output),
                video_resolution=(1280, 720),
                cancel_check=lambda: True,
            )
            # Popen should not even be called when already cancelled
            assert not mock_popen.called

