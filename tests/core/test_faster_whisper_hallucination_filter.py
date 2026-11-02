from unittest.mock import MagicMock, patch
import pytest
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch

def test_transcribe_batch_filters_hallucinations(tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"dummy video")
    
    request = SubtitleGenerationRequest(
        request_id="req_001",
        project_id="proj_001",
        source_fingerprint="fingerprint_001",
        video_path=str(dummy_video),
        model_size="base",
        compute_type="int8",
        language="ja",
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
    )
    batch = SubtitleGenerationBatch(
        batch_id="batch_001",
        start_ms=0,
        end_ms=10000,
        status="PENDING",
        revision=1,
        created_at="2026-11-03T00:00:00",
        updated_at="2026-11-03T00:00:00",
    )
    
    # Giả lập whisper trả về 3 segments: 1 hợp lệ, 2 ảo giác
    seg1 = MagicMock(start=0.0, end=2.0, text="こんにちは", words=[])
    seg2 = MagicMock(start=2.5, end=4.0, text="Diyorlar.", words=[]) # Ảo giác
    seg3 = MagicMock(start=5.0, end=7.0, text="ご視聴ありがとうございました", words=[]) # Ảo giác
    
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([seg1, seg2, seg3], None)
    
    service = FasterWhisperService()
    service.model = mock_model
    service.current_model_size = "base"
    service.current_compute_type = "int8"
    
    with patch.object(service, "_extract_batch_audio", return_value=(str(dummy_video), None)):
        result = service.transcribe_batch(request, batch, is_cancelled=lambda: False)
        
    assert len(result.segments) == 1
    assert result.segments[0].text == "こんにちは"
    texts = [s.text for s in result.segments]
    assert "Diyorlar." not in texts
    assert "ご視聴ありがとうございました" not in texts
