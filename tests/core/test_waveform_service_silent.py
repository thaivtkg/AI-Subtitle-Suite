import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from core.waveform.waveform_service import WaveformService

def test_waveform_service_silent_video_returns_flat_peaks(tmp_path):
    dummy_video = tmp_path / "silent_video.mp4"
    dummy_video.write_bytes(b"dummy mp4 video bytes")
    
    # Mock subprocess.Popen để trả về luồng raw_audio rỗng (video câm)
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"", b"")
    
    with patch("subprocess.Popen", return_value=mock_process):
        peaks = WaveformService.generate_waveform_peaks(str(dummy_video), force_rebuild=True)
        
    assert isinstance(peaks, np.ndarray)
    assert peaks.shape == (100, 2)
    assert np.all(peaks == 0.0)

def test_waveform_service_too_short_video_returns_flat_peaks(tmp_path):
    dummy_video = tmp_path / "short_video.mp4"
    dummy_video.write_bytes(b"dummy mp4 video bytes")
    
    # Mock subprocess.Popen trả về vài bytes (nhỏ hơn 1 chunk)
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"\x00\x01\x00\x02", b"")
    
    with patch("subprocess.Popen", return_value=mock_process):
        peaks = WaveformService.generate_waveform_peaks(str(dummy_video), force_rebuild=True)
        
    assert isinstance(peaks, np.ndarray)
    assert peaks.shape == (100, 2)
    assert np.all(peaks == 0.0)
