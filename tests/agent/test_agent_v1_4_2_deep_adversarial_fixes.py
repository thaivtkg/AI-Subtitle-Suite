import pytest
import time
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import shift_subtitles
from core.agent.models import StepStatus
from ui.components.agent_report_inspector_widget import EditableSegmentRow
from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage


# =========================================================================
# TC-AUDIT-01: BUG-ROLLBACK-FAKE-001
# Khi bấm "Yêu cầu làm lại task này", dữ liệu _active_segments và UI phải
# khôi phục về trạng thái pre-task; khi bấm Duyệt lại, hệ thống phải chạy lại task
# =========================================================================
def test_tc_audit_01_rollback_restores_pre_task_data_and_reruns(qtbot):
    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # Giả lập ban đầu đang có 3 câu phụ đề gốc
    initial_segs = [
        {"start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1 gốc"},
        {"start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2 gốc"},
        {"start": "00:00:07,000", "end": "00:00:09,000", "text": "Câu 3 gốc"},
    ]
    controller._active_segments = list(initial_segs)

    # Người dùng gửi lệnh dịch chuyển phụ đề
    controller.submit_prompt("Lùi sub 500ms")
    assert controller.is_waiting_plan_approval()

    # Duyệt Kế Hoạch (Cổng 1)
    btn_approve = page.findChild(QPushButton, "btn_approve_next")
    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)

    # Đã thực thi xong Cổng 2 -> Mốc thời gian bị lùi 500ms
    assert controller.is_waiting_task_approval()
    assert controller._active_segments[0]["start"] == "00:00:00,500"

    # Người dùng bấm "Yêu cầu làm lại task này" (btn_redo_task)
    btn_redo = page.findChild(QPushButton, "btn_redo_task")
    qtbot.mouseClick(btn_redo, Qt.MouseButton.LeftButton)

    # 1. Dữ liệu _active_segments PHẢI quay về ban đầu ("00:00:01,000")
    assert controller._active_segments[0]["start"] == "00:00:01,000"
    assert controller._active_segments[0]["text"] == "Câu 1 gốc"

    # 2. Bước hiện tại phải là PENDING
    curr_step = controller.active_plan.current_step()
    assert curr_step is not None
    assert curr_step.status == StepStatus.PENDING

    # 3. Nút duyệt đổi nhãn thành "✔ Chạy lại Task này"
    assert btn_approve.text() == "✔ Chạy lại Task này"

    # 4. Khi bấm Duyệt lại, hệ thống PHẢI thực thi lại (thay vì skip về COMPLETED)
    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)
    assert controller.is_waiting_task_approval()
    assert controller._active_segments[0]["start"] == "00:00:00,500"


# =========================================================================
# TC-AUDIT-02: BUG-SYNC-ONEWAY-002
# Chuyển từ Tab 1 sang Tab 9 phải đồng bộ 2 chiều phụ đề thật vào _active_segments,
# không bị AI tự sinh 5 câu giả chép đè xóa sạch phụ đề SubEditor
# =========================================================================
def test_tc_audit_02_tab1_to_tab9_bidirectional_sync_preserves_real_subtitles(qtbot):
    from ui.Gui import MainWindow

    main_win = MainWindow()
    qtbot.addWidget(main_win)

    real_subtitles = [
        {"start": "00:00:01,000", "end": "00:00:03,500", "text": "Thoại nhân vật A"},
        {"start": "00:00:04,000", "end": "00:00:07,000", "text": "Thoại nhân vật B"},
        {"start": "00:00:08,000", "end": "00:00:10,000", "text": "Thoại nhân vật C"},
    ]
    main_win.sub_editor.all_segments = list(real_subtitles)

    # Chuyển từ Tab 1 sang Tab 9
    main_win.switch_page(9)

    # 1. _active_segments của AI Agent phải chứa đúng 3 câu phụ đề thật từ Tab 1
    agent_segs = main_win.page_ai_agent.controller._active_segments
    assert len(agent_segs) == 3
    assert agent_segs[0]["text"] == "Thoại nhân vật A"

    # 2. Chạy lệnh đổi style phụ đề trên Tab 9
    main_win.page_ai_agent.controller.submit_prompt("đổi style phụ đề chữ vàng viền đen")
    main_win.page_ai_agent._on_approve_clicked()

    # 3. Phụ đề thật không bị thay thế bằng "Dòng phụ đề #1..#5"
    assert len(main_win.page_ai_agent.controller._active_segments) == 3
    assert main_win.page_ai_agent.controller._active_segments[0]["text"] == "Thoại nhân vật A"

    # Chuyển về Tab 1
    main_win.switch_page(1)
    assert len(main_win.sub_editor.all_segments) == 3
    assert main_win.sub_editor.all_segments[0]["text"] == "Thoại nhân vật A"


