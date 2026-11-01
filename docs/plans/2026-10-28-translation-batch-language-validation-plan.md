# Translation Batch Language-Aware Untranslated Detection & Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the translation batch tracking and validation logic so that:
1. Untranslated subtitles are accurately identified per the strict rule:
   - Untranslated if empty `""` or placeholder `"[ Chưa có nội dung ]"`.
   - Untranslated if containing CJK characters (Japanese Kanji/Hiragana/Katakana `[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]` or Korean `[\uAC00-\uD7AF]`).
   - Untranslated if in any language other than Vietnamese (such as English, Russian, etc.).
   - A subtitle is considered **TRANSLATED** if and only if it is in **Vietnamese**.
2. The batch start spinbox (`spin_batch_start`) automatically skips already translated Vietnamese sentences and points to the first truly untranslated sentence (e.g. jumping from 1 to 6, or 6 to 11).
3. When all sentences are translated (e.g. 10/10), the UI displays a clear completed status rather than resetting to `1 -> 5`.
4. Exporting a batch validates whether target lines are already translated and presents a confirmation guard to prevent accidental re-exporting of finished translations.

**Architecture:**
- **Language & Translation Classifier (`core/utils/translation_detector.py`):**
  - Implement `is_vietnamese_translated(segment: dict | str) -> bool`:
    - Returns `False` if text is empty `""` or `"[ Chưa có nội dung ]"`.
    - Returns `False` if text contains CJK characters (`[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]`).
    - Returns `False` if text contains Cyrillic characters (`[\u0400-\u04FF]`).
    - Returns `True` if text contains Vietnamese diacritics / tone marks (`[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]`).
    - For non-diacritic Latin text, checks against common English stop-words (`the`, `you`, `what`, `is`, `are`, `this`, `that`, `to`, `in`, `and`, `we`, `for`, `with`, `from`, `have`, `can`, `will`, `not`, etc.) or identical `original_text`: if English/foreign, returns `False` (untranslated). If common conversational particle (`ok`, `alo`, `bye`), treats as translated.
- **UI Progress Synchronization (`MainWindow._sync_translation_batch_ui` in `ui/Gui.py`):**
  - Use `is_vietnamese_translated` to calculate `translated_count`.
  - Locate the first index `first_untranslated` where `not is_vietnamese_translated(s)`.
  - If all sentences are translated, notify `ExportCenterPage` with completed status (`suggested_start=None`).
- **Export Pre-flight Guard (`MainWindow._on_export_batch_translation_requested` in `ui/Gui.py`):**
  - Check whether `target_segments` contain already translated lines.
  - If all target segments are already translated, prompt a confirmation dialog (`QMessageBox.warning`) warning the user that lines are already translated in Vietnamese. If cancelled, offer to advance cursor to `first_untranslated`.
- **UI Display & Progress Label (`ExportCenterPage.update_translation_progress` in `ui/pages/export_center_page.py`):**
  - Update progress label to show `🎉 Đã hoàn thành dịch toàn bộ ({total_count}/{total_count} câu)` when finished.

**Tech Stack:** Python 3.11, PySide6 (Qt6), regex, pytest.

---

### Task 1: Translation Status Classifier Utility

**Files:**
- Create: `core/utils/translation_detector.py`
- Test: `tests/core/test_translation_detector.py`

**Interfaces:**
```python
def is_vietnamese_translated(text_or_segment: dict | str) -> bool: ...
def find_first_untranslated_index(segments: list[dict]) -> Optional[int]: ...
def count_translated_segments(segments: list[dict]) -> tuple[int, int]: ...
```

- [ ] **Step 1: Write unit tests for translation classifier**
  Cover:
  - Empty string and `"[ Chưa có nội dung ]"` return `False`.
  - Japanese text (`"待たせたな"`, `"お前は誰だ？"`) returns `False`.
  - Cyrillic/Russian text (`"На анномалида."`) returns `False`.
  - English text (`"Lord, help my world."`, `"What are you doing?"`) returns `False`.
  - Vietnamese text with diacritics (`"Cuối cùng đã tìm thấy ngươi rồi Ma Vương"`) returns `True`.
  - Mixed lists: sentences 1-5 Vietnamese, 6-10 Japanese -> `count_translated = 5`, `first_untranslated = 6`.
  - Fully translated lists: 10/10 Vietnamese -> `count_translated = 10`, `first_untranslated = None`.
  Run pytest to verify failure.

- [ ] **Step 2: Implement `core/utils/translation_detector.py`**
  Implement regex-based CJK, Cyrillic, Vietnamese diacritics, and English stop-word classification functions.
  Run pytest to verify all tests pass.

---

### Task 2: UI Progress Sync & Export Pre-flight Guard

**Files:**
- Modify: `ui/Gui.py:4245-4290, 4357-4380`
- Modify: `ui/pages/export_center_page.py:174-186`
- Test: `tests/ui/test_batch_translation_workflow.py`

- [ ] **Step 1: Write integration tests for language-aware sync and export guard**
  Test:
  - Syncing a 10-segment project with 1-5 Vietnamese and 6-10 Japanese sets `spin_batch_start` to 6.
  - Syncing a fully translated 10-segment project sets completed progress message.
  - Requesting export on already translated lines triggers confirmation warning.
  Run pytest to verify failure.

- [ ] **Step 2: Implement UI updates in `Gui.py` and `export_center_page.py`**
  - In `_sync_translation_batch_ui`: use `find_first_untranslated_index` and `count_translated_segments`.
  - In `ExportCenterPage.update_translation_progress`: handle `is_completed` / `current_start is None` with complete badge.
  - In `_on_export_batch_translation_requested`: add confirmation dialog if exporting already translated lines.
  Run full test suite to verify 100% pass rate.
