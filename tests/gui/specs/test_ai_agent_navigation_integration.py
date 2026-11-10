from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
import pytest
from core.agent.agent_copilot_controller import AgentStep, StepStatus


def test_nav_switching_to_ai_agent_tab(qtbot):
    from ui.Gui import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    # 1. Verify page_ai_agent exists on win
    assert hasattr(win, "page_ai_agent"), "MainWindow missing page_ai_agent"

    # 2. Switch to AI Agent Mission Control tab (id: 9)
    win.switch_page(9)
    assert win.stack.currentWidget() == win.page_ai_agent
    assert win.liquid_nav.active_index == win.liquid_nav._get_tab_index_by_id(9)
    assert win.lbl_page_title.text() == "Phòng Điều Hành AI Agent"

    # 3. Check peripheral panels are hidden outside Studio Workspace
    assert win.timeline_dock.isHidden()
    assert win.bottom_frame.isHidden()

    # 4. Check alias _on_nav_tab_changed works
    win.switch_page(0)
    assert win.stack.currentWidget() != win.page_ai_agent
    win._on_nav_tab_changed(9)
    assert win.stack.currentWidget() == win.page_ai_agent


def test_ai_agent_translation_sync_to_tab8_when_empty(qtbot):
    """Bảo đảm khi Tab 8 chưa nạp câu nào, hoàn tất dịch ở Tab 9 và switch sang Tab 8 sẽ nạp đầy đủ."""
    from ui.Gui import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    initial_segments = [
        {
            "id": f"seg_{i+1:02d}",
            "stt": i + 1,
            "start": i * 1000,
            "end": (i + 1) * 1000,
            "text": f"Japanese speech {i+1}",
            "original_text": f"Japanese speech {i+1}",
            "translation": "",
            "translation_status": "PENDING",
        }
        for i in range(24)
    ]
    win.sub_editor.all_segments = [dict(s) for s in initial_segments]

    # Tab 8 ban đầu rỗng
    assert win.page_translation.subtitle_model.rowCount() == 0

    # Giả lập Agent dịch câu 6 và câu 7
    agent_controller = win.page_ai_agent.controller
    agent_controller._active_segments = [dict(s) for s in initial_segments]
    agent_controller._active_segments[5]["translation"] = "Bản dịch tiếng Việt câu 6"
    agent_controller._active_segments[5]["text"] = "Bản dịch tiếng Việt câu 6"
    agent_controller._active_segments[5]["translation_status"] = "TRANSLATED"

    agent_controller._active_segments[6]["translation"] = "Bản dịch tiếng Việt câu 7"
    agent_controller._active_segments[6]["text"] = "Bản dịch tiếng Việt câu 7"
    agent_controller._active_segments[6]["translation_status"] = "TRANSLATED"

    step = AgentStep(
        id="step_1",
        title="Dịch Phụ Đề các câu: 6, 7 Sang Tiếng VI",
        tool_name="translate_subtitles",
        tool_args={"segment_indices": [6, 7], "target_lang": "vi"},
        status=StepStatus.COMPLETED,
    )
    result = {
        "status": "ok",
        "segments": agent_controller._active_segments,
        "translated_count": 2,
        "translated_indices": [6, 7],
    }

    win._on_agent_step_completed(0, step, result)

    # Chuyển sang Tab 8 (CAT Studio)
    win.switch_page(8)

    tab8_count = win.page_translation.subtitle_model.rowCount()
    assert tab8_count == 24, f"Tab 8 should have 24 segments loaded, got {tab8_count}"

    tab8_data = win.page_translation.subtitle_model.get_all_data()
    found_6 = next((item for item in tab8_data if item.get("index") == 6), None)
    found_7 = next((item for item in tab8_data if item.get("index") == 7), None)

    assert found_6 is not None, "Câu 6 must exist in Tab 8"
    assert found_6.get("translation") == "Bản dịch tiếng Việt câu 6"
    assert found_7 is not None, "Câu 7 must exist in Tab 8"
    assert found_7.get("translation") == "Bản dịch tiếng Việt câu 7"


def test_ai_agent_translation_sync_to_tab8_when_already_loaded(qtbot):
    """Bảo đảm khi Tab 8 đã nạp sẵn, hoàn tất dịch ở Tab 9 sẽ cập nhật tức thời bản dịch vào SubtitleModel."""
    from ui.Gui import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    initial_segments = [
        {
            "id": f"seg_{i+1:02d}",
            "stt": i + 1,
            "start": i * 1000,
            "end": (i + 1) * 1000,
            "text": f"Japanese speech {i+1}",
            "original_text": f"Japanese speech {i+1}",
            "translation": "",
            "translation_status": "PENDING",
        }
        for i in range(24)
    ]
    win.sub_editor.all_segments = [dict(s) for s in initial_segments]

    # Pre-load Tab 8
    win.page_translation.load_subtitles_from_studio(win.sub_editor.all_segments)
    assert win.page_translation.subtitle_model.rowCount() == 24

    # Giả lập Agent dịch câu 6 và câu 7
    agent_controller = win.page_ai_agent.controller
    agent_controller._active_segments = [dict(s) for s in win.sub_editor.all_segments]
    agent_controller._active_segments[5]["translation"] = "Bản dịch tiếng Việt câu 6"
    agent_controller._active_segments[5]["text"] = "Bản dịch tiếng Việt câu 6"
    agent_controller._active_segments[5]["translation_status"] = "TRANSLATED"

    agent_controller._active_segments[6]["translation"] = "Bản dịch tiếng Việt câu 7"
    agent_controller._active_segments[6]["text"] = "Bản dịch tiếng Việt câu 7"
    agent_controller._active_segments[6]["translation_status"] = "TRANSLATED"

    step = AgentStep(
        id="step_1",
        title="Dịch Phụ Đề các câu: 6, 7 Sang Tiếng VI",
        tool_name="translate_subtitles",
        tool_args={"segment_indices": [6, 7], "target_lang": "vi"},
        status=StepStatus.COMPLETED,
    )
    result = {
        "status": "ok",
        "segments": agent_controller._active_segments,
        "translated_count": 2,
        "translated_indices": [6, 7],
    }

    win._on_agent_step_completed(0, step, result)

    # Chuyển sang Tab 8
    win.switch_page(8)

    tab8_data = win.page_translation.subtitle_model.get_all_data()
    found_6 = next((item for item in tab8_data if item.get("index") == 6), None)
    found_7 = next((item for item in tab8_data if item.get("index") == 7), None)

    assert found_6 is not None
    assert found_6.get("translation") == "Bản dịch tiếng Việt câu 6"
    assert found_7 is not None
    assert found_7.get("translation") == "Bản dịch tiếng Việt câu 7"
