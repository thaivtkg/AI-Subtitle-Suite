import pytest
from unittest.mock import MagicMock, patch

from core.subtitle_generation.faster_whisper_service import (
    FasterWhisperService,
    should_downgrade_to_int8_float16,
)
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.timing.timing_run_request import TimingRunRequest
from workers.TimingBatchWorker import TimingBatchWorker
from core.translation.models.subtitle import SubtitleModel
from core.translation.controllers.translation_controller import TranslationController
from core.translation.controllers.project_controller import ProjectController


def test_rescan_uses_large_v3_and_float16_by_default(qapp):
    from ui.Gui import MainWindow

    win = MainWindow.__new__(MainWindow)
    win.sub_editor = MagicMock()
    win.sub_editor.all_segments = [
        {"id": "s1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Hello world"}
    ]
    win.sub_editor.current_editor = MagicMock()
    win.sub_editor.current_editor.chk_boost_audio.isChecked.return_value = False
    win.project_service = MagicMock()
    win.project_service.current_project = MagicMock(project_id="p1", video_path="v.mp4")
    win.current_vid = "v.mp4"
    win.generation_panel = MagicMock()
    win.generation_panel._timing_settings.return_value = {
        "model_size": "large-v3-turbo",
        "compute_type": "int8",
        "language": "en",
    }
    win.subtitle_whisper_service = MagicMock(device="cuda")

    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True), \
         patch("core.translation.core.hardware_detector.HardwareDetector.get_vram_usage", return_value=(2.0, 8.0)), \
         patch("workers.SegmentScanWorker.SegmentScanWorker.start"):
        win._on_segment_scan_requested("s1", 1000, 3000)
        assert win.scan_worker.request.model_size == "large-v3"
        assert win.scan_worker.request.compute_type == "float16"


def test_rescan_auto_selects_int8_float16_and_2000ms_silence_for_rtx_3050_anime_ja(qapp):
    from ui.Gui import MainWindow

    win = MainWindow.__new__(MainWindow)
    win.sub_editor = MagicMock()
    win.sub_editor.all_segments = [
        {"id": "s1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "「この俺様に一体何の」"}
    ]
    win.sub_editor.current_editor = MagicMock()
    win.sub_editor.current_editor.chk_boost_audio.isChecked.return_value = False
    win.project_service = MagicMock()
    win.project_service.current_project = MagicMock(project_id="p1", video_path="v.mp4")
    win.current_vid = "v.mp4"
    win.generation_panel = MagicMock()
    win.generation_panel._timing_settings.return_value = {
        "model_size": "large-v3-turbo",
        "compute_type": "int8",
        "language": "ja",
        "min_silence_ms": 500,
    }
    win.subtitle_whisper_service = MagicMock(device="cuda")

    # Giả lập GPU RTX 3050 4GB (used 0.8GB, total 4.0GB <= 4.5GB)
    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True), \
         patch("core.translation.core.hardware_detector.HardwareDetector.get_vram_usage", return_value=(0.8, 4.0)), \
         patch("workers.SegmentScanWorker.SegmentScanWorker.start"):
        win._on_segment_scan_requested("s1", 1000, 3000)
        assert win.scan_worker.request.model_size == "large-v3"
        assert win.scan_worker.request.compute_type == "int8_float16"
        assert win.scan_worker.request.min_silence_ms == 2000
        assert win.scan_worker.request.condition_on_previous_text is True


def test_faster_whisper_auto_downgrades_to_int8_float16_when_vram_exceeds_65_percent():
    service = FasterWhisperService(device="cuda")
    loaded_configs = []

    def fake_whisper_model(path, device=None, compute_type=None, download_root=None):
        loaded_configs.append((path, device, compute_type))
        mock_m = MagicMock()
        seg = MagicMock(start=0.0, end=1.5, text="テスト", words=None)
        mock_m.transcribe.return_value = ([seg], MagicMock())
        return mock_m

    with patch("faster_whisper.WhisperModel", side_effect=fake_whisper_model), \
         patch("core.services.model_manager.ModelManager.get_model_path_for_inference", return_value="large-v3"), \
         patch("core.services.model_manager.ModelManager.prepare_models_storage", return_value="models"), \
         patch("core.translation.core.hardware_detector.HardwareDetector.get_vram_usage", return_value=(4.2, 6.0)):
        # 4.2 / 6.0 = 70% > 65% -> tự động nạp bằng int8_float16 thay vì float16
        downgrade, ratio = should_downgrade_to_int8_float16(0.65)
        assert downgrade is True
        assert abs(ratio - 0.70) < 0.01

        service.load_model("large-v3", "float16")
        assert service.current_compute_type == "int8_float16"
        assert loaded_configs[-1][2] == "int8_float16"


