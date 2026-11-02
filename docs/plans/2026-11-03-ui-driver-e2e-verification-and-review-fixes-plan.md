# Kế Hoạch Khắc Phục Lỗi Review & Kiểm Thử E2E Toàn Diện Bằng UI Driver (`QtDriver` + POM)

- **Mã kế hoạch**: `PLAN-UI-DRIVER-E2E-VERIFICATION-001`
- **Ngày lập**: 2026-11-03
- **Phạm vi**:
  - Khắc phục 3 lỗi tiềm ẩn phát hiện qua Code Review (`receiving-code-review`) trên Commit `ba44db4` và `b60b051`.
  - Bổ sung locators chuẩn `objectName` cho `ActivityLogView` và mở rộng Page Object Model (`CatStudioPage`, `SubEditorPage`).
  - Viết bộ E2E Specs chạy thật qua `QtDriver` (`tests/gui/specs/`) thay vì chỉ mock unit test (`MainWindow.__new__`).
- **Nguyên tắc Ponytail**: Sửa tận gốc tại điểm phát sinh, diff nhỏ gọn nhất, kiểm chứng thực tế trên Scene Graph QML và QWidget thật qua `QtDriver`.

---

## 1. Kết Quả Code Review Kỹ Thuật (`receiving-code-review`)

Qua đối chiếu mã nguồn thực tế tại commit `ba44db4` & `b60b051` với quy chuẩn `QtDriver` + POM trong `GEMINI.md`:

1. **[BUG-SCAN-ID-001] Mất khớp `segment_id` khi bấm nút `🔍 Quét lại` (`btn_current_sub_scan`) trên UI thật**:
   - Tại `ui/SubEditor.py:1142`, `_on_current_editor_scan_requested()` phát tín hiệu:
     ```python
     self.segment_scan_requested.emit(seg.get("id"), start_ms, end_ms)
     ```
   - Khi segment được nạp mà chưa có khóa `"id"` tường minh (hoặc `seg.get("id")` là `None`, ví dụ từ fixture hay dữ liệu chỉ có `"stt"`), `Signal(str, int, int)` của PySide6 ép `None` thành chuỗi rỗng `""`.
   - Khi sang `ui/Gui.py:1671` (`_on_segment_scan_requested`) và `ui/Gui.py:1739` (`_on_segment_timing_scan_finished`), phép so sánh `str(s.get("id")) == str(segment_id)` trở thành `"None" == ""` (`False`). Hậu quả:
     - `has_sub` luôn bị tính sai thành `False` dù câu đang có phụ đề ➔ chạy nhầm `scan_mode="timing"` thay vì `"asr"`.
     - Khi worker quét xong, `_on_segment_scan_finished` không tìm thấy câu để cập nhật text lên bảng UI.
   - Lý do unit test `test_rescan_vram_guard_and_log_compression.py` không phát hiện ra: Test dùng `MainWindow.__new__(MainWindow)` và truyền tay `segment_id="1"` thay vì bấm nút `btn_current_sub_scan` qua `QtDriver`.

2. **[BUG-LOG-PREFIX-002] Nhân đôi tiền tố `[TIMING] [ASR]` trên Nhật ký hoạt động**:
   - Tại `workers/TimingBatchWorker.py:110`, worker phát `self.log_signal.emit("[ASR] VRAM đạt ...")`.
   - Nhưng tại `ui/Gui.py:4169`, `_on_timing_log(self, message: str)` lại nối cứng `self.append_log(f"[TIMING] {message}")` tạo thành `"[TIMING] [ASR] VRAM đạt..."`.
   - Hàm `parse_activity_log()` (`ui/activity_log.py:97`) chỉ bóc nhãn ngoặc vuông đầu tiên, khiến log hạ cấp VRAM của ASR bị phân loại nhầm sang nguồn `TIMING` và hiển thị dư chuỗi `[ASR]` trong nội dung.

3. **[GAP-UI-DRIVER-003] Thiếu `objectName` trên `ActivityLogView` và chưa có E2E Spec bằng `QtDriver` cho 3 bản vá gần nhất**:
   - `ActivityLogView` (`ui/activity_log.py:253-308`) chưa gán `objectName` cho `level_filter`, `source_filter`, `clear_button`, và `text_edit`, vi phạm Quy tắc 4 trong `GEMINI.md`.
   - `CatStudioPage` (`tests/gui/pages/cat_studio_page.py`) chưa khai báo locator cho `subjectTagChip` / `subjectTagText` và chưa có spec E2E kiểm tra trên QML Scene Graph thật.

---

## 2. Chi Tiết Các Tác Vụ Triển Khai

### Task 1: Chuẩn hóa `segment_id` khi bấm Quét lại trên `SubEditor` (`ui/SubEditor.py` & `ui/Gui.py`)
- **File can thiệp**:
  - `ui/SubEditor.py` (hàm `_on_current_editor_scan_requested` tại dòng `1130-1143`)
  - `ui/Gui.py` (hàm `_on_segment_scan_requested` tại dòng `1669-1675`)
