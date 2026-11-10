import pytest
from PySide6.QtWidgets import QLabel
from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.agent_tool_registry import translate_subtitles
from core.agent.reasoning_engine import DynamicReasoningEngine
from core.agent.models import AgentStep, AgentContextLedger, StepStatus


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
    """BUG-TRANS-TAG-ALL-001: Chỉ dịch câu trong segment_indices, dùng bản dịch thật và giữ nguyên 100% các câu khác."""
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.generate_with_fallback.side_effect = [
        {"content": "Bản dịch câu 2 hoàn chỉnh"},
        {"content": "Bản dịch câu 4 hoàn chỉnh"},
    ]

    segs = [
        {"id": 1, "start": "00:01.000", "end": "00:03.000", "text": "Câu 1 gốc", "translation": ""},
        {"id": 2, "start": "00:03.500", "end": "00:05.500", "text": "Câu 2 gốc", "translation": ""},
        {"id": 3, "start": "00:06.000", "end": "00:08.000", "text": "Câu 3 gốc", "translation": ""},
        {"id": 4, "start": "00:08.500", "end": "00:10.500", "text": "Câu 4 gốc", "translation": ""},
    ]
    res = translate_subtitles(
        target_lang="vi",
        scope="selected",
        segment_indices=[2, 4],
        segments=segs,
        llm_client=mock_llm,
    )
    res_segs = res["segments"]
    assert len(res_segs) == 4
    assert res["status"] == "ok"
    assert res["translated_count"] == 2
    assert res["failed_indices"] == []

    # Câu 1 và 3 không được chọn -> Phải giữ nguyên 100% không bị dán [VI]
    assert res_segs[0]["text"] == "Câu 1 gốc"
    assert res_segs[0]["translation"] == ""
    assert res_segs[2]["text"] == "Câu 3 gốc"
    assert res_segs[2]["translation"] == ""

    # Câu 2 và 4 được chọn -> Được dịch thành tiếng Việt có nghĩa thật sự (CẤM dán nhãn giả [VI])
    assert res_segs[1]["text"] == "Bản dịch câu 2 hoàn chỉnh"
    assert res_segs[1]["translation"] == "Bản dịch câu 2 hoàn chỉnh"
    assert res_segs[1]["original_text"] == "Câu 2 gốc"
    assert not res_segs[1]["text"].startswith("[VI]")

    assert res_segs[3]["text"] == "Bản dịch câu 4 hoàn chỉnh"
    assert res_segs[3]["translation"] == "Bản dịch câu 4 hoàn chỉnh"
    assert res_segs[3]["original_text"] == "Câu 4 gốc"
    assert not res_segs[3]["text"].startswith("[VI]")


