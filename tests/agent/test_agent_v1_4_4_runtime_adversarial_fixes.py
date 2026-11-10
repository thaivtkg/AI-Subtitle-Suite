import pytest
from unittest.mock import MagicMock
from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import (
    shift_subtitles,
    translate_subtitles,
    adjust_subtitle_bounds,
)
from ui.SubEditor import time_str_to_ms
from ui.components.agent_report_inspector_widget import EditableResultReportWidget


def test_tc_v144_01_selective_shift_overlap_and_order_preservation():
    """TC-V144-01: BUG-SELECTIVE-SHIFT-OVERLAP-INVERSION-004 - Dịch tiến 1 câu lẻ không đè chồng/vượt mặt câu sau."""
    segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1"},
        {"id": 2, "start": "00:00:03,500", "end": "00:00:05,500", "text": "Câu 2"},
    ]
    # Dịch tiến câu 1 thêm +3000ms (từ 1s..3s nhảy lên 4s..6s, va chạm với câu 2 ở 3.5s..5.5s)
    res = shift_subtitles(offset_ms=3000, scope="selected", segment_indices=[1], segments=segs)
    assert res["status"] == "ok"
    out = res["segments"]
    assert len(out) == 2

    st_0 = time_str_to_ms(out[0]["start"])
    en_0 = time_str_to_ms(out[0]["end"])
    st_1 = time_str_to_ms(out[1]["start"])
    en_1 = time_str_to_ms(out[1]["end"])

    assert st_0 < en_0, "Câu đầu tiên phải có start < end"
    assert st_1 < en_1, "Câu thứ hai phải có start < end"
    assert en_0 <= st_1, f"Câu trước kết thúc ({out[0]['end']}) không được vượt quá câu sau bắt đầu ({out[1]['start']})"


def test_tc_v144_02_translate_updates_text_and_preserves_source_text(qtbot):
    """TC-V144-02: BUG-TRANSLATE-INVISIBLE-AND-WIPED-001 - translate_subtitles cập nhật cả text & translation, lưu source_text."""
    segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Hello world"},
    ]
    res = translate_subtitles(target_lang="vi", segments=segs)
    assert res["status"] == "ok"
    out = res["segments"]
    assert len(out) == 1
    assert out[0]["source_text"] == "Hello world"
    assert out[0]["translation"] == "[VI] Hello world"
    assert out[0]["text"] == "[VI] Hello world"

    # Kiểm tra UI Cổng 2 hiển thị ngay văn bản dịch
    card = EditableResultReportWidget()
    qtbot.addWidget(card)
    card.render_result("Dịch phụ đề", res)
    assert len(card._rows) == 1
    assert card._rows[0].editor.text() == "[VI] Hello world"


def test_tc_v144_03_style_not_blocked_by_dau_cuoi_or_compound_prompt():
    """TC-V144-03: BUG-STYLE-BLOCKED-BY-IS-DURATION-002 - Đổi style chứa từ 'đầu/cuối/mốc' hoặc câu ghép vẫn tạo bước style."""
    controller = AgentCopilotController()

    # 1. Câu lệnh đơn đổi style có chữ "từ đầu đến cuối"
    p1 = controller._synthesize_plan("Đổi style chữ vàng viền đen cho các câu từ đầu đến cuối")
    tool_names_1 = [s.tool_name for s in p1.steps]
    assert "apply_subtitle_style" in tool_names_1

    # 2. Câu lệnh ghép: Tạo timing từ đầu video + đổi style chữ vàng
    p2 = controller._synthesize_plan("Tạo 5 câu timing từ đầu video và đổi style chữ vàng viền đen")
    tool_names_2 = [s.tool_name for s in p2.steps]
    assert "create_timing" in tool_names_2
    assert "apply_subtitle_style" in tool_names_2


def test_tc_v144_04_shift_regex_no_hijack_and_multi_sentence_ranges():
    """TC-V144-04: BUG-SHIFT-REGEX-NUMBER-HIJACK-003 - Không bị cướp bởi 'N câu đầu', bắt đúng số offset và dải câu."""
    controller = AgentCopilotController()

    # 1. "Dịch 5 câu đầu lùi 500ms" -> shift_subtitles(-500, segment_indices=[1, 2, 3, 4, 5])
    p1 = controller._synthesize_plan("Dịch 5 câu đầu lùi 500ms")
    assert len(p1.steps) == 1
    assert p1.steps[0].tool_name == "shift_subtitles"
    assert p1.steps[0].tool_args.get("offset_ms") == -500
    assert p1.steps[0].tool_args.get("segment_indices") == [1, 2, 3, 4, 5]

    # 2. "Lùi câu 1 đến câu 3 đi 500ms" -> segment_indices=[1, 2, 3]
    p2 = controller._synthesize_plan("Lùi câu 1 đến câu 3 đi 500ms")
    assert len(p2.steps) == 1
    assert p2.steps[0].tool_name == "shift_subtitles"
    assert p2.steps[0].tool_args.get("offset_ms") == -500
    assert p2.steps[0].tool_args.get("segment_indices") == [1, 2, 3]

    # 3. "Lùi câu 1, 2 và 4 đi 400ms" -> segment_indices=[1, 2, 4]
    p3 = controller._synthesize_plan("Lùi câu 1, 2 và 4 đi 400ms")
    assert len(p3.steps) == 1
    assert p3.steps[0].tool_name == "shift_subtitles"
    assert p3.steps[0].tool_args.get("offset_ms") == -400
    assert p3.steps[0].tool_args.get("segment_indices") == [1, 2, 4]

    # 4. "Sau 2 giây, dịch phụ đề lùi 600ms" -> offset_ms=-600 (không bắt nhầm 2 giây)
    p4 = controller._synthesize_plan("Sau 2 giây, dịch phụ đề lùi 600ms")
    assert len(p4.steps) == 1
    assert p4.steps[0].tool_name == "shift_subtitles"
    assert p4.steps[0].tool_args.get("offset_ms") == -600


