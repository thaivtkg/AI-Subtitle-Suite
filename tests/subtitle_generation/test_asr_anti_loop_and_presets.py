from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.project.project_state import TimingState
from core.project.transcription_context import TranscriptionContext
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.timing.timing_batch_service import TimingBatchService
from core.timing.timing_checkpoint import TimingCheckpoint
from core.timing.timing_run_request import TimingRunRequest
from ui.Gui import MainWindow
from ui.dialogs.asr_config_dialogs import AsrVadConfigDialog
from ui.subtitle_generation_panel import SubtitleGenerationPanel
from workers.SegmentScanWorker import BatchSegmentScanWorker, resolve_tier3_context
from workers.TimingBatchWorker import TimingBatchWorker


def _make_panel(tmp_path):
    gen_svc = MagicMock()
    mock_project = MagicMock()
    mock_project.project_id = "proj_anti_loop"
    mock_project.source.path = str(tmp_path / "video.mp4")
    mock_project.source.fingerprint = "fp_anti_loop"
    mock_project.transcription_context = TranscriptionContext(glossary=["黒崎 -> Kurosaki"])
    mock_project.state.task_mode = "asr"
    mock_project.state.dirty = True
    mock_project.state.timing = TimingState()
    gen_svc.project_service.current_project = mock_project
    gen_svc.compile_prompt_context.return_value = MagicMock(text="Terminology: 黒崎 -> Kurosaki.")
    gen_svc.is_running.return_value = False
    return SubtitleGenerationPanel(gen_svc), mock_project


def test_presets_values_and_condition_checkbox_behavior_in_dialog(qapp, tmp_path):
    panel, project = _make_panel(tmp_path)

    # Select large-v3
    panel.cmb_specialized_model.setCurrentIndex(0)
    panel.cmb_model.setCurrentIndex(panel.cmb_model.findData("large-v3"))

    # Dialog hosts asr_vad_group containing chk_condition_on_previous_text
    dlg = AsrVadConfigDialog(panel.asr_vad_group)
    assert hasattr(panel, "chk_condition_on_previous_text")
    assert panel.chk_condition_on_previous_text.parent() is panel.asr_vad_group

    # 1. Anime JA - large-v3: 300ms / 0.30 / 250ms / 6.0s / condition=True
    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("anime_ja_large_v3"))
    assert panel.spin_min_silence.value() == 300
    assert abs(panel.spin_vad_threshold.value() - 0.30) < 1e-3
    assert panel.spin_speech_pad.value() == 250
    assert abs(panel.spin_max_speech.value() - 6.0) < 1e-3
    assert panel.chk_condition_on_previous_text.isChecked() is True

    # 2. Live-Action / Tokusatsu (18+): 300ms / 0.35 / 250ms / 6.0s / condition=False
    idx_la = panel.cmb_vad_preset.findData("live_action")
    assert idx_la >= 0
    assert "Tokusatsu" in panel.cmb_vad_preset.itemText(idx_la)
    panel.cmb_vad_preset.setCurrentIndex(idx_la)
    assert panel.spin_min_silence.value() == 300
    assert abs(panel.spin_vad_threshold.value() - 0.35) < 1e-3
    assert panel.spin_speech_pad.value() == 250
    assert abs(panel.spin_max_speech.value() - 6.0) < 1e-3
    assert panel.chk_condition_on_previous_text.isChecked() is False

    # Manual toggle allowed even when switching spinboxes to Custom
    panel.chk_condition_on_previous_text.setChecked(True)
    panel.spin_vad_threshold.setValue(0.42)
    assert panel.cmb_vad_preset.currentData() == "custom"
    assert panel.chk_condition_on_previous_text.isChecked() is True

    panel.chk_condition_on_previous_text.setChecked(False)
    assert panel.chk_condition_on_previous_text.isChecked() is False
    assert project.state.timing.condition_on_previous_text is False

    # 3. Switching to kotoba preset auto-unchecks condition_on_previous_text and sets 350/0.25/400/10.0
    panel.cmb_specialized_model.setCurrentIndex(panel.cmb_specialized_model.findData("kotoba-whisper-v2.0"))
    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("anime_ja_kotoba"))
    assert panel.spin_min_silence.value() == 350
    assert abs(panel.spin_vad_threshold.value() - 0.25) < 1e-3
    assert panel.spin_speech_pad.value() == 400
    assert abs(panel.spin_max_speech.value() - 10.0) < 1e-3
    assert panel.chk_condition_on_previous_text.isChecked() is False
    dlg.close()


