import pytest
from unittest.mock import MagicMock
from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import (
    AgentToolRegistry,
    run_asr,
    rescan_subtitles,
    shift_subtitles,
    adjust_subtitle_bounds,
)
from core.agent.models import AgentTaskPlan, AgentStep, StepStatus


def test_tc_audit_08_run_asr_preserves_other_segments_and_subeditor_format():
    """TC-AUDIT-08: BUG-DATA-DESTROY-ASR-001 - run_asr không xóa mất các câu khác khi gen sub câu lẻ/limit,
    và xử lý an toàn phụ đề từ SubEditor (không có khóa 'id')."""
    # 5 câu phụ đề từ SubEditor (không có khóa id)
    initial_segs = [
        {"start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1 cũ"},
        {"start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2 cũ"},
        {"start": "00:00:07,000", "end": "00:00:09,000", "text": "Câu 3 cũ"},
        {"start": "00:00:10,000", "end": "00:00:12,000", "text": "Câu 4 cũ"},
        {"start": "00:00:13,000", "end": "00:00:15,000", "text": "Câu 5 cũ"},
    ]

    # 1. Test tool run_asr trực tiếp với indices=[2, 4] kèm mock service và video file
    import tempfile
    mock_svc = MagicMock()
    mock_svc.model = MagicMock()
    mock_svc.transcribe_batch.side_effect = lambda request, batch, cancelled: MagicMock(
        error=None, segments=[MagicMock(text="Nhận diện mới", start_ms=batch.start_ms, end_ms=batch.end_ms)]
    )
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_vid:
        res = run_asr(indices=[2, 4], segments=initial_segs, video_path=tmp_vid.name, whisper_service=mock_svc)
        assert res["status"] == "ok"
        segs = res["segments"]
        assert len(segs) == 5, f"Kỳ vọng bảo toàn 5 câu nhưng chỉ còn {len(segs)} câu"
        assert segs[0]["text"] == "Câu 1 cũ"
        assert segs[2]["text"] == "Câu 3 cũ"
        assert segs[4]["text"] == "Câu 5 cũ"
        # Câu 2 và 4 được nhận diện lại text
        assert segs[1]["text"] != "Câu 2 cũ"
        assert segs[3]["text"] != "Câu 4 cũ"

        # 2. Test controller _run_current_step với limit=2 trên dự án 5 câu
        controller = AgentCopilotController()
        controller.whisper_service = mock_svc
        controller.context_ledger.video_path = tmp_vid.name
        controller._active_segments = list(initial_segs)
        plan = AgentTaskPlan(
            prompt="Gen sub 2 câu đầu",
            steps=[
                AgentStep(
                    id="step_1",
                    title="ASR Gen Sub 2 câu đầu",
                    tool_name="run_asr",
                    tool_args={"limit": 2},
                )
            ],
        )
        controller.active_plan = plan
        controller._waiting_task_approval = True
        controller._run_current_step()
        # Kiểm tra controller._active_segments không bị cắt cụt về 2 câu
        assert len(controller._active_segments) == 5, "Dự án phải giữ nguyên 5 câu, không bị cắt cụt về limit=2"
        assert controller._active_segments[2]["text"] == "Câu 3 cũ"


def test_tc_audit_09_unregistered_tools_translate_and_render_hardsub():
    """TC-AUDIT-09: BUG-UNREGISTERED-TOOLS-002 - translate_subtitles và render_hardsub được đăng ký và thực thi an toàn."""
    registry = AgentToolRegistry()
    registry.register_default_tools()

    assert registry.has_tool("translate_subtitles"), "Thiếu tool translate_subtitles trong registry"
    assert registry.has_tool("render_hardsub"), "Thiếu tool render_hardsub trong registry"

    segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Hello world"},
    ]

    # Test thực thi translate_subtitles
    res_trans = registry.safe_execute_tool("translate_subtitles", {"target_lang": "vi", "segments": segs})
    assert res_trans["success"] is True
    assert len(res_trans["result"]["segments"]) == 1

    # Test thực thi render_hardsub
    res_render = registry.safe_execute_tool("render_hardsub", {"resolution": "1080p", "segments": segs})
    assert res_render["success"] is True
    assert len(res_render["result"]["segments"]) == 1


