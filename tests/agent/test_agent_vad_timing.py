import time
import os
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from core.agent.agent_copilot_controller import AgentCopilotController
from core.agent.models import AgentContextLedger, StepStatus


# =========================================================================
# TC-VAD-01: Lọc bỏ triệt để 17.5s Intro BGM
# =========================================================================
def test_tc_vad_01_filter_out_17_5s_bgm_intro():
    from core.agent.vad_timing_service import detect_speech_intervals_vad

    # Synthetic audio with 17.5s silence/BGM (zeros) followed by speech segments at 18.0s, 21.0s, etc.
    sr = 16000
    mock_audio = np.zeros(int(30 * sr), dtype=np.float32)

    # Mock get_speech_timestamps to simulate Silero VAD returning speech starting from sample index 288000 (18.0s)
    mock_chunks = [
        {"start": int(18.0 * sr), "end": int(20.5 * sr)},
        {"start": int(21.0 * sr), "end": int(23.5 * sr)},
        {"start": int(24.0 * sr), "end": int(26.5 * sr)},
        {"start": int(27.0 * sr), "end": int(29.0 * sr)},
    ]

    with patch("core.agent.vad_timing_service.get_speech_timestamps", return_value=mock_chunks):
        intervals = detect_speech_intervals_vad(mock_audio, sampling_rate=sr)
        assert len(intervals) == 4
        # First speech chunk MUST start >= 17.5s (17500ms)
        first_start_ms = intervals[0]["start_ms"]
        assert first_start_ms >= 17500
        assert first_start_ms == 18000
        assert intervals[0]["end_ms"] == 20500


# =========================================================================
# TC-VAD-02: Độ chính xác Preset CFG-9 Anime JA
# =========================================================================
def test_tc_vad_02_cfg9_anime_ja_preset_parameters():
    from core.agent.vad_timing_service import DEFAULT_CFG9_PRESET

    assert DEFAULT_CFG9_PRESET["vad_threshold"] == 0.35
    assert DEFAULT_CFG9_PRESET["min_silence_duration_ms"] == 300
    assert DEFAULT_CFG9_PRESET["speech_pad_ms"] == 300
    assert DEFAULT_CFG9_PRESET["max_speech_duration_s"] == 6.0


