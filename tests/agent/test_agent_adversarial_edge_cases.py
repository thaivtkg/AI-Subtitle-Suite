import pytest
from unittest.mock import MagicMock
from core.agent.agent_tool_registry import shift_subtitles, adjust_subtitle_bounds
from core.agent.agent_copilot_controller import AgentCopilotController
from ui.SubEditor import time_str_to_ms, ms_to_time_str


def test_tc_adv_01_shift_negative_clamp_no_overlap():
    """TC-ADV-01: ADV-EDGE-002 - Dịch lùi cực đại âm kẹp sàn 0ms, không chồng lấn và giữ duration >= 200ms."""
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1 (2s)"},
        {"id": 2, "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2 (2s)"},
        {"id": 3, "start": "00:00:07,000", "end": "00:00:08,500", "text": "Câu 3 (1.5s)"},
    ]
    # Dịch lùi cực đại -50s (vượt xa mốc 0)
    res = shift_subtitles(offset_ms=-50000, segments=initial_segs)
    assert res["status"] == "ok"
    shifted = res["segments"]
    assert len(shifted) == 3

    # Kiểm tra kẹp sàn 0ms và giữ nguyên thời lượng gốc (>= 200ms)
    prev_end = 0
    for idx, seg in enumerate(shifted):
        st = time_str_to_ms(seg["start"])
        en = time_str_to_ms(seg["end"])
        dur = en - st

        # Thời lượng không bao giờ dưới 200ms
        assert dur >= 200, f"Segment {idx} dur {dur}ms < 200ms"
        # Mốc đầu câu không bao giờ âm
        assert st >= 0, f"Segment {idx} start {st}ms < 0"
        # Không bị đè chồng lên câu trước (Sequential Non-Overlapping)
        assert st >= prev_end, f"Segment {idx} start {st}ms < prev_end {prev_end}ms (chồng lấn)"
        prev_end = en

    # Kiểm tra không có 2 câu nào bị trùng khít tại [0, 200]
    starts = [time_str_to_ms(s["start"]) for s in shifted]
    assert len(set(starts)) == 3, f"Các mốc start bị trùng lặp: {starts}"
    # Câu 1: [0, 200], Câu 2: [200, 400], Câu 3: [400, 600] (Không bị đè chồng kẹp sàn)
    assert shifted[0]["start"] == "00:00:00,000"
    assert shifted[0]["end"] == "00:00:00,200"
    assert shifted[1]["start"] == "00:00:00,200"
    assert shifted[1]["end"] == "00:00:00,400"
    assert shifted[2]["start"] == "00:00:00,400"
    assert shifted[2]["end"] == "00:00:00,600"


def test_tc_adv_02_reversed_sentence_and_time_ranges():
    """TC-ADV-02: ADV-EDGE-004 - Chuẩn hóa min/max cho dải câu và dải thời gian ngược."""
    controller = AgentCopilotController()

    # 1. Rescan dải câu ngược "từ câu 4 đến câu 2"
    plan1 = controller._synthesize_plan("Quét lại từ câu 4 đến câu 2")
    assert len(plan1.steps) == 1
    step1 = plan1.steps[0]
    assert step1.tool_name == "rescan_subtitles"
    assert step1.tool_args.get("scope") == "range"
    assert step1.tool_args.get("segment_indices") == [2, 3, 4]
    assert "từ câu 2 đến câu 4" in step1.title

    # 2. Rescan dải thời gian ngược "từ giây 20 đến giây 10"
    plan2 = controller._synthesize_plan("Quét lại từ giây 20 đến giây 10")
    assert len(plan2.steps) == 1
    step2 = plan2.steps[0]
    assert step2.tool_name == "rescan_subtitles"
    assert step2.tool_args.get("scope") == "time_interval"
    assert step2.tool_args.get("start_ms") == 10000
    assert step2.tool_args.get("end_ms") == 20000
    assert "từ giây 10" in step2.title

    # 3. ASR Gen Sub dải câu ngược "gen sub từ câu 5 đến câu 1"
    plan3 = controller._synthesize_plan("gen sub từ câu 5 đến câu 1")
    assert len(plan3.steps) == 1
    step3 = plan3.steps[0]
    assert step3.tool_name == "run_asr"
    assert step3.tool_args.get("indices") == [1, 2, 3, 4, 5]
    assert "từ câu 1 đến câu 5" in step3.title


