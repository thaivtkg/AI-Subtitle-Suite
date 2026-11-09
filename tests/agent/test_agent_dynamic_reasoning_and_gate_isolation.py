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


# =========================================================================
# TC-COMPLETION-01: Báo cáo hoàn thành Cổng 2 sinh động & Phi trùng lặp (Anti-Robotic)
# =========================================================================
def test_tc_completion_01_dynamic_and_varied_summaries():
    """Xác thực tin nhắn hoàn thành ở Cổng 2 không dùng template cũ dập khuôn và có nội dung chuyên môn."""
    controller = AgentCopilotController()
    engine = controller.reasoning_engine

    old_template = "Kết quả đã được cập nhật vào khung kiểm tra bên phải"

    # 1. Timing completion
    step_timing = AgentStep(id="1", title="Tạo timing", tool_name="create_timing", tool_args={"count": 5})
    res_timing = {"segments": [{"start": "00:00.500", "end": "00:03.500"}] * 5, "count": 5}
    msg_timing = engine.synthesize_completion(step_timing, res_timing, active_segments_count=5)
    assert old_template not in msg_timing
    assert any(term in msg_timing.lower() for term in ["vad", "intro", "nhịp thoại", "phân đoạn"])

    # 2. Style completion
    step_style = AgentStep(
        id="2",
        title="Đổi style",
        tool_name="apply_subtitle_style",
        tool_args={"font_name": "Roboto", "font_size": 26, "font_color": "#FFFF00", "outline_color": "#000000"},
    )
    res_style = {"style": {"font_name": "Roboto", "font_size": 26, "font_color": "#FFFF00", "outline_color": "#000000"}, "segments": []}
    msg_style = engine.synthesize_completion(step_style, res_style, active_segments_count=5)
    assert old_template not in msg_style
    assert any(term in msg_style.lower() for term in ["font", "viền", "màu", "tương phản", "overlay"])

    # 3. Shift completion
    step_shift = AgentStep(id="3", title="Lùi sub", tool_name="shift_subtitles", tool_args={"offset_ms": -500})
    res_shift = {"offset_ms": -500, "segments": []}
    msg_shift = engine.synthesize_completion(step_shift, res_shift, active_segments_count=5)
    assert old_template not in msg_shift
    assert any(term in msg_shift.lower() for term in ["tịnh tiến", "kẹp biên", "dời", "timeline"])

    # 4. Anti-repetition across consecutive completions: different intros
    intros = [msg_timing.split("\n")[0], msg_style.split("\n")[0], msg_shift.split("\n")[0]]
    assert len(set(intros)) == 3, f"Phát hiện trùng lặp intro hoàn tất: {intros}"


# =========================================================================
# TC-COMPLETION-02: Cổng 2 phát sinh lời thoại thông minh khi thực thi lệnh thật
# =========================================================================
def test_tc_completion_02_controller_emits_dynamic_completion_message():
    """Xác thực controller phát ra tin nhắn hoàn thành chuyên môn và không bị cắt cụt."""
    controller = AgentCopilotController()
    controller.submit_prompt("Tạo timing 5 câu đầu")
    assert controller.is_waiting_plan_approval()

    # Approve plan to trigger step execution
    controller.approve_plan()
    assert controller.is_waiting_task_approval()

    # The last message in chat history must be the dynamic completion summary
    last_msg = controller.chat_history[-1].content
    old_robotic = "Kết quả đã được cập nhật vào khung kiểm tra bên phải. Mời bạn kiểm tra/sửa đổi hoặc bấm Duyệt để tiếp tục."
    assert old_robotic not in last_msg
    assert len(last_msg.split("\n")) >= 3
    assert any(w in last_msg for w in ["VAD", "phân đoạn", "nhịp thoại", "timing"])


# =========================================================================
# TC-UI-CHAT-01: ChatBubble hiển thị đầy đủ văn bản & cuộn trang mượt mà
# =========================================================================
def test_tc_ui_chat_bubble_markdown_and_no_truncation(qtbot):
    """Xác thực ChatBubble không bị cắt cụt chữ, render Markdown đầy đủ và auto-scroll tới đáy."""
    from ui.components.agent_chat_stream_widget import AgentChatStreamWidget, ChatBubble
    from core.agent.models import ChatMessage

    widget = AgentChatStreamWidget()
    qtbot.addWidget(widget)
    widget.show()

    long_content = (
        "🎉 **Hoàn thành xuất sắc:**\n"
        "Tôi đã kích hoạt engine VAD CFG-9 (Anime JA) trích xuất thành công 5 phân đoạn nhịp thoại đầu tiên, "
        "lọc sạch toàn bộ tạp âm và 17.5s nhạc intro không lời.\n\n"
        "👉 Kết quả chi tiết đã hiển thị tại bảng bên phải. Bạn có thể nhấp chuột sửa trực tiếp nội dung hoặc bấm Duyệt."
    )
    msg = ChatMessage(role="assistant", content=long_content, timestamp=100.0)
    widget.add_message(msg)

    # Bubble is in chat layout
    bubbles = widget.findChildren(ChatBubble)
    assert len(bubbles) >= 1
    last_bubble = bubbles[-1]
    lbl = last_bubble.findChild(QLabel)
    assert lbl is not None
    assert "Hoàn thành xuất sắc" in lbl.text()
    assert "17.5s nhạc intro" in lbl.text()
    assert "bấm Duyệt" in lbl.text()