def test_decoder_loop_suppression_large_v3_only_and_compression_drop(tmp_path):
    service = FasterWhisperService(device="cpu")
    captured = {}

    class _FakeModel:
        def __init__(self, segments):
            self._segments = segments

        def transcribe(self, _wav, **opts):
            captured.clear()
            captured.update(opts)
            return iter(self._segments), SimpleNamespace(language="ja")

    batch = SubtitleGenerationBatch("b1", 0, 10000, "RUNNING", 1, "", "")
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        # 1. large-v3 receives repetition_penalty=1.1, no_repeat_ngram_size=3, and drops compression_ratio > 2.4
        service.current_model_size = "large-v3"
        service.model = _FakeModel([
            SimpleNamespace(start=0.5, end=2.0, text="ああああああああ", compression_ratio=3.1, temperature=1.0, words=None),
            SimpleNamespace(start=2.5, end=4.0, text="大丈夫だよ", compression_ratio=1.2, temperature=0.0, words=None),
        ])
        req_lv3 = SubtitleGenerationRequest(
            request_id="r1",
            project_id="p1",
            source_fingerprint="fp1",
            video_path="v.mp4",
            model_size="large-v3",
            compute_type="int8",
            language="ja",
            use_vad=True,
            min_silence_ms=300,
            word_timestamps=True,
            condition_on_previous_text=False,
            prompt_context="Terminology: 黒崎 -> Kurosaki.",
            hotwords="黒崎",
        )
        res_lv3 = service.transcribe_batch(req_lv3, batch, lambda: False)
        assert captured["repetition_penalty"] == 1.1
        assert captured["no_repeat_ngram_size"] == 3
        assert captured["compression_ratio_threshold"] == 2.4
        assert captured["no_speech_threshold"] == 0.6
        assert captured["condition_on_previous_text"] is False
        assert captured.get("initial_prompt") is None
        assert captured["hotwords"] == "黒崎"
        assert [s.text for s in res_lv3.segments] == ["大丈夫だよ"]

        # 2. kotoba-whisper MUST NOT receive repetition_penalty / no_repeat_ngram_size, and keeps condition=False
        service.current_model_size = "kotoba-whisper-v2.0"
        service.model = _FakeModel([
            SimpleNamespace(start=0.5, end=2.0, text="聞こえる？", compression_ratio=1.1, words=None),
        ])
        req_k = SubtitleGenerationRequest(
            request_id="r2",
            project_id="p1",
            source_fingerprint="fp1",
            video_path="v.mp4",
            model_size="kotoba-whisper-v2.0",
            compute_type="int8",
            language="ja",
            use_vad=True,
            min_silence_ms=350,
            word_timestamps=False,
            condition_on_previous_text=True,  # Backend must override to False for kotoba!
        )
        service.transcribe_batch(req_k, batch, lambda: False)
        assert "repetition_penalty" not in captured
        assert "no_repeat_ngram_size" not in captured
        assert captured["condition_on_previous_text"] is False
        assert captured["word_timestamps"] is False

    # 3. TimingBatchWorker also obeys large-v3-only decoder params and request condition_on_previous_text
    lv3_timing_kw = TimingBatchWorker(
        TimingRunRequest(
            video_path="v.mp4",
            start_ms=0,
            target_segment_count=5,
            model_size="large-v3",
            condition_on_previous_text=False,
        )
    )._build_transcribe_kwargs("ja", vad_filter=True, word_timestamps=True)
    assert lv3_timing_kw["repetition_penalty"] == 1.1
    assert lv3_timing_kw["no_repeat_ngram_size"] == 3
    assert lv3_timing_kw["compression_ratio_threshold"] == 2.4
    assert lv3_timing_kw["condition_on_previous_text"] is False
    assert lv3_timing_kw["word_timestamps"] is True

    kotoba_timing_kw = TimingBatchWorker(
        TimingRunRequest(
            video_path="v.mp4",
            start_ms=0,
            target_segment_count=5,
            model_size="kotoba-whisper-v2.2",
            condition_on_previous_text=True,
        )
    )._build_transcribe_kwargs("ja", vad_filter=True, word_timestamps=True)
    assert "repetition_penalty" not in kotoba_timing_kw
    assert "no_repeat_ngram_size" not in kotoba_timing_kw
    assert kotoba_timing_kw["condition_on_previous_text"] is False
    assert kotoba_timing_kw["word_timestamps"] is False


def test_post_processing_case_a_and_case_b_word_end_recovery_and_context_break():
    class _Word:
        def __init__(self, word, start, end):
            self.word = word
            self.start = start
            self.end = end

    # Case A1: pure filler + single char repetition -> ""
    cleaned_a1, had_a1 = SubtitleGenerationValidator.sanitize_repetition_text("ええ、ああああああああ")
    assert cleaned_a1 == "" and had_a1 is True

    # Case A2: filler + phrase repetition -> ""
    cleaned_a2, had_a2 = SubtitleGenerationValidator.sanitize_repetition_text("あっ、ええと、ええと、ええと、ええと")
    assert cleaned_a2 == "" and had_a2 is True

    # Case B1: valid dialogue + separated phrase repetition tail + word.end recovery
    words_b1 = [
        _Word("やめて", 10.0, 10.72),
        _Word("、", 10.72, 10.80),
        _Word("ええと", 11.40, 12.10),
        _Word("、ええと", 12.20, 13.00),
        _Word("、ええと", 13.10, 14.00),
        _Word("、ええと", 14.10, 18.50),
    ]
    cleaned_b1, kept_b1, new_end_b1, had_b1 = SubtitleGenerationValidator.clean_repetition_segment(
        "やめて、ええと、ええと、ええと、ええと",
        words=words_b1,
        start_val=10.0,
        end_val=18.5,
        words_in_ms=False,
    )
    assert had_b1 is True
    assert cleaned_b1 == "やめて"
    assert [w.word for w in kept_b1] == ["やめて"]
    assert abs(new_end_b1 - 10.77) < 1e-4  # 10.72 + 0.05s safety pad

    # Case B2: valid dialogue + single char repetition directly attached
    words_b2 = [_Word("やめて", 1.0, 1.5), _Word("ああああああ", 1.5, 5.2)]
    cleaned_b2, kept_b2, new_end_b2, had_b2 = SubtitleGenerationValidator.clean_repetition_segment(
        "やめてああああああ",
        words=words_b2,
        start_val=1.0,
        end_val=5.2,
        words_in_ms=False,
    )
    assert cleaned_b2 == "やめて"
    assert abs(new_end_b2 - 1.55) < 1e-4

    # Real dialogue with normal ellipsis must NOT be falsely chopped
    clean_ok, had_ok = SubtitleGenerationValidator.sanitize_repetition_text("待って......")
    assert clean_ok == "待って......" and had_ok is False

    # FasterWhisperService.transcribe_batch applies both Case A and Case B with word.end recovery
    service = FasterWhisperService(device="cpu")
    service.current_model_size = "large-v3"
    service.model = MagicMock()
    service.model.transcribe.return_value = (
        iter([
            SimpleNamespace(start=0.5, end=3.0, text="ええ、ああああああ", words=[_Word("ええ、ああああああ", 0.5, 3.0)]),
            SimpleNamespace(start=10.0, end=18.5, text="やめて、ええと、ええと、ええと、ええと", words=words_b1),
        ]),
        SimpleNamespace(language="ja"),
    )
    req = SubtitleGenerationRequest(
        request_id="r_pp",
        project_id="p1",
        source_fingerprint="fp1",
        video_path="v.mp4",
        model_size="large-v3",
        compute_type="int8",
        language="ja",
        use_vad=False,
        min_silence_ms=300,
        word_timestamps=True,
    )
    batch = SubtitleGenerationBatch("b_pp", 0, 20000, "RUNNING", 1, "", "")
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        out = service.transcribe_batch(req, batch, lambda: False)
    assert len(out.segments) == 1
    assert out.segments[0].text == "やめて"
    assert out.segments[0].start_ms == 10000
    assert out.segments[0].end_ms == 10770

    # TimingBatchWorker._extract_valid_sub_ranges also drops Case A and trims Case B end_ms
    worker = TimingBatchWorker(
        TimingRunRequest(
            video_path="v.mp4",
            start_ms=0,
            target_segment_count=5,
            model_size="large-v3",
            min_silence_ms=300,
        )
    )
    assert worker._extract_valid_sub_ranges(
        SimpleNamespace(start=0.5, end=3.0, text="ええ、ああああああ", no_speech_prob=0.1, avg_logprob=-0.2, words=None),
        0,
        0,
    ) == []
    ranges_b = worker._extract_valid_sub_ranges(
        SimpleNamespace(start=10.0, end=18.5, text="やめて、ええと、ええと、ええと、ええと", no_speech_prob=0.1, avg_logprob=-0.2, words=words_b1),
        0,
        0,
    )
    assert ranges_b == [(10000, 10720)]

    # resolve_tier3_context strips Case A / Case B tails from previous sentences
    segs_for_ctx = [
        {"id": "1", "start_ms": 0, "end_ms": 2000, "text": "ええ、ああああああ"},
        {"id": "2", "start_ms": 2100, "end_ms": 4000, "text": "やめてああああああ"},
        {"id": "3", "start_ms": 4100, "end_ms": 6000, "text": ""},
    ]
    _, ctx_prompt = resolve_tier3_context(segs_for_ctx, "3", 4100, 6000)
    assert ctx_prompt == "やめて"

    # BatchSegmentScanWorker breaks context propagation when an earlier segment fails/drops as hallucination
    captured_prompts = []

    class _SeqSvc:
        def load_model(self, *_args):
            pass

        def transcribe_batch(self, request, batch, _cancel):
            captured_prompts.append(request.prompt_context)
            from core.subtitle_generation.subtitle_generation_result import SubtitleGenerationResult, WhisperSegmentResult
            if batch.batch_id == "scan_1":
                return SubtitleGenerationResult(batch.batch_id, [WhisperSegmentResult(0, 1000, "ええ、ああああああ")])
            return SubtitleGenerationResult(batch.batch_id, [WhisperSegmentResult(1000, 2000, "大丈夫")])

    b_worker = BatchSegmentScanWorker(
        [
            {"id": "1", "index": 0, "start_ms": 0, "end_ms": 1000, "context_prompt": ""},
            {"id": "2", "index": 1, "start_ms": 1000, "end_ms": 2000, "context_prompt": "OLD_STALE_LOOP"},
        ],
        req,
        _SeqSvc(),
    )
    b_worker.run()
    # Tier 3 prompt for segment 2 must NOT contain OLD_STALE_LOOP because segment 1 dropped
    assert all("OLD_STALE_LOOP" not in p for p in captured_prompts)