def test_tc_audit_10_rescan_subtitles_time_interval_and_subeditor_format():
    """TC-AUDIT-10: BUG-RESCAN-NOOP-003 - rescan_subtitles hỗ trợ time_interval và phụ đề không có id."""
    initial_segs = [
        {"start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1"},
        {"start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2"},
        {"start": "00:00:07,000", "end": "00:00:09,000", "text": "Câu 3"},
        {"start": "00:00:10,000", "end": "00:00:12,000", "text": "Câu 4"},
    ]

    # 1. Quét lại theo khoảng thời gian [2s, 5s] -> giao thoa câu 1 (1s..3s) và câu 2 (4s..6s)
    res_time = rescan_subtitles(scope="time_interval", start_ms=2000, end_ms=5000, segments=initial_segs)
    assert res_time["status"] == "ok"
    segs_time = res_time["segments"]
    assert "(quét lại)" in segs_time[0]["text"]
    assert "(quét lại)" in segs_time[1]["text"]
    assert "(quét lại)" not in segs_time[2]["text"]
    assert "(quét lại)" not in segs_time[3]["text"]

    # 2. Quét lại theo câu lẻ trên phụ đề thiếu id: "câu 2" (segment_indices=[2])
    res_single = rescan_subtitles(scope="selected", segment_indices=[2], segments=initial_segs)
    assert res_single["status"] == "ok"
    segs_single = res_single["segments"]
    assert "(quét lại)" in segs_single[1]["text"]
    assert "(quét lại)" not in segs_single[0]["text"]


def test_tc_audit_11_gate1_redo_disabled_and_noop_guard():
    """TC-AUDIT-11: BUG-GATE1-REDO-CORRUPT-004 - btn_redo_task bị vô hiệu ở Cổng 1 và request_task_revision có noop guard."""
    from ui.components.agent_report_inspector_widget import AgentReportInspectorWidget
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    # 1. Test widget inspector
    inspector = AgentReportInspectorWidget()
    assert inspector.btn_redo_task.isEnabled() is False, "btn_redo_task phải bị disable ban đầu"

    plan = AgentTaskPlan(prompt="Test", steps=[AgentStep(id="1", title="Step 1", tool_name="create_timing")])
    inspector.render_plan_briefing(plan)
    assert inspector.btn_redo_task.isEnabled() is False, "btn_redo_task phải bị disable ở Cổng 1"

    # 2. Test controller noop guard khi đang chờ duyệt kế hoạch
    controller = AgentCopilotController()
    controller.active_plan = plan
    controller._waiting_plan_approval = True
    controller._waiting_task_approval = False
    controller.request_task_revision("Thử làm lại ở Cổng 1")
    # Không được bật _waiting_task_approval lên True
    assert controller.is_waiting_plan_approval() is True
    assert controller.is_waiting_task_approval() is False


def test_tc_audit_12_tab_pingpong_preserves_subeditor_edits():
    """TC-AUDIT-12: BUG-TAB-PINGPONG-OVERWRITE-005 - Đồng bộ từ SubEditor khi Tab 9 đang ở Cổng 2 không bị chép đè."""
    from ui.Gui import MainWindow

    class DummyMainWindow:
        def __init__(self):
            self.sub_editor = MagicMock()
            self.sub_editor.all_segments = []
            self.video_player = MagicMock()
            self.page_ai_agent = MagicMock()
            self.page_ai_agent.controller = AgentCopilotController()
            self.page_ai_agent.col_inspect = MagicMock()
            self.page_ai_agent.col_inspect.inspection_card = MagicMock()
            self.page_ai_agent.col_inspect.inspection_card.current_segments = []
            self.page_ai_agent.col_inspect.get_current_segments = lambda: self.page_ai_agent.col_inspect.inspection_card.current_segments
            self.page_ai_agent.get_current_segments = lambda: self.page_ai_agent.col_inspect.inspection_card.current_segments
            self._active_nav_index = 9

        def __getattr__(self, name):
            mock = MagicMock()
            setattr(self, name, mock)
            return mock

        switch_page = MainWindow.switch_page
        _sync_from_ai_agent_page = MainWindow._sync_from_ai_agent_page
        _sync_agent_video_context = MainWindow._sync_agent_video_context

    win = DummyMainWindow()
    # Tab 9 đang dừng ở Cổng 2
    win.page_ai_agent.controller._waiting_task_approval = True
    win.page_ai_agent.controller._active_segments = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu cũ Tab 9"}
    ]
    win.page_ai_agent.col_inspect.inspection_card.current_segments = win.page_ai_agent.controller._active_segments

    # Người dùng sang Tab 1 sửa phụ đề
    edited_subeditor_data = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Sửa trực tiếp ở SubEditor Tab 1"}
    ]
    win.sub_editor.all_segments = edited_subeditor_data

    # Chuyển sang Tab 9 (switch_page(9))
    win.switch_page(9)

    # Kiểm tra Tab 9 nhận đúng bản sửa
    assert win.page_ai_agent.controller._active_segments[0]["text"] == "Sửa trực tiếp ở SubEditor Tab 1"

    # Chuyển lại về Tab 1 (switch_page(1))
    win.switch_page(1)
    # Kiểm tra SubEditor không bị chép đè mất câu vừa sửa
    assert win.sub_editor.all_segments[0]["text"] == "Sửa trực tiếp ở SubEditor Tab 1"


