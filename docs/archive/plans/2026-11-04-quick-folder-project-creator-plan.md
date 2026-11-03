# Quick Folder Project Creator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to select a folder containing video files, display an interactive checklist of discovered videos with existing/new project detection, automatically generate `.ai-subtitle` projects adjacent to the video files without manual dialog entry, and open the first selected video directly into the Workspace while queuing the rest.

**Architecture:**
1. Core Service Layer (`ProjectService`): Introduces `scan_video_folder()` to discover video files and detect existing `.ai-subtitle` bundles, and `create_or_get_folder_project()` to instantiate or resolve projects in-place.
2. UI Dialog Layer (`QuickFolderProjectDialog`): A Liquid Dark themed dialog featuring a searchable table with selection checkboxes, format/size indicators, status tags (`✨ Mới` vs `📂 Đã có dự án`), and selection counters.
3. MainWindow Coordination (`MainWindow`): Adds a Project Menu action ("📁 Tạo Dự Án Từ Thư Mục..."), supports dragging & dropping a folder directly into the window to launch the dialog, opens the primary selected project into the Studio Workspace, and registers remaining selected videos into the Queue Manager with bound project paths.

**Tech Stack:** Python 3.11+, PySide6 (Qt for Python), `pytest`, `pytest-qt`.

**Spec:** User specification in conversation `bc09a4cd-ebe2-4025-ac00-5b4d8c23e82d` (Quick Project Creation from Video Folder).

## Global Constraints
- Strictly preserve existing manual project creation (`NewProjectDialog`) and project loading workflows.
- Automatically generated projects must follow canonical naming: `{folder}/{safe_video_name}.ai-subtitle` adjacent to the video.
- Existing project bundles must NEVER be overwritten: if a project already exists for a video, the system opens the existing project instead of resetting state.
- UI theme must strictly adhere to Obsidian Liquid Dark Theme (`#0F172A`, `#1E293B`, `#38BDF8`, `#10B981`, `#F8FAFC`).
- High-coverage automated unit and integration tests with `pytest`.

## Review Focus
1. Folder scanning filters: Supported video extensions (`.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`, `.webm`, `.ts`) are detected; non-video and hidden files are excluded.
2. Status accuracy: Correctly distinguishes between videos that already have an adjacent `.ai-subtitle` bundle vs completely new videos.
3. Single selection flow: Selecting 1 video generates its project and immediately opens it in Workspace.
4. Multi-selection batch flow: Selecting $N$ videos creates projects for all $N$; opens video 1 in Workspace; registers videos $2 \dots N$ into Queue Manager with valid project bindings.
5. Drag & Drop folder: Dropping a folder directory into MainWindow launches the dialog pre-filled with that directory.

---

### Task 1: Core Service Layer (`ProjectService` Folder Scanner & Creator)

**Files:**
- Modify: `core/services/project_service.py`
- Create: `tests/core/test_folder_project_scanner.py`

- [x] **Step 1.1: Write failing unit tests in `tests/core/test_folder_project_scanner.py`**
  Covering:
  - `scan_video_folder(folder_path)`: Scans folder containing a mix of video files, text files, and subfolders. Returns list of metadata dicts (`video_path`, `filename`, `size_mb`, `has_project`, `expected_project_dir`).
  - Detection of existing projects: Accurately reports `has_project=True` when `{safe_name}.ai-subtitle` exists.
  - `create_or_get_folder_project(video_path)`: Creates new bundle if not exists; reopens existing bundle if already present without overwriting.

- [x] **Step 1.2: Run test to confirm failure**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/core/test_folder_project_scanner.py -v
  ```

- [x] **Step 1.3: Implement methods in `core/services/project_service.py`**
  - Implement `scan_video_folder(self, folder_path: str) -> list[dict]`.
  - Implement `create_or_get_folder_project(self, video_path: str) -> tuple[Project, bool]`.

- [x] **Step 1.4: Verify tests pass**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/core/test_folder_project_scanner.py -v
  ```

- [x] **Step 1.5: Commit Task 1**
  ```powershell
  git add core/services/project_service.py tests/core/test_folder_project_scanner.py
  git commit -m "feat(project): implement scan_video_folder and create_or_get_folder_project (DEV-SPEC-FOLDER-PROJECT-001)"
  ```

---

### Task 2: UI Dialog Component (`QuickFolderProjectDialog`)

