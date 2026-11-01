# AI Subtitle Suite - Project Specification & Context Handover

## 1. Project Overview
**AI Subtitle Suite** (`D:\ai-subtitle-suite`) is an enterprise-grade desktop application combining automated speech recognition, interactive waveform/timeline subtitle editing, and the **AI Subtitle Translation CAT Studio** powered by local LLMs (GGUF via llama-cpp / CPU-GPU acceleration).

### Tech Stack
- **Language**: Python 3.11+
- **Desktop UI**: PySide6 (Qt for Python), Qt Quick / QML (Obsidian Liquid Dark Theme)
- **Speech Recognition**: Faster-Whisper, Silero VAD, PyAV, FFmpeg
- **LLM Translation Core**: Local GGUF models (Gemma-2, Qwen-2.5, DeepSeek-R1), ContextEngine, Glossary, Entity Dictionary, Translation Memory (TM)
- **Testing Framework**: `pytest`, `pytest-qt`, `unittest.mock`
- **Virtual Environment**: `.venv` (`.\.venv\Scripts\python.exe`)

---

## 2. Architecture & Modules

### A. Subtitle Studio (Desktop Timeline & Editor)
- **`ui/Gui.py`**: Main window orchestration, video player, timeline controls, page navigation stack, data sync bridge between Studio and Translation.
- **`ui/SubEditor.py`**: Multi-row subtitle editor table, time manipulation commands, context menus.
- **`ui/timeline/timeline_widget.py`**: Waveform visualization, gap detection, live edit scrub, sticky gap controls.
- **3-in-1 Manual Timing Creation**:
  1. `btn_add_manual_timing` (`➕ Thêm Timing`) on toolbar & `Insert` shortcut.
  2. `create_manual_gap_button` (`➕ Tạo Timing thủ công`) on timeline gap row.
  3. Live Tap-to-Time: `[` (Mark In) and `]` (Mark Out) shortcuts with focus guards.

### B. AI Subtitle Translation CAT Studio
- **`ui/pages/translation_studio_page.py`**: Host page for QML Translation Studio.
  - `load_subtitles_from_studio()`: Formats ms to SRT timecode, loads active row 0, auto-detects native project language, maps `segment_id`.
  - `export_subtitles_to_studio()`: Matches by unique `segment_id`, enforces **Overwrite Guard** (prevents stale translations from overwriting rescanned speech on Timeline).
  - `update_segment_source()`: Synchronizes newly rescanned audio speech into Translation workspace and resets status to `PENDING`.
- **`ui/qml_translation/` (Liquid Dark QML UI)**:
  - `TranslationStudioView.qml`: Master translation screen.
  - `TranslationWorkspace.qml`: Central workspace displaying reactive title `⚡ KHÔNG GIAN DỊCH THUẬT (CÂU #X)`, reactive source badge `CÂU GỐC (JAPANESE / KOREAN / ENGLISH)`, target translation editor, QA status indicators, and keyboard shortcuts (`Ctrl+T`, `Ctrl+Enter`, `Alt+Up`, `Alt+Down`).
  - `SubtitleListView.qml`: Left list displaying `#020 • 00:01:35,270 (2.8s)`, statuses, selection handling.
  - `ContextInspector.qml`: Right sidebar with high-contrast WCAG dark mode cards (Timeline/QA, Intelligence/Glossary, Summary).
  - `LanguageSelector.qml` & `ModelManagerDialog.qml`.
- **`core/translation/` (Translation Engine)**:
  - `translation_controller.py`: Manages subtitle lifecycle, token streaming, Unicode native language detection via `ContextAnalyzer`, exposes `currentSourceLanguage` and `currentDisplayIndex`.
  - `context_analyzer.py`: Unicode block analyzer (`[\u3040-\u30ff]` Japanese, `[\uac00-\ud7af]` Korean, `[\u4e00-\u9fff]` Chinese).
  - `prompt_builder.py`: Constructs strict non-thinking translation prompts with Vietnamese localization rules.
  - `llm/worker.py`: Background worker running local GGUF models.

### C. Desktop GUI Test Automation Framework (Selenium-Equivalent for PySide6 / QML)
- **`tests/gui/drivers/qt_driver.py`**: Selenium-like desktop driver providing Unicode-safe typing, widget discovery by `objectName`, wait conditions, and recursive QML Scene Graph traversal (`find_qml_item()`).
- **Core UI Triad (Page Object Model - POM)**:
  - **`tests/gui/pages/sub_editor_page.py`** (`SubEditorPage`): Encapsulates `CurrentSubtitleEditor`, row navigation, subtitle table inspection, and cursor preservation checks (`BUG-SUB-001`).
  - **`tests/gui/pages/cat_studio_page.py`** (`CatStudioPage`): Encapsulates QML CAT Studio view, source/target translation fields, and action buttons (`btnTranslate`, `btnAccept`, `btnModelManager`).
  - **`tests/gui/pages/timeline_page.py`** (`TimelineWidgetPage`): Encapsulates waveform seeking, gap detection/selection, `create_manual_gap_button`, live tap-to-time (`[` Mark In, `]` Mark Out), and toolbar timing generation.
- **`tests/gui/conftest.py`**: Pytest fixtures (`sub_editor_driver`, `cat_studio_driver`, `timeline_driver`, `main_window_driver`) with safe lifecycle management and eventFilter teardown.

---

## 3. Test Automation Conventions
Run all tests using the virtual environment:
```powershell
# Desktop GUI E2E Specs (Page Object Model - Core UI Triad)
.\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v

# Subtitle Editor Cursor Stability (BUG-SUB-001 Verification)
.\.venv\Scripts\python.exe -m pytest tests/ui/test_current_subtitle_editor_cursor.py -v

# Manual Timing & Hotkeys
.\.venv\Scripts\python.exe -m pytest tests/ui/test_manual_timing_creation.py tests/ui/test_hotkeys_dialog.py -v

# Translation Language Detection & Rescan Overwrite Protection
.\.venv\Scripts\python.exe -m pytest tests/translation/test_language_and_rescan_protection.py -v

# E2E Visual & Integration Tests
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_ui_visual_sync_cat_studio.py -v

# Full Regression Suite (All 39 Specs)
.\.venv\Scripts\python.exe -m pytest tests/ui/test_current_subtitle_editor_cursor.py tests/core/test_editor_ui.py tests/ui/test_manual_timing_creation.py tests/translation/test_language_and_rescan_protection.py tests/e2e/test_ui_visual_sync_cat_studio.py tests/gui/specs/ tests/core/test_architecture_audit_fixes.py -v
```

---

## 4. Key Rules & State
- All translation and bilingual features belong strictly to `D:\ai-subtitle-suite`.
- UI text colors on dark panels must maintain high WCAG contrast (`#F8FAFC`, `#38BDF8`, `#4ADE80`, `#CBD5E1`).
- Subtitle synchronization between Timeline and CAT Studio is locked by `segment_id` with active overwrite protection.
- GUI test automation must adhere to the Page Object Model (POM) pattern in `tests/gui/pages/` and interact through `QtDriver`. Locators for QWidgets must use standard `objectName` properties, and QML elements must use `objectName` identifiers.
