import os
import pytest
from unittest.mock import patch
from core.utils.file_utils import atomic_save_text
from core.subtitle_exporter import SubtitleExporter

def test_atomic_save_text_basic(tmp_path):
    target = tmp_path / "sample.txt"
    atomic_save_text(str(target), "Hello World\nLine 2")
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Hello World\nLine 2"

def test_atomic_save_text_preserves_original_on_failure(tmp_path):
    target = tmp_path / "original.txt"
    target.write_text("Original Content", encoding="utf-8")
    
    # Giả lập crash khi đang ghi đĩa
    with patch("os.fsync", side_effect=IOError("Disk Full")):
        with pytest.raises(IOError):
            atomic_save_text(str(target), "Corrupted Content")
            
    # File gốc phải còn nguyên vẹn 100%, không bị cắt về 0 byte
    assert target.read_text(encoding="utf-8") == "Original Content"

def test_subtitle_exporter_atomic_export(tmp_path):
    subtitles = [
        (0, 2000, "Câu thứ nhất"),
        (2500, 5000, "Câu thứ hai")
    ]
    srt_file = str(tmp_path / "out.srt")
    vtt_file = str(tmp_path / "out.vtt")
    txt_file = str(tmp_path / "out.txt")
    
    assert SubtitleExporter.export_srt(subtitles, srt_file) is True
    assert SubtitleExporter.export_vtt(subtitles, vtt_file) is True
    assert SubtitleExporter.export_txt(subtitles, txt_file) is True
    
    assert os.path.exists(srt_file)
    with open(srt_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "00:00:00,000 --> 00:00:02,000" in content
        assert "Câu thứ nhất" in content