def test_ui_condition_on_previous_text_end_to_end_wiring(qapp, tmp_path):
    panel, project = _make_panel(tmp_path)
    panel.cmb_specialized_model.setCurrentIndex(0)
    panel.cmb_model.setCurrentIndex(panel.cmb_model.findData("large-v3"))
    panel.chk_condition_on_previous_text.setChecked(False)

    # 1. Gen Sub request
    asr_req = panel._build_asr_request()
    assert asr_req.condition_on_previous_text is False

    # 2. Rescan request via MainWindow
    win = MainWindow.__new__(MainWindow)
    win.sub_editor = None
    win.generation_panel = panel
    rescan_req = win._build_segment_scan_request(
        "scan_1", panel._timing_settings(), str(tmp_path / "video.mp4"), project
    )
    assert rescan_req.condition_on_previous_text is False

    # 3. Timing Draft pipeline via TimingBatchService
    mock_proj_svc = MagicMock()
    mock_proj_svc.current_project = project
    timing_svc = TimingBatchService(mock_proj_svc)
    validated = timing_svc._validate_settings(panel._timing_settings(), project.state.timing)
    assert validated["condition_on_previous_text"] is False

    cp = TimingCheckpoint(
        project_id=project.project_id,
        source_fingerprint="fp_anti_loop",
        timing_artifact_id="art1",
        timing_revision=1,
        batch_size=5,
        model_size="large-v3",
        compute_type="float16",
        use_vad=True,
        min_silence_ms=300,
        fix_overlap=True,
        overlap_gap_ms=50,
        overlap_ms=800,
        max_window_ms=120000,
        condition_on_previous_text=False,
    )
    restored_settings = timing_svc._settings_from_checkpoint(cp)
    assert restored_settings["condition_on_previous_text"] is False

    with patch("workers.TimingBatchWorker.TimingBatchWorker.start"):
        timing_svc._execute_run(0, 5, panel._timing_settings())
    assert timing_svc.worker.request.condition_on_previous_text is False

    # 4. Sync from project restores unchecked state
    panel.chk_condition_on_previous_text.setChecked(True)
    project.state.timing.condition_on_previous_text = False
    panel.sync_timing_settings_from_project()
    assert panel.chk_condition_on_previous_text.isChecked() is False


