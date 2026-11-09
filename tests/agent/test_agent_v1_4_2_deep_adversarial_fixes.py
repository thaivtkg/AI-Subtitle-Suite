import time
import pytest
from unittest.mock import MagicMock, patch
from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import shift_subtitles, create_timing
from core.agent.models import StepStatus, AgentStep, AgentTaskPlan
from ui.SubEditor import time_str_to_ms, ms_to_time_str


def test_tc_audit_01_rollback_fake_and_rerun():
    """TC-AUDIT-01: BUG-ROLLBACK-FAKE-001 - Transactional Rollback & Re-run.
    Khôi phục _active_segments và bảng báo cáo khi bấm Redo (kể cả khi trước task là rỗng []),
    và khi bấm Duyệt lại phải thực thi lại bước PENDING chứ không nhảy bước."""
    controller = AgentCopilotController()

    # Part A: Ban đầu có 3 câu, chạy task shift -> Redo -> khôi phục 3 câu ban đầu
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1"},
        {"id": 2, "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2"},
        {"id": 3, "start": "00:00:07,000", "end": "00:00:09,000", "text": "Câu 3"},
    ]
    controller._active_segments = list(initial_segs)

    # Lập plan dịch chuyển
    plan = AgentTaskPlan(
        prompt="Shift sub",
        steps=[
            AgentStep(
                id="step_1",
                title="Dịch chuyển phụ đề",
                tool_name="shift_subtitles",
                tool_args={"offset_ms": 1000},
            )
        ],
    )
    controller.active_plan = plan
    controller._waiting_task_approval = True
    controller._run_current_step()

    # Sau khi chạy, câu 1 phải ở 2000ms
    assert time_str_to_ms(controller._active_segments[0]["start"]) == 2000

    # Bấm Redo task
    reverted_received = []
    controller.step_reverted.connect(lambda idx, step, segs: reverted_received.append((idx, step, segs)))
    controller.request_task_revision("Làm lại bước này")

    # Kiểm chứng: _active_segments quay về 3 câu ban đầu (start 1000ms)
    assert len(controller._active_segments) == 3
    assert time_str_to_ms(controller._active_segments[0]["start"]) == 1000
    # Bước hiện tại phải ở trạng thái PENDING
    curr_step = controller.active_plan.current_step()
    assert curr_step.status == StepStatus.PENDING
    assert len(reverted_received) == 1
    assert reverted_received[0][2][0]["start"] == "00:00:01,000"

    # Khi bấm Duyệt (approve_next_step), phải chạy lại bước PENDING này
    controller.approve_next_step()
    # Sau khi chạy lại, câu 1 lại dịch sang 2000ms và status hoàn thành
    assert time_str_to_ms(controller._active_segments[0]["start"]) == 2000
    assert curr_step.status == StepStatus.COMPLETED

    # Part B: Ban đầu RỖNG ([]), chạy task tạo timing -> Redo -> khôi phục về RỖNG []
    controller2 = AgentCopilotController()
    controller2._active_segments = []
    plan2 = AgentTaskPlan(
        prompt="Create timing",
        steps=[
            AgentStep(
                id="step_1",
                title="Tạo timing",
                tool_name="create_timing",
                tool_args={"count": 3},
            )
        ],
    )
    controller2.active_plan = plan2
    controller2._waiting_task_approval = True
    controller2._run_current_step()
    assert len(controller2._active_segments) == 3

    # Redo: Phải khôi phục về đúng []
    controller2.request_task_revision("Hủy timing")
    assert controller2._active_segments == [], "Rollback phải đưa về [] nếu trước task là rỗng"


def test_tc_audit_02_bidirectional_sync_tab1_tab9_and_style_guard():
    """TC-AUDIT-02: BUG-SYNC-ONEWAY-002 - Đồng bộ 2 chiều Tab 1 <-> Tab 9 & Style Guard không tạo sub giả."""
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
            self._active_nav_index = 1

        def __getattr__(self, name):
            mock = MagicMock()
            setattr(self, name, mock)
            return mock

        switch_page = MainWindow.switch_page
        _sync_agent_video_context = MainWindow._sync_agent_video_context

    win = DummyMainWindow()
    # Tab 1 có 8 câu thật
    real_subtitles = [{"id": i, "start": f"00:00:0{i},000", "end": f"00:00:0{i+1},000", "text": f"Sub {i}"} for i in range(1, 9)]
    win.sub_editor.all_segments = list(real_subtitles)

    # Chuyển sang Tab 9 (switch_page(9))
    win.switch_page(9)

    # Kiểm chứng: controller._active_segments và col_inspect nhận đủ 8 câu thật
    assert len(win.page_ai_agent.controller._active_segments) == 8
    assert win.page_ai_agent.controller._active_segments[0]["text"] == "Sub 1"

    # Style Guard: Chạy apply_subtitle_style khi danh sách rỗng KHÔNG ĐƯỢC sinh 5 câu mẫu giả
    controller_empty = AgentCopilotController()
    controller_empty._active_segments = []
    plan_style = AgentTaskPlan(
        prompt="Change style",
        steps=[
            AgentStep(
                id="step_1",
                title="Đổi style",
                tool_name="apply_subtitle_style",
                tool_args={"font": "Arial", "color": "#FFFF00"},
            )
        ],
    )
    controller_empty.active_plan = plan_style
    controller_empty._waiting_task_approval = True
    controller_empty._run_current_step()
    assert controller_empty._active_segments == [], "apply_subtitle_style không được tự sinh 5 câu mẫu giả khi danh sách rỗng"


