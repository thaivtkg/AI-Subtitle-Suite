from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.project.project_state import TimingState
from core.project.transcription_context import TranscriptionContext
from core.services.model_manager import ModelManager
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.language_utils import (
    extract_glossary_hotwords,
    get_initial_prompt_for_language,
)
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.timing.timing_run_request import TimingRunRequest
from workers.TimingBatchWorker import TimingBatchWorker


def test_model_manager_specialized_models_discovery_and_snapshot_resolution(tmp_path):
    assert ModelManager.resolve_repo_id("kotoba-whisper-v2.0") == "kotoba-tech/kotoba-whisper-v2.0-faster"
    assert ModelManager.resolve_repo_id("kotoba-whisper-v2.2") == "RoachLin/kotoba-whisper-v2.2-faster"
    assert "kotoba-whisper-v2.0" not in ModelManager.SUPPORTED_MODELS

    snap = tmp_path / "models--kotoba-tech--kotoba-whisper-v2.0-faster" / "snapshots" / "rev1"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    (snap / "model.bin").write_bytes(b"bin")

    with patch("core.runtime.runtime_paths.RuntimePaths.get_models_dir", return_value=tmp_path):
        assert ModelManager.is_installed("kotoba-whisper-v2.0") is True
        assert ModelManager.is_installed("kotoba-whisper-v2.2") is False
        assert ModelManager.get_model_path_for_inference("kotoba-whisper-v2.0") == str(snap)
        assert ModelManager.get_model_path_for_inference("kotoba-whisper-v2.2") == "RoachLin/kotoba-whisper-v2.2-faster"


def test_language_utils_prompt_and_hotwords():
    assert get_initial_prompt_for_language("ja") == ""

    ctx = TranscriptionContext(
        context="Anime scene",
        glossary=["黒崎 -> Kurosaki", "御影 = Mikage", "黒崎 -> duplicate", "天城"],
    )
    assert extract_glossary_hotwords(ctx) == "黒崎 御影 天城"


def test_faster_whisper_ffmpeg_filter_and_kotoba_options(tmp_path):
    assert FasterWhisperService.build_ffmpeg_audio_filter(speech_filter=False, audio_boost=False) is None
    assert FasterWhisperService.build_ffmpeg_audio_filter(speech_filter=False, audio_boost=True) == "volume=2.0"
    assert FasterWhisperService.build_ffmpeg_audio_filter(speech_filter=True, audio_boost=False) == (
        "highpass=f=80,lowpass=f=7800,dynaudnorm=f=150:g=15"
    )

    service = FasterWhisperService(device="cpu")
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], SimpleNamespace(language="ja"))
    service.model = mock_model
    service._extract_batch_audio = lambda _req, _batch: ("dummy.wav", None)

    req = SubtitleGenerationRequest(
        request_id="req-kotoba",
        project_id="p1",
        source_fingerprint="fp",
        video_path="v.mp4",
        model_size="kotoba-whisper-v2.0",
        compute_type="int8",
        language=None,
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=True,
        condition_on_previous_text=True,
        speech_filter=True,
        hotwords="黒崎, 御影",
        patience=1.5,
        hallucination_silence_threshold=2.5,
        vad_speech_pad_ms=300,
        min_speech_duration_ms=120,
    )
    batch = SubtitleGenerationBatch("b1", 0, 5000, "RUNNING", 1, "", "")
    service.transcribe_batch(req, batch, lambda: False)

    kwargs = mock_model.transcribe.call_args.kwargs
    assert kwargs["language"] == "ja"
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["word_timestamps"] is False
    assert kwargs["initial_prompt"] is None
    assert kwargs["hotwords"] is None
    assert kwargs["patience"] == 1.5
    assert kwargs["hallucination_silence_threshold"] == 2.5
    assert kwargs["vad_parameters"]["speech_pad_ms"] == 300
    assert kwargs["vad_parameters"]["min_speech_duration_ms"] == 120


def test_timing_batch_worker_applies_tail_padding_without_overlap(tmp_path):
    dummy_vid = tmp_path / "clip.mp4"
    dummy_vid.write_bytes(b"video")

    class Word:
        def __init__(self, start, end):
            self.start = start
            self.end = end

    seg1 = SimpleNamespace(
        start=1.0,
        end=4.0,
        text="耳が腐ると思ったわ",
        no_speech_prob=0.0,
        avg_logprob=-0.2,
        words=[Word(1.0, 4.0)],
    )
    seg2 = SimpleNamespace(
        start=4.1,
        end=5.5,
        text="本当",
        no_speech_prob=0.0,
        avg_logprob=-0.2,
        words=[Word(4.1, 5.5)],
    )

    class FakeModel:
        def transcribe(self, _wav, **_kwargs):
            info = SimpleNamespace(duration=15.0, duration_after_vad=5.0, language="ja", language_probability=0.99)
            return [seg1, seg2], info

    req = TimingRunRequest(
        video_path=str(dummy_vid),
        start_ms=0,
        target_segment_count=2,
        language="ja",
        fix_overlap=True,
        overlap_gap_ms=50,
        tail_pad_ms=180,
        min_speech_duration_ms=120,
        patience=1.5,
        hallucination_silence_threshold=2.5,
    )
    worker = TimingBatchWorker(req)
    emitted = []
    worker.finished_signal.connect(lambda segs, _eof: emitted.extend(segs))

    with patch("faster_whisper.WhisperModel", return_value=FakeModel()), \
         patch("workers.TimingBatchWorker.subprocess.run", return_value=SimpleNamespace(returncode=0, stderr="")), \
         patch("workers.TimingBatchWorker.wave.open") as mock_wave, \
         patch("workers.TimingBatchWorker.os.path.exists", return_value=True), \
         patch("workers.TimingBatchWorker.os.path.getsize", return_value=4096):
        mock_wave.return_value.__enter__.return_value.getnframes.return_value = 16000 * 120
        mock_wave.return_value.__enter__.return_value.getframerate.return_value = 16000
        worker.run()

    assert len(emitted) == 2
    # Segment 2 extended tail by 180ms; segment 1 stays strictly >=50ms before segment 2
    assert emitted[0]["end_ms"] + 50 <= emitted[1]["start_ms"]
    assert emitted[1]["end_ms"] == 5500 + 180