def test_kotoba_hard_guard_30_term_glossary_single_call_pass(qapp, tmp_path):
    """Dù dự án có 30 từ Glossary + context tự nhiên, kotoba-whisper luôn chạy đúng 1 lượt với None/None/False."""
    terms_30 = [f"用語{i:02d}" for i in range(1, 31)]
    glossary_entries = [f"{t} -> Term{i:02d}" for i, t in enumerate(terms_30, start=1)]
    joined_hotwords = " ".join(terms_30)
    natural_ctx = f"Terminology: {', '.join(terms_30)}. Context: Cuộc trò chuyện dài tại học viện ma thuật Nhật Bản."

    # 1) FasterWhisperService.transcribe_batch() calls model.transcribe ONCE with hard guard
    service = FasterWhisperService(device="cpu")
    calls = []

    class _KotobaModel:
        def transcribe(self, _wav, **opts):
            calls.append(dict(opts))
            return iter([SimpleNamespace(start=0.2, end=1.8, text="本当に来たのね", words=None)]), SimpleNamespace(language="ja")

    service.model = _KotobaModel()
    service.current_model_size = "kotoba-whisper-v2.0"
    batch = SubtitleGenerationBatch("b_k30", 0, 5000, "RUNNING", 1, "", "")
    req = SubtitleGenerationRequest(
        request_id="r_k30",
        project_id="p_k30",
        source_fingerprint="fp_k30",
        video_path="v.mp4",
        model_size="kotoba-whisper-v2.0",
        compute_type="int8",
        language="ja",
        use_vad=False,
        min_silence_ms=350,
        word_timestamps=True,
        condition_on_previous_text=True,
        prompt_context=natural_ctx,
        hotwords=joined_hotwords,
    )
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        res = service.transcribe_batch(req, batch, lambda: False)

    assert len(calls) == 1
    assert calls[0]["initial_prompt"] is None
    assert calls[0]["hotwords"] is None
    assert calls[0]["condition_on_previous_text"] is False
    assert calls[0]["word_timestamps"] is False
    assert "repetition_penalty" not in calls[0]
    assert "no_repeat_ngram_size" not in calls[0]
    assert [s.text for s in res.segments] == ["本当に来たのね"]

    # 2) FasterWhisperService.run() also enforces kotoba guard right before model.transcribe
    dummy_media = tmp_path / "k_run.mp4"
    dummy_media.write_bytes(b"mp4")
    service.current_model_size = "kotoba-whisper-v2.2"
    service.current_compute_type = "int8"
    calls.clear()
    service.run(str(dummy_media), model_size="kotoba-whisper-v2.2", language="ja")
    assert len(calls) == 1
    assert calls[0]["initial_prompt"] is None
    assert calls[0]["hotwords"] is None
    assert calls[0]["condition_on_previous_text"] is False
    assert calls[0]["word_timestamps"] is False

    # 3) UI + TimingBatchWorker clear/override Glossary for kotoba
    panel, project = _make_panel(tmp_path)
    project.transcription_context = TranscriptionContext(
        context="Học viện ma thuật.", glossary=glossary_entries
    )
    panel.generation_service.compile_prompt_context.return_value = MagicMock(text=natural_ctx)
    panel.cmb_specialized_model.setCurrentIndex(panel.cmb_specialized_model.findData("kotoba-whisper-v2.2"))
    panel_req = panel._build_asr_request()
    assert panel_req.prompt_context == ""
    assert panel_req.hotwords == ""

    tb_kw = TimingBatchWorker(
        TimingRunRequest(
            video_path="v.mp4",
            start_ms=0,
            target_segment_count=5,
            model_size="kotoba-whisper-v2.0",
            initial_prompt=natural_ctx,
            hotwords=joined_hotwords,
            condition_on_previous_text=True,
        )
    )._build_transcribe_kwargs("ja", vad_filter=True, word_timestamps=True)
    assert tb_kw["initial_prompt"] is None
    assert tb_kw["hotwords"] is None
    assert tb_kw["condition_on_previous_text"] is False
    assert tb_kw["word_timestamps"] is False


def test_empty_glossary_and_large_v3_separation_and_ui_hints(qapp, tmp_path):
    """Xác minh xóa 100% prompt/hotwords ẩn và tách bạch hotwords space-separated trên large-v3."""
    service = FasterWhisperService(device="cpu")
    captured = {}

    class _LargeModel:
        def transcribe(self, _wav, **opts):
            captured.clear()
            captured.update(opts)
            return iter([SimpleNamespace(start=0.0, end=1.2, text="大丈夫だよ", words=None)]), SimpleNamespace(language="ja")

    service.model = _LargeModel()
    service.current_model_size = "large-v3"
    batch = SubtitleGenerationBatch("b_lv3_sep", 0, 5000, "RUNNING", 1, "", "")

    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        # 1) Empty glossary + empty context => None / None
        req_empty = SubtitleGenerationRequest(
            request_id="r_e",
            project_id="p1",
            source_fingerprint="fp1",
            video_path="v.mp4",
            model_size="large-v3",
            compute_type="int8",
            language="ja",
            use_vad=False,
            min_silence_ms=300,
            word_timestamps=True,
            prompt_context="",
            hotwords="",
        )
        service.transcribe_batch(req_empty, batch, lambda: False)
        assert captured["initial_prompt"] is None
        assert captured["hotwords"] is None

        # 2) Glossary only => space-separated hotwords, initial_prompt is None
        req_glossary_only = SubtitleGenerationRequest(
            request_id="r_go",
            project_id="p1",
            source_fingerprint="fp1",
            video_path="v.mp4",
            model_size="large-v3",
            compute_type="int8",
            language="ja",
            use_vad=False,
            min_silence_ms=300,
            word_timestamps=True,
            prompt_context="Terminology: 魔物 -> Quái vật, マンコ, チンポ.",
            hotwords="魔物 マンコ チンポ",
        )
        service.transcribe_batch(req_glossary_only, batch, lambda: False)
        assert captured["initial_prompt"] is None
        assert captured["hotwords"] == "魔物 マンコ チンポ"

        # 3) Glossary + natural context => context kept in initial_prompt, glossary in space-separated hotwords
        req_with_ctx = SubtitleGenerationRequest(
            request_id="r_ctx",
            project_id="p1",
            source_fingerprint="fp1",
            video_path="v.mp4",
            model_size="large-v3",
            compute_type="int8",
            language="ja",
            use_vad=False,
            min_silence_ms=300,
            word_timestamps=True,
            prompt_context="Terminology: 魔物 -> Quái vật, マンコ. Context: Hai nhân vật đang nói chuyện trong phòng.",
            hotwords="魔物 マンコ",
        )
        service.transcribe_batch(req_with_ctx, batch, lambda: False)
        assert captured["initial_prompt"] == "Hai nhân vật đang nói chuyện trong phòng."
        assert captured["hotwords"] == "魔物 マンコ"

    # UI: Speech Pad hint = 250–350ms, Live-Action / Tokusatsu preset updated
    large_profile = SubtitleGenerationPanel._MODEL_VAD_PROFILES["large"]
    assert "250–350ms" in large_profile["hints"]["speech_pad"]
    assert "250–350ms" in large_profile["tooltips"]["speech_pad"]
    la_preset = SubtitleGenerationPanel.get_fixed_vad_preset("live_action")
    assert la_preset is not None
    assert "Tokusatsu" in la_preset["label"]
    assert (la_preset["min_silence"], la_preset["threshold"], la_preset["speech_pad"], la_preset["max_speech"], la_preset["condition_on_previous_text"]) == (
        300, 0.35, 250, 6.0, False
    )