**Files:**
- Create: `ui/dialogs/quick_folder_project_dialog.py`
- Create: `tests/ui/test_quick_folder_project_dialog.py`

- [x] **Step 2.1: Write failing unit tests in `tests/ui/test_quick_folder_project_dialog.py`**
  Covering:
  - Dialog populates video table from scanned directory.
  - Checkbox toggle and "Select All" / "Deselect All" button behavior.
  - Real-time search filter updates visible rows.
  - Returns list of selected video paths upon clicking "🚀 Khởi Tạo Dự Án & Mở Workspace".

- [x] **Step 2.2: Run test to confirm failure**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_quick_folder_project_dialog.py -v
  ```

- [x] **Step 2.3: Implement `QuickFolderProjectDialog` in `ui/dialogs/quick_folder_project_dialog.py`**
  - Header: Folder selector bar (`QLineEdit` + "Chọn Thư Mục..." button).
  - Search box: `QLineEdit` with placeholder "🔍 Tìm kiếm video trong thư mục...".
  - Table: `QTableWidget` (Cols: `[✓]`, Tên Video, Kích thước, Trạng thái).
  - Action row: "Chọn tất cả", "Bỏ chọn", summary counter ("Đã chọn: X / Y video").
  - Footer buttons: "Hủy" and "🚀 Khởi Tạo & Mở Workspace".

- [x] **Step 2.4: Verify tests pass**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_quick_folder_project_dialog.py -v
  ```

- [x] **Step 2.5: Commit Task 2**
  ```powershell
  git add ui/dialogs/quick_folder_project_dialog.py tests/ui/test_quick_folder_project_dialog.py
  git commit -m "feat(ui): create QuickFolderProjectDialog with multi-select table and search filter (DEV-SPEC-FOLDER-PROJECT-001)"
  ```

---

### Task 3: MainWindow Coordinator & Drag-Drop Integration (`ui/Gui.py`)

**Files:**
- Modify: `ui/Gui.py`
- Create: `tests/ui/test_gui_quick_folder_project.py`

- [x] **Step 3.1: Write failing integration tests in `tests/ui/test_gui_quick_folder_project.py`**
  Covering:
  - Menu action `action_quick_folder_project` opens dialog.
  - Dragging a folder into MainWindow launches `QuickFolderProjectDialog` with that directory.
  - Single selection opens project directly into Workspace.
  - Multi-selection opens first project in Workspace and registers remaining items into Queue Manager.

- [x] **Step 3.2: Run test to confirm failure**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_gui_quick_folder_project.py -v
  ```

- [x] **Step 3.3: Implement integration in `ui/Gui.py`**
  - Add menu item to Project Menu: `self.action_quick_folder_project = project_menu.addAction("📁  Tạo Dự Án Từ Thư Mục...", self._action_quick_folder_project)`.
  - Implement `_action_quick_folder_project(folder_path=None)`.
  - Update `dropEvent(event)`: if dropped URL is a directory, invoke `_action_quick_folder_project(folder_path)`.
  - Process accepted dialog result: create projects, open primary video in Workspace, bind remaining videos in `queue_mgr`.

- [x] **Step 3.4: Verify tests pass**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_gui_quick_folder_project.py -v
  ```

- [x] **Step 3.5: Commit Task 3**
  ```powershell
  git add ui/Gui.py tests/ui/test_gui_quick_folder_project.py
  git commit -m "feat(gui): integrate quick folder project creation, menu action, and folder drag-and-drop (DEV-SPEC-FOLDER-PROJECT-001)"
  ```

---

### Task 4: Full Regression & E2E Validation

- [x] **Step 4.1: Run full regression test suite**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/core/test_folder_project_scanner.py tests/ui/test_quick_folder_project_dialog.py tests/ui/test_gui_quick_folder_project.py tests/core/test_missing_video_recovery.py tests/ui/test_missing_media_dialog.py tests/ui/test_gui_missing_video_relink.py -v
  ```

- [x] **Step 4.2: Archive completed plan and update catalog in `docs/README.md`**
  - Move plan to `docs/archive/plans/`.
  - Update table in `docs/README.md`.

- [x] **Step 4.3: Final Commit**
  ```powershell
  git add docs/README.md docs/archive/plans/
  git commit -m "docs: archive completed quick folder project plan into docs/archive/plans"
  ```