def test_subtitle_generation_panel_specialized_model_box_and_rescan(qapp, tmp_path):
    from ui.subtitle_generation_panel import SubtitleGenerationPanel
    from ui.Gui import MainWindow

    gen_service = MagicMock()
    mock_project = MagicMock()
    mock_project.project_id = "p_spec"
    mock_project.source.path = str(tmp_path / "video.mp4")
    mock_project.source.fingerprint = "fp"
    mock_project.state.timing = TimingState()
    mock_project.state.task_mode = "asr"
    mock_project.transcription_context = TranscriptionContext(glossary=["黒崎 -> Kurosaki"])
    gen_service.project_service.current_project = mock_project
    gen_service.compile_prompt_context.return_value = SimpleNamespace(text="")

    with patch("core.services.model_manager.ModelManager.is_installed", side_effect=lambda m: m in ("large-v3", "kotoba-whisper-v2.0")):
        panel = SubtitleGenerationPanel(gen_service)
        assert hasattr(panel, "cmb_specialized_model")
        assert hasattr(panel, "btn_download_specialized_model")
        assert hasattr(panel, "btn_delete_specialized_model")

        idx_v20 = panel.cmb_specialized_model.findData("kotoba-whisper-v2.0")
        assert idx_v20 > 0
        panel.cmb_specialized_model.setCurrentIndex(idx_v20)

        assert panel._get_effective_model_size() == "kotoba-whisper-v2.0"
        req = panel._build_asr_request()
        assert req.model_size == "kotoba-whisper-v2.0"
        assert req.language == "ja"
        assert req.speech_filter is True
        assert req.patience == 1.5
        assert req.hallucination_silence_threshold == 2.5
        assert req.vad_speech_pad_ms == 350
        assert abs(req.vad_threshold - 0.25) < 1e-3
        assert abs(req.vad_max_speech_duration_s - 8.0) < 1e-3
        assert req.min_speech_duration_ms == 120
        assert req.hotwords == ""
        assert req.prompt_context == ""

        win = MainWindow.__new__(MainWindow)
        win.subtitle_whisper_service = MagicMock(device="cuda")
        with patch("core.translation.core.hardware_detector.HardwareDetector.get_vram_usage", return_value=(1.0, 4.0)):
            model_name, _ = win._resolve_rescan_model_and_compute(panel._timing_settings())
            assert model_name == "kotoba-whisper-v2.0"


def test_vad_params_hints_and_tooltips_adapt_to_selected_model(qapp, tmp_path):
    from ui.subtitle_generation_panel import SubtitleGenerationPanel

    gen_service = MagicMock()
    gen_service.project_service.current_project = None
    with patch("core.services.model_manager.ModelManager.is_installed", side_effect=lambda m: m == "large-v3"):
        panel = SubtitleGenerationPanel(gen_service)

        # 1. large-v3 uses shared Standard preset (350ms / 0.25 / 350ms / 8.0s) + model hints/tooltips
        assert panel.cmb_model.currentData() == "large-v3"
        assert panel.spin_min_silence.value() == 350
        assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
        assert panel.spin_speech_pad.value() == 350
        assert abs(panel.spin_max_speech.value() - 8.0) < 1e-3
        _, _, pad_hint_lbl = panel._vad_row_widgets["speech_pad"]
        assert "Large" in pad_hint_lbl.text()
        assert "large-v3" in panel.spin_vad_threshold.toolTip()

        # 2. Switch specialized model -> kotoba-whisper-v2.2 keeps shared Standard values, adapts hints & tooltips
        idx_k22 = panel.cmb_specialized_model.findData("kotoba-whisper-v2.2")
        assert idx_k22 > 0
        panel.cmb_specialized_model.setCurrentIndex(idx_k22)
        assert panel.spin_min_silence.value() == 350
        assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
        assert panel.spin_speech_pad.value() == 350
        assert abs(panel.spin_max_speech.value() - 8.0) < 1e-3
        _, _, min_sil_hint_lbl = panel._vad_row_widgets["min_silence"]
        assert "Kotoba" in min_sil_hint_lbl.text()
        assert "わ/よ/ね" in pad_hint_lbl.text()
        assert "kotoba-whisper-v2.2" in panel.spin_max_speech.toolTip()
        assert panel.cmb_vad_preset.itemText(panel.cmb_vad_preset.findData("standard")) == "Standard"

        # 3. Clear specialized model and pick small -> compact hints/tooltips with shared Standard values
        panel.cmb_specialized_model.setCurrentIndex(0)
        idx_small = panel.cmb_model.findData("small")
        panel.cmb_model.setCurrentIndex(idx_small)
        assert panel.spin_min_silence.value() == 350
        assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
        assert panel.spin_speech_pad.value() == 350
        assert abs(panel.spin_max_speech.value() - 8.0) < 1e-3
        assert "Tiny–Med" in pad_hint_lbl.text()
        assert "small" in panel.spin_speech_pad.toolTip()

        # 4. Restoring a saved project preserves saved custom values while refreshing guidance
        mock_project = MagicMock()
        mock_project.state.task_mode = "asr"
        mock_project.state.dirty = True
        mock_project.state.timing = TimingState(
            model_size="small",
            specialized_model="kotoba-whisper-v2.0",
            vad_preset="custom",
            min_silence_ms=250,
            vad_threshold=0.25,
            vad_speech_pad_ms=450,
            vad_max_speech_duration_s=8.5,
        )
        gen_service.project_service.current_project = mock_project
        panel.sync_timing_settings_from_project()
        assert panel.spin_min_silence.value() == 250
        assert panel.spin_speech_pad.value() == 450
        assert "kotoba-whisper-v2.0" in panel.spin_speech_pad.toolTip()