def test_prompt_echo_guard_and_single_shot_retry_rescue_and_drop(tmp_path):
    """Prompt-Echo Guard chặn nhại Glossary, retry 1 lượt không Glossary để cứu lời thật hoặc bỏ hẳn."""
    hotwords = "魔物 マンコ チンポ おちんちん 黒崎 御影"
    natural_prompt = "Cuộc đối thoại giữa các nhân vật tại học viện."

    # 1) Direct Prompt-Echo cases MUST return True
    assert SubtitleGenerationValidator.is_prompt_echo("魔物 マンコ チンポ", initial_prompt=None, hotwords=hotwords) is True
    assert SubtitleGenerationValidator.is_prompt_echo("魔物、マンコ、チンポ、おちんちん", initial_prompt=None, hotwords=hotwords) is True
    assert SubtitleGenerationValidator.is_prompt_echo("魔物、魔物、魔物、魔物、魔物", initial_prompt=None, hotwords=hotwords) is True
    assert SubtitleGenerationValidator.is_prompt_echo("Cuộc đối thoại giữa các nhân vật", initial_prompt=natural_prompt, hotwords=hotwords) is True

    # 2) Valid dialogue MUST NOT false-positive even when containing Glossary terms
    assert SubtitleGenerationValidator.is_prompt_echo("黒崎！", initial_prompt=None, hotwords=hotwords) is False
    assert SubtitleGenerationValidator.is_prompt_echo("黒崎と御影が来たよ", initial_prompt=None, hotwords=hotwords) is False
    assert SubtitleGenerationValidator.is_prompt_echo("魔物が襲ってきたよ", initial_prompt=None, hotwords=hotwords) is False

    # 3) Batch <= 30s: Echo detected -> single-shot retry without prompt/hotwords rescues real speech
    service = FasterWhisperService(device="cpu")
    service.current_model_size = "large-v3"
    call_history = []

    class _RescueModel:
        def transcribe(self, _wav, **opts):
            call_history.append(dict(opts))
            if len(call_history) == 1:
                return iter([SimpleNamespace(start=1.0, end=2.5, text="魔物、マンコ、チンポ", words=None)]), SimpleNamespace(language="ja")
            return iter([SimpleNamespace(start=1.0, end=2.5, text="本当だ、見て！", words=None)]), SimpleNamespace(language="ja")

    service.model = _RescueModel()
    req = SubtitleGenerationRequest(
        request_id="r_echo_rescue",
        project_id="p1",
        source_fingerprint="fp1",
        video_path="v.mp4",
        model_size="large-v3",
        compute_type="int8",
        language="ja",
        use_vad=False,
        min_silence_ms=300,
        word_timestamps=True,
        prompt_context="",
        hotwords=hotwords,
    )
    batch_short = SubtitleGenerationBatch("b_short", 0, 10000, "RUNNING", 1, "", "")
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        res_rescue = service.transcribe_batch(req, batch_short, lambda: False)

    assert len(call_history) == 2
    assert call_history[0]["hotwords"] == hotwords
    assert call_history[1]["initial_prompt"] is None
    assert call_history[1]["hotwords"] is None
    assert call_history[1]["condition_on_previous_text"] is False
    assert [s.text for s in res_rescue.segments] == ["本当だ、見て！"]

    # 4) Batch > 30s with real WAV slice: Echo -> slice retry returns moaning -> cleanly dropped
    import wave

    wav_path = tmp_path / "long_batch.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * (16000 * 40))

    slice_calls = []

    class _DropModel:
        def transcribe(self, audio_path, **opts):
            slice_calls.append((audio_path, dict(opts)))
            if len(slice_calls) == 1:
                return iter([SimpleNamespace(start=35.0, end=37.0, text="魔物、マンコ、チンポ", words=None)]), SimpleNamespace(language="ja")
            return iter([SimpleNamespace(start=0.1, end=1.4, text="あっあっあっあっあっあっ", words=None)]), SimpleNamespace(language="ja")

    service.model = _DropModel()
    batch_long = SubtitleGenerationBatch("b_long", 0, 40000, "RUNNING", 1, "", "")
    slice_tmp = str(tmp_path / "temp_slice_dir")
    os_temp = slice_tmp
    import os
    os.makedirs(os_temp, exist_ok=True)
    with patch.object(service, "_extract_batch_audio", return_value=(str(wav_path), os_temp)):
        res_drop = service.transcribe_batch(req, batch_long, lambda: False)

    assert len(slice_calls) == 2
    assert slice_calls[1][0] != str(wav_path)
    assert slice_calls[1][1]["initial_prompt"] is None
    assert slice_calls[1][1]["hotwords"] is None
    assert slice_calls[1][1]["condition_on_previous_text"] is False
    assert res_drop.segments == []

    # 5) TimingBatchWorker and BatchSegmentScanWorker also drop echoed text cleanly
    worker = TimingBatchWorker(
        TimingRunRequest(
            video_path="v.mp4",
            start_ms=0,
            target_segment_count=5,
            model_size="large-v3",
            hotwords=hotwords,
        )
    )
    assert worker._extract_valid_sub_ranges(
        SimpleNamespace(start=1.0, end=3.0, text="魔物、マンコ、チンポ", no_speech_prob=0.1, avg_logprob=-0.2, words=None),
        0,
        0,
    ) == []

    class _EchoScanSvc:
        def load_model(self, *_args):
            pass

        def transcribe_batch(self, _request, batch, _cancel):
            from core.subtitle_generation.subtitle_generation_result import SubtitleGenerationResult, WhisperSegmentResult
            return SubtitleGenerationResult(batch.batch_id, [WhisperSegmentResult(0, 1500, "魔物、マンコ、チンポ")])

    scan_worker = BatchSegmentScanWorker(
        [{"id": "s1", "index": 0, "start_ms": 0, "end_ms": 1500, "context_prompt": ""}],
        req,
        _EchoScanSvc(),
    )
    completed_scan = []
    errors_scan = []
    scan_worker.segment_completed_signal.connect(lambda seg_id, text: completed_scan.append((seg_id, text)))
    scan_worker.segment_error_signal.connect(lambda seg_id, err: errors_scan.append((seg_id, err)))
    scan_worker.run()
    assert completed_scan == []
    assert len(errors_scan) == 1 and errors_scan[0][0] == "s1"


