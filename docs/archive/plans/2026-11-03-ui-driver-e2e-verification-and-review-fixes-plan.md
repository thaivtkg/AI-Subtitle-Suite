# Kế Hoạch Khắc Phục Lỗi Review, Tối Ưu Hóa Cấu Hình RTX 3050 (4GB VRAM) Cho Anime Nhật & Kiểm Thử E2E Bằng `QtDriver`

- **Mã kế hoạch**: `PLAN-UI-DRIVER-E2E-VERIFICATION-001`
- **Ngày lập**: 2026-11-03
- **Phạm vi**:
  - **Phần A (Code Review Fixes & UI Driver E2E)**: Khắc phục 2 lỗi logic phát hiện qua Code Review (`BUG-SCAN-ID-001`, `BUG-LOG-PREFIX-002`), bổ sung `objectName` cho `ActivityLogView`, mở rộng POM (`CatStudioPage`, `SubEditorPage`) và viết E2E Specs chạy thật qua `QtDriver`.
  - **Phần B (RTX 3050 4GB VRAM & Japanese Anime ASR Optimization)**: Áp dụng cấu hình thực dụng `large-v3 + int8_float16` cho GPU ≤ 4GB VRAM và chuẩn hóa bộ tham số giải mã Faster-Whisper (`beam_size=5`, `best_of=5`, `patience=1.0`, `temperature=(0.0, 0.2, 0.4)`, `log_prob_threshold=-1.0`, `compression_ratio_threshold=2.4`, `no_speech_threshold=0.6`, `condition_on_previous_text=True` cho luồng Full/Batch ASR và `False` cho quét 1 câu ngắn, `min_silence_duration_ms=2000` khi bật VAD cho tiếng Nhật anime).
- **Nguyên tắc Ponytail**: Sửa tận gốc tại điểm dùng chung (`FasterWhisperService`, `SubtitleGenerationPanel`, `MainWindow`), giữ nguyên hợp đồng các test cũ (`TimingState` legacy defaults), diff nhỏ gọn nhất, kiểm chứng thực tế qua `QtDriver`.

---

## 1. Phân Tích Kỹ Thuật & Đối Chiếu Codebase Hiện Tại

### A. Kết quả Code Review trên Commit `ba44db4` & `b60b051`
1. **`[BUG-SCAN-ID-001]` Mất khớp `segment_id` khi bấm nút `🔍 Quét lại` (`btn_current_sub_scan`) trên UI**:
   - Tại `ui/SubEditor.py:1142`, `_on_current_editor_scan_requested()` phát `self.segment_scan_requested.emit(seg.get("id"), start_ms, end_ms)`.
   - Khi segment chưa có khóa `"id"` tường minh (hoặc `seg.get("id")` là `None`, chỉ có `"stt"`), `Signal(str, int, int)` ép `None` thành `""`. Sang `ui/Gui.py:1671`, `sid == str(segment_id)` trượt khớp khiến `has_sub` bị tính sai thành `False` (chạy nhầm `scan_mode="timing"` thay vì `"asr"`) và khi quét xong không cập nhật được câu trên bảng.
2. **`[BUG-LOG-PREFIX-002]` Nhân đôi tiền tố `[TIMING] [ASR]` trên Nhật ký hoạt động**:
   - `TimingBatchWorker` phát `[ASR] VRAM đạt...`, nhưng `ui/Gui.py:4169` (`_on_timing_log`) luôn nối cứng `f"[TIMING] {message}"` tạo thành `"[TIMING] [ASR] ..."`.
3. **`[GAP-UI-DRIVER-003]` Thiếu `objectName` trên `ActivityLogView` và thiếu E2E Spec bằng `QtDriver`**.