def test_model_configuration_combos_equal_width_and_no_symlink_guard(qapp):
    import os
    from ui.subtitle_generation_panel import SubtitleGenerationPanel

    gen_service = MagicMock()
    gen_service.project_service.current_project = None
    panel = SubtitleGenerationPanel(gen_service)
    panel.resize(450, 720)
    panel.show()
    qapp.processEvents()

    w_model = panel.cmb_model.width()
    assert w_model == 188
    assert panel.cmb_specialized_model.width() == w_model
    assert panel.cmb_compute.width() == w_model
    assert panel.cmb_language.width() == w_model
    assert panel.btn_download_model.fontMetrics().horizontalAdvance("Đang tải…") + 12 <= panel.btn_download_model.width()

    # Toggle installed/uninstalled buttons -> combo widths stay fixed and Download button fits inside panel
    with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
        panel._on_model_selection_changed()
        qapp.processEvents()
        assert panel.cmb_model.width() == w_model
        assert panel.cmb_specialized_model.width() == w_model
        dl_right = panel.btn_download_model.mapTo(panel, panel.btn_download_model.rect().topRight()).x()
        assert dl_right <= panel.width()

        # Selecting specialized model locks Model Size combo so 2 models cannot appear active in parallel
        idx_k20 = panel.cmb_specialized_model.findData("kotoba-whisper-v2.0")
        assert idx_k20 > 0
        panel.cmb_specialized_model.setCurrentIndex(idx_k20)
        qapp.processEvents()
        assert not panel.cmb_model.isEnabled()
        assert not panel.btn_download_model.isEnabled()
        spec_dl_right = panel.btn_download_specialized_model.mapTo(
            panel, panel.btn_download_specialized_model.rect().topRight()
        ).x()
        assert spec_dl_right <= panel.width()

        # Clearing specialized model unlocks Model Size again
        panel.cmb_specialized_model.setCurrentIndex(0)
        qapp.processEvents()
        assert panel.cmb_model.isEnabled()

    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True):
        panel._on_model_selection_changed()
        qapp.processEvents()
        assert panel.cmb_model.width() == w_model
        assert panel.cmb_compute.width() == w_model
        assert panel.cmb_language.width() == w_model

    if os.name == "nt":
        import huggingface_hub.file_download as fd
        orig = fd.are_symlinks_supported
        try:
            ModelManager.ensure_windows_hf_no_symlink()
            assert fd.are_symlinks_supported("C:\\") is False
        finally:
            fd.are_symlinks_supported = orig