def test_v3_legacy_preset_normalization_and_dynamic_tokusatsu_hints(qapp, tmp_path):
    """Tương thích ngược tên preset cũ Live-Action & đồng bộ chú thích UI cho large-v3 và Tokusatsu."""
    from core.project.project_state import normalize_vad_preset_key

    assert normalize_vad_preset_key("Live-Action / Phim người đóng (18+)") == "live_action"
    assert normalize_vad_preset_key("Live-Action / Tokusatsu (18+)") == "live_action"
    assert normalize_vad_preset_key("anime_ja_shared") == "standard"
    assert TimingState(vad_preset="Live-Action / Phim người đóng (18+)").vad_preset == "live_action"

    fixed_legacy = SubtitleGenerationPanel.get_fixed_vad_preset("Live-Action / Phim người đóng (18+)")
    assert fixed_legacy is not None and fixed_legacy["key"] == "live_action"

    validated = TimingBatchService._validate_settings(
        {"vad_preset": "Live-Action / Phim người đóng (18+)", "use_vad": True}
    )
    assert validated["vad_preset"] == "live_action"

    # Legacy project file syncs straight to live_action (Tokusatsu 0.35 / 6.0s) and updates UI hints
    panel, project = _make_panel(tmp_path)
    project.state.timing.vad_preset = "Live-Action / Phim người đóng (18+)"
    project.state.timing.vad_threshold = 0.35
    project.state.timing.vad_max_speech_duration_s = 6.0
    panel.cmb_specialized_model.setCurrentIndex(0)
    panel.cmb_model.setCurrentIndex(panel.cmb_model.findData("large-v3"))
    panel.sync_timing_settings_from_project()

    assert panel.cmb_vad_preset.currentData() == "live_action"
    assert "Tokusatsu gợi ý 0.35" in panel._vad_row_widgets["vad_threshold"][2].text()
    assert "5–6s" in panel._vad_row_widgets["max_speech"][2].text()

    # Switching to Anime JA - Riêng large-v3 displays Large gợi ý 250–350ms
    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("anime_ja_large_v3"))
    assert "Large gợi ý 250–350ms" in panel._vad_row_widgets["speech_pad"][2].text()