def test_tc_trans_04b_offline_no_model_preserves_original_and_returns_warning():
    """CRIT-FAKE-TRANS-FALLBACK-001: Khi offline không có mô hình và không có TM, CẤM dán [VI], giữ nguyên bản gốc."""
    segs = [
        {"id": 1, "text": "この俺様に一体何の", "translation": ""},
        {"id": 2, "text": "そんなの決まってるわ。", "translation": ""},
    ]
    res = translate_subtitles(
        target_lang="vi",
        scope="selected",
        segment_indices=[1, 2],
        segments=segs,
        project_dir=r"C:\nonexistent_project_folder",
        llm_client=None,
    )
    assert res["status"] == "warning"
    assert res["translated_count"] == 0
    assert res["failed_indices"] == [1, 2]

    # Cả 2 câu phải giữ nguyên văn bản gốc tiếng Nhật 100%, tuyệt đối CẤM dán [VI]
    for s in res["segments"]:
        assert not s["text"].startswith("[VI]"), f"Phát hiện nhãn giả [VI] trong: {s['text']}"
        assert not str(s.get("translation", "")).startswith("[VI]")
    assert res["segments"][0]["text"] == "この俺様に一体何の"
    assert res["segments"][1]["text"] == "そんなの決まってるわ。"


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
    """Kiểm thử thực chiến trên 24 câu phụ đề dự án JMSZ.ai-subtitle và đối chiếu project.aisrt."""
    import os, json
    proj_file = r"D:\Projects\JMSZ.ai-subtitle\artifacts\subtitle\ccecdae5-f64c-41d1-b998-0a5ec1d423e4.sub.json"
    proj_dir = r"D:\Projects\JMSZ.ai-subtitle"
    if not os.path.exists(proj_file) or not os.path.exists(proj_dir):
        pytest.skip("File dự án JMSZ.ai-subtitle không tồn tại trên máy")

    with open(proj_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments", [])
    assert len(segments) == 24

    orig_texts = [s["text"] for s in segments]

    # Chạy dịch chọn lọc câu [6, 7, 13] với project_dir thực tế
    res = translate_subtitles(
        target_lang="vi",
        scope="selected",
        segment_indices=[6, 7, 13],
        segments=segments,
        project_dir=proj_dir,
    )
    res_segs = res["segments"]
    assert len(res_segs) == 24
    assert res["status"] == "warning"  # 6, 7 dịch từ project.aisrt, 13 chưa dịch được do chưa có model
    assert res["translated_count"] == 2
    assert res["translated_indices"] == [6, 7]
    assert res["failed_indices"] == [13]

    # Kiểm tra 21 câu không chọn: 100% giữ nguyên text cũ, không bị dán [VI]
    for idx, seg in enumerate(res_segs):
        stt = idx + 1
        if stt not in [6, 7, 13]:
            assert seg["text"] == orig_texts[idx], f"Câu #{stt} bị thay đổi dữ liệu trái phép!"
            assert not str(seg.get("translation", "")).startswith("[VI]"), f"Câu #{stt} bị dán nhãn translation!"
            assert not str(seg.get("text", "")).startswith("[VI]")

    # Câu #6 và #7: Lấy bản dịch tiếng Việt chuẩn xác từ project.aisrt (CAT Studio)
    assert res_segs[5]["text"] == "Đến tớ đây thì làm cái gì"
    assert res_segs[5]["translation"] == "Đến tớ đây thì làm cái gì"
    assert not res_segs[5]["text"].startswith("[VI]")

    assert res_segs[6]["text"] == "Đó là điều đương nhiên rồi."
    assert res_segs[6]["translation"] == "Đó là điều đương nhiên rồi."
    assert not res_segs[6]["text"].startswith("[VI]")

    # Câu #13: Không có model -> Giữ nguyên text gốc, tuyệt đối CẤM dán [VI]
    assert res_segs[12]["text"] == orig_texts[12]
    assert not res_segs[12]["text"].startswith("[VI]")
    assert not str(res_segs[12].get("translation", "")).startswith("[VI]")


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


def test_tc_trans_09_shift_time_quantity_not_hijacked_as_sentence_index():
    """ADV-NLP-SHIFT-NUMBER-HIJACK-001: Số đo thời gian trong 'Tiến sub 2s', 'Dịch chuyển sub 500ms' không được nuốt thành segment_indices."""
    ctrl = AgentCopilotController()

    p1 = ctrl._synthesize_plan("Tiến sub 2s")
    assert len(p1.steps) == 1
    assert p1.steps[0].tool_name == "shift_subtitles"
    assert p1.steps[0].tool_args.get("offset_ms") == 2000
    assert p1.steps[0].tool_args.get("segment_indices") is None
    assert p1.steps[0].tool_args.get("scope") == "all"

    p2 = ctrl._synthesize_plan("Dịch chuyển sub 500ms")
    assert len(p2.steps) == 1
    assert p2.steps[0].tool_name == "shift_subtitles"
    assert p2.steps[0].tool_args.get("offset_ms") == 500
    assert p2.steps[0].tool_args.get("segment_indices") is None

    p3 = ctrl._synthesize_plan("Lùi phụ đề 300ms")
    assert len(p3.steps) == 1
    assert p3.steps[0].tool_name == "shift_subtitles"
    assert p3.steps[0].tool_args.get("offset_ms") == -300
    assert p3.steps[0].tool_args.get("segment_indices") is None


def test_tc_trans_10_translate_with_duration_phrase_not_split_to_shift():
    """ADV-NLP-SHIFT-COMBINED-TRANSLATE-002: Lệnh dịch kèm thời lượng 'trong vòng 5s' không được sinh thêm bước shift."""
    ctrl = AgentCopilotController()
    p = ctrl._synthesize_plan("Dịch câu 6 sang tiếng Việt trong vòng 5s")
    assert len(p.steps) == 1
    assert p.steps[0].tool_name == "translate_subtitles"
    assert p.steps[0].tool_args.get("segment_indices") == [6]
    assert p.steps[0].tool_args.get("target_lang") == "vi"


def test_tc_trans_11_translate_discontinuous_stt_matched_by_1based_index():
    """ADV-TRANS-DISCONTINUOUS-STT-INDEX-003: Phân giải số câu đa chiều (stt, id, 1-based index) khi stt bị đứt đoạn."""
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.generate_with_fallback.return_value = {"content": "Nội dung câu 24 đã dịch thành công"}

    # Giả lập 24 câu giống JMSZ: câu #16 có stt=None, câu #24 có stt="23"
    segs = []
    for i in range(1, 25):
        stt_val = None if i == 16 else (str(i) if i < 16 else str(i - 1))
        segs.append({
            "id": f"uuid-{i}",
            "stt": stt_val,
            "text": f"Nội dung câu {i}",
            "translation": "",
        })

    # Người dùng gõ 'Dịch câu 24' -> target_indices = [24]
    res = translate_subtitles(
        target_lang="vi",
        scope="selected",
        segment_indices=[24],
        segments=segs,
        llm_client=mock_llm,
    )
    res_segs = res["segments"]
    assert len(res_segs) == 24
    assert res["status"] == "ok"
    assert res["translated_count"] == 1
    assert res["translated_indices"] == [24]

    # Câu #24 (index 23 trong mảng) phải được dịch dù stt là '23'
    assert res_segs[23]["text"] == "Nội dung câu 24 đã dịch thành công"
    assert res_segs[23]["translation"] == "Nội dung câu 24 đã dịch thành công"
    assert res_segs[23]["original_text"] == "Nội dung câu 24"
    assert not res_segs[23]["text"].startswith("[VI]")

    # Câu #23 (index 22 trong mảng, stt '22') không được dịch
    assert res_segs[22]["text"] == "Nội dung câu 23"
    assert res_segs[22]["translation"] == ""


def test_tc_trans_12_doan_keyword_extracts_indices():
    """ADV-NLP-DOAN-KEYWORD-MISSING-004: Từ khóa 'đoạn' trích xuất đúng segment_indices."""
    ctrl = AgentCopilotController()
    p = ctrl._synthesize_plan("Dịch đoạn 6, 7, 13")
    assert len(p.steps) == 1
    assert p.steps[0].tool_name == "translate_subtitles"
    assert p.steps[0].tool_args.get("segment_indices") == [6, 7, 13]
    assert p.steps[0].tool_args.get("scope") == "selected"


def test_tc_trans_13_end_to_end_forensic_bug_scenario():
    """CRIT-FAKE-TRANS-FALLBACK-001: Tái hiện 100% kịch bản User trên JMSZ - Không chúc mừng giả, lấy đúng bản dịch #6,#7 và giữ nguyên #13."""
    import os, json

    proj_file = r"D:\Projects\JMSZ.ai-subtitle\artifacts\subtitle\ccecdae5-f64c-41d1-b998-0a5ec1d423e4.sub.json"
    proj_dir = r"D:\Projects\JMSZ.ai-subtitle"
    if not os.path.exists(proj_file) or not os.path.exists(proj_dir):
        pytest.skip("File dự án JMSZ.ai-subtitle không tồn tại trên máy")

    with open(proj_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments", [])

    ctrl = AgentCopilotController()
    ctrl.context_ledger.project_dir = proj_dir
    ctrl._active_segments = segments

    plan = ctrl._synthesize_plan("Dịch các câu 6,7,13")
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "translate_subtitles"

    # Thực thi tool với cấu hình thực tế của desktop (không có API Key, chưa nạp GGUF)
    args = dict(step.tool_args)
    args["segments"] = segments
    args["project_dir"] = proj_dir
    args["llm_client"] = ctrl.llm_client

    exec_res = ctrl.tool_registry.safe_execute_tool("translate_subtitles", args)
    assert exec_res["success"] is True
    res_dict = exec_res["result"]

    assert res_dict["status"] == "warning"
    assert res_dict["translated_count"] == 2
    assert res_dict["translated_indices"] == [6, 7]
    assert res_dict["failed_indices"] == [13]

    res_segs = res_dict["segments"]
    # Câu 6 và 7 lấy đúng bản dịch tiếng Việt từ project.aisrt
    assert res_segs[5]["text"] == "Đến tớ đây thì làm cái gì"
    assert not res_segs[5]["text"].startswith("[VI]")
    assert res_segs[6]["text"] == "Đó là điều đương nhiên rồi."
    assert not res_segs[6]["text"].startswith("[VI]")

    # Câu 13 giữ nguyên văn bản tiếng Nhật gốc, CẤM dán [VI]
    assert res_segs[12]["text"] == segments[12]["text"]
    assert not res_segs[12]["text"].startswith("[VI]")

    # DynamicReasoningEngine: Báo cáo trung thực, CẤM icon 🎉 và CẤM chúc mừng giả
    step.status = StepStatus.COMPLETED
    report = ctrl.reasoning_engine.synthesize_completion(
        step=step,
        result=res_dict,
        context_ledger=ctrl.context_ledger,
        active_segments_count=len(segments),
    )
    assert "🎉" not in report
    assert "Hoàn thành tác vụ thành công" not in report
    assert "câu #6, #7" in report
    assert "câu #13" in report
    assert "Chưa thể dịch" in report



def test_tc_trans_14_translategemma_auto_load_cuda_hybrid_and_prompt_template(monkeypatch):
    """Kiểm tra AI Agent tự động kết nối llama_cpp, nạp TranslateGemma với CUDA Hybrid cho RTX 3050 và prompt template Gemma 2."""
    from unittest.mock import MagicMock
    from core.agent.agent_tool_registry import _perform_single_translation
    from core.translation.llm.model_manager import ModelManager
    from core.translation.core.hardware_detector import HardwareDetector

    # 1. Giả lập phần cứng RTX 3050 4GB VRAM
    fake_gpu = {"has_gpu_hardware": True, "name": "NVIDIA GeForce RTX 3050 Laptop GPU", "vram_gb": 4.0}
    monkeypatch.setattr(HardwareDetector, "get_gpu_info", lambda: fake_gpu)
    monkeypatch.setattr(HardwareDetector, "check_llama_cuda_backend", lambda: True)

    mock_mm = MagicMock()
    mock_mm.current_model_name = ""
    def fake_load(path, **kwargs):
        mock_mm.current_model_name = path
        return True
    mock_mm.load_model.side_effect = fake_load

    # Giả lập model sinh ra câu dịch kèm khối [TỪ GỐC]
    captured_prompts = []
    def fake_generate(prompt="", **kwargs):
        captured_prompts.append(prompt)
        return "Xin chào, đây là bản dịch chuẩn xác.\n[TỪ GỐC]\n- hello -> xin chào"

    mock_mm.generate = fake_generate
    monkeypatch.setattr(ModelManager, "get_instance", lambda backend="llama_cpp": mock_mm)

    # 2. Gọi _perform_single_translation với auto_load_model=True
    res = _perform_single_translation(
        text="Hello world",
        target_lang="vi",
        auto_load_model=True,
    )

    # 3. Kiểm tra load_model được gọi với số layer tối ưu cho RTX 3050 (16-20 layers)
    assert mock_mm.load_model.called
    call_kwargs = mock_mm.load_model.call_args[1]
    n_gpu_layers = call_kwargs.get("n_gpu_layers", 0)
    assert 16 <= n_gpu_layers <= 20, f"n_gpu_layers {n_gpu_layers} nằm ngoài dải 16-20 tối ưu cho RTX 3050"

    # 4. Kiểm tra Prompt áp dụng đúng chuẩn Gemma 2 (<start_of_turn>user ... <start_of_turn>model)
    assert len(captured_prompts) == 1
    prompt_used = captured_prompts[0]
    assert "<start_of_turn>user" in prompt_used
    assert "<start_of_turn>model" in prompt_used
    assert "VIETNAMESE LOCALIZATION RULES (MUST FOLLOW)" in prompt_used

    # 5. Kiểm tra kết quả trả về đã lọc sạch các thẻ [TỪ GỐC] và không dính nhãn giả
    assert res == "Xin chào, đây là bản dịch chuẩn xác."
    assert "[TỪ GỐC]" not in res
    assert not res.startswith("[VI]")
