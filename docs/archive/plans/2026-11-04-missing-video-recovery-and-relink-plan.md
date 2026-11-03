# Missing Video Recovery & Relink Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide an intelligent, robust 3-tier media recovery mechanism when opening a project whose original video has been moved, renamed, or is unavailable, preventing abrupt import cancellation and allowing seamless re-linking or video-free editing.

**Architecture:** 
1. Core layer (`ProjectService` & `ProjectState`): Adds `MissingVideoError`, `probe_project_source()`, `relink_project_video()`, and extends `open_project()` with `allow_missing_video` & `relink_video_path` options.
2. UI Dialog layer (`MissingMediaDialog`): Modern Dark-themed dialog allowing users to browse a new video, use an auto-discovered adjacent video, open in subtitle/CAT studio-only mode, or cancel.
3. GUI Coordinator layer (`MainWindow`): Integrates zero-click auto-relocate on exact fingerprint match, triggers `MissingMediaDialog` on ambiguity, adds a persistent "🔗 Định vị lại Video gốc..." action in the Project menu, and handles missing-video fallbacks for video player and timeline.

**Tech Stack:** Python 3.11+, PySide6 (Qt for Python), `hashlib`, `pytest`, `pytest-qt`.

**Spec:** User specification in conversation `bc09a4cd-ebe2-4025-ac00-5b4d8c23e82d` (Offline Media Recovery & Re-link).

## Global Constraints
- Preserve existing backward compatibility for all existing `.ai-subtitle` projects.
- Preserve atomic file writes (`atomic_save_json`) to prevent project corruption during re-linking.
- Subtitle synchronization, CAT Studio, and SubEditor must remain 100% functional even when opening without video.
- All UI colors must adhere to the Obsidian Liquid Dark Theme (`#0F172A`, `#1E293B`, `#38BDF8`, `#F8FAFC`).
- High-coverage automated tests using `pytest` for all newly created components.

## Review Focus
1. Video moved to adjacent folder: Zero-click auto-relocate discovers the video with matching fingerprint and opens without prompting.
2. Video moved to a different directory or renamed: User selects the new file via File Dialog; system validates hash, updates `project.json`, and loads the project.
3. Video replaced with a re-encoded/different version (Hash mismatch): System prompts warning confirmation; if confirmed, forces re-link and loads project.
4. Video deleted or unavailable: User chooses "Mở không có video"; project loads subtitles, timeline, and CAT Studio without crash.
5. Post-open relink: User who opened in video-free mode clicks "Định vị lại Video gốc..." from the menu to link video later; video player and timeline update immediately.

---

### Task 1: Core Service Layer (`ProjectService` & `ProjectState`)

**Files:**
- Modify: `core/project/project_state.py:45-68`
- Modify: `core/services/project_service.py:16-40, 163-255`
- Create: `tests/core/test_missing_video_recovery.py`

- [ ] **Step 1.1: Write failing unit tests for core recovery methods**
  Write tests in `tests/core/test_missing_video_recovery.py` covering:
  - `probe_project_source`: returns `(source_info, current_path, is_valid=False, suggested_path)` when video is missing, and discovers matching candidate in adjacent folder.
  - `relink_project_video`: updates `project.json` source info with new video fingerprint and updates `current_project.source`.
  - `open_project(allow_missing_video=True)`: succeeds without raising `FileNotFoundError` and sets `project.state.is_video_missing = True`.
  - `open_project(allow_missing_video=False)`: raises `MissingVideoError` with original path and suggested candidate.

- [ ] **Step 1.2: Run test to confirm failures**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/core/test_missing_video_recovery.py -v
  ```

- [ ] **Step 1.3: Implement core recovery logic in `core/project/project_state.py` and `core/services/project_service.py`**
  - Add `is_video_missing: bool = False` to `ProjectState`.
  - Define `MissingVideoError(FileNotFoundError)` in `core/services/project_service.py` storing `video_path`, `project_dir`, `source_info`, and `suggested_path`.
  - Implement `probe_project_source(project_dir: str) -> tuple[ProjectSourceInfo, str, bool, str | None]`.
  - Implement `relink_project_video(project_dir: str, new_video_path: str, force: bool = False) -> ProjectSourceInfo`.
  - Update `open_project(project_dir: str, allow_missing_video: bool = False, relink_video_path: str | None = None) -> Project`.

- [ ] **Step 1.4: Verify tests pass**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/core/test_missing_video_recovery.py -v
  ```

- [ ] **Step 1.5: Commit Task 1**
  ```powershell
  git add core/project/project_state.py core/services/project_service.py tests/core/test_missing_video_recovery.py
  git commit -m "feat(project): implement missing video probe, relink, and offline mode support (DEV-SPEC-RELINK-MEDIA-001)"
  ```

---

### Task 2: UI Dialog Component (`MissingMediaDialog`)

**Files:**
- Create: `ui/dialogs/missing_media_dialog.py`
- Create: `tests/ui/test_missing_media_dialog.py`

