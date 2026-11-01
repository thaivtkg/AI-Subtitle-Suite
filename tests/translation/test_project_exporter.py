import os
import json
import pytest
from core.translation.core.srt_exporter import SRTExporter
from core.translation.core.srt_validator import SRTValidator


def _make_sub(index=1, start="00:00:01,000", end="00:00:03,000", orig="Hello world", trans="Xin chào", status="TRANSLATED"):
    return {
        "index": index,
        "start_time": start,
        "end_time": end,
        "original": orig,
        "translation": trans,
        "status": status,
    }


def test_tc01_export_batch_translated_and_edited_subtitles(tmp_path):
    """TC01: Các câu TRANSLATED và EDITED phải xuất ra bản dịch chứ không bị ép về câu gốc."""
    subs = [
        _make_sub(1, "00:00:01,000", "00:00:02,000", "Line one", "Dòng một", "TRANSLATED"),
        _make_sub(2, "00:00:03,000", "00:00:04,000", "Line two", "Dòng hai", "EDITED"),
        _make_sub(3, "00:00:05,000", "00:00:06,000", "Line three", "Dòng ba", "ACCEPTED"),
    ]
    is_valid, msg = SRTValidator.validate_for_export(subs)
    assert is_valid is True
    assert msg == "Hợp lệ."

    out_file = tmp_path / "out.srt"
    ok, _ = SRTExporter.export(subs, str(out_file))
    assert ok is True

    content = out_file.read_text(encoding="utf-8")
    assert "Dòng một" in content
    assert "Dòng hai" in content
    assert "Dòng ba" in content
    assert "Line one" not in content


def test_tc02_validator_allows_proper_nouns_and_warns_on_long_echo():
    """TC02: Tên riêng giống câu gốc (<= 3 từ) hợp lệ tuyệt đối; câu dài giống hệt chỉ cảnh báo chứ không chặn xuất."""
    subs = [
        _make_sub(1, "00:00:01,000", "00:00:02,000", "John!", "John!", "TRANSLATED"),
        _make_sub(2, "00:00:03,000", "00:00:04,000", "Agent Smith", "Agent Smith", "ACCEPTED"),
        _make_sub(
            3,
            "00:00:05,000",
            "00:00:07,000",
            "What are you doing right now?",
            "What are you doing right now?",
            "TRANSLATED",
        ),
    ]
    is_valid, msg = SRTValidator.validate_for_export(subs)
    assert is_valid is True
    assert "1 câu AI giữ nguyên câu gốc dài" in msg


def test_tc03_export_mixed_statuses_and_whitespace_fallback(tmp_path):
    """TC03: Câu PENDING, ERROR hoặc bản dịch chỉ chứa khoảng trắng phải fallback an toàn về câu gốc."""
    subs = [
        _make_sub(1, "00:00:01,000", "00:00:02,000", "Translated line", "Câu đã dịch", "TRANSLATED"),
        _make_sub(2, "00:00:03,000", "00:00:04,000", "Pending line", "", "PENDING"),
        _make_sub(3, "00:00:05,000", "00:00:06,000", "Whitespace trans", "   \n  ", "TRANSLATED"),
        _make_sub(4, "00:00:07,000", "00:00:08,000", "Error line", "Bản dịch lỗi dở dang", "ERROR"),
    ]
    is_valid, msg = SRTValidator.validate_for_export(subs)
    assert is_valid is True
    assert "3 câu chưa dịch" in msg

    out_file = tmp_path / "mixed.srt"
    ok, _ = SRTExporter.export(subs, str(out_file))
    assert ok is True

    content = out_file.read_text(encoding="utf-8")
    assert "Câu đã dịch" in content
    assert "Pending line" in content
    assert "Whitespace trans" in content
    assert "Error line" in content
    assert "Bản dịch lỗi dở dang" not in content


def test_tc04_validator_blocks_100_percent_untranslated_or_bad_timestamps():
    """TC04: Chặn cứng nếu 100% file chưa dịch câu nào hoặc sai cấu trúc thời gian."""
    untranslated_subs = [
        _make_sub(1, "00:00:01,000", "00:00:02,000", "Hello", "", "PENDING"),
        _make_sub(2, "00:00:03,000", "00:00:04,000", "World", "   ", "ERROR"),
    ]
    is_valid, msg = SRTValidator.validate_for_export(untranslated_subs)
    assert is_valid is False
    assert "Chưa có câu phụ đề nào được dịch" in msg

    bad_time_subs = [
        _make_sub(1, "00:00:05,000", "00:00:02,000", "Hello", "Xin chào", "ACCEPTED"),
    ]
    is_valid_time, msg_time = SRTValidator.validate_for_export(bad_time_subs)
    assert is_valid_time is False
    assert "Start Time phải nhỏ hơn End Time" in msg_time


def test_logic_07_validator_supports_dot_and_overlapping_subtitles():
    """Kiểm tra LOGIC-07: SRTValidator hỗ trợ timestamp dấu chấm . và không chặn cứng câu lồng nhau."""
    # 1. Hỗ trợ dấu chấm trong ms (VD: 00:00:01.500)
    dot_subs = [
        _make_sub(1, "00:00:01.000", "00:00:02.500", "Hello", "Xin chào", "ACCEPTED"),
    ]
    is_valid, msg = SRTValidator.validate_for_export(dot_subs)
    assert is_valid is True

    # 2. Câu lồng nhau (overlapping / out of order timestamps)
    overlapping_subs = [
        _make_sub(1, "00:00:01,000", "00:00:05,000", "Speaker 1", "Người 1", "ACCEPTED"),
        _make_sub(2, "00:00:02,000", "00:00:04,000", "Sign text", "Biển báo", "ACCEPTED"),
    ]
    is_valid_overlap, msg_overlap = SRTValidator.validate_for_export(overlapping_subs)
    assert is_valid_overlap is True