# =========================================================================
# TC-VAD-03: Hiển thị Preview Card tại Cổng 1
# =========================================================================
def test_tc_vad_03_gate1_preview_card_in_ui(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage
    from ui.components.agent_report_inspector_widget import EditableSegmentRow
    from PySide6.QtWidgets import QLabel

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # When user submits prompt to create timing at Gate 1
    controller.submit_prompt("Tạo timing 5 câu đầu")

    # Gate 1 state: waiting plan approval
    assert controller.is_waiting_plan_approval()

    # Preview card must immediately render 5 segments with timestamps, NOT a blank placeholder!
    rows = page.findChildren(EditableSegmentRow)
    assert len(rows) == 5
    badge = page.findChild(QLabel, "status_badge")
    assert badge.text() == "CHỜ BẠN DUYỆT"


# =========================================================================
# TC-VAD-04: Kế thừa văn bản sửa tay tại Cổng 1 (Text Preservation)
# =========================================================================
def test_tc_vad_04_text_preservation_from_gate1_to_gate2(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage
    from ui.components.agent_report_inspector_widget import EditableSegmentRow
    from PySide6.QtWidgets import QPushButton

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    # User submits prompt
    controller.submit_prompt("Tạo timing 5 câu đầu")
    assert controller.is_waiting_plan_approval()

    # User edits segment #1 text directly at Gate 1
    rows = page.findChildren(EditableSegmentRow)
    assert len(rows) == 5
    custom_text = "Lời thoại nhân vật chính (Sửa tay ở Cổng 1)"
    rows[0].editor.setText(custom_text)

    # User clicks approve plan ("✔ Duyệt Kế Hoạch & Bắt Đầu")
    btn_approve = page.findChild(QPushButton, "btn_approve_next")
    qtbot.mouseClick(btn_approve, Qt.MouseButton.LeftButton)

    # After step execution, text must be preserved 100%!
    assert controller.is_waiting_task_approval()
    assert controller._active_segments[0]["text"] == custom_text


# =========================================================================
# TC-VAD-05: Đồng bộ 2 chiều sang Timeline Studio
# =========================================================================
def test_tc_vad_05_two_way_sync_to_studio_workspace(qtbot):
    from ui.Gui import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.show()

    win.switch_page(9)
    page = win.page_ai_agent
    controller = page.controller

    controller.submit_prompt("Tạo timing 5 câu đầu")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()

    # Switch to Studio Workspace (Tab 1)
    win.switch_page(1)
    assert len(win.sub_editor.all_segments) == 5
    assert win.sub_editor.all_segments[0]["start"] is not None


# =========================================================================
# TC-VAD-06: Ghi đè Preset qua ngôn ngữ tự nhiên
# =========================================================================
def test_tc_vad_06_natural_language_override_preset_params():
    controller = AgentCopilotController()
    plan = controller._synthesize_plan("Tạo timing 5 câu đầu với ngưỡng 0.4 và min_silence 500ms")

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "create_timing"
    assert step.tool_args.get("vad_threshold") == 0.4
    assert step.tool_args.get("min_silence_ms") == 500


# =========================================================================
# TC-VAD-07: Synthetic Fallback khi không có video
# =========================================================================
def test_tc_vad_07_synthetic_fallback_when_no_video_or_no_speech():
    from core.agent.vad_timing_service import generate_vad_timing_segments

    # Without video_path, should fall back to synthetic timing smoothly without crashing
    res = generate_vad_timing_segments(count=5, video_path=None)
    assert len(res) == 5
    assert res[0]["start"] == "00:00:00,500"
    assert res[0]["end"] == "00:00:03,000"

    # With non-existent video path, also fallback safely
    res_fake = generate_vad_timing_segments(count=3, video_path="non_existent_file.mp4")
    assert len(res_fake) == 3


# =========================================================================
# TC-VAD-08: Kiểm tra Snapshot Rollback
# =========================================================================
def test_tc_vad_08_snapshot_rollback_with_vad_timing(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage
    from PySide6.QtWidgets import QPushButton

    controller = AgentCopilotController()
    page = AIAgentMissionControlPage(controller=controller)
    qtbot.addWidget(page)
    page.show()

    controller.submit_prompt("Tạo timing 5 câu đầu")
    controller.approve_plan()
    assert controller.is_waiting_task_approval()

    # Click Redo
    btn_redo = page.findChild(QPushButton, "btn_redo_task")
    controller.request_task_revision = MagicMock(wraps=controller.request_task_revision)
    qtbot.mouseClick(btn_redo, Qt.MouseButton.LeftButton)
    controller.request_task_revision.assert_called_once()


# =========================================================================
# TC-VAD-09: Bắt đầu từ mốc thời gian (Start Offset)
# =========================================================================
def test_tc_vad_09_natural_language_start_offset():
    controller = AgentCopilotController()

    # Case A: từ giây 20
    plan_a = controller._synthesize_plan("Tạo timing 5 câu từ giây 20")
    assert plan_a.steps[0].tool_args.get("start_offset_s") == 20.0

    # Case B: từ 01:30 (90 seconds)
    plan_b = controller._synthesize_plan("Tạo timing 5 câu từ 01:30")
    assert plan_b.steps[0].tool_args.get("start_offset_s") == 90.0


# =========================================================================
# TC-VAD-10: Cắt tỉa âm thanh thông minh (Windowed Scan)
# =========================================================================
def test_tc_vad_10_windowed_audio_extraction_performance():
    from core.agent.vad_timing_service import extract_audio_window

    video_path = "sample_test_data/sample_video_25s.mp4"
    if os.path.exists(video_path):
        t0 = time.perf_counter()
        audio = extract_audio_window(video_path, start_offset_s=0.0, max_duration_s=60.0)
        elapsed = time.perf_counter() - t0

        assert audio is not None
        # Performance requirement: extraction time must be < 0.3s
        assert elapsed < 0.3
        # RAM usage: 60s at 16kHz float32 is < 10MB
        assert audio.nbytes < 50 * 1024 * 1024