- [ ] **Step 2.1: Write failing unit test for `MissingMediaDialog`**
  Write tests in `tests/ui/test_missing_media_dialog.py` verifying:
  - Dialog initializes with missing path and project name.
  - If `suggested_path` is provided, displays suggested file banner and "Dùng video này" button.
  - Clicking "Mở không có video" accepts with action `OPEN_WITHOUT_VIDEO`.
  - Clicking "Hủy bỏ" rejects with action `CANCEL`.
  - Clicking "Chọn video khác..." invokes file dialog and returns `RELINK` action.

- [ ] **Step 2.2: Run test to confirm failure**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_missing_media_dialog.py -v
  ```

- [ ] **Step 2.3: Implement `MissingMediaDialog` in `ui/dialogs/missing_media_dialog.py`**
  - Subclass `QDialog` with Obsidian Liquid Dark Theme stylesheet.
  - Present missing video details (original filename, old path).
  - Include conditional suggestion banner if candidate path detected.
  - Provide buttons:
    - `btn_use_suggested` (if suggested path available)
    - `btn_browse`: "🔍 Chọn Lại Video Mới..."
    - `btn_open_no_video`: "📄 Mở Không Cần Video (Chỉ Sửa Phụ Đề & Dịch)"
    - `btn_cancel`: "❌ Hủy Bỏ"
  - Store selected choice in `dialog.result_action` and `dialog.selected_video_path`.

- [ ] **Step 2.4: Verify tests pass**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_missing_media_dialog.py -v
  ```

- [ ] **Step 2.5: Commit Task 2**
  ```powershell
  git add ui/dialogs/missing_media_dialog.py tests/ui/test_missing_media_dialog.py
  git commit -m "feat(ui): create MissingMediaDialog with auto-discovery and offline mode options (DEV-SPEC-RELINK-MEDIA-001)"
  ```

---

### Task 3: MainWindow Coordinator & Menu Integration (`ui/Gui.py`)

**Files:**
- Modify: `ui/Gui.py:470-490, 5320-5425`
- Create: `tests/ui/test_gui_missing_video_relink.py`

- [ ] **Step 3.1: Write failing integration test for GUI missing video workflow**
  Write tests in `tests/ui/test_gui_missing_video_relink.py`:
  - When opening project with missing video and exact candidate found in adjacent directory: auto-relocates and opens successfully without popup.
  - When opening project with missing video and user chooses "OPEN_WITHOUT_VIDEO": opens project in offline mode, loads timeline and editor, displays toast warning.
  - When user chooses "RELINK" with matching/mismatched video: updates video player source and timeline duration.
  - Project menu has "🔗 Định Vị Lại Video Gốc..." action enabled when a project is open.

- [ ] **Step 3.2: Run test to confirm failures**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_gui_missing_video_relink.py -v
  ```

- [ ] **Step 3.3: Implement recovery coordination in `ui/Gui.py`**
  - In `_open_project_by_path(project_dir)`:
    - Probe source using `self.project_service.probe_project_source(project_dir)`.
    - If video is missing:
      - If exact candidate exists in adjacent folder with 100% matching fingerprint: auto-relink silently via `self.project_service.relink_project_video(project_dir, candidate)` and show Toast notification.
      - Otherwise, show `MissingMediaDialog`.
      - Handle `RELINK`: if hash mismatch, confirm via `QMessageBox.question`, then relink and open.
      - Handle `OPEN_WITHOUT_VIDEO`: call `self.project_service.open_project(project_dir, allow_missing_video=True)`.
      - Handle `CANCEL`: abort and return `False`.
  - Add `self.action_relink_video = project_menu.addAction("🔗  Định Vị Lại Video Gốc...", self._action_relink_video)`.
  - Implement `_action_relink_video(self)` to allow relinking video on an active project at any time.
  - In `workspace_service.py` / `Gui.py`, guard video loading and ensure timeline uses `last_seg.end_ms + 5000` when video duration is unavailable.

- [ ] **Step 3.4: Verify tests pass**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_gui_missing_video_relink.py -v
  ```

- [ ] **Step 3.5: Commit Task 3**
  ```powershell
  git add ui/Gui.py tests/ui/test_gui_missing_video_relink.py
  git commit -m "feat(gui): integrate smart auto-relocate, missing media recovery dialog, and Project menu relink action (DEV-SPEC-RELINK-MEDIA-001)"
  ```

---

### Task 4: Full Regression & Documentation Clean-up

**Files:**
- Archive: `docs/plans/2026-11-04-missing-video-recovery-and-relink-plan.md` -> `docs/archive/plans/2026-11-04-missing-video-recovery-and-relink-plan.md`
- Modify: `docs/README.md`

- [ ] **Step 4.1: Run full regression test suite**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/core/test_missing_video_recovery.py tests/ui/test_missing_media_dialog.py tests/ui/test_gui_missing_video_relink.py tests/ui/test_open_project_restores_saved_tab.py tests/ui/test_current_subtitle_editor_cursor.py tests/ui/test_subeditor_arrow_navigation.py tests/translation/test_cat_studio_realtime_structural_sync.py -v
  ```

- [ ] **Step 4.2: Archive completed plan and update catalog in `docs/README.md`**
  - Move plan to `docs/archive/plans/`.
  - Add record entry to `docs/README.md`.

- [ ] **Step 4.3: Final Commit**
  ```powershell
  git add docs/README.md docs/archive/plans/
  git commit -m "docs: archive completed missing video recovery plan into docs/archive/plans"
  ```