def test_tc_audit_03_gate2_edit_preserved_on_prompt_submit():
    """TC-AUDIT-03: BUG-GATE2-EDIT-LOST-003 - Bảo toàn sửa tay tại Cổng 2 khi người dùng gõ lệnh mới."""
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    # Khởi tạo page với controller
    controller = AgentCopilotController()
    controller._active_segments = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Văn bản gốc"},
    ]

    class DummyPage:
        def __init__(self):
            self.controller = controller
            self.col_inspect = MagicMock()
            self.col_chat = MagicMock()

        _on_prompt_submitted = AIAgentMissionControlPage._on_prompt_submitted

    page = DummyPage()

    # Giả lập người dùng đã sửa văn bản trên EditableSegmentRow tại Cổng 2
    edited_data = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Văn bản đã sửa tay"},
    ]
    page.col_inspect.get_current_segments.return_value = edited_data

    # Người dùng gõ luôn prompt mới mà không bấm duyệt
    page._on_prompt_submitted("đổi màu vàng")

    # Kiểm chứng: _active_segments đã được cập nhật văn bản sửa tay trước khi submit_prompt
    assert controller._active_segments[0]["text"] == "Văn bản đã sửa tay"


def test_tc_audit_04_shift_rigid_translation_invariant():
    """TC-AUDIT-04: BUG-SHIFT-SQUASH-004 - Bảo toàn 100% orig_dur (bất biến thời lượng) khi dịch lùi."""
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,500", "text": "Câu 1 (2.5s)"},
        {"id": 2, "start": "00:00:04,000", "end": "00:00:06,500", "text": "Câu 2 (2.5s)"},
        {"id": 3, "start": "00:00:07,000", "end": "00:00:09,500", "text": "Câu 3 (2.5s)"},
    ]

    # 1. Chạm sàn toàn phần: offset_ms = -50000ms
    res_full = shift_subtitles(offset_ms=-50000, segments=initial_segs)
    assert res_full["status"] == "ok"
    shifted_full = res_full["segments"]
    # Kiểm tra thời lượng từng câu: 100% phải giữ nguyên 2500ms
    assert shifted_full[0]["start"] == "00:00:00,000"
    assert shifted_full[0]["end"] == "00:00:02,500"
    assert shifted_full[1]["start"] == "00:00:02,500"
    assert shifted_full[1]["end"] == "00:00:05,000"
    assert shifted_full[2]["start"] == "00:00:05,000"
    assert shifted_full[2]["end"] == "00:00:07,500"

    # 2. Chạm sàn một phần: offset_ms = -1500ms trên câu [1000ms, 3500ms]
    res_partial = shift_subtitles(offset_ms=-1500, segments=[initial_segs[0]])
    assert res_partial["status"] == "ok"
    shifted_partial = res_partial["segments"]
    assert shifted_partial[0]["start"] == "00:00:00,000"
    assert shifted_partial[0]["end"] == "00:00:02,500", "Câu chạm sàn 1 phần phải giữ nguyên thời lượng gốc 2500ms"


def test_tc_audit_05_nlp_multi_odd_sentences():
    """TC-AUDIT-05: BUG-NLP-MULTI-ODD-005 - Nhận diện danh sách câu lẻ liệt kê."""
    controller = AgentCopilotController()

    # 1. Quét lại nhiều câu lẻ "Quét lại câu 1, 3 và 5"
    plan_rescan = controller._synthesize_plan("Quét lại câu 1, 3 và 5")
    assert len(plan_rescan.steps) == 1
    step_r = plan_rescan.steps[0]
    assert step_r.tool_name == "rescan_subtitles"
    assert step_r.tool_args.get("segment_indices") == [1, 3, 5]

    # 2. Gen sub nhiều câu lẻ "Gen sub câu 2, 4 và 6" và "Gen sub câu số 2, 4 và 6"
    plan_asr = controller._synthesize_plan("Gen sub câu 2, 4 và 6")
    assert len(plan_asr.steps) == 1
    step_a = plan_asr.steps[0]
    assert step_a.tool_name == "run_asr"
    assert step_a.tool_args.get("indices") == [2, 4, 6]

    plan_asr2 = controller._synthesize_plan("Gen sub câu số 2, 4 và 6")
    assert len(plan_asr2.steps) == 1
    assert plan_asr2.steps[0].tool_args.get("indices") == [2, 4, 6]


def test_tc_audit_06_nlp_avoid_collision_moc_dau_with_shift():
    """TC-AUDIT-06: BUG-NLP-COLLISION-006 - 'Lùi sub từ mốc đầu 500ms' phải vào shift_subtitles chứ không vào adjust_subtitle_bounds."""
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("Lùi sub từ mốc đầu 500ms")
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "shift_subtitles", f"Kỳ vọng shift_subtitles nhưng nhận {step.tool_name}"
    assert step.tool_args.get("offset_ms") == -500


def test_tc_audit_07_perf_gate1_no_synchronous_vad():
    """TC-AUDIT-07: BUG-PERF-GATE1-VAD-007 - Cổng 1 không gọi VAD đồng bộ và phản hồi tức thì (< 50ms)."""
    controller = AgentCopilotController()
    controller.context_ledger.video_path = r"D:\Projects\Video\JMSZ38_02.wmv"

    with patch("core.agent.vad_timing_service.generate_vad_timing_segments") as mock_vad:
        t0 = time.perf_counter()
        plan = controller._synthesize_plan("Tạo timing 5 câu đầu")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # VAD không được gọi tại Cổng 1 (chỉ gọi tại Cổng 2 khi execute tool)
        mock_vad.assert_not_called()
        assert elapsed_ms < 50, f"Cổng 1 phản hồi chậm: {elapsed_ms:.2f}ms >= 50ms"
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "create_timing"
        assert plan.steps[0].tool_args.get("count") == 5
