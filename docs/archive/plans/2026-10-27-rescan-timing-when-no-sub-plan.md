# Dynamic Re-Scan (Quét Lại) Context-Aware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the "Quét lại" (Re-scan) button context-aware: when a subtitle segment has no text (empty or `"[ Chưa có nội dung ]"`), clicking "Quét lại" re-scans the audio to refine the segment's timing boundaries (start_ms, end_ms) without hallucinating text; when the segment already has subtitles, it re-transcribes the speech to update the text (ASR).

**Architecture:**
- **Worker Level (`SegmentScanWorker` & `BatchSegmentScanWorker`):**
  - Add `scan_mode: str = "asr"` (supports `"asr"` and `"timing"`).
  - Add `timing_finished_signal = Signal(str, int, int)` emitting `(segment_id, new_start_ms, new_end_ms)`.
  - In timing mode, Whisper's detected speech boundaries inside the audio slice (`min(s.start_ms)` to `max(s.end_ms)`) are emitted via `timing_finished_signal`. Subtitle text is NOT generated or overwritten.
- **UI Controller (`MainWindow` in `ui/Gui.py`):**
  - In `_on_segment_scan_requested`: inspect target segment text. If `not text.strip()` or `text == "[ Chưa có nội dung ]"`, route to `scan_mode="timing"`.
  - Add `_on_segment_timing_scan_finished`: pushes `EditTimingCommand` to `undo_manager`, updates table (`COL_START`, `COL_END`, `COL_DUR`) and editor inputs, and emits `live_edit_applied` to sync Timeline and Video Player.
  - In `_on_segment_scan_finished` (ASR mode): also ensure table cell `COL_TEXT` and `live_edit_applied` are updated synchronously.
- **UX & Tooltip (`SubEditor.py`):**
  - In `_load_current_editor`: dynamically set tooltip on `btn_scan` to "Quét lại mốc thời gian (Timing) đoạn này" when empty, and "Nhận diện lại chữ (ASR) đoạn này" when text exists.

**Tech Stack:** Python 3.11, PySide6 (Qt6), Faster-Whisper, pytest.

---

### Task 1: Worker Support for Timing Re-Scan

**Files:**
- Modify: `workers/SegmentScanWorker.py:15-75, 78-135`
- Test: `tests/ui/test_playback_sync_fixes.py`

- [ ] **Step 1: Write unit tests for `SegmentScanWorker` timing mode**
  In `tests/ui/test_playback_sync_fixes.py`, add `test_segment_scan_worker_timing_mode`:
  Instantiate `SegmentScanWorker(..., scan_mode="timing")`, mock `transcribe_batch` returning segments `[1200, 1800]`.
  Verify `timing_finished_signal` is emitted with `("seg_1", 1200, 1800)` and `finished_signal` is not emitted.
  Run pytest to verify failure.

- [ ] **Step 2: Implement `scan_mode` in `SegmentScanWorker` and `BatchSegmentScanWorker`**
  - In `SegmentScanWorker`:
    - Add `timing_finished_signal = Signal(str, int, int)`
    - Add `scan_mode: str = "asr"` to `__init__`
    - In `run()`: if `self.scan_mode == "timing"`: if `result.segments`, emit `timing_finished_signal(self.segment_id, speech_start_ms, speech_end_ms)`; if no speech, emit `error_signal(self.segment_id, "NO_SPEECH_DETECTED")`.
  - In `BatchSegmentScanWorker`:
    - Add `segment_timing_completed_signal = Signal(str, int, int)`
    - Route per segment based on `seg.get("has_sub", True)`.
  Run pytest to verify test passes.

---

### Task 2: UI Controller Routing & SubEditor Synchronization

**Files:**
- Modify: `ui/Gui.py:1512-1560, 1687-1760`
- Modify: `ui/SubEditor.py:1168-1180`
- Test: `tests/ui/test_playback_sync_fixes.py`

- [ ] **Step 1: Write integration tests for context-aware routing**
  Test that clicking scan on a segment with empty text invokes timing update, while non-empty text invokes text update.
  Run pytest to verify failure.

- [ ] **Step 2: Implement UI routing and state update in `Gui.py` and `SubEditor.py`**
  - In `_on_segment_scan_requested`: detect `has_sub`, pass `scan_mode="timing"` if not `has_sub`.
  - Implement `_on_segment_timing_scan_finished` to apply timing changes to `all_segments`, `current_editor`, table, and emit `live_edit_applied`.
  - In `_on_segment_scan_finished`: also update table item `COL_TEXT` and emit `live_edit_applied`.
  - In `_load_current_editor`: dynamic tooltip for `btn_scan`.
  Run full test suite to verify 100% pass rate.
