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
    """TC-V144-02: BUG-TRANSLATE-INVISIBLE-AND-WIPED-001 - translate_subtitles cập nhật cả text & translation, lưu source_text (văn bản dịch thật, CẤM dán [VI])."""
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    mock_llm.generate_with_fallback.return_value = {"content": "Xin chào thế giới"}

    segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Hello world"},
    ]
    res = translate_subtitles(target_lang="vi", segments=segs, llm_client=mock_llm)
    assert res["status"] == "ok"
    out = res["segments"]
    assert len(out) == 1
    assert out[0]["source_text"] == "Hello world"
    assert out[0]["translation"] == "Xin chào thế giới"
    assert out[0]["text"] == "Xin chào thế giới"
    assert not out[0]["text"].startswith("[VI]")

    # Kiểm tra UI Cổng 2 hiển thị ngay văn bản dịch
    card = EditableResultReportWidget()
    qtbot.addWidget(card)
    card.render_result("Dịch phụ đề", res)
    assert len(card._rows) == 1
    assert card._rows[0].editor.text() == "Xin chào thế giới"


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


def test_tc_v144_08_shift_no_dialogue_swap_no_duration_crush_and_backward_selective():
    """TC-V144-08: BUG-SHIFT-DIALOGUE-SWAP-AND-DURATION-CRUSH-001 - Không đảo thứ tự thoại/ID, không ép thời lượng xuống 200ms, cho phép lùi câu lẻ."""
    segs = [
        {"id": 1, "start": "00:01.000", "end": "00:03.000", "text": "Lời thoại câu 1 (Xin chào)"},
        {"id": 2, "start": "00:03.500", "end": "00:05.500", "text": "Lời thoại câu 2 (Bạn khỏe không?)"},
        {"id": 3, "start": "00:06.000", "end": "00:08.000", "text": "Lời thoại câu 3 (Tạm biệt)"},
    ]
    # 1A: Tiến câu 1 thêm 2400ms -> câu 2 giữ nguyên thời lượng 2000ms (không bị ép xuống 200ms)
    res_1a = shift_subtitles(offset_ms=2400, scope="selected", segment_indices=[1], segments=segs)
    s2 = res_1a["segments"][1]
    dur_s2 = time_str_to_ms(s2["end"]) - time_str_to_ms(s2["start"])
    assert dur_s2 == 2000, f"Thời lượng câu 2 phải giữ nguyên 2000ms nhưng bị ép còn {dur_s2}ms"

    # 1B: Tiến câu 1 thêm 3000ms -> thứ tự câu 1 và câu 2 không bị đảo ngược
    res_1b = shift_subtitles(offset_ms=3000, scope="selected", segment_indices=[1], segments=segs)
    assert res_1b["segments"][0]["id"] == 1
    assert "Xin chào" in res_1b["segments"][0]["text"]
    assert res_1b["segments"][1]["id"] == 2
    assert "Bạn khỏe không" in res_1b["segments"][1]["text"]
    assert time_str_to_ms(res_1b["segments"][0]["end"]) <= time_str_to_ms(res_1b["segments"][1]["start"])

    # 1C: Lùi câu 2 đi 800ms khi câu 1 (1s..3s) và câu 2 (3s..5s) chạm nhau
    segs_touching = [
        {"id": 1, "start": "00:01.000", "end": "00:03.000", "text": "Câu 1"},
        {"id": 2, "start": "00:03.000", "end": "00:05.000", "text": "Câu 2"},
    ]
    res_1c = shift_subtitles(offset_ms=-800, scope="selected", segment_indices=[2], segments=segs_touching)
    st_c2 = time_str_to_ms(res_1c["segments"][1]["start"])
    en_c1 = time_str_to_ms(res_1c["segments"][0]["end"])
    assert st_c2 == 2200, f"Câu 2 phải lùi về 2200ms nhưng thực tế ở {st_c2}ms"
    assert en_c1 <= st_c2, "Câu 1 phải thu ngắn end để không đè chồng lên câu 2"