def test_tc_v144_05_bounds_multi_sentence_and_range_support():
    """TC-V144-05: BUG-BOUNDS-MULTI-SENTENCE-UNSUPPORTED-005 - Hỗ trợ dải câu và danh sách câu lẻ cho adjust_subtitle_bounds."""
    controller = AgentCopilotController()

    # 1. Dải câu: "Giảm mốc cuối từ câu 1 đến câu 3 đi 300ms"
    p1 = controller._synthesize_plan("Giảm mốc cuối từ câu 1 đến câu 3 đi 300ms")
    assert len(p1.steps) == 1
    assert p1.steps[0].tool_name == "adjust_subtitle_bounds"
    assert p1.steps[0].tool_args.get("delta_end_ms") == -300
    assert p1.steps[0].tool_args.get("segment_indices") == [1, 2, 3]

    # 2. Danh sách câu lẻ: "Tăng mốc đầu câu 1, 3 và 5 thêm 200ms"
    p2 = controller._synthesize_plan("Tăng mốc đầu câu 1, 3 và 5 thêm 200ms")
    assert len(p2.steps) == 1
    assert p2.steps[0].tool_name == "adjust_subtitle_bounds"
    assert p2.steps[0].tool_args.get("delta_start_ms") == 200
    assert p2.steps[0].tool_args.get("segment_indices") == [1, 3, 5]


def test_tc_v144_06_tab9_reconciles_row_count_and_timecodes_on_switch(qtbot):
    """TC-V144-06: BUG-TAB9-STALE-ROWS-AND-TIMECODES-006 - Chuyển vào Tab 9 cập nhật lại đúng số dòng và timecode mới từ SubEditor."""
    from ui.Gui import MainWindow

    card = EditableResultReportWidget()
    qtbot.addWidget(card)
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:02,000", "text": "Câu 1"},
        {"id": 2, "start": "00:00:03,000", "end": "00:00:04,000", "text": "Câu 2"},
        {"id": 3, "start": "00:00:05,000", "end": "00:00:06,000", "text": "Câu 3"},
    ]
    card.render_result("Task 1", {"segments": initial_segs})
    assert len(card._rows) == 3

    class DummyMainWindow:
        def __init__(self):
            self.sub_editor = MagicMock()
            # Người dùng ở Tab 1 đã xóa câu 3 (còn 2 câu) và sửa timecode câu 1
            self.sub_editor.all_segments = [
                {"id": 1, "start": "00:00:02,500", "end": "00:00:04,500", "text": "Câu 1 mới"},
                {"id": 2, "start": "00:00:05,000", "end": "00:00:07,000", "text": "Câu 2 mới"},
            ]
            self.video_player = MagicMock()
            self.page_ai_agent = MagicMock()
            self.page_ai_agent.controller = AgentCopilotController()
            self.page_ai_agent.col_inspect = MagicMock()
            self.page_ai_agent.col_inspect.inspection_card = card
            self._active_nav_index = 1

        def __getattr__(self, name):
            mock = MagicMock()
            setattr(self, name, mock)
            return mock

        switch_page = MainWindow.switch_page
        _sync_from_ai_agent_page = MainWindow._sync_from_ai_agent_page
        _sync_agent_video_context = MainWindow._sync_agent_video_context

    win = DummyMainWindow()
    win.switch_page(9)

    assert len(card._rows) == 2, f"Kỳ vọng bảng Cổng 2 cập nhật còn 2 dòng nhưng thực tế có {len(card._rows)} dòng"
    assert "00:00:02,500 → 00:00:04,500" in card._rows[0].lbl_info.text()
    assert card._rows[0].editor.text() == "Câu 1 mới"


def test_tc_v144_07_gate2_no_30_row_truncation(qtbot):
    """TC-V144-07: BUG-GATE2-30-ROW-HARD-TRUNCATION-007 - Cổng 2 hiển thị đầy đủ 50 câu phụ đề không cắt ở 30."""
    card = EditableResultReportWidget()
    qtbot.addWidget(card)
    segs_50 = [
        {"id": i + 1, "start": "00:00:01,000", "end": "00:00:02,000", "text": f"Câu #{i+1}"}
        for i in range(50)
    ]
    card.render_result("Tạo 50 câu", {"segments": segs_50})
    assert len(card._rows) == 50, f"Kỳ vọng hiển thị đủ 50 dòng nhưng bị cắt còn {len(card._rows)} dòng"
