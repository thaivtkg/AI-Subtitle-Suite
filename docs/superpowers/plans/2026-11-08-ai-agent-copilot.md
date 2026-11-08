# AI Agent Copilot Điều Khiển Ứng Dụng Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng hệ thống AI Agent Copilot tích hợp vào AI Subtitle Suite, điều khiển toàn bộ ứng dụng qua prompt tự nhiên với quy trình duyệt từng bước (HITL), bộ nhớ dự án dài hạn, fallback đa nhà cung cấp Online-Offline, và giao diện Tab Chuyên Dụng chuẩn xác 100% theo mockup đã được phê duyệt.

**Architecture:** Kiến trúc gồm 4 lớp phân tách rõ ràng:
1. `Core Engine & Models`: Data models, Session Context Memory Ledger, và `SnapshotManager` cho phép hoàn tác an toàn trước mỗi bước.
2. `MultiProviderLLMClient`: Client giao tiếp đa nhà cung cấp (Gemini, OpenAI, Claude, OpenRouter) với thuật toán 3-tier fallback tự động về Local GGUF khi mất kết nối.
3. `AgentCopilotController` & `ToolRegistry`: Máy trạng thái HITL chuyển đổi giữa các pha (Plan $\rightarrow$ Review $\rightarrow$ Execute $\rightarrow$ Report $\rightarrow$ Advance) và cầu nối Tool Calling tới các service nghiệp vụ (ASR, CAT Studio, Style, Hardsub).
4. `UI Presentation (Tab C)`: Giao diện `AIAgentMissionControlPage` bố cục 2 cột song song (Cột trái: Memory Bar + Chat Stream + Prompt; Cột phải: Stepper + Báo cáo kết quả trực quan cho phép sửa trực tiếp + Nút duyệt bước tiếp) chuẩn 100% theo mockup Obsidian Liquid Dark Theme.

**Tech Stack:** Python 3.11+, PySide6 (Qt 6.6+), Qt Quick / QML, `llama-cpp-python`, `requests` / `urllib3`, Windows Win32 / `QApplication.alert`, `QSoundEffect`, `pytest`, `pytest-qt`.