def test_distilled_kotoba_models_disable_word_timestamps_everywhere():
    from types import SimpleNamespace
    from core.services.model_manager import ModelManager
    from core.subtitle_generation.faster_whisper_service import FasterWhisperService
    from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
    from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
    from core.timing.timing_run_request import TimingRunRequest
    from workers.TimingBatchWorker import TimingBatchWorker

    assert ModelManager.supports_word_timestamps("kotoba-whisper-v2.0") is False
    assert ModelManager.supports_word_timestamps("kotoba-whisper-v2.2") is False
    assert ModelManager.supports_word_timestamps("distil-large-v3") is False
    assert ModelManager.supports_word_timestamps("large-v3") is True
    assert ModelManager.supports_word_timestamps("large-v3-turbo") is True

    # TimingBatchWorker must strip word_timestamps + hallucination_silence_threshold for kotoba models
    kotoba_req = TimingRunRequest(
        video_path="dummy.mp4",
        start_ms=0,
        target_segment_count=5,
        model_size="kotoba-whisper-v2.0",
        compute_type="int8_float16",
        language="ja",
        initial_prompt="こんにちは。",
        hotwords="黒崎, 御影",
    )
    kotoba_worker = TimingBatchWorker(kotoba_req)
    kotoba_kw = kotoba_worker._build_transcribe_kwargs(
        "ja", vad_filter=True, word_timestamps=True
    )
    assert kotoba_kw["word_timestamps"] is False
    assert "hallucination_silence_threshold" not in kotoba_kw
    assert kotoba_kw.get("initial_prompt") is None
    assert kotoba_kw.get("hotwords") is None
    assert kotoba_kw["condition_on_previous_text"] is False

    # Standard large-v3 keeps word_timestamps, natural initial_prompt, and space-separated hotwords
    std_req = TimingRunRequest(
        video_path="dummy.mp4",
        start_ms=0,
        target_segment_count=5,
        model_size="large-v3",
        compute_type="int8_float16",
        language="ja",
        initial_prompt="こんにちは。",
        hotwords="黒崎, 御影",
    )
    std_kw = TimingBatchWorker(std_req)._build_transcribe_kwargs(
        "ja", vad_filter=True, word_timestamps=True
    )
    assert std_kw["word_timestamps"] is True
    assert std_kw["hallucination_silence_threshold"] == 1.0
    assert std_kw["initial_prompt"] == "こんにちは。"
    assert std_kw["hotwords"] == "黒崎 御影"

    # FasterWhisperService.transcribe_batch also disables word_timestamps when kotoba is loaded
    service = FasterWhisperService(device="cpu")
    captured_opts = {}

    class _FakeModel:
        def transcribe(self, _path, **opts):
            captured_opts.update(opts)
            return ([SimpleNamespace(start=0.0, end=1.2, text="テスト", words=None)], SimpleNamespace())

    service.model = _FakeModel()
    service.current_model_size = "kotoba-whisper-v2.0"
    service.current_compute_type = "int8"

    req = SubtitleGenerationRequest(
        request_id="r1",
        project_id="p1",
        source_fingerprint="fp1",
        video_path="dummy.mp4",
        model_size="kotoba-whisper-v2.0",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=380,
        word_timestamps=True,
        hallucination_silence_threshold=1.0,
    )
    batch = SubtitleGenerationBatch("b1", 0, 5000, "RUNNING", 1, "", "")
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        res = service.transcribe_batch(req, batch, is_cancelled=lambda: False)
    assert res.error is None
    assert captured_opts["word_timestamps"] is False
    assert len(res.segments) == 1
    assert res.segments[0].text == "テスト"


def test_timing_worker_vad_speech_relaxed_retry_and_monotonic_progress():
    from types import SimpleNamespace
    from core.timing.timing_run_request import TimingRunRequest
    from workers.TimingBatchWorker import TimingBatchWorker

    req = TimingRunRequest(
        video_path="dummy.mp4",
        start_ms=0,
        target_segment_count=5,
        model_size="kotoba-whisper-v2.0",
        compute_type="int8_float16",
        language="ja",
        vad_preset="standard",
        vad_threshold=0.30,
    )
    worker = TimingBatchWorker(req)
    emitted_pcts = []
    worker.progress_signal.connect(lambda pct, _msg: emitted_pcts.append(pct))

    # Progress must never jump backward from 8% -> 5% -> 8% across empty scan windows
    worker._last_emitted_pct = 0
    worker._emit_timing_progress(0, "Đang trích xuất âm thanh", min_pct=5)
    worker._emit_timing_progress(0, "", min_pct=8)
    worker._emit_timing_progress(0, "Đang trích xuất âm thanh", min_pct=5)
    worker._emit_timing_progress(0, "", min_pct=8)
    assert emitted_pcts == [5, 8, 8, 8]

    # When VAD detected speech (duration_after_vad=40.0s) yet first pass skipped on thresholds,
    # _transcribe_with_vad_retry retries with relaxed thresholds instead of returning [].
    calls = []
    fake_seg = SimpleNamespace(start=1.0, end=2.5, text="大丈夫", no_speech_prob=0.1, avg_logprob=-0.4, words=None)

    class _FakeWhisper:
        def transcribe(self, _wav, **kw):
            calls.append(dict(kw))
            if len(calls) == 1:
                return iter([]), SimpleNamespace(duration=120.0, duration_after_vad=40.0, language="ja", language_probability=1.0)
            return iter([fake_seg]), SimpleNamespace(duration=120.0, duration_after_vad=40.0, language="ja", language_probability=1.0)

    with patch("workers.TimingBatchWorker.ensure_silero_vad_anti_saturation_patch"):
        segs, _info = worker._transcribe_with_vad_retry(_FakeWhisper(), "chunk.wav", language="ja")
    assert len(calls) == 2
    assert calls[0]["no_speech_threshold"] == 0.6
    assert calls[1]["no_speech_threshold"] is None
    assert calls[1]["log_prob_threshold"] is None
    assert len(segs) == 1
    assert segs[0].text == "大丈夫"


def test_kotoba_coarse_segments_clipped_to_vad_speech_spans():
    from types import SimpleNamespace
    from core.timing.timing_run_request import TimingRunRequest
    from workers.TimingBatchWorker import TimingBatchWorker

    req = TimingRunRequest(
        video_path="dummy.mp4",
        start_ms=0,
        target_segment_count=5,
        model_size="kotoba-whisper-v2.0",
        compute_type="int8_float16",
        language="ja",
    )
    worker = TimingBatchWorker(req)
    # Silero VAD active-speech chunks: a 0.35s breath pause between chunks 1 & 2 (< 1.0s)
    # stays merged into one sentence, while the ~12.6s silence gap still splits cleanly.
    worker._active_vad_speech_spans = [(7.73, 8.68), (9.03, 10.66), (23.30, 24.54), (26.38, 30.34)]
    coarse_seg = SimpleNamespace(
        start=7.73, end=26.70, text="", no_speech_prob=0.1, avg_logprob=-0.4, words=None
    )
    ranges = worker._extract_valid_sub_ranges(coarse_seg, actual_start_ms=460000, current_start_ms=460000)
    assert ranges == [
        (467730, 470660),
        (483300, 484540),
        (486380, 486700),
    ]


