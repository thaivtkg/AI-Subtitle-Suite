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
    worker.finished_signal.connect(lambda seg_id, text: completed_text.append(text))
    worker.run()

    assert len(completed_text) == 1
    # Từ Diyorlar. bị chặn hoàn toàn, worker trả về thông báo không có tiếng nói
    assert completed_text[0] == "[Không nhận diện được giọng nói]"