**Spec:** [`docs/superpowers/specs/2026-11-08-ai-agent-copilot-design.md`](file:///d:/ai-subtitle-suite/docs/superpowers/specs/2026-11-08-ai-agent-copilot-design.md)

---

## Global Constraints
- Giao diện phải giống 100% bố cục và màu sắc của bản mockup đã phê duyệt (`d:\ai-subtitle-suite\.superpowers\brainstorm\1035-1794085552\content\layout1-memory-chat.html`).
- Nghiêm cấm mô phỏng click chuột theo tọa độ màn hình; mọi hành động phải qua Service Tool Calling chuẩn xác.
- Quy trình kiểm soát HITL tuyệt đối: không tự ý chạy bước tiếp theo khi người dùng chưa bấm nút duyệt (Zero unconfirmed auto-advance).
- Trước mỗi task phải tự động chụp checkpoint snapshot; khi người dùng bấm "Yêu cầu làm lại task", khôi phục 100% dữ liệu về trước task đó.
- Cơ chế Fallback khi người dùng gửi prompt: Thử Online Provider 1 $\rightarrow$ lỗi thì thử tối đa 2 lần với các provider/model online khác $\rightarrow$ nếu vẫn mất mạng thì tự động chuyển mượt về Local GGUF offline và thông báo rõ trong chat.
- Hoàn tất tác vụ kéo dài phải kích hoạt đồng thời chuông âm thanh (`QSoundEffect`) và nhấp nháy Taskbar Windows (`QApplication.alert`).

---

## Review Focus
1. **Network drop during mid-stream tool execution:** Khi mất kết nối mạng đột ngột giữa chừng khi đang gọi LLM online, hệ thống phải bắt exception timeout/connection error, ghi nhật ký cảnh báo vào Chat Stream và kích hoạt fallback sang mô hình offline mà không làm crash app.
2. **Corrupted or missing pre-task snapshot on rollback:** Khi khôi phục trạng thái bằng "Yêu cầu làm lại task", nếu snapshot bị lỗi hoặc không tìm thấy, hệ thống phải giữ nguyên dữ liệu hiện tại, báo lỗi cho người dùng và không làm rỗng phụ đề (bảo vệ chống data loss tương tự BUG-DATA-001).
3. **Invalid or hallucinated tool parameters from LLM:** Khi LLM sinh ra tham số không hợp lệ (ví dụ mã ngôn ngữ không tồn tại, đường dẫn video rỗng, hoặc timecode âm), `ToolRegistry` phải validate tham số tại ranh giới và trả về thông báo lỗi dạng chuỗi về cho Agent xử lý lại thay vì để bắn uncaught exception.
4. **Rapid double-click on Approval Buttons:** Ngăn chặn race condition khi người dùng bấm liên tiếp 2 lần vào nút "✔ Duyệt & Chạy bước tiếp" (nút phải bị disable ngay lập tức khi bắt đầu chạy task).
5. **Cross-tab sync consistency:** Khi người dùng sửa trực tiếp trên khung báo cáo của Copilot rồi chuyển sang Studio Workspace hoặc CAT Studio, dữ liệu phụ đề trên Timeline và Editor phải phản ánh tức thì thay đổi đó.

---

## Danh Sách Các Task Triển Khai (Tasks Breakdown)

### Task 1: Core Data Models & Session Memory Ledger
**Files:**
- Create: `core/agent/models.py`
- Test: `tests/agent/test_agent_models.py`

**Interfaces:**
- Produces: `StepStatus`, `AgentStep`, `AgentTaskPlan`, `ChatMessage`, `AgentContextLedger`

- [ ] **Step 1: Write failing tests for Agent data models & serialization**
```python
# tests/agent/test_agent_models.py
def test_agent_models_serialization():
    from core.agent.models import AgentStep, StepStatus, AgentTaskPlan, ChatMessage, AgentContextLedger
    step = AgentStep(id="step_1", title="ASR Gen Sub", tool_name="run_asr", tool_args={"language": "ja"}, status=StepStatus.PENDING)
    plan = AgentTaskPlan(prompt="Gen sub and translate", steps=[step])
    assert plan.current_step().title == "ASR Gen Sub"
    
    ledger = AgentContextLedger(project_id="proj_1", video_path="test.mp4", duration_ms=25000, source_lang="ja", target_lang="vi")
    ledger.lock_rule("Giữ nguyên thuật ngữ AI")
    d = ledger.to_dict()
    restored = AgentContextLedger.from_dict(d)
    assert "Giữ nguyên thuật ngữ AI" in restored.active_rules
```
- [ ] **Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_models.py -v`
Expected: FAIL (No module named `core.agent`)
- [ ] **Step 3: Implement data models in `core/agent/models.py`**
Implement dataclasses/Pydantic models with `to_dict()` and `from_dict()` for clean serialization into `.ai-subtitle` projects.
- [ ] **Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_models.py -v`
Expected: PASS
- [ ] **Step 5: Commit**
```bash
git add core/agent/models.py tests/agent/test_agent_models.py
git commit -m "feat(agent): add core agent models and context memory ledger"
```

---

### Task 2: Multi-Provider LLM Client & 3-Tier Hybrid Fallback Engine
**Files:**
- Create: `core/agent/multi_provider_client.py`
- Test: `tests/agent/test_multi_provider_client.py`

**Interfaces:**
- Consumes: `ChatMessage` from `core/agent/models.py`
- Produces: `MultiProviderLLMClient.generate_response(messages, tools, available_providers)`

- [ ] **Step 1: Write failing tests for Multi-Provider Fallback logic**
```python
# tests/agent/test_multi_provider_client.py
from unittest.mock import MagicMock
def test_multi_provider_fallback_to_local_on_network_failure():
    from core.agent.multi_provider_client import MultiProviderLLMClient
    client = MultiProviderLLMClient()
    # Mock online providers failing twice
    client._call_online = MagicMock(side_effect=[ConnectionError("Timeout"), ConnectionError("Quota exceeded")])
    client._call_local = MagicMock(return_value={"role": "assistant", "content": "Kế hoạch 3 bước..."})
    
    res = client.generate_with_fallback(
        messages=[{"role": "user", "content": "Dịch video"}],
        online_configs=[{"provider": "gemini", "key": "k1"}, {"provider": "openai", "key": "k2"}],
        allow_local_fallback=True
    )
    assert client._call_online.call_count == 2
    assert client._call_local.call_count == 1
    assert res["content"] == "Kế hoạch 3 bước..."
    assert res["fallback_notice"] is not None
```
- [ ] **Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_multi_provider_client.py -v`
Expected: FAIL
- [ ] **Step 3: Implement `MultiProviderLLMClient` in `core/agent/multi_provider_client.py`**
Implement standard REST requests for OpenAI, Google Gemini, Anthropic, and local llama-cpp fallback worker.
- [ ] **Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_multi_provider_client.py -v`
Expected: PASS
- [ ] **Step 5: Commit**
```bash
git add core/agent/multi_provider_client.py tests/agent/test_multi_provider_client.py
git commit -m "feat(agent): implement multi-provider client with 3-tier hybrid fallback"
```

---

### Task 3: Agent Tool Registry & Pre-Task Snapshot Manager
**Files:**
- Create: `core/agent/agent_tool_registry.py`
- Create: `core/agent/snapshot_manager.py`
- Test: `tests/agent/test_agent_tool_registry.py`
- Test: `tests/agent/test_snapshot_manager.py`

**Interfaces:**
- Consumes: Core application services (`WorkspaceService`, `ProjectState`, `WaveformService`, `SubtitleStyle`)
- Produces: `AgentToolRegistry.execute_tool(name, args)`, `SnapshotManager.take_snapshot()`, `SnapshotManager.restore_snapshot()`

- [ ] **Step 1: Write failing tests for Tool execution and Snapshot rollback**
```python
# tests/agent/test_snapshot_manager.py
def test_snapshot_manager_clean_rollback(tmp_path):
    from core.agent.snapshot_manager import SnapshotManager
    from core.models.project_state import ProjectState
    state = ProjectState(project_name="TestProj")
    state.subtitle_source_segments = [{"id": 1, "text": "Before"}]
    sm = SnapshotManager(state)
    snap_id = sm.take_snapshot("pre_task_1")
    
    # Mutate state
    state.subtitle_source_segments = [{"id": 1, "text": "Mutated"}]
    assert state.subtitle_source_segments[0]["text"] == "Mutated"
    
    # Rollback
    sm.restore_snapshot(snap_id)
    assert state.subtitle_source_segments[0]["text"] == "Before"
```
- [ ] **Step 2: Run tests to verify failure**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_snapshot_manager.py -v`
Expected: FAIL
- [ ] **Step 3: Implement `SnapshotManager` and `AgentToolRegistry`**
Implement snapshot storage using deep serialization of `ProjectState`. Register tools: `load_video`, `run_asr`, `translate_subtitles`, `apply_subtitle_style`, `edit_segment`, `render_hardsub`, `export_srt` with parameter validation.
- [ ] **Step 4: Run tests to verify pass**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_snapshot_manager.py tests/agent/test_agent_tool_registry.py -v`
Expected: PASS
- [ ] **Step 5: Commit**
```bash
git add core/agent/agent_tool_registry.py core/agent/snapshot_manager.py tests/agent/
git commit -m "feat(agent): implement tool registry and transactional snapshot manager"
```

---

### Task 4: Agent Copilot Controller (HITL State Machine)
**Files:**
- Create: `core/agent/agent_copilot_controller.py`
- Test: `tests/agent/test_agent_copilot_controller.py`

**Interfaces:**
- Consumes: `MultiProviderLLMClient`, `AgentToolRegistry`, `SnapshotManager`, `AgentContextLedger`
- Produces: `AgentCopilotController` signals (`plan_ready`, `step_started`, `step_completed_waiting_approval`, `step_failed`, `plan_completed`)

- [ ] **Step 1: Write failing tests for HITL workflow**
```python
# tests/agent/test_agent_copilot_controller.py
def test_copilot_controller_requires_approval_between_steps():
    from core.agent.agent_copilot_controller import AgentCopilotController
    ctrl = AgentCopilotController(tool_registry=MagicMock(), llm_client=MagicMock())
    # Submitting prompt sets plan and pauses
    ctrl.submit_prompt("Tạo phụ đề video này")
    assert ctrl.is_waiting_plan_approval()
    
    ctrl.approve_plan()
    # Runs step 1 and pauses for user review
    assert ctrl.is_waiting_task_approval()
    # Does NOT run step 2 automatically!
    assert ctrl.current_step_index == 0
    
    ctrl.approve_next_step()
    # Now moves to step 2
    assert ctrl.current_step_index == 1
```
- [ ] **Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_copilot_controller.py -v`
Expected: FAIL
- [ ] **Step 3: Implement `AgentCopilotController`**
Implement the state machine enforcing approval gates, capturing snapshot before each step, calling tools, and pausing on completion.
- [ ] **Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_copilot_controller.py -v`
Expected: PASS
- [ ] **Step 5: Commit**
```bash
git add core/agent/agent_copilot_controller.py tests/agent/test_agent_copilot_controller.py
git commit -m "feat(agent): implement hitl state machine controller"
```

---

### Task 5: Windows Notification System (Taskbar Flash & Audio Chime)
**Files:**
- Create: `ui/notifications/task_alert_service.py`
- Test: `tests/ui/test_task_alert_service.py`

**Interfaces:**
- Produces: `TaskAlertService.notify_task_waiting_approval(window, message)`

- [ ] **Step 1: Write failing test for alert service**
```python
# tests/ui/test_task_alert_service.py
def test_task_alert_triggers_flash_and_sound(qtbot):
    from PySide6.QtWidgets import QWidget
    from ui.notifications.task_alert_service import TaskAlertService
    win = QWidget()
    qtbot.addWidget(win)
    service = TaskAlertService()
    service.alert_window = MagicMock()
    service.play_chime = MagicMock()
    service.notify_task_waiting_approval(win, "Task 1 hoàn tất, đang chờ bạn duyệt!")
    service.alert_window.assert_called_once()
    service.play_chime.assert_called_once()
```
- [ ] **Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\python.exe -m pytest tests/ui/test_task_alert_service.py -v`
Expected: FAIL
- [ ] **Step 3: Implement `TaskAlertService` in `ui/notifications/task_alert_service.py`**
Use `QApplication.alert(win)` and `QSoundEffect` (with a bundled synthesized soft chime) to trigger non-intrusive alert.
- [ ] **Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\python.exe -m pytest tests/ui/test_task_alert_service.py -v`
Expected: PASS
- [ ] **Step 5: Commit**
```bash
git add ui/notifications/task_alert_service.py tests/ui/test_task_alert_service.py
git commit -m "feat(ui): implement taskbar alert and audio chime notification service"
```

---

### Task 6: UI Presentation – AIAgentMissionControlPage (100% Mockup Fidelity)
**Files:**
- Create: `ui/pages/ai_agent_mission_control_page.py`
- Create: `ui/components/agent_chat_stream_widget.py`
- Create: `ui/components/agent_task_stepper_widget.py`
- Create: `ui/components/agent_report_inspector_widget.py`
- Test: `tests/gui/specs/test_ai_agent_mission_control_gui.py`

**Interfaces:**
- Consumes: `AgentCopilotController`, `AgentContextLedger`, `TaskAlertService`
- Produces: `AIAgentMissionControlPage` widget embedded in `MainWindow.stack`

- [ ] **Step 1: Write failing GUI tests verifying 100% visual and structural compliance**
```python
# tests/gui/specs/test_ai_agent_mission_control_gui.py
def test_mission_control_page_structure_matches_approved_mockup(qtbot):
    from ui.pages.ai_agent_mission_control_page import AIAgentMissionControlPage
    page = AIAgentMissionControlPage()
    qtbot.addWidget(page)
    
    # 1. Verify 2-Column Split
    assert page.findChild(object, "mc_col_chat") is not None
    assert page.findChild(object, "mc_col_inspect") is not None
    
    # 2. Verify Left Column components
    assert page.findChild(object, "memory_bar") is not None
    assert page.findChild(object, "chat_stream") is not None
    assert page.findChild(object, "prompt_input") is not None
    assert page.findChild(object, "btn_send_prompt") is not None
    
    # 3. Verify Right Column components
    assert page.findChild(object, "step_stepper") is not None
    assert page.findChild(object, "inspection_card") is not None
    assert page.findChild(object, "btn_redo_task") is not None
    assert page.findChild(object, "btn_approve_next") is not None
```
- [ ] **Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\python.exe -m pytest tests/gui/specs/test_ai_agent_mission_control_gui.py -v`
Expected: FAIL
- [ ] **Step 3: Implement `AIAgentMissionControlPage` and child widgets**
Implement exact CSS styling, colors (`#090d16`, `#0f172a`, `#1e293b`, `#38bdf8`, `#a855f7`, `#4ade80`, `#f59e0b`), bubble messages, memory pills, stepper chips, editable report rows, and action buttons.
- [ ] **Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\python.exe -m pytest tests/gui/specs/test_ai_agent_mission_control_gui.py -v`
Expected: PASS
- [ ] **Step 5: Commit**
```bash
git add ui/pages/ai_agent_mission_control_page.py ui/components/ tests/gui/specs/test_ai_agent_mission_control_gui.py
git commit -m "feat(ui): implement ai agent mission control page matching 100% approved mockup"
```

---

### Task 7: Navigation Integration & App Wiring (`Gui.py` & `liquid_nav.py`)
**Files:**
- Modify: `ui/liquid_nav.py`
- Modify: `ui/Gui.py`
- Test: `tests/gui/specs/test_ai_agent_navigation_integration.py`

**Interfaces:**
- Connects: `liquid_nav.tabs` $\rightarrow$ `tab_id: 9` ("🤖 Phòng Điều Hành AI Agent") $\rightarrow$ `Gui.py.stack` (Index 8)

- [ ] **Step 1: Write failing test for navigation switching**
```python
# tests/gui/specs/test_ai_agent_navigation_integration.py
def test_nav_switching_to_ai_agent_tab(qtbot):
    from ui.Gui import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    
    # Switch to tab 9
    win._on_nav_tab_changed(9)
    assert win.stack.currentWidget() == win.page_ai_agent
    assert win.liquid_nav.active_index == win.liquid_nav._get_tab_index_by_id(9)
```
- [ ] **Step 2: Run test to verify it fails**
Run: `.\.venv\Scripts\python.exe -m pytest tests/gui/specs/test_ai_agent_navigation_integration.py -v`
Expected: FAIL
- [ ] **Step 3: Wire `page_ai_agent` into `MainWindow` and `LiquidNavWidget`**
Add tab `id: 9` with robot icon `"🤖"` to `LiquidNavWidget`. Instantiate `AIAgentMissionControlPage` and add to `self.stack`. Connect project state and notifications.
- [ ] **Step 4: Run test to verify it passes**
Run: `.\.venv\Scripts\python.exe -m pytest tests/gui/specs/test_ai_agent_navigation_integration.py -v`
Expected: PASS
- [ ] **Step 5: Commit**
```bash
git add ui/liquid_nav.py ui/Gui.py tests/gui/specs/test_ai_agent_navigation_integration.py
git commit -m "feat(nav): integrate ai agent mission control tab into main navigation"
```

---

### Task 8: End-to-End Acceptance Test & Live Verification
**Files:**
- Create: `tests/e2e/test_ai_agent_copilot_e2e.py`

- [ ] **Step 1: Write End-to-End GUI Test**
Verify the complete user journey:
1. User enters prompt in Mission Control Tab.
2. Agent parses plan with 3 steps.
3. User clicks "Duyệt kế hoạch".
4. Step 1 (ASR) runs, completes, pauses, and triggers Taskbar alert.
5. User edits segment text directly in Report.
6. User clicks "✔ Duyệt & Chạy bước tiếp".
7. Step 2 (Translation) completes.
8. User switches to Studio Workspace: confirms subtitles and translations are 100% synchronized on Timeline and Editor.
- [ ] **Step 2: Run End-to-End test**
Run: `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_ai_agent_copilot_e2e.py -v`
Expected: PASS
- [ ] **Step 3: Run Full Regression Suite**
Run: `.\.venv\Scripts\python.exe -m pytest tests/ -k "not manual" -v`
Expected: 100% PASS across entire application.
- [ ] **Step 4: Commit**
```bash
git add tests/e2e/test_ai_agent_copilot_e2e.py
git commit -m "test(e2e): add end-to-end acceptance tests for ai agent copilot"
```
