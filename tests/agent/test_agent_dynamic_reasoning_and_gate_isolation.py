import pytest
from unittest.mock import MagicMock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QLineEdit

from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.models import AgentContextLedger, AgentStep, AgentTaskPlan
from core.agent.reasoning_engine import DynamicReasoningEngine
from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage
from ui.components.agent_report_inspector_widget import (
    EditableSegmentRow,
    SubtitleStyleCardWidget,
)
from ui.components.plan_briefing_widget import PlanBriefingCardWidget


# =========================================================================
# TC-REASONING-01: Phản hồi đa sắc thái & Phi trùng lặp (Anti-Repetition)
# =========================================================================
def test_tc_reasoning_01_varied_templates_and_anti_repetition():
    """Xác thực AI không dùng câu máy móc và 4 câu trả lời liên tiếp có mở đầu/kết bài khác nhau."""
    controller = AgentCopilotController()
    prompts = [
        "Khởi tạo 5 câu timing",
        "Đổi style chữ vàng viền đen cỡ 26",
        "Quét lại câu số 2",
        "Lùi sub 500ms",
    ]

    replies = []
    old_template_marker = "Kế hoạch gồm"

    for p in prompts:
        controller.submit_prompt(p)
        last_msg = controller.chat_history[-1].content
        # 1. Tuyệt đối không chứa chuỗi máy móc cũ
        assert old_template_marker not in last_msg, f"Vẫn chứa template cũ trong: {last_msg}"
        replies.append(last_msg)

    # 2. Kiểm tra tính đa dạng (Anti-Repetition): Không có 2 câu nào có dòng mở đầu giống nhau
    first_lines = [r.strip().split("\n")[0] for r in replies]
    assert len(set(first_lines)) == len(prompts), f"Phát hiện trùng lặp dòng mở đầu: {first_lines}"


# =========================================================================
# TC-REASONING-02: Lập luận có bối cảnh kỹ thuật (Context-Aware Reasoning)
# =========================================================================
def test_tc_reasoning_02_context_aware_explanation():
    """Xác thực AI giải thích lý do kỹ thuật (VAD CFG-9, Overlap Guard, tương phản style...)."""
    engine = DynamicReasoningEngine()
    ledger = AgentContextLedger(video_path="D:/Video/test.mp4", duration_ms=120000)

    # 1. Timing request -> giải thích VAD
    p1 = "Tạo 5 câu timing từ đầu"
    step1 = AgentStep(id="1", title="Tạo timing", tool_name="create_timing", tool_args={"count": 5})
    plan1 = AgentTaskPlan(prompt=p1, steps=[step1])
    res1 = engine.synthesize_reasoning(p1, plan1, ledger, active_segments_count=0)
    assert any(term in res1.lower() for term in ["vad", "anime", "nhịp thoại", "âm thanh"])

    # 2. Style request -> giải thích độ tương phản hoặc kích cỡ
    p2 = "Đổi style chữ đỏ viền trắng cỡ 30"
    step2 = AgentStep(
        id="2",
        title="Đổi style",
        tool_name="apply_subtitle_style",
        tool_args={"font_color": "#FF0000", "outline_color": "#FFFFFF", "font_size": 30},
    )
    plan2 = AgentTaskPlan(prompt=p2, steps=[step2])
    res2 = engine.synthesize_reasoning(p2, plan2, ledger, active_segments_count=5)
    assert any(term in res2.lower() for term in ["tương phản", "dễ đọc", "hiển thị", "định dạng"])


# =========================================================================
# TC-REASONING-03: Fallback an toàn khi tham số rỗng hoặc prompt dị biệt
# =========================================================================
def test_tc_reasoning_03_safe_fallback_on_empty_args():
    """Xác thực nếu prompt lạ hoặc tham số rỗng, reasoning vẫn sinh câu văn tiếng Việt hoàn chỉnh."""
    engine = DynamicReasoningEngine()
    ledger = AgentContextLedger()

    step_empty = AgentStep(id="1", title="Tác vụ tổng quát", tool_name="process_general_task", tool_args={})
    plan_empty = AgentTaskPlan(prompt="một yêu cầu chưa rõ ràng", steps=[step_empty])
    res = engine.synthesize_reasoning("một yêu cầu chưa rõ ràng", plan_empty, ledger, active_segments_count=0)

    assert isinstance(res, str)
    assert len(res) > 30
    assert not res.endswith(":")  # Không bị cụt câu
    assert "Duyệt" in res  # Vẫn có hướng dẫn hành động rõ ràng


# =========================================================================
# TC-GATE-ISOLATION-01: Cổng 1 chỉ hiển thị PlanBriefingCard (Không lộ kết quả)
# =========================================================================
def test_tc_gate_isolation_01_gate1_shows_plan_briefing_only(qtbot):
    """Tại Cổng 1 (Duyệt Kế Hoạch), chỉ hiển thị Thẻ Tóm Tắt Kế Hoạch, KHÔNG lộ danh sách câu hay swatch."""
    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # User gửi lệnh tạo timing
    controller.submit_prompt("Tạo timing 5 câu đầu")
    assert controller.is_waiting_plan_approval()

    # Cổng 1: Phải có Thẻ Kế Hoạch PlanBriefingCardWidget
    briefing = page.findChild(PlanBriefingCardWidget)
    assert briefing is not None

    # Cổng 1: Tuyệt đối KHÔNG có bất kỳ dòng phụ đề nào (chưa chạy tác vụ!)
    rows = page.findChildren(EditableSegmentRow)
    assert len(rows) == 0

    # Cổng 1: Tuyệt đối KHÔNG có SubtitleStyleCardWidget
    style_card = page.findChild(SubtitleStyleCardWidget)
    assert style_card is None


# =========================================================================
# TC-GATE-ISOLATION-02: Cổng 2 bung kết quả thực tế sau khi duyệt và chạy xong
# =========================================================================
def test_tc_gate_isolation_02_gate2_shows_execution_report_after_approval(qtbot):
    """Tại Cổng 2 (sau khi bấm Duyệt và chạy xong), kết quả thực tế mới bung ra với âm báo."""
    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    page.alert_service.play_chime = MagicMock()
    page.alert_service.alert_window = MagicMock()

    # Gửi lệnh
    controller.submit_prompt("Tạo timing 5 câu đầu")
    assert controller.is_waiting_plan_approval()

    # Trước khi duyệt: 0 dòng kết quả
    assert len(page.findChildren(EditableSegmentRow)) == 0

    # Bấm Duyệt Kế Hoạch
    btn_approve = page.findChild(QPushButton, "btn_approve_next")
    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)

    # Sau khi duyệt: Tác vụ chạy xong -> Chuông kêu -> Bung 5 dòng kết quả ở Cổng 2!
    assert controller.is_waiting_task_approval()
    page.alert_service.play_chime.assert_called_once()

    rows = page.findChildren(EditableSegmentRow)
    assert len(rows) == 5