### B. Đối chiếu Đề xuất Cấu hình RTX 3050 Laptop (4GB VRAM) · Japanese Anime với Codebase
| Thông số đề xuất | Trạng thái hiện tại trong Codebase | Điểm lệch & Giải pháp kỹ thuật |
| :--- | :--- | :--- |
| **Model Size**: `large-v3` | `SubtitleGenerationPanel._populate_model_combo` (`ui/subtitle_generation_panel.py:442`) đang để `preferred="large-v3-turbo"`. | Đổi `preferred="large-v3"` nếu máy đã cài `large-v3` (giữ fallback an toàn nếu chưa cài). Trong `_resolve_rescan_model_and_compute` (`ui/Gui.py:1645`), luôn ưu tiên `"large-v3"`. |
| **Compute Type**: `int8_float16` trên GPU 4GB VRAM | - `ui/subtitle_generation_panel.py:533`: `if has_cuda and vram_gb >= 4: recommended = "float16"` (sai với RTX 3050 4GB vì `large-v3` FP16 tốn ~4.5GB VRAM!).<br>- `ui/Gui.py:1655`: `_resolve_rescan_model_and_compute` đang gán cứng `"float16"` cho mọi GPU.<br>- `faster_whisper_service.py:60`: Chỉ hạ xuống `int8_float16` khi VRAM đã dùng > 65%, chưa kiểm tra tổng VRAM `total_gb <= 4.5`. | 1. Tại `ui/subtitle_generation_panel.py:533`: Chỉ khuyên dùng `"float16"` khi `vram_gb >= 6`; với GPU `<= 4GB` (như RTX 3050 4GB), khuyên dùng `★ int8_float16 (Recommended)`.<br>2. Tại `faster_whisper_service.py:19` (`should_downgrade_to_int8_float16`) và `ui/Gui.py:1645` (`_resolve_rescan_model_and_compute`): Nếu `total_gb <= 4.5` (GPU 4GB) hoặc `used/total > 0.65`, chọn ngay `"int8_float16"` từ đầu mà không cần thử nạp `float16` gây tràn VRAM. |
| **Beam Size / Best Of / Patience**: `5` / `5` / `1.0` | `faster_whisper_service.py:150` mới truyền `"beam_size": 5`, thiếu `"best_of": 5` và `"patience": 1.0`. | Bổ sung `"best_of": 5` và `"patience": 1.0` vào `transcribe_options` trong `FasterWhisperService.transcribe_batch()`. |
| **Temperature**: `(0.0, 0.2, 0.4)` & **Log Prob Threshold**: `-1.0` | `faster_whisper_service.py:148-155` chưa truyền `temperature` (Faster-Whisper mặc định nhảy tới `0.6, 0.8, 1.0` dễ sinh ảo giác câu không có trong audio) và chưa truyền `log_prob_threshold: -1.0`. | Bổ sung `"temperature": (0.0, 0.2, 0.4)` và `"log_prob_threshold": -1.0` (cùng `"compression_ratio_threshold": 2.4`, `"no_speech_threshold": 0.6` đã có) vào `transcribe_options`. |
| **Condition on Previous Text**: `ON` (`True`) | `faster_whisper_service.py:154` đang khóa cứng `"condition_on_previous_text": False` cho mọi trường hợp! | Thêm trường `condition_on_previous_text: bool = True` vào `SubtitleGenerationRequest`. Mặc định `True` cho luồng nhận diện tập anime (`transcribe_batch` bảo toàn ngữ cảnh tên riêng/hội thoại nối tiếp). Riêng khi quét lại 1 câu đơn lẻ cực ngắn (`< 3000ms`), có thể truyền từ `request.condition_on_previous_text` (mặc định `True` theo đúng khuyến nghị). |
| **VAD Filter**: `ON` + `min_silence_duration_ms = 2000` (Anime) | `faster_whisper_service.py:166` truyền `request.min_silence_ms` (đang để 500ms ở `Gui.py:1709, 2007`), dễ cắt vụn khoảng ngắt tự nhiên của nhân vật anime. | Trong `FasterWhisperService.transcribe_batch()`, khi `request.language == "ja"` và `request.min_silence_ms == 500` (giá trị mặc định chưa tùy chỉnh), hoặc trong `_on_segment_scan_requested` / `_on_batch_segment_scan_requested` khi ngôn ngữ là `"ja"`, sử dụng `min_silence_ms = 2000` (vẫn giữ nguyên mặc định `500` ở `TimingState` để không làm gãy 30 unit test cũ của `test_subtitle_generation.py`). |
| **Language**: Cố định `Japanese (ja)` khi dự án là Anime Nhật | Khi user để `Auto Detect` trên `SubtitleGenerationPanel` (`ui/subtitle_generation_panel.py:843`), `_build_asr_request` truyền `language=None`. | Trong `_build_asr_request` và `_on_segment_scan_requested` / `_on_batch_segment_scan_requested`: Nếu combo đang để `Auto Detect` nhưng dự án đã xác định gốc Nhật (`_is_ja_origin` hoặc câu thoại có Kana), tự động khóa `language="ja"` thay vì để `None`. |

---

## 2. Chi Tiết Các Tác Vụ Triển Khai

### Task 1: Tối ưu `FasterWhisperService` & `SubtitleGenerationRequest` cho RTX 3050 4GB & Anime Nhật
- **File can thiệp**:
  - `core/subtitle_generation/subtitle_generation_request.py`
  - `core/subtitle_generation/faster_whisper_service.py`