def test_tc_adv_03_bounds_inversion_guard_and_seconds_unit():
    """TC-ADV-03: ADV-EDGE-006 - Nhận diện đơn vị s/giây và bảo vệ chống đảo biên (Boundary Inversion Guard)."""
    controller = AgentCopilotController()

    # 1. Plan recognition với đơn vị s/giây
    plan = controller._synthesize_plan("điều chỉnh thời lượng tăng 5s ở mốc đầu và giảm 5s ở mốc cuối")
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "adjust_subtitle_bounds"
    assert step.tool_args.get("delta_start_ms") == 5000
    assert step.tool_args.get("delta_end_ms") == -5000

    # Test biến thể cú pháp "tăng mốc đầu 1.5s, giảm mốc cuối 500ms"
    plan_var = controller._synthesize_plan("mốc đầu tăng 1.5s, mốc cuối giảm 500ms")
    assert len(plan_var.steps) == 1
    assert plan_var.steps[0].tool_args.get("delta_start_ms") == 1500
    assert plan_var.steps[0].tool_args.get("delta_end_ms") == -500

    # 2. Tool execution: Xung đột co biên quá mức trên câu [1000ms, 3000ms]
    initial_segs = [
        {"id": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu test biên"},
    ]
    # delta_start = +5000, delta_end = -5000 -> raw_st = 6000, raw_en = -2000 -> xung đột cực đại
    res = adjust_subtitle_bounds(delta_start_ms=5000, delta_end_ms=-5000, segments=initial_segs)
    assert res["status"] == "ok"
    adj = res["segments"]
    st = time_str_to_ms(adj[0]["start"])
    en = time_str_to_ms(adj[0]["end"])

    # Phải giữ độ dài >= 200ms
    assert en - st >= 200
    # Phải kẹp đối xứng quanh tâm mid = (1000 + 3000) // 2 = 2000ms -> [1900ms, 2100ms]
    assert st == 1900
    assert en == 2100
    # Không vượt ra ngoài khung thời gian ban đầu [1000, 3000]
    assert st >= 1000
    assert en <= 3000


def test_tc_adv_04_tab9_live_sync_on_step_completed_and_tab_switch():
    """TC-ADV-04: ADV-SYNC-001 - Đồng bộ tức thời từ Tab 9 sang SubEditor khi xong bước hoặc đổi tab."""
    from ui.Gui import MainWindow

    assert hasattr(MainWindow, "_sync_from_ai_agent_page"), "MainWindow thiếu helper _sync_from_ai_agent_page"

    class DummyMainWindow:
        def __init__(self):
            self.sub_editor = MagicMock()
            self.sub_editor.all_segments = []
            self.video_player = MagicMock()
            self.page_ai_agent = MagicMock()
            self._active_nav_index = None

        def __getattr__(self, name):
            mock = MagicMock()
            setattr(self, name, mock)
            return mock

        _sync_from_ai_agent_page = MainWindow._sync_from_ai_agent_page
        _on_agent_step_completed = MainWindow._on_agent_step_completed
        switch_page = MainWindow.switch_page

    win = DummyMainWindow()
    synced_data = [
        {"id": 1, "start": "00:00:00,500", "end": "00:00:02,500", "text": "Synced 1"},
        {"id": 2, "start": "00:00:03,000", "end": "00:00:05,000", "text": "Synced 2"},
    ]
    win.page_ai_agent.get_current_segments.return_value = synced_data

    # 1. Gọi trực tiếp helper _sync_from_ai_agent_page
    win._sync_from_ai_agent_page()
    assert len(win.sub_editor.all_segments) == 2
    assert win.sub_editor.all_segments[0]["text"] == "Synced 1"
    win.sub_editor.render_page.assert_called()

    # 2. Test gọi qua _on_agent_step_completed (hoàn tất duyệt Cổng 2)
    win.sub_editor.all_segments = []
    step_mock = MagicMock()
    step_mock.tool_name = "create_timing"
    win._on_agent_step_completed(0, step_mock, {"status": "ok"})
    assert len(win.sub_editor.all_segments) == 2

    # 3. Test chuyển tab từ 9 sang tab khác (ví dụ tab 8 Dịch thuật hoặc tab 5 Xuất)
    win.sub_editor.all_segments = []
    win._active_nav_index = 9
    win.switch_page(8)
    assert len(win.sub_editor.all_segments) == 2

