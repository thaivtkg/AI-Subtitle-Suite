# Recent Projects (Mở Dự Án Gần Đây) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a persistent Recent Projects feature enabling users to quickly access and reopen past projects both via a Topbar Submenu under "📁 Dự Án" and an interactive Zen Card on the Dashboard page.

**Architecture:**
- **Persistence (`core/utils/recent_projects.py`):**
  - Manages MRU (Most Recently Used) list stored under key `"recent_projects"` in `%LOCALAPPDATA%/AI Subtitle Studio/settings.json` via `core/utils/settings_utils.py`.
  - Cap at 10 items; deduplicates paths, bumps accessed project to top.
  - Automatically prunes non-existent directory entries on access with safety toasts.
- **Controller Refactor (`ui/Gui.py`):**
  - Extract `_open_project_by_path(self, project_dir: str)` from `action_open_project(self)`.
  - Record project to recent history upon `create_project` and `open_project`.
  - Populate dynamic Topbar Submenu `🕒 Mở Dự Án Gần Đây` with project items and `🗑 Xóa Lịch Sử`.
- **Dashboard Quick-Access Card (`ui/pages/dashboard_page.py`):**
  - Add `Recent Projects` card styled with Liquid Theme design tokens (`SURFACE_ELEVATED`, `BORDER`, hover transitions).
  - Connect `open_project_requested = Signal(str)` to `MainWindow._open_project_by_path`.

**Tech Stack:** Python 3.11, PySide6 (Qt6), pytest.

---

### Task 1: Core Recent Projects Manager & Storage Utilities

**Files:**
- Create: `core/utils/recent_projects.py`
- Test: `tests/core/test_recent_projects.py`

**Interfaces:**
```python
def get_recent_projects() -> list[dict]: ...
def add_recent_project(project_dir: str, name: str, video_path: str = "") -> list[dict]: ...
def remove_recent_project(project_dir: str) -> list[dict]: ...
def clear_recent_projects() -> None: ...
```

- [ ] **Step 1: Write unit tests for `recent_projects.py`**
  Cover:
  - Adding a new project prepends to MRU list.
  - Re-adding existing project moves it to the top without duplicate entries.
  - Adding more than 10 projects truncates oldest items.
  - Removing a specific path prunes entry correctly.
  - Clearing resets list to empty.
  Run pytest to verify failure.

- [ ] **Step 2: Implement `core/utils/recent_projects.py`**
  Implement the 4 utility functions reading and writing to `RuntimePaths.get_settings_file()` via `load_settings()` / `save_settings()`.
  Run pytest to confirm all unit tests pass.

---

### Task 2: Controller Refactor & Topbar Submenu Integration

**Files:**
- Modify: `ui/Gui.py:465-475, 4743-4821`
- Test: `tests/ui/test_recent_projects_ui.py`

- [ ] **Step 1: Write tests for Topbar Submenu and controller**
  Test:
  - Submenu exists under `project_menu` named `🕒  Mở Dự Án Gần Đây`.
  - Opening a project via `_open_project_by_path` adds it to recent projects.
  - Clicking a recent project action invokes `_open_project_by_path`.
  - Non-existent directory triggers `remove_recent_project` and shows warning Toast.

- [ ] **Step 2: Refactor `MainWindow` in `ui/Gui.py`**
  - Extract `_open_project_by_path(self, project_dir: str)` containing the existing loading/restoring logic.
  - In `action_open_project`, prompt directory and delegate to `_open_project_by_path`.
  - In `action_new_project` (or post-creation), call `add_recent_project`.
  - Build `recent_menu = QMenu("🕒  Mở Dự Án Gần Đây", project_menu)` and connect `project_menu.aboutToShow` to `_refresh_recent_projects_menu`.
  - Implement `_refresh_recent_projects_menu` to populate actions dynamically and add `🗑  Xóa Lịch Sử`.

---

### Task 3: Dashboard Quick-Access Card & Integration

**Files:**
- Modify: `ui/pages/dashboard_page.py`
- Modify: `ui/Gui.py` (connect signals & refresh on page switch)
- Test: `tests/ui/test_dashboard_recent_projects.py`

- [ ] **Step 1: Write tests for Dashboard Recent Projects Card**
  Test:
  - Dashboard shows empty placeholder when no recent projects exist.
  - Dashboard renders project rows (title, path, open button) when items exist.
  - Clicking row emits `open_project_requested` with correct path.

- [ ] **Step 2: Implement UI card in `DashboardPage`**
  - Add `open_project_requested = Signal(str)`.
  - Add Zen card container below hardware metrics with item rows.
  - Implement `refresh_recent_projects(self)` to re-render items from `get_recent_projects()`.
  - In `MainWindow.switch_page`, call `dashboard_page.refresh_recent_projects()` when switching to index 0.
  - Connect `dashboard_page.open_project_requested` to `self._open_project_by_path`.

- [ ] **Step 3: Run full regression test suite**
  Execute all tests (`tests/core/`, `tests/ui/`, `tests/subtitle_generation/`) ensuring 100% pass rate.