- **Thay đổi**:
  1. Trong `ui/SubEditor.py:_on_current_editor_scan_requested()`:
     Đảm bảo mỗi segment luôn có `"id"` hợp lệ trước khi emit signal:
     ```python
     seg_id = str(seg.get("id") or seg.get("stt") or (self.current_index + 1))
     seg["id"] = seg_id
     self.segment_scan_requested.emit(seg_id, start_ms, end_ms)
     ```
  2. Trong `ui/Gui.py:_on_segment_scan_requested()`:
     Khi dò segment trong `self.sub_editor.all_segments`, fallback khớp theo cả `s.get("id")` hoặc `s.get("stt")` để an toàn tuyệt đối với mọi nguồn dữ liệu:
     ```python
     for idx, s in enumerate(self.sub_editor.all_segments):
         sid = str(s.get("id") or s.get("stt") or (idx + 1))
         if sid == str(segment_id):
             s["id"] = sid
             has_sub = bool(str(s.get("text", "")).strip())
             break
     ```

---

### Task 2: Chặn nhân đôi tiền tố trong `_on_timing_log` & Gán `objectName` cho `ActivityLogView` (`ui/Gui.py` & `ui/activity_log.py`)
- **File can thiệp**:
  - `ui/Gui.py` (hàm `_on_timing_log` tại dòng `4169-4170`)
  - `ui/activity_log.py` (lớp `ActivityLogView.__init__` tại dòng `253-308`)
- **Thay đổi**:
  1. Trong `ui/Gui.py:_on_timing_log(self, message: str)`:
     Nếu `message` đã bắt đầu bằng nhãn nguồn `[...]` (ví dụ `[ASR]` hoặc `[TIMING]`), giữ nguyên khi đẩy vào `self.append_log`:
     ```python
     def _on_timing_log(self, message: str):
         clean = str(message or "").lstrip()
         self.append_log(clean if clean.startswith("[") else f"[TIMING] {message}")
     ```
  2. Trong `ui/activity_log.py` (`ActivityLogView.__init__`):
     Gán `objectName` chuẩn cho 4 widget điều khiển để `QtDriver` truy xuất:
     ```python
     self.level_filter.setObjectName("activity_level_filter")
     self.source_filter.setObjectName("activity_source_filter")
     self.clear_button.setObjectName("activity_clear_button")
     self.text_edit.setObjectName("activity_log_text")
     ```

---

### Task 3: Mở rộng Page Object Model (`tests/gui/pages/cat_studio_page.py` & `tests/gui/pages/sub_editor_page.py`)
- **File can thiệp**:
  - `tests/gui/pages/cat_studio_page.py`
  - `tests/gui/pages/sub_editor_page.py`
- **Thay đổi**:
  1. Trong `CatStudioPage` (`tests/gui/pages/cat_studio_page.py`):
     - Bổ sung hằng số locator QML:
       ```python
       LOC_SUBJECT_TAG_CHIP = "subjectTagChip"
       LOC_SUBJECT_TAG_TEXT = "subjectTagText"
       ```
     - Bổ sung property `subject_tag_chip_item`, `subject_tag_text_item` dùng `self.driver.find_qml_item(...)`.
     - Bổ sung helper:
       - `get_subject_tag_text() -> str`: trả về `str(self.subject_tag_text_item.property("text"))`.
       - `is_subject_tag_visible() -> bool`: trả về `bool(self.subject_tag_chip_item.property("visible"))`.
       - `set_subject_pronoun(pronoun_pair: str) -> None`: gọi `self.page_widget._controller.setSubjectPronoun(pronoun_pair)` và `self.driver.wait_ui(50)`.
  2. Trong `SubEditorPage` (`tests/gui/pages/sub_editor_page.py`):
     - Bổ sung helper kiểm tra căn lề dọc của ô trong bảng `table_subtitles`:
       ```python
       def get_table_cell_alignment(self, row: int, col: int = 4) -> int:
           item = self.table.item(row, col)
           return int(item.textAlignment()) if item else 0
       ```

---

### Task 4: Viết Bộ Kiểm Thử E2E Bằng `QtDriver` (`tests/gui/specs/test_cat_studio_flow.py` & `tests/gui/specs/test_sub_editor_flow.py`)
- **File can thiệp**:
  - `tests/gui/specs/test_cat_studio_flow.py`
  - `tests/gui/specs/test_sub_editor_flow.py`
