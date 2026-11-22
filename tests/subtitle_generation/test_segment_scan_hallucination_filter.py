# -*- coding: utf-8 -*-
from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import QObject

from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_result import (
    SubtitleGenerationResult,
    WhisperSegmentResult,
)
from workers.SegmentScanWorker import SegmentScanWorker


def test_filter_inconsistent_language():
    # Khi ngôn ngữ kỳ vọng là ja, nếu chỉ có Latin mà không có Kana/Kanji -> loại bỏ
    assert SubtitleGenerationValidator.filter_inconsistent_language("Diyorlar.", "ja") == ""
    assert SubtitleGenerationValidator.filter_inconsistent_language("Thank you.", "ja") == ""
    assert SubtitleGenerationValidator.filter_inconsistent_language("Watching", "ja") == ""
    # Giữ nguyên nếu có ký tự tiếng Nhật
    assert SubtitleGenerationValidator.filter_inconsistent_language("はい、そうです", "ja") == "はい、そうです"
    assert SubtitleGenerationValidator.filter_inconsistent_language("OKです", "ja") == "OKです"
    # Giữ nguyên nếu ngôn ngữ không phải là ja
    assert SubtitleGenerationValidator.filter_inconsistent_language("Thank you.", "en") == "Thank you."


def test_segment_scan_worker_filters_hallucinations(qtbot):
    mock_service = MagicMock()
    # Giả lập whisper trả về từ ảo giác Diyorlar.
    mock_service.transcribe_batch.return_value = SubtitleGenerationResult(
        batch_id="scan_1",
        segments=[WhisperSegmentResult(1000, 2500, "Diyorlar.")],
        error=None,
    )

    req = SubtitleGenerationRequest(
        request_id="test_req",
        project_id="test_p",
        source_fingerprint="fp",
        video_path="v.mp4",
        model_size="tiny",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
    )

    worker = SegmentScanWorker(
        segment_id="seg_1",
        start_ms=1000,
        end_ms=3000,
        request=req,
        whisper_service=mock_service,
        scan_mode="asr",
    )

    completed_text = []
    errors = []
    worker.finished_signal.connect(lambda seg_id, text: completed_text.append(text))
    worker.error_signal.connect(lambda seg_id, error: errors.append((seg_id, error)))
    worker.run()

    assert completed_text == []
    assert len(errors) == 1
    assert errors[0][0] == "seg_1"
    assert "Không nhận diện" in errors[0][1]
    assert "khác ngôn ngữ" in errors[0][1]


def test_segment_scan_worker_3tier_fallback_recovers_speech():
    mock_service = MagicMock()
    captured_requests = []

    def fake_transcribe(req, batch, is_cancelled):
        captured_requests.append((req.use_vad, req.audio_boost, req.vad_threshold, req.min_speech_duration_ms, req.no_speech_threshold, req.log_prob_threshold, batch.start_ms, batch.end_ms))
        if len(captured_requests) < 3:
            return SubtitleGenerationResult(batch_id=batch.batch_id, segments=[], error=None)
        return SubtitleGenerationResult(
            batch_id=batch.batch_id,
            segments=[WhisperSegmentResult(1000, 2000, "うん")],
            error=None,
        )

    mock_service.transcribe_batch.side_effect = fake_transcribe

    req = SubtitleGenerationRequest(
        request_id="test_fallback",
        project_id="p1",
        source_fingerprint="fp",
        video_path="v.mp4",
        model_size="tiny",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
        min_speech_duration_ms=150,
    )

    worker = SegmentScanWorker(
        segment_id="seg_fb",
        start_ms=1000,
        end_ms=2000,
        request=req,
        whisper_service=mock_service,
        scan_mode="asr",
    )
    completed = []
    errors = []
    worker.finished_signal.connect(lambda sid, txt: completed.append((sid, txt)))
    worker.error_signal.connect(lambda sid, err: errors.append((sid, err)))
    worker.run()

    assert errors == []
    assert completed == [("seg_fb", "うん")]
    assert len(captured_requests) == 3
    # Tier 1: exact clip + min_speech=150
    assert captured_requests[0][0] is True
    assert captured_requests[0][3] == 150
    assert (captured_requests[0][6], captured_requests[0][7]) == (1000, 2000)
    # Tier 2: sensitive VAD + audio_boost + ±150ms padding
    assert captured_requests[1][0] is True
    assert captured_requests[1][1] is True
    assert captured_requests[1][2] == 0.2
    assert captured_requests[1][3] == 100
    assert (captured_requests[1][6], captured_requests[1][7]) == (850, 2150)
    # Tier 3: bypass VAD + audio_boost + relaxed no_speech/log_prob
    assert captured_requests[2][0] is False
    assert captured_requests[2][1] is True
    assert captured_requests[2][4] == 0.85
    assert captured_requests[2][5] == -1.5