def test_custom_vad_preset_persists_across_timing_run_reset_and_mode_switch(qapp):
    from core.project.project_state import TimingState
    from ui.subtitle_generation_panel import SubtitleGenerationPanel

    gen_service = MagicMock()
    mock_project = MagicMock()
    mock_project.state.task_mode = "timing"
    mock_project.state.dirty = True
    mock_project.state.timing = TimingState(
        model_size="large-v3",
        specialized_model="kotoba-whisper-v2.0",
    )
    gen_service.project_service.current_project = mock_project

    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True):
        panel = SubtitleGenerationPanel(gen_service)
        idx_k20 = panel.cmb_specialized_model.findData("kotoba-whisper-v2.0")
        assert idx_k20 > 0
        panel.cmb_specialized_model.setCurrentIndex(idx_k20)

        # User edits VAD parameters -> preset switches to "custom"
        panel.spin_min_silence.setValue(240)
        panel.spin_vad_threshold.setValue(0.22)
        panel.spin_speech_pad.setValue(280)
        panel.spin_max_speech.setValue(7.5)
        assert panel.cmb_vad_preset.currentData() == "custom"

        # Simulate timing job start -> finish (_reset_ui_state) -> mode toggle
        panel._set_ui_state_running()
        panel._reset_ui_state()
        assert panel.cmb_vad_preset.currentData() == "custom"
        assert panel.spin_min_silence.value() == 240
        assert abs(panel.spin_vad_threshold.value() - 0.22) < 1e-3
        assert panel.spin_speech_pad.value() == 280
        assert abs(panel.spin_max_speech.value() - 7.5) < 1e-3

        # Switching specialized model back to None while custom stays custom
        panel.cmb_specialized_model.setCurrentIndex(0)
        assert panel.cmb_vad_preset.currentData() == "custom"
        assert panel.spin_min_silence.value() == 240


def test_segment_scan_request_and_tier3_omit_prompts_for_kotoba(tmp_path):
    from types import SimpleNamespace
    from core.project.transcription_context import TranscriptionContext
    from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
    from core.subtitle_generation.subtitle_generation_result import (
        SubtitleGenerationResult,
        WhisperSegmentResult,
    )
    from ui.Gui import MainWindow
    from workers.SegmentScanWorker import SegmentScanWorker

    win = MainWindow.__new__(MainWindow)
    win.sub_editor = None
    win.subtitle_whisper_service = MagicMock(device="cpu")
    win.generation_panel = MagicMock()
    win.generation_panel.cmb_language.currentText.return_value = "ja"

    project = MagicMock()
    project.project_id = "p_scan"
    project.source.fingerprint = "fp_scan"
    project.transcription_context = TranscriptionContext(glossary=["黒崎 -> Kurosaki"])

    with patch("core.services.model_manager.ModelManager.is_installed", return_value=True):
        req_kotoba = win._build_segment_scan_request(
            "scan_k",
            {
                "model_size": "large-v3",
                "specialized_model": "kotoba-whisper-v2.2",
                "compute_type": "int8",
                "language": "ja",
            },
            str(tmp_path / "v.mp4"),
            project,
        )
        assert req_kotoba.model_size == "kotoba-whisper-v2.2"
        assert req_kotoba.prompt_context == ""
        assert req_kotoba.hotwords == ""

        req_large = win._build_segment_scan_request(
            "scan_l",
            {
                "model_size": "large-v3",
                "specialized_model": "",
                "compute_type": "int8",
                "language": "ja",
            },
            str(tmp_path / "v.mp4"),
            project,
        )
        assert req_large.model_size == "large-v3"
        assert req_large.prompt_context == ""
        assert req_large.hotwords == "黒崎"

    # SegmentScanWorker must not expand context_window or inject context_prompt on kotoba Tier 3
    captured_tiers = []

    class FakeService:
        def load_model(self, _model_size, _compute_type):
            pass

        def transcribe_batch(self, request, batch, _check_cancel):
            captured_tiers.append((request.use_vad, request.word_timestamps, request.prompt_context, batch.start_ms, batch.end_ms))
            if len(captured_tiers) < 3:
                return SubtitleGenerationResult(batch_id=batch.batch_id, segments=[], error=None)
            return SubtitleGenerationResult(
                batch_id=batch.batch_id,
                segments=[WhisperSegmentResult(start_ms=batch.start_ms, end_ms=batch.end_ms, text="大丈夫だよ")],
                error=None,
            )

    completed = []
    worker = SegmentScanWorker(
        segment_id="seg-k",
        start_ms=4000,
        end_ms=4800,
        request=SubtitleGenerationRequest(
            request_id="scan_k22",
            project_id="p_scan",
            source_fingerprint="fp_scan",
            video_path="dummy.mp4",
            model_size="kotoba-whisper-v2.2",
            compute_type="int8",
            language="ja",
            use_vad=True,
            min_silence_ms=350,
            word_timestamps=False,
        ),
        whisper_service=FakeService(),
        context_window=(1000, 7000),
        context_prompt="前の台詞",
    )
    worker.finished_signal.connect(lambda sid, txt: completed.append((sid, txt)))
    worker.run()

    assert len(captured_tiers) == 3
    tier3_vad, tier3_word_ts, tier3_prompt, tier3_start, tier3_end = captured_tiers[2]
    assert tier3_vad is False
    assert tier3_word_ts is False
    assert tier3_prompt == ""
    assert tier3_start == 3850
    assert tier3_end == 4950
    assert completed == [("seg-k", "大丈夫だよ")]


