import pytest
from PySide6.QtWidgets import QLabel
from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import translate_subtitles
from core.agent.reasoning_engine import DynamicReasoningEngine
from core.agent.models import AgentStep, AgentContextLedger


def test_tc_trans_01_prompt_with_sub_word_triggers_translation_not_shift():
    """Kịch bản 1: 'Dịch các câu sub 6,7,13' phải vào translate_subtitles với indices [6, 7, 13], không vào process_general_task."""
    ctrl = AgentCopilotController()
    plan = ctrl._synthesize_plan("Dịch các câu sub 6,7,13")
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "translate_subtitles", f"Kỳ vọng translate_subtitles nhưng nhận {step.tool_name}"
    assert step.tool_args.get("target_lang") == "vi"
    assert step.tool_args.get("segment_indices") == [6, 7, 13]
    assert step.tool_args.get("scope") == "selected"


def test_tc_trans_02_prompt_without_sub_extracts_indices():
    """Kịch bản 2: 'Dịch các câu 6,7,13' phải trích xuất đúng indices [6, 7, 13]."""
    ctrl = AgentCopilotController()
    plan = ctrl._synthesize_plan("Dịch các câu 6,7,13")
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "translate_subtitles"
    assert step.tool_args.get("target_lang") == "vi"
    assert step.tool_args.get("segment_indices") == [6, 7, 13]


def test_tc_trans_03_prompt_with_sang_does_not_hijack_shift():
    """Kịch bản 3: 'Dịch câu 6,7,13 sang tiếng việt' không được hiểu nhầm '13 sang' thành '13s' để tạo shift_subtitles(13000ms)."""
    ctrl = AgentCopilotController()
    plan = ctrl._synthesize_plan("Dịch câu 6,7,13 sang tiếng việt")
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "translate_subtitles"
    assert step.tool_args.get("segment_indices") == [6, 7, 13]
    assert step.tool_args.get("target_lang") == "vi"


def test_tc_trans_04_translate_subtitles_preserves_untargeted_segments():
    """BUG-TRANS-TAG-ALL-001: Chỉ dịch câu trong segment_indices, giữ nguyên 100% các câu khác."""
    segs = [
        {"id": 1, "start": "00:01.000", "end": "00:03.000", "text": "Câu 1 gốc", "translation": ""},
        {"id": 2, "start": "00:03.500", "end": "00:05.500", "text": "Câu 2 gốc", "translation": ""},
        {"id": 3, "start": "00:06.000", "end": "00:08.000", "text": "Câu 3 gốc", "translation": ""},
        {"id": 4, "start": "00:08.500", "end": "00:10.500", "text": "Câu 4 gốc", "translation": ""},
    ]
    res = translate_subtitles(target_lang="vi", scope="selected", segment_indices=[2, 4], segments=segs)
    res_segs = res["segments"]
    assert len(res_segs) == 4

    # Câu 1 và 3 không được chọn -> Phải giữ nguyên 100% không bị dán [VI]
    assert res_segs[0]["text"] == "Câu 1 gốc"
    assert res_segs[0]["translation"] == ""
    assert res_segs[2]["text"] == "Câu 3 gốc"
    assert res_segs[2]["translation"] == ""

    # Câu 2 và 4 được chọn -> Được dịch
    assert res_segs[1]["text"] != "Câu 2 gốc"
    assert res_segs[1]["translation"] != ""
    assert res_segs[1]["original_text"] == "Câu 2 gốc"

    assert res_segs[3]["text"] != "Câu 4 gốc"
    assert res_segs[3]["translation"] != ""
    assert res_segs[3]["original_text"] == "Câu 4 gốc"


def test_tc_trans_05_reasoning_engine_process_general_task_honest_reporting():
    """BUG-AI-FAKE-REPORTING-004: process_general_task không được báo cáo giả 'Hoàn thành thành công' hay 'đồng bộ vào dự án'."""
    engine = DynamicReasoningEngine()
    step = AgentStep(
        id="step_1",
        title="Thực thi tác vụ tổng quát",
        tool_name="process_general_task",
        tool_args={"prompt": "Lệnh không rõ ràng"},
    )
    result = {"status": "ok", "prompt": "Lệnh không rõ ràng", "message": "Đã ghi nhận và xử lý tác vụ: Lệnh không rõ ràng"}
    summary = engine.synthesize_completion(step=step, result=result, context_ledger=AgentContextLedger(), active_segments_count=5)

    assert "🎉" not in summary
    assert "Hoàn thành tác vụ thành công" not in summary
    assert "đồng bộ hóa vào dự án" not in summary
    assert "chưa tìm thấy thao tác phụ đề tương ứng" in summary
    assert "bảo toàn nguyên vẹn" in summary