def test_segment_scan_worker_hallucination_only_reports_clear_reason():
    mock_service = MagicMock()
    mock_service.transcribe_batch.return_value = SubtitleGenerationResult(
        batch_id="scan_h",
        segments=[WhisperSegmentResult(1000, 2000, "♪ ♪")],
        error=None,
    )
    req = SubtitleGenerationRequest(
        request_id="req_h",
        project_id="p1",
        source_fingerprint="fp",
        video_path="v.mp4",
        model_size="tiny",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
    )
    worker = SegmentScanWorker("seg_h", 1000, 2000, req, mock_service, scan_mode="asr")
    errors = []
    worker.error_signal.connect(lambda sid, err: errors.append((sid, err)))
    worker.run()

    assert len(errors) == 1
    assert "Không nhận diện được giọng nói trong đoạn đã chọn" in errors[0][1]
    assert "tạp âm/nhạc nền hoặc ảo giác" in errors[0][1]


def test_segment_scan_force_no_vad_runs_single_tier():
    mock_service = MagicMock()
    mock_service.transcribe_batch.return_value = SubtitleGenerationResult(
        batch_id="scan_f",
        segments=[WhisperSegmentResult(1000, 2200, "Hello")],
        error=None,
    )
    req = SubtitleGenerationRequest(
        request_id="req_f",
        project_id="p1",
        source_fingerprint="fp",
        video_path="v.mp4",
        model_size="tiny",
        compute_type="int8",
        language="en",
        use_vad=False,
        min_silence_ms=500,
        word_timestamps=False,
        audio_boost=True,
        no_speech_threshold=0.85,
        log_prob_threshold=-1.5,
    )
    worker = SegmentScanWorker("seg_f", 1000, 2200, req, mock_service, scan_mode="asr", force_no_vad=True)
    completed = []
    worker.finished_signal.connect(lambda sid, txt: completed.append((sid, txt)))
    worker.run()

    assert completed == [("seg_f", "Hello")]
    assert mock_service.transcribe_batch.call_count == 1