def test_faster_whisper_distilled_strips_ja_filler_and_retries_clean_on_empty_tier3():
    from types import SimpleNamespace
    from core.subtitle_generation.faster_whisper_service import FasterWhisperService
    from core.subtitle_generation.language_utils import get_initial_prompt_for_language
    from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
    from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest

    service = FasterWhisperService(device="cpu")
    call_opts = []

    class _FakeModel:
        def transcribe(self, _path, **opts):
            call_opts.append(dict(opts))
            if len(call_opts) == 1:
                return (iter([]), SimpleNamespace(language="ja"))
            return (iter([SimpleNamespace(start=0.1, end=1.1, text="ごめん", words=None)]), SimpleNamespace(language="ja"))

    service.model = _FakeModel()
    service.current_model_size = "kotoba-whisper-v2.0"
    service.current_compute_type = "int8"

    req = SubtitleGenerationRequest(
        request_id="r_tier3",
        project_id="p1",
        source_fingerprint="fp1",
        video_path="dummy.mp4",
        model_size="kotoba-whisper-v2.0",
        compute_type="int8",
        language="ja",
        use_vad=False,
        min_silence_ms=350,
        word_timestamps=False,
        prompt_context=get_initial_prompt_for_language("ja"),
        hotwords="黒崎",
        no_speech_threshold=0.85,
        log_prob_threshold=-1.5,
    )
    batch = SubtitleGenerationBatch("b_t3", 3850, 4950, "RUNNING", 1, "", "")
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        res = service.transcribe_batch(req, batch, is_cancelled=lambda: False)

    assert len(call_opts) == 2
    assert call_opts[0].get("initial_prompt") is None
    assert call_opts[0].get("hotwords") is None
    assert call_opts[1].get("initial_prompt") is None
    assert call_opts[1].get("hotwords") is None
    assert call_opts[1]["no_speech_threshold"] is None
    assert call_opts[1]["log_prob_threshold"] is None
    assert [s.text for s in res.segments] == ["ごめん"]


def test_timing_worker_progressive_slices_early_stop_and_cancel(tmp_path):
    import wave
    from types import SimpleNamespace
    from core.timing.timing_run_request import TimingRunRequest
    from workers.TimingBatchWorker import TimingBatchWorker

    wav_path = str(tmp_path / "long_120s.wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\0" * 16000 * 120 * 2)

    req = TimingRunRequest(
        video_path="dummy.mp4",
        start_ms=0,
        target_segment_count=5,
        model_size="large-v3",
        compute_type="int8_float16",
        language="ja",
        patience=1.5,
    )
    worker = TimingBatchWorker(req)
    kw = worker._build_transcribe_kwargs("ja", vad_filter=True, word_timestamps=True)
    assert kw["temperature"] == (0.0, 0.2)
    assert kw["best_of"] == 2
    assert kw["patience"] == 1.0

    # 1) Stops after first 25s slice once 5 segments are collected (does not decode remaining 95s)
    slice_calls = []

    class _EarlyStopModel:
        def transcribe(self, _wav, **_kw):
            slice_calls.append(len(slice_calls) + 1)
            segs = [
                SimpleNamespace(start=float(i * 3), end=float(i * 3 + 1.5), text="あ", no_speech_prob=0.1, avg_logprob=-0.3, words=None)
                for i in range(5)
            ]
            return iter(segs), SimpleNamespace(duration=25.0, duration_after_vad=10.0, language="ja", language_probability=1.0)

    count = 0

    def _on_seg(_seg):
        nonlocal count
        count += 1
        return count >= 5

    segs, info = worker._transcribe_progressive_slices(_EarlyStopModel(), wav_path, kw, on_segment=_on_seg)
    assert len(slice_calls) == 1
    assert len(segs) == 5
    assert info.duration == 120.0

    # 2) Stops immediately when worker.cancel() is called before generator iteration
    cancel_calls = []

    class _CancelModel:
        def transcribe(self, _wav, **_kw):
            cancel_calls.append(1)
            worker.cancel()
            return iter([
                SimpleNamespace(start=1.0, end=2.5, text="い", no_speech_prob=0.1, avg_logprob=-0.3, words=None)
            ]), SimpleNamespace(duration=25.0, duration_after_vad=2.0, language="ja", language_probability=1.0)

    segs_c, _ = worker._transcribe_progressive_slices(_CancelModel(), wav_path, kw)
    assert len(cancel_calls) == 1
    assert segs_c == []

    # 3) Stops between slices when worker.cancel() is called during slice 1 emission
    worker2 = TimingBatchWorker(req)
    cancel_between_calls = []

    class _SliceCancelModel:
        def transcribe(self, _wav, **_kw):
            cancel_between_calls.append(1)
            return iter([
                SimpleNamespace(start=1.0, end=2.5, text="う", no_speech_prob=0.1, avg_logprob=-0.3, words=None)
            ]), SimpleNamespace(duration=25.0, duration_after_vad=2.0, language="ja", language_probability=1.0)

    def _cancel_on_seg(_seg):
        worker2.cancel()
        return False

    segs_b, _ = worker2._transcribe_progressive_slices(_SliceCancelModel(), wav_path, kw, on_segment=_cancel_on_seg)
    assert len(cancel_between_calls) == 1
    assert len(segs_b) == 1