def test_v3_max_speech_duration_enforcement_and_manual_clip_preservation(tmp_path):
    """Siết max_speech_duration_s=6.0s trên VAD dài (cắt tại điểm năng lượng thấp) và giữ nguyên khung ngắn thủ công."""
    import numpy as np
    import wave
    import os
    from core.agent.vad_timing_service import detect_speech_intervals_vad

    # 1) Energy-dip splitting on a continuous 14s waveform with quiet valley around 5.2s and 10.1s
    sr = 16000
    audio = np.full(14 * sr, 0.35, dtype=np.float32)
    audio[int(5.1 * sr) : int(5.3 * sr)] = 0.002
    audio[int(10.0 * sr) : int(10.2 * sr)] = 0.002

    bounded = FasterWhisperService.enforce_max_speech_spans(
        [(0.0, 14.0), (15.0, 18.5)], max_speech_s=6.0, audio=audio, sampling_rate=sr
    )
    assert len(bounded) >= 4
    assert all((e - s) <= 6.0 + 1e-6 for s, e in bounded)
    assert bounded[-1] == (15.0, 18.5)
    # First split selects the low-energy valley near 5.2s
    assert 5.05 <= bounded[0][1] <= 5.35

    # Agent VAD interval helper also caps any continuous chunk > 6.0s
    with patch("core.agent.vad_timing_service.get_speech_timestamps", return_value=[{"start": 0, "end": 14 * sr}]):
        with patch("core.agent.vad_timing_service.VadOptions", side_effect=lambda **kw: kw):
            intervals = detect_speech_intervals_vad(audio, max_speech_duration_s=6.0)
    assert len(intervals) >= 3
    assert all((item["end_ms"] - item["start_ms"]) <= 6000 for item in intervals)

    # 2) FasterWhisperService.transcribe_batch() pre-splits oversized VAD runs (15s continuous) to <= 6.0s slices,
    #    while preserving short manual clips (<= 6.0s) in a single untransformed call.
    pcm = (audio * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()
    wav_long = tmp_path / "long_moan.wav"
    with wave.open(str(wav_long), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)

    wav_short = tmp_path / "short_manual.wav"
    with wave.open(str(wav_short), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm[: int(3.5 * sr) * 2])

    service = FasterWhisperService(device="cpu")
    service.current_model_size = "large-v3"
    transcribe_calls = []

    class _SliceSpyModel:
        def transcribe(self, audio_path, **opts):
            dur_s = 0.0
            if os.path.exists(audio_path):
                with wave.open(audio_path, "rb") as wf:
                    dur_s = wf.getnframes() / float(wf.getframerate() or sr)
            transcribe_calls.append((audio_path, dur_s, dict(opts)))
            return iter([SimpleNamespace(start=0.1, end=1.2, text="大丈夫だよ", words=None)]), SimpleNamespace(language="ja")

    service.model = _SliceSpyModel()
    req_v3 = SubtitleGenerationRequest(
        request_id="r_maxsp",
        project_id="p1",
        source_fingerprint="fp1",
        video_path="v.mp4",
        model_size="large-v3",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=300,
        word_timestamps=True,
        vad_threshold=0.35,
        vad_speech_pad_ms=250,
        vad_max_speech_duration_s=6.0,
    )

    tmp_slice_dir = str(tmp_path / "cap_tmp")
    os.makedirs(tmp_slice_dir, exist_ok=True)
    with patch.object(service, "_extract_batch_audio", return_value=(str(wav_long), tmp_slice_dir)):
        with patch("faster_whisper.vad.get_speech_timestamps", return_value=[{"start": 0, "end": 14 * sr}]):
            res_long = service.transcribe_batch(
                req_v3, SubtitleGenerationBatch("b_14s", 0, 14000, "RUNNING", 1, "", ""), lambda: False
            )
    assert len(transcribe_calls) >= 3
    assert all(call[1] <= 6.0 + 1e-3 for call in transcribe_calls)
    assert all(call[2]["vad_filter"] is True for call in transcribe_calls)
    assert all(call[2]["vad_parameters"]["max_speech_duration_s"] == 6.0 for call in transcribe_calls)
    assert len(res_long.segments) >= 3

    # Short manual frame (3.5s <= 6.0s) is NOT pre-sliced and forwards exact max_speech_duration_s=6.0
    transcribe_calls.clear()
    with patch.object(service, "_extract_batch_audio", return_value=(str(wav_short), None)):
        service.transcribe_batch(
            req_v3, SubtitleGenerationBatch("b_manual_3s", 1000, 4500, "RUNNING", 1, "", ""), lambda: False
        )
    assert len(transcribe_calls) == 1
    assert transcribe_calls[0][0] == str(wav_short)
    assert transcribe_calls[0][2]["vad_filter"] is True
    assert transcribe_calls[0][2]["vad_parameters"]["max_speech_duration_s"] == 6.0

    # 3) TimingBatchWorker also caps continuous raw segment ranges to <= 6.0s
    worker = TimingBatchWorker(
        TimingRunRequest(
            video_path="v.mp4",
            start_ms=0,
            target_segment_count=10,
            model_size="large-v3",
            vad_preset="live_action",
            vad_threshold=0.35,
            vad_speech_pad_ms=250,
            vad_max_speech_duration_s=6.0,
        )
    )
    worker._active_chunk_wav = str(wav_long)
    ranges = worker._extract_valid_sub_ranges(
        SimpleNamespace(start=0.0, end=14.0, text="", no_speech_prob=0.1, avg_logprob=-0.2, words=None),
        0,
        0,
    )
    assert len(ranges) >= 3
    assert all((e - s) <= 6000 for s, e in ranges)


def test_v3_low_cps_courtesy_hallucination_guard_and_preservation(tmp_path):
    """Low-CPS Courtesy Hallucination Guard chặn ảo giác xã giao kéo dài hoặc nhãn YouTube nhưng giữ thoại thật."""
    # 1) Pure YouTube/subtitle labels blocked unconditionally even on short clips
    for label in (
        "ご視聴ありがとうございました",
        "ご視聴ありがとうございます。",
        "チャンネル登録よろしくお願いします",
        "字幕作成：ABC",
        "ご覧いただきありがとうございました！",
    ):
        assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination(label, duration_s=2.0) is True

    # 2) Courtesy phrases blocked when stretched (>= 4.5s and CPS < 1.8) or high no_speech_prob >= 0.6
    assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination("おやすみなさい", duration_s=8.57) is True
    assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination("おやすみなさい。", duration_s=5.0) is True
    assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination("お疲れ様でした", duration_s=5.5) is True
    assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination("ありがとうございました", duration_s=6.2) is True
    assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination("お疲れさまでした", duration_s=2.0, no_speech_prob=0.65) is True

    # 3) Clear spoken "おやすみなさい" inside normal 1.0s-3.0s span MUST be preserved 100%
    assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination("おやすみなさい", duration_s=2.0, no_speech_prob=0.1) is False
    assert SubtitleGenerationValidator.is_low_cps_courtesy_hallucination("おやすみなさい！", duration_s=1.5, no_speech_prob=0.2) is False

    # 4) Pipeline integration: stretched "おやすみなさい" (9.98s - 18.55s) dropped; crisp "おやすみなさい" (1.0s - 3.0s) kept
    service = FasterWhisperService(device="cpu")
    service.current_model_size = "large-v3"

    class _CourtesyModel:
        def transcribe(self, _wav, **_opts):
            return iter([
                SimpleNamespace(start=9.98, end=18.55, text="おやすみなさい", no_speech_prob=0.2, compression_ratio=1.1, words=None),
                SimpleNamespace(start=20.0, end=22.0, text="おやすみなさい", no_speech_prob=0.1, compression_ratio=1.1, words=None),
            ]), SimpleNamespace(language="ja")

    service.model = _CourtesyModel()
    req = SubtitleGenerationRequest(
        request_id="r_c",
        project_id="p1",
        source_fingerprint="fp1",
        video_path="v.mp4",
        model_size="large-v3",
        compute_type="int8",
        language="ja",
        use_vad=False,
        min_silence_ms=300,
        word_timestamps=True,
    )
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        res = service.transcribe_batch(req, SubtitleGenerationBatch("b_c", 0, 25000, "RUNNING", 1, "", ""), lambda: False)
    assert [(s.start_ms, s.end_ms, s.text) for s in res.segments] == [(20000, 22000, "おやすみなさい")]

    # Never leaks stretched courtesy hallucination into previous_text via resolve_tier3_context
    _, ctx_prompt = resolve_tier3_context(
        [
            {"id": "1", "start_ms": 9980, "end_ms": 18550, "text": "おやすみなさい"},
            {"id": "2", "start_ms": 18600, "end_ms": 20000, "text": ""},
        ],
        "2",
        18600,
        20000,
    )
    assert "おやすみなさい" not in ctx_prompt

    # TimingBatchWorker also skips stretched courtesy hallucination
    worker = TimingBatchWorker(TimingRunRequest(video_path="v.mp4", start_ms=0, target_segment_count=5, model_size="large-v3"))
    assert worker._extract_valid_sub_ranges(
        SimpleNamespace(start=9.98, end=18.55, text="おやすみなさい", no_speech_prob=0.1, avg_logprob=-0.2, words=None),
        0,
        0,
    ) == []


def test_v3_glossary_parity_across_full_selected_and_rescan_modes(qapp, tmp_path):
    """Glossary thuần hotwords (initial_prompt=None) đồng nhất qua Full Video, Gen Sub Selected, Rescan Audio và chặn trên Kotoba."""
    panel, project = _make_panel(tmp_path)
    project.transcription_context = TranscriptionContext(
        context="",
        glossary=["黒崎 -> Kurosaki", "御影 = Mikage", "魔物"],
    )
    compiled_str = "Terminology: 黒崎 -> Kurosaki, 御影 = Mikage, 魔物."
    panel.generation_service.compile_prompt_context.return_value = MagicMock(text=compiled_str)

    win = MainWindow.__new__(MainWindow)
    win.sub_editor = None
    win.generation_panel = panel

    service = FasterWhisperService(device="cpu")
    captured_opts = []

    class _ParityModel:
        def transcribe(self, _wav, **opts):
            captured_opts.append(dict(opts))
            return iter([SimpleNamespace(start=0.1, end=1.2, text="大丈夫", words=None)]), SimpleNamespace(language="ja")

    service.model = _ParityModel()
    batch = SubtitleGenerationBatch("b_p", 0, 3000, "RUNNING", 1, "", "")

    # 1) large-v3 across Full Video, Gen Sub Selected, and Rescan Audio -> identical hotwords + initial_prompt=None
    panel.cmb_specialized_model.setCurrentIndex(0)
    panel.cmb_model.setCurrentIndex(panel.cmb_model.findData("large-v3"))
    panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData("live_action"))
    panel.chk_apply_preset_rescan.setChecked(True)

    req_full = panel._build_asr_request()
    settings = panel._timing_settings()
    req_selected = win._build_segment_scan_request("batch_scan_1", settings, str(tmp_path / "video.mp4"), project)
    req_rescan = win._build_segment_scan_request("scan_1", settings, str(tmp_path / "video.mp4"), project)

    service.current_model_size = "large-v3"
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        for req in (req_full, req_selected, req_rescan):
            assert req.vad_max_speech_duration_s == 6.0
            service.transcribe_batch(req, batch, lambda: False)

    assert len(captured_opts) == 3
    for opts in captured_opts:
        assert opts["initial_prompt"] is None
        assert opts["hotwords"] == "黒崎 御影 魔物"

    # 2) kotoba-whisper across all 3 modes -> strict initial_prompt=None & hotwords=None on call #1
    captured_opts.clear()
    panel.cmb_specialized_model.setCurrentIndex(panel.cmb_specialized_model.findData("kotoba-whisper-v2.0"))
    k_full = panel._build_asr_request()
    k_settings = panel._timing_settings()
    k_selected = win._build_segment_scan_request("batch_scan_1", k_settings, str(tmp_path / "video.mp4"), project)
    k_rescan = win._build_segment_scan_request("scan_1", k_settings, str(tmp_path / "video.mp4"), project)

    service.current_model_size = "kotoba-whisper-v2.0"
    with patch.object(service, "_extract_batch_audio", return_value=("fake.wav", None)):
        for req in (k_full, k_selected, k_rescan):
            service.transcribe_batch(req, batch, lambda: False)

    assert len(captured_opts) == 3
    for opts in captured_opts:
        assert opts["initial_prompt"] is None
        assert opts["hotwords"] is None
        assert opts["condition_on_previous_text"] is False
        assert opts["word_timestamps"] is False