# =========================================================================
# TC-AUDIT-03: BUG-GATE2-EDIT-LOST-003
# Sửa tay trực tiếp ở Cổng 2 rồi gõ ngay lệnh mới vào ô chat không bị mất dữ liệu
# =========================================================================
def test_tc_audit_03_gate2_manual_edit_preserved_on_next_prompt(qtbot):
    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # Step 1: Tạo timing
    controller.submit_prompt("Tạo timing 3 câu đầu")
    page._on_approve_clicked()  # Approve Gate 1
    assert controller.is_waiting_task_approval()

    # Sửa trực tiếp câu 1 trên UI Cổng 2
    rows = page.findChildren(EditableSegmentRow)
    assert len(rows) >= 3
    edited_text = "Nội dung sửa tay quan trọng tại Cổng 2"
    rows[0].editor.setText(edited_text)

    # Người dùng gõ luôn lệnh tiếp theo vào chat
    page._on_prompt_submitted("Đổi style font Arial chữ trắng")

    # Nội dung sửa tay câu 1 PHẢI được bảo toàn trong _active_segments của controller
    assert controller._active_segments[0]["text"] == edited_text


# =========================================================================
# TC-AUDIT-04: BUG-SHIFT-SQUASH-004
# Lùi sub cực đại chạm biên 0ms phải bảo toàn orig_dur, không bị bóp nghẹt về 200ms
# =========================================================================
def test_tc_audit_04_shift_subtitles_preserves_orig_duration_at_zero_floor():
    # 3 câu dài 2500ms mỗi câu
    segs = [
        {"start": "00:00:01,000", "end": "00:00:03,500", "text": "Câu 1"},
        {"start": "00:00:04,000", "end": "00:00:06,500", "text": "Câu 2"},
        {"start": "00:00:07,000", "end": "00:00:09,500", "text": "Câu 3"},
    ]
    # Lùi 50000ms chạm sàn 0ms
    res = shift_subtitles(offset_ms=-50000, segments=segs)
    res_segs = res["segments"]

    from ui.SubEditor import time_str_to_ms
    dur_1 = time_str_to_ms(res_segs[0]["end"]) - time_str_to_ms(res_segs[0]["start"])
    dur_2 = time_str_to_ms(res_segs[1]["end"]) - time_str_to_ms(res_segs[1]["start"])
    dur_3 = time_str_to_ms(res_segs[2]["end"]) - time_str_to_ms(res_segs[2]["start"])

    # Cả 3 câu phải bảo toàn đúng thời lượng gốc 2500ms thay vì bị bóp về 200ms!
    assert dur_1 == 2500
    assert dur_2 == 2500
    assert dur_3 == 2500
    assert res_segs[0]["start"] == "00:00:00,000"
    assert res_segs[0]["end"] == "00:00:02,500"
    assert res_segs[1]["start"] == "00:00:02,500"
    assert res_segs[1]["end"] == "00:00:05,000"
    assert res_segs[2]["start"] == "00:00:05,000"
    assert res_segs[2]["end"] == "00:00:07,500"


# =========================================================================
# TC-AUDIT-05: BUG-NLP-MULTI-ODD-005
# Liệt kê nhiều câu lẻ ("câu 1, 3 và 5" / "câu 2, 4 và 6") nhận diện đầy đủ danh sách
# =========================================================================
def test_tc_audit_05_multi_odd_sentences_parsed_cleanly():
    controller = AgentCopilotController()

    # Rescan danh sách câu lẻ
    plan_rescan = controller._synthesize_plan("Quét lại câu 1, 3 và 5")
    assert len(plan_rescan.steps) == 1
    assert plan_rescan.steps[0].tool_name == "rescan_subtitles"
    assert plan_rescan.steps[0].tool_args["segment_indices"] == [1, 3, 5]

    # ASR danh sách câu lẻ
    plan_asr = controller._synthesize_plan("Gen sub câu 2, 4 và 6")
    assert len(plan_asr.steps) == 1
    assert plan_asr.steps[0].tool_name == "run_asr"
    assert plan_asr.steps[0].tool_args["indices"] == [2, 4, 6]


# =========================================================================
# TC-AUDIT-06: BUG-NLP-COLLISION-006
# Xung đột từ khóa "mốc"/"đầu" không được chặn lệnh dịch chuyển (shift)
# =========================================================================
def test_tc_audit_06_collision_between_shift_and_bounds_keywords_resolved():
    controller = AgentCopilotController()

    plan = controller._synthesize_plan("Lùi sub từ mốc đầu 500ms")
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "shift_subtitles"
    assert plan.steps[0].tool_args["offset_ms"] == -500


# =========================================================================
# TC-AUDIT-07: BUG-PERF-GATE1-VAD-007
# Khi tổng hợp kế hoạch ở Cổng 1, không được chạy VAD đồng bộ gây trễ UI
# =========================================================================
def test_tc_audit_07_gate1_plan_synthesis_does_not_block_on_vad():
    controller = AgentCopilotController()
    controller.context_ledger.video_path = r"D:\Projects\Video\JMSZ38_02.wmv"

    with patch("core.agent.vad_timing_service.generate_vad_timing_segments") as mock_vad:
        # Tổng hợp kế hoạch Cổng 1
        plan = controller._synthesize_plan("Tạo timing 5 câu đầu")
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "create_timing"
        # Mock VAD KHÔNG được gọi tại Cổng 1 (tránh làm đơ UI thread)
        mock_vad.assert_not_called()