def test_faster_whisper_transcribe_batch_rtx_3050_anime_options():
    service = FasterWhisperService(device="cuda")
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], MagicMock(language="ja"))
    service.model = mock_model
    service._extract_batch_audio = lambda req, b: ("dummy.wav", "")

    req = SubtitleGenerationRequest(
        request_id="r1",
        project_id="p1",
        source_fingerprint="fp",
        video_path="v.mp4",
        model_size="large-v3",
        compute_type="int8_float16",
        language="ja",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
        condition_on_previous_text=True,
    )
    batch = SubtitleGenerationBatch(
        batch_id="b1",
        start_ms=0,
        end_ms=2000,
        status="RUNNING",
        revision=1,
        created_at="now",
        updated_at="now",
    )

    with patch("core.translation.core.hardware_detector.HardwareDetector.get_vram_usage", return_value=(0.8, 4.0)):
        service.transcribe_batch(req, batch, lambda: False)

    called_kwargs = mock_model.transcribe.call_args[1]
    assert called_kwargs["beam_size"] == 5
    assert called_kwargs["best_of"] == 5
    assert called_kwargs["patience"] == 1.0
    assert called_kwargs["temperature"] == (0.0, 0.2, 0.4)
    assert called_kwargs["log_prob_threshold"] == -1.0
    assert called_kwargs["no_speech_threshold"] == 0.6
    assert called_kwargs["compression_ratio_threshold"] == 2.4
    assert called_kwargs["condition_on_previous_text"] is True
    assert called_kwargs["vad_parameters"]["min_silence_duration_ms"] == 2000


def test_timing_batch_worker_downgrades_mid_generation_on_high_vram(tmp_path):
    req = TimingRunRequest(
        video_path=str(tmp_path / "video.mp4"),
        model_size="large-v3",
        compute_type="float16",
        language="ja",
        use_vad=False,
        min_silence_ms=500,
        start_ms=0,
        target_segment_count=2,
        max_window_ms=10000,
        overlap_ms=1000,
    )
    worker = TimingBatchWorker(req)
    emitted_computes = []
    worker.effective_compute_signal.connect(lambda c: emitted_computes.append(c))

    # Lần kiểm tra 1 (lúc nạp model ban đầu): 3.0 / 6.0 = 50% (giữ float16)
    # Lần kiểm tra 2 (trong vòng lặp gen): 4.5 / 6.0 = 75% > 65% (hạ xuống int8_float16)
    vram_samples = iter([(3.0, 6.0), (4.5, 6.0), (3.2, 6.0)])

    def fake_vram():
        return next(vram_samples, (3.2, 6.0))

    created_computes = []

    def fake_whisper_model(path, device=None, compute_type=None, download_root=None):
        created_computes.append(compute_type)
        m = MagicMock()
        seg1 = MagicMock(start=0.5, end=2.0, words=None)
        seg2 = MagicMock(start=3.5, end=5.0, words=None)
        info = MagicMock(duration=10.0)
        m.transcribe.return_value = ([seg1, seg2], info)
        return m

    def fake_ffmpeg_run(cmd, **kwargs):
        out_wav = cmd[-1]
        with open(out_wav, "wb") as f:
            f.write(b"\x00" * 4096)
        return MagicMock(returncode=0, stderr="")

    with patch("torch.cuda.is_available", return_value=True), \
         patch("torch.cuda.empty_cache"), \
         patch("faster_whisper.WhisperModel", side_effect=fake_whisper_model), \
         patch("core.services.model_manager.ModelManager.get_model_path_for_inference", return_value="large-v3"), \
         patch("core.translation.core.hardware_detector.HardwareDetector.get_vram_usage", side_effect=fake_vram), \
         patch("subprocess.run", side_effect=fake_ffmpeg_run):
        worker.run()

    assert "float16" in created_computes
    assert "int8_float16" in created_computes
    assert emitted_computes[-1] == "int8_float16"


def test_translation_log_is_concise_and_utf8_readable(capsys, qapp):
    model = SubtitleModel()
    model.load_data([
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:03,000",
            "original": "「この俺様に一体何の」",
            "translation": "",
            "status": "PENDING",
        }
    ])
    tc = TranslationController(model)
    tc._active_translation_index = 0
    tc._current_index = 0
    tc.worker = MagicMock(extracted_terms=[])

    # Clear startup output
    capsys.readouterr()

    tc.on_finished(0, "Ngươi tìm ta đây rốt cuộc có chuyện gì?")
    out = capsys.readouterr().out

    assert "[MODEL_COMMIT]" not in out
    assert "[MODEL_AFTER]" not in out
    assert "[TRANSLATION_CALLBACK]" not in out
    assert "\\u" not in out
    assert "[CAT] Câu #1: Ngươi tìm ta đây rốt cuộc có chuyện gì?" in out