- **Chi tiết 4 kịch bản E2E chạy qua `QtDriver`**:
  1. `test_flow_cat_studio_subject_tag_chip_and_pronoun_override(cat_studio_driver)` (trong `test_cat_studio_flow.py`):
     - Nạp câu thoại anime Nhật `「この俺様に一体何の」` qua `cat_studio_driver.page_widget.load_subtitles_from_studio(...)`.
     - Dùng `QtDriver` kiểm tra trực tiếp trên QML Scene Graph:
       - `cat_studio_driver.is_subject_tag_visible() is True`
       - `cat_studio_driver.get_subject_tag_text() == "Ta ➔ Ngươi (俺様)"`
     - Đổi đại từ qua `cat_studio_driver.set_subject_pronoun("Tao - Mày")` và xác nhận `cat_studio_driver.get_subject_tag_text()` cập nhật tức thì trên QML thành `"Tao ➔ Mày (俺様)"`.
  2. `test_flow_sub_editor_vertical_alignment_and_newline_sanitization(sub_editor_driver)` (trong `test_sub_editor_flow.py`):
     - Nạp segment có ký tự xuống dòng thừa ở đầu `"\n\nEm cảm ơn ngài\n"` vào `sub_editor_driver.editor.load_segments(...)`.
     - Chọn dòng 0 qua `sub_editor_driver.select_row(0)`.
     - Xác nhận qua `QtDriver`:
       - `sub_editor_driver.get_table_cell_text(0, 4) == "Em cảm ơn ngài"` (không còn `\n` đầu dòng).
       - `sub_editor_driver.get_current_text() == "Em cảm ơn ngài"`.
       - `bool(sub_editor_driver.get_table_cell_alignment(0, 4) & int(Qt.AlignVCenter)) is True`.
  3. `test_flow_rescan_button_click_via_qt_driver_triggers_large_v3_and_vram_guard(main_window_driver, monkeypatch)` (trong `test_sub_editor_flow.py`):
     - Nạp 1 segment (không cần truyền sẵn `"id"`, chỉ có `"stt": 1, "start_ms": 1000, "end_ms": 3000, "text": "Câu cũ"`) vào `win.sub_editor`.
     - Khởi tạo `sub_page = SubEditorPage(driver, win.sub_editor)`, chọn dòng 0 (`sub_page.select_row(0)`).
     - Mock `ModelManager.is_installed` trả về `True` cho `"large-v3"`, bắt cấu hình khởi tạo `SingleSegmentScanWorker`, và dùng `sub_page.click_scan()` (`QtDriver.click` thật vào nút `btn_current_sub_scan`).
     - Xác nhận:
       - `scan_mode == "asr"` (nhờ đã sửa `BUG-SCAN-ID-001`), `model_size == "large-v3"`, `compute_type == "float16"`.
       - Khi giả lập callback hoàn tất `_on_segment_scan_finished(seg_id, "Câu mới từ large-v3")`, ô bảng tại dòng 0 cột 4 (`sub_page.get_table_cell_text(0, 4)`) cập nhật thành `"Câu mới từ large-v3"`.
  4. `test_flow_activity_log_view_filters_and_noise_suppression_via_qt_driver(main_window_driver)` (trong `test_sub_editor_flow.py`):
     - Dùng `QtDriver` tìm các widget `activity_source_filter`, `activity_clear_button`, `activity_log_text` trong `win.log_box`.
     - Bấm `driver.click("activity_clear_button", root=win.log_box)` để làm sạch log.
     - Đẩy qua `win.append_log` và `win._on_timing_log`:
       - Nhiễu kỹ thuật: `"llama_kv_cache_iswa: using full-size SWA cache"` và `"[MODEL_COMMIT] target=0"`
       - Log chuẩn: `"[CAT] Câu #1: Ngươi tìm ta đây rốt cuộc có chuyện gì?"`
       - Log từ timing worker: `win._on_timing_log("[ASR] VRAM đạt 75% (>65%) ➔ Tự động chuyển sang int8_float16.")`
     - Kiểm tra trên `activity_log_text.toPlainText()`:
       - Không chứa `"llama_kv_cache_iswa"`, không chứa `"[MODEL_COMMIT]"`, không bị nhân đôi `"[TIMING] [ASR]"`.
       - Hiển thị tiếng Việt UTF-8 rõ ràng (`"Ngươi tìm ta đây rốt cuộc có chuyện gì?"`).
       - Khi chọn bộ lọc `source_filter.setCurrentText("CAT")`, chỉ còn dòng `CAT`; khi chọn `"ASR"`, chỉ còn dòng `ASR`.

---

## 3. Lệnh Kiểm Chứng Tự Động (Verification Commands)

```powershell
# 1. Chạy toàn bộ Desktop GUI E2E Specs qua QtDriver (bao gồm 4 E2E specs mới)
.\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v

# 2. Chạy kiểm thử unit cho Rescan VRAM Guard, Subject Tag & Alignment
.\.venv\Scripts\python.exe -m pytest tests/core/test_rescan_vram_guard_and_log_compression.py tests/translation/test_subject_tag_and_gemma_prompt.py tests/ui/test_subeditor_alignment_and_leading_newline.py -v
```
