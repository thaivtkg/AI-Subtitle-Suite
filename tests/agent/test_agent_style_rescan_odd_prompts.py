import pytest
from unittest.mock import MagicMock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.models import AgentStep, StepStatus


# =========================================================================
# TC-ACC-STYLE-01: Bóc tách Font, Màu, Cỡ chữ & Viền
# =========================================================================
def test_tc_acc_style_01_parse_font_color_size_outline():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("đổi style sub chữ vàng viền đen cỡ 24 font Roboto")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "apply_subtitle_style"
    assert step.tool_args.get("font_name") == "Roboto"
    assert step.tool_args.get("font_size") == 24
    assert step.tool_args.get("font_color") == "#FFFF00"
    assert step.tool_args.get("outline_color") == "#000000"

    # Tool execution must be registered and return ok
    assert controller.tool_registry.has_tool("apply_subtitle_style")
    res = controller.tool_registry.execute_tool("apply_subtitle_style", step.tool_args)
    assert res["status"] == "ok"
    assert res["style"]["font_name"] == "Roboto"


# =========================================================================
# TC-ACC-STYLE-02: Đồng bộ Video Overlay khi Duyệt Style
# =========================================================================
def test_tc_acc_style_02_video_overlay_synchronization(qtbot):
    from ui.Gui import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.show()

    win.switch_page(9)
    page = win.page_ai_agent
    controller = page.controller

    controller.submit_prompt("đổi style sub chữ đỏ viền trắng cỡ 30 font Arial")
    controller.approve_plan()

    assert controller.is_waiting_task_approval()
    # Overlay in video player must reflect applied style
    overlay = win.video_player.subtitle_overlay
    assert overlay.font_family == "Arial"
    assert overlay.font_size == 30
    assert overlay.text_color.name().lower() == "#ff0000"
    assert overlay.outline_color.name().lower() == "#ffffff"


# =========================================================================
# TC-ACC-RESCAN-01: Quét lại câu đơn
# =========================================================================
def test_tc_acc_rescan_01_single_sentence():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("quét lại câu 1")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "rescan_subtitles"
    assert step.tool_args.get("scope") == "selected"
    assert step.tool_args.get("segment_indices") == [1]

    # Verify tool execution
    assert controller.tool_registry.has_tool("rescan_subtitles")
    res = controller.tool_registry.execute_tool("rescan_subtitles", step.tool_args)
    assert res["status"] == "ok"
    assert res["segment_indices"] == [1]


# =========================================================================
# TC-ACC-RESCAN-02: Quét lại dải câu
# =========================================================================
def test_tc_acc_rescan_02_range_of_sentences():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("quét lại từ câu 2 đến câu 4")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "rescan_subtitles"
    assert step.tool_args.get("segment_indices") == [2, 3, 4]


# =========================================================================
# TC-ACC-RESCAN-03: Quét lại theo khoảng thời gian
# =========================================================================
def test_tc_acc_rescan_03_time_interval():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("quét lại từ giây 10 đến 20")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "rescan_subtitles"
    assert step.tool_args.get("start_ms") == 10000
    assert step.tool_args.get("end_ms") == 20000