def test_project_save_suppresses_zero_subtitle_log(capsys, tmp_path):
    model = SubtitleModel()
    model.load_data([])
    pc = ProjectController(model)
    capsys.readouterr()

    save_file = str(tmp_path / "empty_project.aisrt")
    pc.saveProject(save_file, "", "Japanese", "Vietnamese", notify=False)
    out = capsys.readouterr().out

    assert "Saving 0 subtitles" not in out


def test_rescan_and_batch_rescan_default_vad_to_false(qapp, tmp_path):
    from ui.Gui import MainWindow
    from workers.SegmentScanWorker import SegmentScanWorker, BatchSegmentScanWorker

    win = MainWindow.__new__(MainWindow)
    win.sub_editor = MagicMock()
    win.sub_editor.all_segments = [
        {"id": "s1", "start": "00:00:01,000", "end": "00:00:03,000", "start_ms": 1000, "end_ms": 3000, "text": "Câu có chữ"},
        {"id": "s2", "start": "00:00:03,500", "end": "00:00:05,000", "start_ms": 3500, "end_ms": 5000, "text": ""},
    ]
    win.sub_editor.current_editor = MagicMock()
    win.sub_editor.current_editor.chk_boost_audio.isChecked.return_value = False
    win.sub_editor.current_editor.text_edit = MagicMock()
    win.sub_editor.current_editor.btn_scan = MagicMock()
    win.project_service = MagicMock()
    win.project_service.current_project = MagicMock(project_id="p1", video_path=str(tmp_path / "v.mp4"))
    win.current_vid = str(tmp_path / "v.mp4")
    (tmp_path / "v.mp4").write_bytes(b"dummy")
    win.get_current_video_path = lambda: str(tmp_path / "v.mp4")
    win.generation_panel = MagicMock()
    win.generation_panel._timing_settings.return_value = {
        "model_size": "large-v3",
        "compute_type": "int8_float16",
        "language": "ja",
        "use_vad": True,  # panel setting has use_vad=True, but rescan/batch scan must default to False
    }
    win.subtitle_whisper_service = MagicMock(device="cuda")

    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True), \
         patch("core.translation.core.hardware_detector.HardwareDetector.get_vram_usage", return_value=(1.0, 4.0)), \
         patch.object(SegmentScanWorker, "start"), \
         patch.object(BatchSegmentScanWorker, "start"):

        # 1. Quét lại câu có sẵn chữ (scan_mode == 'asr') -> use_vad phải là False
        win._on_segment_scan_requested("s1", 1000, 3000)
        assert win.scan_worker.scan_mode == "asr"
        assert win.scan_worker.request.use_vad is False

        # 2. Quét mốc timing cho câu trống (scan_mode == 'timing') -> use_vad phải là True
        win._on_segment_scan_requested("s2", 3500, 5000)
        assert win.scan_worker.scan_mode == "timing"
        assert win.scan_worker.request.use_vad is True

        # 3. Gen Sub hàng loạt các câu đang chọn -> use_vad phải là False
        win._on_batch_segment_scan_requested([0, 1])
        assert win._batch_scan_worker.request.use_vad is False


def test_subtitle_generation_panel_delete_model_button(qapp):
    from ui.subtitle_generation_panel import SubtitleGenerationPanel
    from core.services.model_manager import ModelManager
    from PySide6.QtWidgets import QMessageBox

    panel = SubtitleGenerationPanel(MagicMock())
    panel.show()
    assert hasattr(panel, "btn_delete_model")

    # Giả lập model large-v3 đã cài đặt
    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True):
        idx = panel.cmb_model.findData("large-v3")
        if idx >= 0:
            panel.cmb_model.setCurrentIndex(idx)
        panel._on_model_selection_changed()
        assert not panel.btn_delete_model.isHidden()
        assert panel.btn_download_model.isHidden()

    # Giả lập model chưa cài đặt
    with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
        panel._on_model_selection_changed()
        assert panel.btn_delete_model.isHidden()
        assert not panel.btn_download_model.isHidden()

    # Test bấm nút Xóa khi người dùng xác nhận Yes
    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True), \
         patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
         patch("core.services.model_manager.ModelManager.delete_model", return_value=True) as mock_delete:
        panel._on_delete_model_clicked()
        assert mock_delete.called