- **Thay đổi**:
  1. Trong `SubtitleGenerationRequest` (`core/subtitle_generation/subtitle_generation_request.py:31`):
     Thêm trường cấu hình với giá trị mặc định chuẩn:
     ```python
     condition_on_previous_text: bool = True
     temperature: tuple = (0.0, 0.2, 0.4)
     ```
  2. Trong `should_downgrade_to_int8_float16(threshold: float = 0.65)` (`core/subtitle_generation/faster_whisper_service.py:19-30`):
     - Nếu `0 < total_gb <= 4.5` (GPU 4GB như RTX 3050 Laptop), trả về ngay `(True, ratio)` vì `large-v3` ở `float16` cần ~4.5GB VRAM, bắt buộc dùng `int8_float16` để không tràn bộ nhớ.
     - Nếu `total_gb > 4.5`, giữ cơ chế kiểm tra `ratio > threshold` (65%).
  3. Trong `FasterWhisperService.transcribe_batch()` (`core/subtitle_generation/faster_whisper_service.py:148-170`):
     Chuẩn hóa `transcribe_options` theo đúng bảng thông số khuyến nghị:
     ```python
     transcribe_options = {
         "language": request.language,
         "beam_size": 5,
         "best_of": 5,
         "patience": 1.0,
         "temperature": tuple(getattr(request, "temperature", (0.0, 0.2, 0.4))),
         "compression_ratio_threshold": 2.4,
         "log_prob_threshold": -1.0,
         "no_speech_threshold": 0.6,
         "condition_on_previous_text": bool(getattr(request, "condition_on_previous_text", True)),
         "word_timestamps": request.word_timestamps,
     }
     ```
     Và khi `request.use_vad` bật:
     ```python
     effective_silence_ms = (
         2000
         if (request.language == "ja" and request.min_silence_ms == 500)
         else request.min_silence_ms
     )
     transcribe_options["vad_filter"] = True
     transcribe_options["vad_parameters"] = {
         "min_silence_duration_ms": effective_silence_ms
     }
     ```

---

### Task 2: Khuyến nghị `int8_float16` cho GPU 4GB trên UI & Đồng bộ Luồng Quét lại (`ui/subtitle_generation_panel.py` & `ui/Gui.py`)
- **File can thiệp**:
  - `ui/subtitle_generation_panel.py` (dòng `530-540`)
  - `ui/Gui.py` (dòng `1645-1712`, `1990-2010`, `4169`)
  - `ui/SubEditor.py` (dòng `1130-1143`)
- **Thay đổi**:
  1. Trong `SubtitleGenerationPanel._populate_compute_combo()` (`ui/subtitle_generation_panel.py:533`):
     Đổi ngưỡng khuyến nghị `float16` từ `vram_gb >= 4` lên `vram_gb >= 6` để máy 4GB VRAM (RTX 3050 Laptop) luôn được gợi ý và chọn mặc định `★ int8_float16  (Recommended)`:
     ```python
     if has_cuda and vram_gb >= 6:
         recommended = "float16"
     elif has_cuda:
         recommended = "int8_float16"
     else:
         recommended = "int8"
     ```
  2. Trong `MainWindow._resolve_rescan_model_and_compute()` (`ui/Gui.py:1645-1656`):
     - Nếu `device == "cpu"` ➔ `"int8"`.
     - Nếu `device == "cuda"`: Kiểm tra `should_downgrade_to_int8_float16(0.65)`. Nếu trả về `True` (máy 4GB VRAM như RTX 3050 hoặc VRAM đang > 65%) ➔ trả về ngay `("large-v3", "int8_float16")`; ngược lại trả về `("large-v3", "float16")`.
     - Trong `_on_segment_scan_requested` và `_on_batch_segment_scan_requested`: Nếu `iso_lang == "ja"` và `settings.get("min_silence_ms", 500) == 500`, truyền `min_silence_ms=2000`.
  3. **Sửa `BUG-SCAN-ID-001` (`ui/SubEditor.py:1140-1143`)**:
     Trong `_on_current_editor_scan_requested()`, gán `seg_id = str(seg.get("id") or seg.get("stt") or (self.current_index + 1))` và `seg["id"] = seg_id` trước khi emit `self.segment_scan_requested.emit(seg_id, start_ms, end_ms)`.
  4. **Sửa `BUG-LOG-PREFIX-002` (`ui/Gui.py:4169`)**:
     Trong `_on_timing_log(self, message: str)`, không ghép thêm `[TIMING] ` nếu `message.lstrip().startswith("[")`.

---

### Task 3: Bổ sung `objectName` cho `ActivityLogView` & Mở rộng POM (`ui/activity_log.py`, `tests/gui/pages/`)
- **File can thiệp**:
  - `ui/activity_log.py` (dòng `253-308`)
  - `tests/gui/pages/cat_studio_page.py`
  - `tests/gui/pages/sub_editor_page.py`