def test_subeditor_scan_recovery_banner_quick_actions(qapp):
    from unittest.mock import patch
    from ui.SubEditor import SubtitleEditorWidget
    from ui.Gui import MainWindow
    from core.subtitle_editing.global_undo_manager import GlobalUndoManager

    editor = SubtitleEditorWidget()
    editor.undo_manager = GlobalUndoManager()
    editor.all_segments = [
        {"id": "s1", "start": "00:00:01,000", "end": "00:00:02,500", "start_ms": 1000, "end_ms": 2500, "text": "[ Chưa có nội dung ]"},
        {"id": "s2", "start": "00:00:03,000", "end": "00:00:05,000", "start_ms": 3000, "end_ms": 5000, "text": "Existing text"},
    ]
    editor.render_page()
    editor.select_segment(0)

    win = MainWindow.__new__(MainWindow)
    win.sub_editor = editor
    win.append_log = MagicMock()
    win._is_any_ai_process_running = lambda: False

    with patch("ui.Gui.Toast.show_warning") as mock_warn:
        win._on_segment_scan_error("s1", "Không nhận diện được giọng nói trong đoạn đã chọn — Tạp âm.")
        mock_warn.assert_called_once()
    assert not editor.scan_recovery_banner.isHidden()

    # Switching to segment 1 preserves existing text and auto-hides banner
    editor.select_segment(1)
    assert editor.scan_recovery_banner.isHidden()
    assert editor.all_segments[1]["text"] == "Existing text"

    # Quick action 1: Force retry emits force_asr_scan_requested & checks audio boost
    editor.select_segment(0)
    win._on_segment_scan_error("s1", "NO_SPEECH_DETECTED")
    assert not editor.scan_recovery_banner.isHidden()
    forced = []
    editor.force_asr_scan_requested.connect(lambda sid, s, e: forced.append((sid, s, e)))
    editor.btn_force_asr_retry.click()
    assert forced == [("s1", 1000, 2500)]
    assert editor.current_editor.chk_boost_audio.isChecked() is True
    assert editor.scan_recovery_banner.isHidden()

    # Quick action 2: Manual type clears placeholder and hides banner
    editor.show_scan_recovery_banner("s1", "Thử lại")
    editor.btn_manual_type_sub.click()
    assert editor.current_editor.text_edit.toPlainText() == ""
    assert editor.scan_recovery_banner.isHidden()

    # Quick action 3: Delete empty timing removes segment via undo manager
    editor.show_scan_recovery_banner("s1", "Đoạn trống")
    editor.btn_delete_empty_timing.click()
    assert len(editor.all_segments) == 1
    assert editor.all_segments[0]["id"] == "s2"


def test_faster_whisper_forwards_custom_thresholds(tmp_path):
    from unittest.mock import patch
    from core.subtitle_generation.faster_whisper_service import FasterWhisperService
    from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch

    svc = FasterWhisperService(device="cpu")
    svc.model = MagicMock()
    svc.model.transcribe.return_value = ([], MagicMock())

    req = SubtitleGenerationRequest(
        request_id="req_thr",
        project_id="p1",
        source_fingerprint="fp",
        video_path="v.mp4",
        model_size="tiny",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=300,
        word_timestamps=False,
        min_speech_duration_ms=150,
        no_speech_threshold=0.85,
        log_prob_threshold=-1.5,
    )
    batch = SubtitleGenerationBatch("b1", 1000, 2500, "RUNNING", 1, "now", "now")
    dummy_wav = tmp_path / "audio.wav"
    dummy_wav.write_bytes(b"RIFF")

    with patch.object(FasterWhisperService, "_extract_batch_audio", return_value=(str(dummy_wav), None)):
        svc.transcribe_batch(req, batch, lambda: False)

    kwargs = svc.model.transcribe.call_args.kwargs
    assert kwargs["no_speech_threshold"] == 0.85
    assert kwargs["log_prob_threshold"] == -1.5
    assert kwargs["vad_parameters"]["min_speech_duration_ms"] == 150


def test_resolve_tier3_context_combines_neighbors_and_skips_placeholders():
    from workers.SegmentScanWorker import resolve_tier3_context

    all_segments = [
        {"id": "1", "start": 1000, "end": 3000, "text": "さっきの話だけど"},
        {"id": "2", "start": 3200, "end": 4200, "text": "[ Chưa có nội dung ]"},
        {"id": "3", "start": 4500, "end": 5300, "text": ""},
        {"id": "4", "start": 5600, "end": 7500, "text": "本当に大丈夫？"},
    ]

    ctx_window, ctx_prompt = resolve_tier3_context(all_segments, "3", 4500, 5300)

    assert ctx_window == (3050, 7650)
    assert "さっきの話だけど" in ctx_prompt
    assert "Chưa có nội dung" not in ctx_prompt


