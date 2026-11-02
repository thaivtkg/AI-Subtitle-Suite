# -*- coding: utf-8 -*-
import pytest
from PySide6.QtCore import Qt
from core.export.subtitle_parser import parse_srt_content
from ui.SubEditor import SubtitleEditorWidget, CurrentSubtitleEditor


def test_parse_srt_content_strips_leading_and_trailing_newlines():
    """Tác vụ 1: parse_srt_content phải làm sạch dòng trống ngầm ở đầu/cuối câu phụ đề."""
    srt_sample = (
        "1\n"
        "00:00:01,000 --> 00:00:03,000\n"
        "\n"
        "Em cảm ơn ngài\n"
        "\n"
        "2\n"
        "00:00:04,000 --> 00:00:06,000\n"
        "Thứ này hợp với nàng hơn cái kia nhiều đấy.\n"
    )
    segments = parse_srt_content(srt_sample)
    assert len(segments) == 2
    assert segments[0]["text"] == "Em cảm ơn ngài"
    assert segments[1]["text"] == "Thứ này hợp với nàng hơn cái kia nhiều đấy."


def test_multiline_subtitle_preserves_internal_newlines():
    """DoD: Phụ đề nhiều dòng hợp lệ (thoại 2 người) phải giữ nguyên ngắt dòng bên trong."""
    srt_multiline = (
        "1\n"
        "00:00:01,000 --> 00:00:03,000\n"
        "\n"
        "- Chào anh\n"
        "- Chào em\n"
        "\n"
    )
    segments = parse_srt_content(srt_multiline)
    assert len(segments) == 1
    assert segments[0]["text"] == "- Chào anh\n- Chào em"


def test_subeditor_table_item_vertical_alignment_and_stripped_text(qapp):
    """Tác vụ 2: Table SubEditor hiển thị text sạch và căn giữa dọc Qt.AlignVCenter."""
    sub_editor = SubtitleEditorWidget()
    sub_editor.all_segments = [
        {
            "stt": "1",
            "start": "00:00:01,000",
            "end": "00:00:03,000",
            "text": "\n\nEm cảm ơn ngài\n",
        }
    ]
    sub_editor.render_page()

    item = sub_editor.table.item(0, sub_editor.COL_TEXT)
    assert item is not None
    assert item.text() == "Em cảm ơn ngài"
    assert bool(item.textAlignment() & Qt.AlignVCenter)
    assert bool(item.textAlignment() & Qt.AlignLeft)
    sub_editor.close()


def test_current_subtitle_editor_strips_text_on_set_values(qapp):
    """Tác vụ 3: CurrentSubtitleEditor tự làm sạch khoảng trắng/dòng trống khi nạp giá trị."""
    editor = CurrentSubtitleEditor()
    editor.set_values(
        start="00:00:01,000",
        end="00:00:03,000",
        text="\n\nEm cảm ơn ngài\n",
        original_text="\n\nArigatou gozaimasu\n",
    )
    assert editor.text_edit.toPlainText() == "Em cảm ơn ngài"
    assert editor.text_original.toPlainText() == "Arigatou gozaimasu"
    editor.close()