- **Thay đổi**:
  1. Trong `ActivityLogView.__init__` (`ui/activity_log.py`):
     Gán `objectName` chuẩn cho 4 widget:
     - `self.level_filter.setObjectName("activity_level_filter")`
     - `self.source_filter.setObjectName("activity_source_filter")`
     - `self.clear_button.setObjectName("activity_clear_button")`
     - `self.text_edit.setObjectName("activity_log_text")`
  2. Trong `CatStudioPage` (`tests/gui/pages/cat_studio_page.py`):
     Thêm `LOC_SUBJECT_TAG_CHIP = "subjectTagChip"`, `LOC_SUBJECT_TAG_TEXT = "subjectTagText"`, `is_subject_tag_visible()`, `get_subject_tag_text()`, `set_subject_pronoun(pair)`.
  3. Trong `SubEditorPage` (`tests/gui/pages/sub_editor_page.py`):
     Thêm `get_table_cell_alignment(row: int, col: int = 4) -> int`.

---

### Task 4: Kiểm Thử E2E Toàn Diện Bằng `QtDriver` & Unit Test Cấu Hình RTX 3050
- **File can thiệp**:
  - `tests/gui/specs/test_cat_studio_flow.py`
  - `tests/gui/specs/test_sub_editor_flow.py`
  - `tests/core/test_rescan_vram_guard_and_log_compression.py`
- **Các kịch bản kiểm thử**:
  1. `test_rtx_3050_4gb_anime_ja_recommended_profile()` (trong `test_rescan_vram_guard_and_log_compression.py`):
     - Giả lập GPU RTX 3050 Laptop 4GB (`HardwareDetector.get_vram_usage` trả về `(1.2, 4.0)` — mới dùng 30% nhưng tổng VRAM là 4.0GB).
     - Xác nhận `should_downgrade_to_int8_float16()` trả về `True`, `_resolve_rescan_model_and_compute()` chọn `("large-v3", "int8_float16")`, và `FasterWhisperService.transcribe_batch()` truyền đúng bộ thông số chuẩn anime Nhật:
       - `beam_size == 5`, `best_of == 5`, `patience == 1.0`
       - `temperature == (0.0, 0.2, 0.4)`
       - `condition_on_previous_text is True`
       - `compression_ratio_threshold == 2.4`, `log_prob_threshold == -1.0`, `no_speech_threshold == 0.6`
       - `vad_filter is True`, `vad_parameters["min_silence_duration_ms"] == 2000`
       - `language == "ja"`
  2. `test_flow_cat_studio_subject_tag_chip_and_pronoun_override(cat_studio_driver)` (E2E `QtDriver` trong `test_cat_studio_flow.py`):
     - Kiểm tra QML `subjectTagChip` hiển thị `"Ta ➔ Ngươi (俺様)"` với câu `「この俺様に一体何の」` và đổi sang `"Tao ➔ Mày (俺様)"`.
  3. `test_flow_sub_editor_vertical_alignment_and_newline_sanitization(sub_editor_driver)` (E2E `QtDriver` trong `test_sub_editor_flow.py`):
     - Kiểm tra cắt `\n` đầu dòng và căn giữa dọc `Qt.AlignVCenter` trên `table_subtitles`.
  4. `test_flow_rescan_button_click_via_qt_driver_uses_rtx3050_profile(main_window_driver)` (E2E `QtDriver` trong `test_sub_editor_flow.py`):
     - Nạp segment không có khóa `"id"` sẵn, bấm nút `btn_current_sub_scan` thật qua `SubEditorPage.click_scan()`, xác nhận trên GPU 4GB máy khởi tạo `SegmentScanWorker` ở chế độ `"asr"` với `model_size="large-v3"`, `compute_type="int8_float16"`, `language="ja"`, `min_silence_ms=2000`, và cập nhật câu mới lên bảng sau khi hoàn tất.
  5. `test_flow_activity_log_view_filters_and_noise_suppression_via_qt_driver(main_window_driver)` (E2E `QtDriver` trong `test_sub_editor_flow.py`):
     - Dùng `QtDriver` tương tác với `activity_source_filter`, `activity_clear_button`, `activity_log_text` để xác nhận lọc riêng `CAT` / `ASR`, không bị nhân đôi `[TIMING] [ASR]`, và ẩn sạch log rác `llama_kv_cache_iswa` / `[MODEL_COMMIT]`.

---

## 3. Lệnh Kiểm Chứng Tự Động (Verification Commands)

```powershell
# 1. Chạy toàn bộ Desktop GUI E2E Specs qua QtDriver
.\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v

# 2. Chạy bộ kiểm thử RTX 3050 4GB Profile, VRAM Guard, Subject Tag & Subtitle Generation
.\.venv\Scripts\python.exe -m pytest tests/core/test_rescan_vram_guard_and_log_compression.py tests/translation/test_subject_tag_and_gemma_prompt.py tests/ui/test_subeditor_alignment_and_leading_newline.py tests/subtitle_generation/test_subtitle_generation.py -v
```