def test_v3_apply_preset_rescan_checkbox_full_control_and_legacy_project_restore(qapp, tmp_path):
    """Toàn quyền quyết định của chk_apply_preset_rescan ở cả Preset chuyển đổi, bỏ tick và mở dự án cũ/mới."""
    import json
    import os
    from core.artifacts.artifact_store import ArtifactStore
    from core.services.project_service import ProjectService

    panel, project = _make_panel(tmp_path)
    win = MainWindow.__new__(MainWindow)
    win.sub_editor = None
    win.generation_panel = panel

    panel.cmb_specialized_model.setCurrentIndex(0)
    panel.cmb_model.setCurrentIndex(panel.cmb_model.findData("large-v3"))
    assert panel.chk_apply_preset_rescan.isChecked() is False

    # 1) Chọn preset chuyên biệt (live_action / anime_ja_large_v3) -> tự động tick chk_apply_preset_rescan = True
    for preset_key, exp_thresh in (("live_action", 0.35), ("anime_ja_large_v3", 0.30)):
        panel.chk_apply_preset_rescan.setChecked(False)
        panel.cmb_vad_preset.setCurrentIndex(panel.cmb_vad_preset.findData(preset_key))
        assert panel.chk_apply_preset_rescan.isChecked() is True
        settings = panel._timing_settings()
        assert settings["apply_preset_to_rescan"] is True
        for req_id in ("scan_1", "batch_scan_1"):
            req = win._build_segment_scan_request(req_id, settings, str(tmp_path / "video.mp4"), project)
            assert abs(req.vad_threshold - exp_thresh) < 1e-3
            assert abs(req.vad_max_speech_duration_s - 6.0) < 1e-3

        # 2) Chủ động bỏ tick -> Rescan & Gen Sub Selected phải bỏ qua preset (không bị nhánh or ghi đè)
        panel.chk_apply_preset_rescan.setChecked(False)
        settings_off = panel._timing_settings()
        assert settings_off["apply_preset_to_rescan"] is False
        for req_id in ("scan_off", "batch_scan_off"):
            req_off = win._build_segment_scan_request(req_id, settings_off, str(tmp_path / "video.mp4"), project)
            assert req_off.vad_threshold is None
            assert req_off.vad_max_speech_duration_s is None
            assert req_off.word_timestamps is False

    # 3) Khôi phục dự án đã lưu sẵn "apply_preset_to_rescan": False -> phải tôn trọng False
    vid_path = tmp_path / "restore_vid.mp4"
    vid_path.write_bytes(b"mp4")
    proj_dir = tmp_path / "proj_saved_false.ai-subtitle"
    proj_svc = ProjectService(ArtifactStore())
    proj_svc.create_project(str(proj_dir), "restore_vid.mp4", str(vid_path))
    proj_svc.current_project.state.timing.model_size = "large-v3"
    proj_svc.current_project.state.timing.vad_preset = "live_action"
    proj_svc.current_project.state.timing.apply_preset_to_rescan = False
    proj_svc.save_project()

    reopened_svc = ProjectService(ArtifactStore())
    reopened_svc.open_project(str(proj_dir))
    reopened_gen = MagicMock()
    reopened_gen.project_service = reopened_svc
    reopened_gen.compile_prompt_context.return_value = MagicMock(text="")
    reopened_gen.is_running.return_value = False
    panel_reopen = SubtitleGenerationPanel(reopened_gen)
    panel_reopen.sync_timing_settings_from_project()
    assert panel_reopen.cmb_vad_preset.currentData() == "live_action"
    assert panel_reopen.chk_apply_preset_rescan.isChecked() is False

    # 4) Mở file dự án cũ CHƯA CÓ khóa apply_preset_to_rescan nhưng đang dùng preset chuyên biệt -> tự bật True
    state_json_path = os.path.join(str(proj_dir), "state.json")
    with open(state_json_path, "r", encoding="utf-8") as f:
        s_data = json.load(f)
    s_data["timing"]["vad_preset"] = "Live-Action / Phim người đóng (18+)"
    s_data["timing"].pop("apply_preset_to_rescan", None)
    with open(state_json_path, "w", encoding="utf-8") as f:
        json.dump(s_data, f, ensure_ascii=False, indent=2)

    legacy_svc = ProjectService(ArtifactStore())
    legacy_svc.open_project(str(proj_dir))
    legacy_gen = MagicMock()
    legacy_gen.project_service = legacy_svc
    legacy_gen.compile_prompt_context.return_value = MagicMock(text="")
    legacy_gen.is_running.return_value = False
    panel_legacy = SubtitleGenerationPanel(legacy_gen)
    panel_legacy.sync_timing_settings_from_project()
    assert panel_legacy.cmb_vad_preset.currentData() == "live_action"
    assert panel_legacy.chk_apply_preset_rescan.isChecked() is True