def test_anime_ja_shared_and_model_specific_vad_presets(qapp, tmp_path):
    """3 fixed Anime JA VAD presets: shared always visible, model-specific presets filtered strictly per model."""
    from core.project.project_state import TimingState
    from ui.subtitle_generation_panel import SubtitleGenerationPanel

    gen_svc = MagicMock()
    mock_project = MagicMock()
    mock_project.project_id = "proj_anime_ja_presets"
    mock_project.source.path = str(tmp_path / "anime.mp4")
    mock_project.source.fingerprint = "fp_anime"
    mock_project.state.task_mode = "timing"
    mock_project.state.dirty = True
    mock_project.state.timing = TimingState()
    gen_svc.project_service.current_project = mock_project
    gen_svc.compile_prompt_context.return_value = MagicMock(text="")
    gen_svc.is_running.return_value = False

    panel = SubtitleGenerationPanel(gen_svc)

    def _preset_keys():
        return [panel.cmb_vad_preset.itemData(i) for i in range(panel.cmb_vad_preset.count())]

    def _preset_labels():
        return [panel.cmb_vad_preset.itemText(i) for i in range(panel.cmb_vad_preset.count())]

    # 1) large-v3 shows Standard (shared) + cfg9 + large-v3 preset + Live-Action, hides kotoba preset
    panel.cmb_specialized_model.setCurrentIndex(0)
    idx_lv3 = panel.cmb_model.findData("large-v3")
    assert idx_lv3 >= 0
    panel.cmb_model.setCurrentIndex(idx_lv3)
    keys_lv3 = _preset_keys()
    assert keys_lv3 == ["standard", "cfg9", "anime_ja_large_v3", "live_action", "custom"]
    assert panel.cmb_vad_preset.currentData() == "standard"
    assert panel.spin_min_silence.value() == 350
    assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
    assert panel.spin_speech_pad.value() == 350
    assert abs(panel.spin_max_speech.value() - 8.0) < 1e-3
    assert panel.chk_condition_on_previous_text.isChecked() is True
    ts_std = panel._timing_settings()
    assert ts_std["vad_preset"] == "standard"
    assert ts_std["min_silence_ms"] == 350
    assert abs(ts_std["vad_threshold"] - 0.25) < 1e-3
    assert ts_std["vad_speech_pad_ms"] == 350
    assert abs(ts_std["vad_max_speech_duration_s"] - 8.0) < 1e-3

    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("anime_ja_large_v3"))
    assert panel.spin_min_silence.value() == 300
    assert abs(panel.spin_vad_threshold.value() - 0.30) < 1e-3
    assert panel.spin_speech_pad.value() == 250
    assert abs(panel.spin_max_speech.value() - 6.0) < 1e-3
    assert panel.chk_word_timestamps.isChecked() is True
    assert panel.chk_condition_on_previous_text.isChecked() is True
    ts_lv3 = panel._timing_settings()
    assert ts_lv3["vad_preset"] == "anime_ja_large_v3"
    assert ts_lv3["min_silence_ms"] == 300
    assert abs(ts_lv3["vad_threshold"] - 0.30) < 1e-3
    assert ts_lv3["vad_speech_pad_ms"] == 250
    assert abs(ts_lv3["vad_max_speech_duration_s"] - 6.0) < 1e-3
    assert ts_lv3["condition_on_previous_text"] is True

    # Selecting Live-Action / Tokusatsu automatically unchecks condition_on_previous_text and sets 300/0.35/250/6.0
    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("live_action"))
    assert "Tokusatsu" in panel.cmb_vad_preset.currentText()
    assert panel.spin_min_silence.value() == 300
    assert abs(panel.spin_vad_threshold.value() - 0.35) < 1e-3
    assert panel.spin_speech_pad.value() == 250
    assert abs(panel.spin_max_speech.value() - 6.0) < 1e-3
    assert panel.chk_condition_on_previous_text.isChecked() is False

    # Re-select large-v3-only preset before switching model to verify model-specific fallback -> standard
    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("anime_ja_large_v3"))

    # 2) Switching to kotoba-whisper-v2.0 hides large-v3 preset, shows kotoba + Standard, falls back to Standard
    idx_k20 = panel.cmb_specialized_model.findData("kotoba-whisper-v2.0")
    assert idx_k20 > 0
    panel.cmb_specialized_model.setCurrentIndex(idx_k20)
    keys_k20 = _preset_keys()
    assert keys_k20 == ["standard", "cfg9", "anime_ja_kotoba", "live_action", "custom"]
    assert panel.cmb_vad_preset.currentData() == "standard"

    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("anime_ja_kotoba"))
    assert panel.spin_min_silence.value() == 350
    assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
    assert panel.spin_speech_pad.value() == 400
    assert abs(panel.spin_max_speech.value() - 10.0) < 1e-3
    assert panel.chk_word_timestamps.isChecked() is False
    assert panel.chk_condition_on_previous_text.isChecked() is False
    req_k20 = panel._build_asr_request()
    assert req_k20.min_silence_ms == 350
    assert abs(req_k20.vad_threshold - 0.25) < 1e-3
    assert req_k20.vad_speech_pad_ms == 400
    assert abs(req_k20.vad_max_speech_duration_s - 10.0) < 1e-3

    # Also kotoba-whisper-v2.2 keeps anime_ja_kotoba visible and selected
    idx_k22 = panel.cmb_specialized_model.findData("kotoba-whisper-v2.2")
    assert idx_k22 > 0
    panel.cmb_specialized_model.setCurrentIndex(idx_k22)
    assert "anime_ja_kotoba" in _preset_keys()
    assert panel.cmb_vad_preset.currentData() == "anime_ja_kotoba"

    # 3) Standard works on every model (small, large-v3-turbo) with shared values and hides model-specific presets
    panel.cmb_specialized_model.setCurrentIndex(0)
    panel.cmb_model.setCurrentIndex(panel.cmb_model.findData("small"))
    assert _preset_keys() == ["standard", "cfg9", "live_action", "custom"]
    assert panel.cmb_vad_preset.currentData() == "standard"
    assert panel.spin_min_silence.value() == 350
    assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
    assert panel.spin_speech_pad.value() == 350
    assert abs(panel.spin_max_speech.value() - 8.0) < 1e-3

    panel.cmb_model.setCurrentIndex(panel.cmb_model.findData("large-v3-turbo"))
    assert _preset_keys() == ["standard", "cfg9", "live_action", "custom"]
    assert panel.cmb_vad_preset.currentData() == "standard"

    # 4) Restoring project state with specialized kotoba preset restores both items and selection
    mock_project.state.timing = TimingState(
        model_size="kotoba-whisper-v2.0",
        specialized_model="kotoba-whisper-v2.0",
        vad_preset="anime_ja_kotoba",
        min_silence_ms=350,
        vad_threshold=0.25,
        vad_speech_pad_ms=400,
        vad_max_speech_duration_s=10.0,
    )
    panel.sync_timing_settings_from_project()
    assert panel.cmb_vad_preset.currentData() == "anime_ja_kotoba"
    assert panel.spin_min_silence.value() == 350
    assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
    assert panel.spin_speech_pad.value() == 400
    assert abs(panel.spin_max_speech.value() - 10.0) < 1e-3


