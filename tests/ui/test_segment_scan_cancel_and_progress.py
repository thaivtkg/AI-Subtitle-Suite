import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QProgressDialog, QProgressBar, QMessageBox
from workers.SegmentScanWorker import BatchSegmentScanWorker, SegmentScanWorker
from ui.Gui import MainWindow

def test_batch_segment_scan_cancel_cleans_up_and_rescan_allowed(qapp, tmp_path):
    """Xác thực khi bấm Hủy trong box gen sub, worker dừng an toàn,
    dọn dẹp state và cho phép quét lại ngay mà không bị báo 'Quá trình AI đang chạy'.
    """
    win = MainWindow.__new__(MainWindow)
    win.sub_editor = MagicMock()
    win.sub_editor.all_segments = [
        {"id": "1", "start": "00:00:01,000", "end": "00:00:03,000", "start_ms": 1000, "end_ms": 3000, "text": "Câu 1"},
        {"id": "2", "start": "00:00:04,000", "end": "00:00:06,000", "start_ms": 4000, "end_ms": 6000, "text": "Câu 2"},
    ]
    win.project_service = MagicMock()
    win.project_service.current_project = MagicMock(project_id="p1", video_path=str(tmp_path / "video.mp4"))
    win.current_vid = str(tmp_path / "video.mp4")
    (tmp_path / "video.mp4").write_bytes(b"dummy")
    win.get_current_video_path = lambda: str(tmp_path / "video.mp4")
    win.generation_panel = MagicMock()
    win.generation_panel._timing_settings.return_value = {"model_size": "large-v3-turbo"}
    win.subtitle_whisper_service = MagicMock()
    win.scan_worker = None
    win._batch_scan_worker = None

    # Lần 1: Khởi động batch scan và bấm Hủy
    with patch.object(BatchSegmentScanWorker, "start") as mock_start, \
         patch("ui.toast.Toast.show_info"):
        win._on_batch_segment_scan_requested([0, 1])

        # Đã tạo worker và gán vào win._batch_scan_worker
        assert win._batch_scan_worker is not None
        assert mock_start.called

        # Mô phỏng user bấm Hủy trên progress dialog
        win._batch_scan_worker.cancel()
        assert win._batch_scan_worker._is_cancelled is True

        # Mô phỏng worker hoàn thành / emit finished
        win._batch_scan_worker.finished.emit()

        # Sau khi cleanup, _batch_scan_worker phải là None và _is_any_ai_process_running trả về False
        assert getattr(win, "_batch_scan_worker", None) is None
        assert win._is_any_ai_process_running() is False

    # Lần 2: Người dùng bấm quét lại ngay lập tức và hoàn thành bình thường (was_cancelled=False)
    with patch.object(BatchSegmentScanWorker, "start") as mock_start2, \
         patch.object(QMessageBox, "warning") as mock_warn, \
         patch("ui.toast.Toast.show_success") as mock_toast_success:
        win._on_batch_segment_scan_requested([0, 1])

        # Cảnh báo "Quá trình AI đang chạy" KHÔNG được gọi
        assert mock_warn.called is False
        assert mock_start2.called is True
        assert win._batch_scan_worker is not None

        # Mô phỏng worker hoàn thành thành công (không hủy)
        win._batch_scan_worker.finished_signal.emit()
        assert mock_toast_success.called is True
        assert getattr(win, "_batch_scan_worker", None) is None


def test_batch_segment_scan_detailed_progress_signal():
    """Xác thực detailed_progress_signal phát ra đúng tỷ lệ % và chuỗi mô tả tầng."""
    request = MagicMock()
    request.model_size = "large-v3-turbo"
    request.source_language = "ja"
    whisper_service = MagicMock()

    segments = [
        {"id": "1", "start_ms": 1000, "end_ms": 3000, "text": "C1", "has_sub": True, "scan_mode": "asr"},
        {"id": "2", "start_ms": 4000, "end_ms": 6000, "text": "C2", "has_sub": True, "scan_mode": "asr"},
    ]

    worker = BatchSegmentScanWorker(segments, request, whisper_service)
    emitted = []
    errors = []
    worker.error_signal.connect(lambda err: errors.append(err))
    worker.detailed_progress_signal.connect(lambda pct, msg: emitted.append((pct, msg)))

    # Giả lập fallback transcription với tier callback
    def fake_fallback(service, req, sid, s_ms, e_ms, is_cancelled_fn, force_no_vad=False, on_tier_callback=None):
        if on_tier_callback:
            on_tier_callback(1, 3, "Tầng 1/3: Nhận diện tiêu chuẩn (VAD)")
            on_tier_callback(2, 3, "Tầng 2/3: Tăng âm & Hạ ngưỡng VAD")
        return "Văn bản nhận diện", ""

    with patch("workers.SegmentScanWorker._transcribe_segment_with_fallback", side_effect=fake_fallback):
        worker.run()

    assert not errors, f"Worker raised errors: {errors}"
    assert len(emitted) > 0
    # Câu 1 và câu 2 đều emit tier_name và %
    assert any("Tầng 1/3" in msg for _, msg in emitted)
    assert any("Tầng 2/3" in msg for _, msg in emitted)
    # Câu 2 kết thúc phát ra 100%
    assert any(pct == 100 for pct, _ in emitted)


def test_batch_scan_progress_dialog_ui(qapp):
    """Xác thực giao diện QProgressDialog hiển thị thanh % và độ cao nhãn thông tin."""
    win = MainWindow.__new__(MainWindow)
    dlg = win._create_batch_scan_progress_dialog(10)
    try:
        assert isinstance(dlg, QProgressDialog)
        pbar = dlg.findChild(QProgressBar)
        assert pbar is not None
        assert pbar.isTextVisible() is True
        assert pbar.format() == "%p%"
        assert dlg.maximum() == 100
        assert dlg.minimum() == 0
    finally:
        dlg.close()