def test_tc_audit_13_shift_sign_dich_sub_and_target_sentence():
    """TC-AUDIT-13: BUG-SHIFT-SIGN-AND-TARGET-006 - Nhận diện dấu âm, 'dịch sub' không nhầm CAT, và chỉ định câu lẻ."""
    controller = AgentCopilotController()

    # 1. Dấu trừ âm: "Dịch chuyển sub -500ms"
    p1 = controller._synthesize_plan("Dịch chuyển sub -500ms")
    assert len(p1.steps) == 1
    assert p1.steps[0].tool_name == "shift_subtitles"
    assert p1.steps[0].tool_args.get("offset_ms") == -500

    # 2. "Dịch sub -500ms" không nhảy sang translate_subtitles
    p2 = controller._synthesize_plan("Dịch sub -500ms")
    assert len(p2.steps) == 1
    assert p2.steps[0].tool_name == "shift_subtitles"
    assert p2.steps[0].tool_args.get("offset_ms") == -500

    # 3. Chỉ định câu: "Lùi câu 2 đi 300ms"
    p3 = controller._synthesize_plan("Lùi câu 2 đi 300ms")
    assert len(p3.steps) == 1
    assert p3.steps[0].tool_name == "shift_subtitles"
    assert p3.steps[0].tool_args.get("offset_ms") == -300
    assert p3.steps[0].tool_args.get("segment_indices") == [2]

    # Test tool shift_subtitles với segment_indices=[2]
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1"},
        {"id": 2, "start": "00:00:05,000", "end": "00:00:07,000", "text": "Câu 2"},
    ]
    res_shift = shift_subtitles(offset_ms=-300, segment_indices=[2], segments=initial_segs)
    assert res_shift["status"] == "ok"
    assert res_shift["segments"][0]["start"] == "00:00:01,000"  # Câu 1 giữ nguyên
    assert res_shift["segments"][1]["start"] == "00:00:04,700"  # Câu 2 bị lùi 300ms


def test_tc_audit_14_nlp_bounds_vietnamese_word_order_and_sentence_target():
    """TC-AUDIT-14: BUG-NLP-BOUNDS-WORD-ORDER-007 - Trật tự từ tiếng Việt tự nhiên [Động từ] + [Mốc] + [Số]."""
    controller = AgentCopilotController()

    # 1. "Giảm mốc cuối 300ms"
    p1 = controller._synthesize_plan("Giảm mốc cuối 300ms")
    assert len(p1.steps) == 1
    assert p1.steps[0].tool_name == "adjust_subtitle_bounds"
    assert p1.steps[0].tool_args.get("delta_end_ms") == -300

    # 2. "Tăng mốc đầu câu 2 thêm 200ms"
    p2 = controller._synthesize_plan("Tăng mốc đầu câu 2 thêm 200ms")
    assert len(p2.steps) == 1
    assert p2.steps[0].tool_name == "adjust_subtitle_bounds"
    assert p2.steps[0].tool_args.get("delta_start_ms") == 200
    assert p2.steps[0].tool_args.get("segment_indices") == [2]

    # 3. "Lùi đầu câu đi 150ms"
    p3 = controller._synthesize_plan("Lùi đầu câu đi 150ms")
    assert len(p3.steps) == 1
    assert p3.steps[0].tool_name == "adjust_subtitle_bounds"
    assert p3.steps[0].tool_args.get("delta_start_ms") == -150