def test_segment_scan_short_clip_phantom_defers_to_tier3_combined_context():
    from workers.SegmentScanWorker import SegmentScanWorker

    captured_requests = []
    captured_batches = []
    completed = []
    errors = []

    class FakeService:
        def load_model(self, model_size, compute_type):
            pass

        def transcribe_batch(self, request, batch, check_cancel):
            captured_requests.append(request)
            captured_batches.append(batch)
            idx = len(captured_requests)
            if idx in (1, 2):
                segs = [
                    WhisperSegmentResult(
                        start_ms=batch.start_ms,
                        end_ms=batch.end_ms,
                        text="はい、ありがとうございます。",
                    )
                ]
            else:
                segs = [
                    WhisperSegmentResult(
                        start_ms=1000,
                        end_ms=7000,
                        text="えっと待ってくれそうかな",
                        words=[
                            {"word": "えっと", "start_ms": 1200, "end_ms": 2000},
                            {"word": "待って", "start_ms": 4050, "end_ms": 4450},
                            {"word": "くれ", "start_ms": 4460, "end_ms": 4750},
                            {"word": "そうかな", "start_ms": 5800, "end_ms": 6600},
                        ],
                    )
                ]
            return SubtitleGenerationResult(batch_id=batch.batch_id, segments=segs, error=None)

    req = SubtitleGenerationRequest(
        request_id="test_tier3_ctx",
        project_id="p1",
        source_fingerprint="fp",
        video_path="dummy.mp4",
        model_size="large-v3",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
        min_speech_duration_ms=150,
    )

    worker = SegmentScanWorker(
        segment_id="seg-3",
        start_ms=4000,
        end_ms=4800,
        request=req,
        whisper_service=FakeService(),
        context_window=(1000, 7000),
        context_prompt="さっきの話",
    )
    worker.finished_signal.connect(lambda sid, txt: completed.append((sid, txt)))
    worker.error_signal.connect(lambda sid, err: errors.append((sid, err)))

    worker.run()

    assert errors == []
    assert len(captured_requests) == 3
    tier3_req = captured_requests[2]
    tier3_batch = captured_batches[2]
    assert tier3_req.use_vad is False
    assert tier3_req.word_timestamps is True
    assert "さっきの話" in (tier3_req.prompt_context or "")
    assert tier3_batch.start_ms == 1000
    assert tier3_batch.end_ms == 7000
    assert completed == [("seg-3", "待ってくれ")]


def test_segment_scan_ungrounded_short_clip_phantom_reports_hallucination_filtered():
    from workers.SegmentScanWorker import SegmentScanWorker

    completed = []
    errors = []

    class FakeService:
        def load_model(self, model_size, compute_type):
            pass

        def transcribe_batch(self, request, batch, check_cancel):
            return SubtitleGenerationResult(
                batch_id=batch.batch_id,
                segments=[
                    WhisperSegmentResult(
                        start_ms=batch.start_ms,
                        end_ms=batch.end_ms,
                        text="はい、ありがとうございます。",
                    )
                ],
                error=None,
            )

    req = SubtitleGenerationRequest(
        request_id="test_phantom_filter",
        project_id="p1",
        source_fingerprint="fp",
        video_path="dummy.mp4",
        model_size="large-v3",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
        min_speech_duration_ms=150,
    )

    worker = SegmentScanWorker(
        segment_id="seg-short",
        start_ms=4000,
        end_ms=4800,
        request=req,
        whisper_service=FakeService(),
        context_window=(2500, 6300),
        context_prompt="",
    )
    worker.finished_signal.connect(lambda sid, txt: completed.append((sid, txt)))
    worker.error_signal.connect(lambda sid, err: errors.append((sid, err)))

    worker.run()

    assert completed == []
    assert len(errors) == 1
    seg_id, msg = errors[0]
    assert seg_id == "seg-short"
    assert "ảo giác AI đã bị lọc" in msg