# =========================================================================
# TC-ACC-GEN-01: Gen sub câu chỉ định (vị trí câu lẻ)
# =========================================================================
def test_tc_acc_gen_01_specific_odd_sentence():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("gen sub câu 3")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "run_asr"
    assert step.tool_args.get("indices") == [3]

    # Verify tool execution với mock ASR theo chuẩn kiểm thử
    assert controller.tool_registry.has_tool("run_asr")
    import tempfile
    mock_svc = MagicMock()
    mock_svc.model = MagicMock()
    mock_res = MagicMock(error=None, segments=[MagicMock(text="Nhận diện câu 3", start_ms=1000, end_ms=3000)])
    mock_svc.transcribe_batch.return_value = mock_res
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_vid:
        exec_args = dict(step.tool_args)
        exec_args["video_path"] = tmp_vid.name
        exec_args["whisper_service"] = mock_svc
        exec_args["segments"] = [{"id": 3, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Cũ"}]
        res = controller.tool_registry.execute_tool("run_asr", exec_args)
        assert res["status"] == "ok"
        assert res["indices"] == [3]


# =========================================================================
# TC-ACC-GEN-02: Gen sub dải câu
# =========================================================================
def test_tc_acc_gen_02_range_of_sentences():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("nhận diện từ câu 1 đến 3")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "run_asr"
    assert step.tool_args.get("indices") == [1, 2, 3]


# =========================================================================
# TC-ACC-UX-ERR-01: Hiển thị Badge Lỗi & Báo cáo lỗi chi tiết
# =========================================================================
def test_tc_acc_ux_err_01_failed_badge_and_error_display(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # Create dummy failed step
    dummy_step = AgentStep(id="step_fail", title="Test Failed Step", tool_name="unknown_tool")
    controller.active_plan = MagicMock()
    controller.active_plan.steps = [dummy_step]
    controller.active_plan.current_step_index = 0

    # Simulate step failure
    controller.step_failed.emit(0, dummy_step, "Lỗi giả lập: Không tìm thấy tài nguyên")

    badge = page.findChild(QLabel, "status_badge")
    assert badge is not None
    # Must NOT be "CHỜ BẠN DUYỆT"
    assert badge.text() != "CHỜ BẠN DUYỆT"
    assert badge.text() == "THẤT BẠI"

    # Redo button must be enabled
    btn_redo = page.findChild(QPushButton, "btn_redo_task")
    assert btn_redo.isEnabled()

    # Next approve button must be disabled
    btn_approve = page.findChild(QPushButton, "btn_approve_next")
    assert not btn_approve.isEnabled()


# =========================================================================
# TC-ACC-UX-ERR-02: Thoát ngõ cụt UX khi nhấn Redo
# =========================================================================
def test_tc_acc_ux_err_02_redo_button_unlocks_deadlock(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    dummy_step = AgentStep(id="step_fail", title="Test Failed Step", tool_name="unknown_tool")
    controller.active_plan = MagicMock()
    controller.active_plan.steps = [dummy_step]
    controller.active_plan.current_step_index = 0
    controller.request_task_revision = MagicMock()

    controller.step_failed.emit(0, dummy_step, "Lỗi nghiêm trọng")

    btn_redo = page.findChild(QPushButton, "btn_redo_task")
    qtbot.mouseClick(btn_redo, Qt.MouseButton.LeftButton)

    controller.request_task_revision.assert_called_once()


# =========================================================================
# TC-ACC-STYLE-REPORT-01: Data Continuity khi đổi Subtitle Style (Gate 1)
# =========================================================================
def test_tc_acc_style_report_01_data_continuity():
    controller = AgentCopilotController()

    # 1. Tạo 5 câu timing
    controller.submit_prompt("tạo timing 5 câu đầu")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()
    assert len(controller._active_segments) == 5

    # 2. Đổi style
    controller.submit_prompt("đổi style sub chữ vàng viền đen cỡ 24 font Roboto")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()

    # Gate 1: Phải bảo tồn nguyên vẹn 5 câu phụ đề, không làm mất danh sách!
    assert len(controller._active_segments) == 5
    assert controller._active_segments[0]["start"] == "00:00:00,500"
    assert controller._last_step_result.get("style", {}).get("font_name") == "Roboto"
    assert "segments" in controller._last_step_result
    assert len(controller._last_step_result["segments"]) == 5


# =========================================================================
# TC-ACC-STYLE-REPORT-02: Visual Style Card & Đồng thời hiển thị (Gate 2 & 3)
# =========================================================================
def test_tc_acc_style_report_02_visual_card_and_simultaneous_rendering(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage
    from ui.components.agent_report_inspector_widget import SubtitleStyleCardWidget, EditableSegmentRow
    from PySide6.QtWidgets import QTextEdit

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # 1. Tạo 5 câu timing
    controller.submit_prompt("tạo timing 5 câu đầu")
    controller.approve_plan()

    # 2. Đổi style chữ đỏ viền trắng cỡ 30 font Arial
    controller.submit_prompt("đổi style sub chữ đỏ viền trắng cỡ 30 font Arial")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()

    # Gate 2: Khối hiển thị đồ họa StyleCardWidget phải tồn tại, KHÔNG dùng QTextEdit in thô dictionary!
    style_card = page.findChild(SubtitleStyleCardWidget)
    assert style_card is not None
    text_edits = page.col_inspect.inspection_card.findChildren(QTextEdit)
    assert len(text_edits) == 0

    # Gate 3: Cả thẻ Style ở trên VÀ danh sách 5 câu phụ đề ở dưới đều được hiển thị đồng thời!
    rows = page.findChildren(EditableSegmentRow)
    assert len(rows) == 5