def test_tc_v144_09_tab9_switch_preserves_style_card_gate1_isolation_and_empty_placeholder(qtbot):
    """TC-V144-09: BUG-TAB9-SWITCH-WIPES-STYLE-AND-CORRUPTS-GATE1-002 - Bảo toàn Style Card, cô lập Cổng 1 và không dump raw text khi rỗng."""
    from PySide6.QtWidgets import QTextEdit
    from ui.Gui import MainWindow
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage
    from ui.components.agent_report_inspector_widget import SubtitleStyleCardWidget

    class Harness:
        _sync_from_ai_agent_page = MainWindow._sync_from_ai_agent_page
        _on_agent_step_completed = MainWindow._on_agent_step_completed
        _on_agent_step_reverted = MainWindow._on_agent_step_reverted
        _sync_agent_video_context = MainWindow._sync_agent_video_context
        switch_page = MainWindow.switch_page

        def __getattr__(self, name):
            return MagicMock()

        def __init__(self):
            self._active_nav_index = 1
            self.sub_editor = MagicMock()
            self.sub_editor.all_segments = [
                {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1"},
            ]
            self.video_player = MagicMock()
            self.video_player.video_path = ""
            self.stack = MagicMock()
            self.page_ai_agent = AIAgentMissionControlPage()

    win = Harness()
    qtbot.addWidget(win.page_ai_agent)
    card = win.page_ai_agent.col_inspect.inspection_card

    # 2A: Đổi style ở Cổng 2 -> chuyển tab 0 -> quay lại tab 9 -> giữ nguyên SubtitleStyleCardWidget
    win.switch_page(9)
    win.page_ai_agent.col_chat.prompt_input.setText("Đổi style chữ vàng viền đen cỡ 26")
    win.page_ai_agent.col_chat.btn_send_prompt.click()
    win.page_ai_agent.col_inspect.btn_approve_next.click()
    assert len(card.findChildren(SubtitleStyleCardWidget)) == 1
    win.switch_page(0)
    win.switch_page(9)
    assert len(card.findChildren(SubtitleStyleCardWidget)) == 1, "Không được xóa mất SubtitleStyleCardWidget khi chuyển tab"

    # 2B: Đang ở Cổng 1 -> chuyển tab 0 -> quay lại tab 9 -> current_segments phải vẫn là []
    win.page_ai_agent.col_chat.prompt_input.setText("Dịch phụ đề sang tiếng Việt")
    win.page_ai_agent.col_chat.btn_send_prompt.click()
    assert win.page_ai_agent.controller.is_waiting_plan_approval() is True
    assert len(card.get_current_segments()) == 0
    win.switch_page(0)
    win.switch_page(9)
    assert len(card.get_current_segments()) == 0, "Cổng 1 không được rò rỉ current_segments khi chuyển tab"

    # 2C: Dự án rỗng [] -> quay lại tab 9 không được hiện QTextEdit raw dump
    win.page_ai_agent.col_inspect.btn_approve_next.click()  # Chạy sang Cổng 2
    win.switch_page(0)
    win.sub_editor.all_segments = []
    win.switch_page(9)
    assert len(card.findChildren(QTextEdit)) == 0, "Không được hiện QTextEdit raw dump khi segments rỗng"


def test_tc_v144_10_translate_preserves_original_text_key_for_cat_studio():
    """TC-V144-10: BUG-CAT-STUDIO-ORIGINAL-TEXT-OVERWRITTEN-003 - Lưu câu gốc vào 'original_text' chuẩn của CAT Studio."""
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    mock_llm.generate_with_fallback.return_value = {"content": "Xin chào thế giới"}

    orig_segs = [
        {"id": 1, "stt": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "こんにちは、世界"},
    ]
    res = translate_subtitles(target_lang="vi", segments=orig_segs, llm_client=mock_llm)
    out = res["segments"][0]
    assert out.get("original_text") == "こんにちは、世界"
    assert out.get("source_text") == "こんにちは、世界"
    assert out.get("text") == "Xin chào thế giới"
    assert not out.get("text").startswith("[VI]")


def test_tc_v144_11_nlp_repeated_cau_keyword_across_all_tools():
    """TC-V144-11: BUG-NLP-REPEATED-CAU-KEYWORD-DROPPED-004 - Hỗ trợ lặp lại từ 'câu' trong danh sách câu trên cả 4 công cụ."""
    controller = AgentCopilotController()
    cases = [
        ("Tăng mốc đầu câu 1 và câu 2 thêm 200ms", "adjust_subtitle_bounds", [1, 2]),
        ("Giảm mốc cuối câu 1, câu 2 và câu 3 đi 300ms", "adjust_subtitle_bounds", [1, 2, 3]),
        ("Dịch câu 1 và câu 3 tiến 400ms", "shift_subtitles", [1, 3]),
        ("Quét lại câu 1, câu 3 và câu 5", "rescan_subtitles", [1, 3, 5]),
        ("Gen sub câu 2 và câu 4", "run_asr", [2, 4]),
    ]
    for prompt, expected_tool, expected_indices in cases:
        plan = controller._synthesize_plan(prompt)
        step = plan.steps[0]
        actual_indices = step.tool_args.get("segment_indices") or step.tool_args.get("indices")
        assert step.tool_name == expected_tool, f"Prompt '{prompt}': kỳ vọng {expected_tool}, nhận {step.tool_name}"
        assert actual_indices == expected_indices, f"Prompt '{prompt}': kỳ vọng {expected_indices}, nhận {actual_indices}"