def test_extract_text_for_target_span_preserves_whole_japanese_words_and_excludes_next_word():
    """Regression for line #62 (GHKO63_01): never slice 'やめてー' + 'こっちも' into 'めてーこ'."""
    from workers.SegmentScanWorker import _extract_text_for_target_span

    # Variant A: spaced 'あー やめてー' followed by next-sentence 'こっちも' (exact RTX 3050 tokens)
    segs_spaced = [
        WhisperSegmentResult(
            start_ms=749700,
            end_ms=751500,
            text="あー やめてー",
            words=[
                {"word": "あー", "start_ms": 749700, "end_ms": 750340},
                {"word": " や", "start_ms": 750340, "end_ms": 750840},
                {"word": "め", "start_ms": 750840, "end_ms": 751160},
                {"word": "て", "start_ms": 751160, "end_ms": 751340},
                {"word": "ー", "start_ms": 751340, "end_ms": 751500},
            ],
        ),
        WhisperSegmentResult(
            start_ms=752060,
            end_ms=753100,
            text="こっちも",
            words=[
                {"word": "こ", "start_ms": 752060, "end_ms": 752400},
                {"word": "っち", "start_ms": 752400, "end_ms": 752940},
                {"word": "も", "start_ms": 752940, "end_ms": 753100},
            ],
        ),
    ]
    extracted_a, has_outside_a = _extract_text_for_target_span(segs_spaced, 750750, 752430)
    assert extracted_a == "やめてー"
    assert has_outside_a is True

    # Variant B: unspaced 'あーやめてー' with Whisper DTW stretching 'や' over prior silence
    segs_unspaced = [
        WhisperSegmentResult(
            start_ms=748920,
            end_ms=751500,
            text="あーやめてー",
            words=[
                {"word": "あー", "start_ms": 748920, "end_ms": 749640},
                {"word": "や", "start_ms": 749640, "end_ms": 750900},
                {"word": "め", "start_ms": 750900, "end_ms": 751180},
                {"word": "て", "start_ms": 751180, "end_ms": 751340},
                {"word": "ー", "start_ms": 751340, "end_ms": 751500},
            ],
        ),
        WhisperSegmentResult(
            start_ms=752060,
            end_ms=753080,
            text="こっちも",
            words=[
                {"word": "こ", "start_ms": 752060, "end_ms": 752400},
                {"word": "っち", "start_ms": 752400, "end_ms": 752920},
                {"word": "も", "start_ms": 752920, "end_ms": 753080},
            ],
        ),
    ]
    extracted_b, has_outside_b = _extract_text_for_target_span(segs_unspaced, 750750, 752430)
    assert extracted_b == "やめてー"
    assert has_outside_b is True


def test_extract_text_for_target_span_edge_punctuation_and_katakana_english_units():
    from workers.SegmentScanWorker import _extract_text_for_target_span

    # Katakana loanword with medial 'ー' stays atomic even when leading 'スー' starts before target;
    # stray edge commas/ideographic commas inside span are stripped cleanly.
    segs_ja = [
        WhisperSegmentResult(
            start_ms=1000,
            end_ms=2600,
            text="、スーパー,",
            words=[
                {"word": "、", "start_ms": 1205, "end_ms": 1215},
                {"word": "スー", "start_ms": 1030, "end_ms": 1240},
                {"word": "パー", "start_ms": 1240, "end_ms": 1800},
                {"word": ",", "start_ms": 1800, "end_ms": 1850},
            ],
        )
    ]
    txt_ja, has_out_ja = _extract_text_for_target_span(segs_ja, 1200, 2000)
    assert txt_ja == "スーパー"
    assert has_out_ja is False

    # English whole-word boundaries exclude right-edge spilling word without partial cut.
    segs_en = [
        WhisperSegmentResult(
            start_ms=1000,
            end_ms=3000,
            text="Hello world next",
            words=[
                {"word": "Hello", "start_ms": 1000, "end_ms": 1400},
                {"word": " world", "start_ms": 1500, "end_ms": 1950},
                {"word": " next", "start_ms": 1980, "end_ms": 2700},
            ],
        )
    ]
    txt_en, has_out_en = _extract_text_for_target_span(segs_en, 1450, 2100)
    assert txt_en == "world"
    assert has_out_en is True