def test_tc_trans_06_reasoning_engine_translate_subtitles_selective_reporting():
    """translate_subtitles báo cáo trung thực số câu được chọn dịch và số câu được bảo toàn."""
    engine = DynamicReasoningEngine()
    step = AgentStep(
        id="step_1",
        title="Dịch Phụ Đề Các câu 6, 7, 13 Sang Tiếng VI (CAT Studio)",
        tool_name="translate_subtitles",
        tool_args={"target_lang": "vi", "segment_indices": [6, 7, 13]},
    )
    result = {
        "status": "ok",
        "target_lang": "vi",
        "segment_indices": [6, 7, 13],
        "segments": [{"id": i} for i in range(1, 25)],
    }
    summary = engine.synthesize_completion(step=step, result=result, context_ledger=AgentContextLedger(), active_segments_count=24)
    assert "câu #6, #7, #13" in summary
    assert "21 câu khác" in summary or "bảo toàn" in summary


def test_tc_trans_07_real_project_jmsz_24_segments_selective_translation():
    """Kiểm thử thực chiến trên 24 câu phụ đề dự án JMSZ.ai-subtitle."""
    import os, json
    proj_file = r"D:\Projects\JMSZ.ai-subtitle\artifacts\subtitle\ccecdae5-f64c-41d1-b998-0a5ec1d423e4.sub.json"
    if not os.path.exists(proj_file):
        pytest.skip("File dự án JMSZ.ai-subtitle không tồn tại trên máy")

    with open(proj_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments", [])
    assert len(segments) == 24

    orig_texts = [s["text"] for s in segments]

    # Chạy dịch chọn lọc câu [6, 7, 13]
    res = translate_subtitles(target_lang="vi", scope="selected", segment_indices=[6, 7, 13], segments=segments)
    res_segs = res["segments"]
    assert len(res_segs) == 24
    assert res["translated_count"] == 3

    # Kiểm tra 21 câu không chọn: 100% giữ nguyên text cũ, không bị dán [VI]
    for idx, seg in enumerate(res_segs):
        stt = idx + 1
        if stt not in [6, 7, 13]:
            assert seg["text"] == orig_texts[idx], f"Câu #{stt} bị thay đổi dữ liệu trái phép!"
            assert not str(seg.get("translation", "")).startswith("[VI]"), f"Câu #{stt} bị dán nhãn translation!"
        else:
            assert seg["text"] != orig_texts[idx] or seg.get("translation") != ""
            assert seg.get("original_text") == orig_texts[idx]


def test_tc_trans_08_inspector_renders_styled_info_box_for_general_task(qtbot):
    """Kiểm tra Inspector Widget hiển thị Card thông tin chuyên nghiệp thay vì raw QTextEdit JSON dump."""
    from PySide6.QtWidgets import QFrame, QTextEdit
    from ui.components.agent_report_inspector_widget import EditableResultReportWidget

    widget = EditableResultReportWidget()
    qtbot.addWidget(widget)

    # Khi kết quả là từ process_general_task
    general_result = {
        "status": "ok",
        "prompt": "Dịch các câu sub 6,7,13",
        "message": "Đã ghi nhận và xử lý tác vụ: Dịch các câu sub 6,7,13",
    }
    widget.render_result("Thực thi tác vụ tổng quát", general_result)

    # Không còn QTextEdit raw dump
    text_edits = widget.findChildren(QTextEdit)
    assert len(text_edits) == 0

    # Xuất hiện QFrame info box với tiêu đề 'Thông Tin Tác Vụ'
    frames = widget.findChildren(QFrame)
    assert len(frames) > 0
    labels = [lbl.text() for lbl in widget.findChildren(QLabel)]
    assert any("Thông Tin Tác Vụ" in t for t in labels)
