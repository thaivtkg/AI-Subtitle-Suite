# Timing Draft Language Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable explicit language selection (e.g. `ja`, `vi`, `en`) in Timing Draft mode and persist it in project state so that single-segment scans ("🎙️ Gen Sub 1 câu" / "Quét lại") and timing batches enforce the target language, preventing Whisper from hallucinating foreign languages (like Russian Cyrillic `На анномалида.`) on noisy or short audio segments.

**Architecture:**
- **UI State & Policy:** Unlock `cmb_language` in `SubtitleGenerationPanel._on_mode_changed` so users can choose the source language in all task modes (ASR and Timing Draft).
- **Data Persistence:** Add `language: Optional[str] = None` to `TimingState` dataclass in `core/project/project_state.py`. Update `sync_timing_settings_from_project` and `_on_timing_setting_changed` in `SubtitleGenerationPanel` to save and restore language preferences per project.
- **Inference Pipeline:** Ensure `_timing_settings()` exports `language` to `SubtitleGenerationRequest`, which is consumed by `SegmentScanWorker` and `BatchSegmentScanWorker` into `FasterWhisperService.transcribe_batch(transcribe_options["language"] = request.language)`, locking Whisper's decoder strictly to the selected language token (e.g. `<|ja|>`).

**Tech Stack:** Python 3.11, PySide6 (Qt6), Faster-Whisper, pytest.

**Spec / Requirements:**
- Prevent Whisper from defaulting to `Auto Detect` when generating or rescanning segments in Timing Draft mode.
- Retain backwards compatibility for legacy projects without `language` in `TimingState`.
- Maintain test suite integrity across UI, core project restoration, and subtitle generation suites.

## Global Constraints
- Minimal diff principle (Ponytail senior dev): no unnecessary abstractions or redundant signal hops.
- Backwards compatibility: existing `.json` project files without `timing.language` must load without error, defaulting to `Auto Detect` (`language=None`).
- Preservation of runtime state: when switching task modes back and forth (`ASR` $\leftrightarrow$ `Timing Draft`), the selected language in `cmb_language` must not be cleared or reset.

## Review Focus
1. Switching to `Timing Draft` mode $\rightarrow$ `cmb_language` remains enabled and interactive.
2. Selecting `ja` in `Timing Draft` mode $\rightarrow$ `_timing_settings()` returns `{"language": "ja", ...}`.
3. Triggering `🎙️ Gen Sub 1 câu` on a segment with `ja` selected $\rightarrow$ `SubtitleGenerationRequest.language` is `"ja"`, and Whisper transcribe receives `language="ja"`, never `None`.
4. Saving and reopening a project with `language="ja"` $\rightarrow$ `TimingState.language` is `"ja"` and `cmb_language` displays `"ja"`.
5. Opening a legacy project where `timing.language` is absent $\rightarrow$ `cmb_language` defaults safely to `"Auto Detect"` without exceptions.

---

### Task 1: Data Model & Panel Language Unlocking

**Files:**
- Modify: `core/project/project_state.py:28-30`
- Modify: `ui/subtitle_generation_panel.py:595, 1030-1040`
- Test: `tests/subtitle_generation/test_subtitle_generation.py:1230-1235`
- Test: `tests/core/test_timing_project_restore.py`

**Interfaces:**
- `TimingState.language: Optional[str] = None`
- `SubtitleGenerationPanel.cmb_language.setEnabled(True)` in `_on_mode_changed`
- `SubtitleGenerationPanel.sync_timing_settings_from_project` reads `timing.language` and syncs `cmb_language`

- [ ] **Step 1: Write failing tests for enabled language selector and project restoration**
  Update `test_t3_timing_language_remains_disabled` in `tests/subtitle_generation/test_subtitle_generation.py` to assert that `panel.cmb_language.enabled` is `True` in Timing Draft mode. Add test `test_timing_language_restoration` in `tests/core/test_timing_project_restore.py` verifying `timing.language="ja"` sets `cmb_language` to `"ja"`.
  Run pytest to confirm failure.

- [ ] **Step 2: Implement model and UI changes**
  - In `core/project/project_state.py`, add `language: Optional[str] = None` to `TimingState`.
  - In `ui/subtitle_generation_panel.py._on_mode_changed`, change `self.cmb_language.setEnabled(is_asr)` to `self.cmb_language.setEnabled(True)`.
  - In `ui/subtitle_generation_panel.py.sync_timing_settings_from_project`, sync `self.cmb_language` with `getattr(timing, "language", None)`.
  Run pytest to confirm tests pass.

- [ ] **Step 3: Commit Task 1**
  `git commit -m "feat(timing): allow language selection in Timing Draft mode and persist in TimingState"`

---

### Task 2: Segment Scan Propagation & End-to-End Verification

**Files:**
- Modify (if needed) / Verify: `ui/Gui.py:1521-1535` and `ui/Gui.py:1717-1733`
- Test: `tests/subtitle_generation/test_segment_scan_language.py`

**Interfaces:**
- `_on_segment_scan_requested` reads `settings.get("language")` and passes to `SubtitleGenerationRequest`.
- `SegmentScanWorker` calls `FasterWhisperService.transcribe_batch` with `request.language`.

- [ ] **Step 1: Write unit tests verifying single and batch segment scan language propagation**
  Create `tests/subtitle_generation/test_segment_scan_language.py` to assert that when `generation_panel._timing_settings()["language"]` is `"ja"`, `_on_segment_scan_requested` constructs a `SubtitleGenerationRequest` with `language="ja"` and `transcribe_batch` receives `transcribe_options["language"] == "ja"`.
  Also assert that when `cmb_language` is `"Auto Detect"`, `language=None` is passed.
  Run pytest to confirm tests execute cleanly.

- [ ] **Step 2: Run full regression test suite**
  Run all existing test suites:
  - `tests/subtitle_generation/`
  - `tests/core/`
  - `tests/ui/`
  Confirm 100% pass rate.

- [ ] **Step 3: Commit Task 2**
  `git commit -m "test(timing): verify segment scan language propagation and regression suite"`