def test_ja_hidden_initial_prompt_hotwords_and_natural_formatting():
    from types import SimpleNamespace
    from core.subtitle_generation.faster_whisper_service import FasterWhisperService
    from core.subtitle_generation.language_utils import (
        format_whisper_initial_prompt,
        get_default_hotwords_for_language,
        get_initial_prompt_for_language,
    )
    from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
    from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest

    # 1) Japanese Terminology prompt formats naturally with '、' (no English prefix/period), English stays intact
    assert format_whisper_initial_prompt("Terminology: 黒崎 -> Kurosaki, 御影.", "ja") == "黒崎、御影"
    assert format_whisper_initial_prompt("Terminology: 先輩, 後輩. Context: 会話", "ja") == "先輩、後輩。会話"
    assert format_whisper_initial_prompt("Terminology: Demacia.", "en") == "Terminology: Demacia."

    # 2) Hidden JA prompt + hotwords are completely removed; large-v3 isolates Glossary -> space-separated hotwords, kotoba forces None
    assert get_initial_prompt_for_language("ja") == ""
    assert get_default_hotwords_for_language("ja") == ""

    service = FasterWhisperService(device="cpu")
    captured = {}

    class _CapModel:
        def transcribe(self, _wav, **opts):
            captured.clear()
            captured.update(opts)
            return iter([SimpleNamespace(start=0.0, end=1.0, text="テスト", words=None)]), SimpleNamespace(language="ja")

    service.model = _CapModel()
    batch = SubtitleGenerationBatch("b1", 0, 2000, "RUNNING", 1, "", "")
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        # large-v3 receives NO initial_prompt when only Glossary terms exist, and space-separated hotwords
        service.current_model_size = "large-v3"
        req_lv3 = SubtitleGenerationRequest(
            request_id="r_lv3",
            project_id="p1",
            source_fingerprint="fp1",
            video_path="v.mp4",
            model_size="large-v3",
            compute_type="int8",
            language="ja",
            use_vad=False,
            min_silence_ms=300,
            word_timestamps=True,
            prompt_context="Terminology: 黒崎 -> Kurosaki, 御影.",
            hotwords="黒崎, 御影",
        )
        service.transcribe_batch(req_lv3, batch, is_cancelled=lambda: False)
        assert captured.get("initial_prompt") is None
        assert captured["hotwords"] == "黒崎 御影"

        # kotoba-whisper ALWAYS forces initial_prompt=None and hotwords=None
        service.current_model_size = "kotoba-whisper-v2.0"
        req_k = SubtitleGenerationRequest(
            request_id="r_k",
            project_id="p1",
            source_fingerprint="fp1",
            video_path="v.mp4",
            model_size="kotoba-whisper-v2.0",
            compute_type="int8",
            language="ja",
            use_vad=False,
            min_silence_ms=350,
            word_timestamps=False,
            prompt_context="Trường học Nhật Bản.",
            hotwords="黒崎, 御影",
        )
        service.transcribe_batch(req_k, batch, is_cancelled=lambda: False)
        assert captured.get("initial_prompt") is None
        assert captured.get("hotwords") is None



