# Kế hoạch Kỹ thuật: Nâng cấp Quét lại (Large-v3 + Float16), Tự động Hạ cấp VRAM (>65%) & Tinh gọn Hệ thống Log

> **Mã Kế hoạch:** `PLAN-RESCAN-LARGEV3-VRAM-GUARD-AND-LOG-COMPRESSION-001`  
> **Người lập:** Senior QA Lead / Software Quality Architect  
> **Tiêu chuẩn Kỹ thuật:** Ponytail Senior Dev Mode (Xử lý triệt để tại tầng dùng chung, diff tối thiểu, TDD 100% Green, không sinh boilerplate).  
> **Thời gian:** 2026-11-03  
> **Trạng thái:** Sẵn sàng chuyển giao cho Developer triển khai  

---

## 1. Nghiệm thu Báo cáo Developer & Bối cảnh

### 1.1. Nghiệm thu Kế hoạch `PLAN-CAT-SUBJECT-TAG-AND-GEMMA-ENHANCEMENT-001`
- Developer đã hoàn tất xuất sắc toàn bộ 5 tác vụ (Commit [`b60b051`](https://github.com/thaivtkg/AI-Subtitle-Suite/commit/b60b051)):
  - Nhận diện chủ ngữ & khẩu khí anime tự động (`detect_japanese_subject_pronoun`) trong [`core/translation/core/context_analyzer.py`](file:///d:/ai-subtitle-suite/core/translation/core/context_analyzer.py).
  - Quản lý trạng thái `currentSubjectTag` và `setSubjectPronoun` trong [`core/translation/controllers/translation_controller.py`](file:///d:/ai-subtitle-suite/core/translation/controllers/translation_controller.py).
  - Hiển thị Thẻ Chủ Ngữ `👑 Chủ ngữ: Ta ➔ Ngươi` màu Tím Sapphire và menu chọn nhanh trên [`ui/qml_translation/components/TranslationWorkspace.qml`](file:///d:/ai-subtitle-suite/ui/qml_translation/components/TranslationWorkspace.qml).
  - Nâng cấp Prompt TranslateGemma & quy tắc hội thoại Anime trong [`core/translation/core/prompt_builder.py`](file:///d:/ai-subtitle-suite/core/translation/core/prompt_builder.py).
  - Toàn bộ 34/34 bài kiểm thử TDD và E2E liên quan đạt 100% Green.
- **Xác nhận nghiệm thu:** ĐẠT YÊU CẦU.

---

## 2. Phân tích Kỹ thuật 2 Yêu cầu Mới

### 2.1. Yêu cầu 1: Nâng cấp Quét lại lên `large-v3` + `float16` & Tự động chuyển sang `int8_float16` khi VRAM > 65%
- **Hiện trạng & Điểm nghẽn:**
  1. Tại [`ui/Gui.py:1690-1691`](file:///d:/ai-subtitle-suite/ui/Gui.py#L1690-L1691) (`_on_segment_scan_requested`) và [`ui/Gui.py:1984-1985`](file:///d:/ai-subtitle-suite/ui/Gui.py#L1984-L1985) (`_on_batch_segment_scan_requested`), khi người dùng bấm **Quét lại (Rescan)**, hệ thống đang lấy cấu hình từ `_timing_settings()` với fallback `"large-v3-turbo"` và `"int8"`.
  2. Trong anime tiếng Nhật (giọng cường điệu, nuốt âm, nhạc nền lớn), `int8` hoặc model nhỏ dễ nhận dạng sai. Cần ưu tiên **`large-v3` + `float16`** khi quét lại để đạt độ chính xác tối đa.
  3. Tại [`core/subtitle_generation/faster_whisper_service.py:36-60`](file:///d:/ai-subtitle-suite/core/subtitle_generation/faster_whisper_service.py#L36-L60) và [`workers/TimingBatchWorker.py:102-115`](file:///d:/ai-subtitle-suite/workers/TimingBatchWorker.py#L102-L115), khi đang gen phụ đề bằng `float16`, hệ thống chưa có cơ chế giám sát VRAM động để tự động hạ xuống `int8_float16` khi mức chiếm dụng VRAM vượt quá **65%**.

### 2.2. Yêu cầu 2: Tách biệt và Rút gọn Nhật ký Hoạt động (Log Compression & Isolation)
- **Hiện trạng & Điểm nghẽn:**
  1. Tại [`ui/Gui.py:725-731`](file:///d:/ai-subtitle-suite/ui/Gui.py#L725-L731), `sys.stdout` được chuyển hướng toàn cục vào `append_log`.
  2. Mỗi khi dịch 1 câu, các hàm debug nội bộ dùng `print(..., !a)` bắn ra 7-8 dòng log dài dòng kèm chuỗi escape Unicode (`\u0110\u1ebfn t\u1edb \u0111\xe2y...`):
     - [`core/translation/models/subtitle.py:210-230`](file:///d:/ai-subtitle-suite/core/translation/models/subtitle.py#L210-L230): `[MODEL_COMMIT]`, `[MODEL_AFTER]`
     - [`core/translation/controllers/translation_controller.py:671-678, 710-717`](file:///d:/ai-subtitle-suite/core/translation/controllers/translation_controller.py#L671-L717): `[TRANSLATION_CALLBACK]`, `[TRANSLATION_CALLBACK_AFTER]`
     - [`core/translation/llm/worker.py:168-174`](file:///d:/ai-subtitle-suite/core/translation/llm/worker.py#L168-L174): `[TRANSLATION_FINISH] ... clean_text={final_clean!a}`
  3. Tại [`core/translation/controllers/project_controller.py:852`](file:///d:/ai-subtitle-suite/core/translation/controllers/project_controller.py#L852), timer autosave in lặp lại `[PROJECT_SAVE] Saving 0 subtitles to project.aisrt` mỗi phút.
  4. Tại [`ui/activity_log.py:32-50`](file:///d:/ai-subtitle-suite/ui/activity_log.py#L32-L50), chưa có định danh nguồn `[CAT]` / `[ASR]`, khiến mọi log bị gộp chung vào `INFO SYSTEM` và đan xen hỗn loạn với log nhận diện phụ đề.

---

## 3. Các Tác vụ Kỹ thuật Triển khai (Developer Action Items)

### Tác vụ 1: Nâng cấp Cấu hình Mặc định của Quét lại (Rescan) lên `large-v3` và `float16`
- **Vị trí can thiệp:** [`ui/Gui.py:1690-1691`](file:///d:/ai-subtitle-suite/ui/Gui.py#L1690-L1691) và [`ui/Gui.py:1984-1985`](file:///d:/ai-subtitle-suite/ui/Gui.py#L1984-L1985)
- **Nội dung thực hiện:**
  - Trong `_on_segment_scan_requested` và `_on_batch_segment_scan_requested`:
    - Thiết lập model ưu tiên cho tác vụ Quét lại là `"large-v3"` (nếu model `"large-v3"` đã tải trên máy, ngược lại fallback về model đang chọn để không gây lỗi thiếu model).
    - Thiết lập `compute_type = "float16"` (nếu thiết bị là `"cuda"`, fallback `"int8"` nếu là `"cpu"`).

### Tác vụ 2: Cơ chế Giám sát VRAM Thời gian thực (> 65%) & Tự động Chuyển sang `int8_float16`
- **Vị trí can thiệp:**
  - [`core/subtitle_generation/faster_whisper_service.py`](file:///d:/ai-subtitle-suite/core/subtitle_generation/faster_whisper_service.py)
  - [`workers/TimingBatchWorker.py`](file:///d:/ai-subtitle-suite/workers/TimingBatchWorker.py)
- **Nội dung thực hiện:**
  1. Bổ sung hàm kiểm tra áp lực VRAM `should_downgrade_to_int8_float16(threshold: float = 0.65) -> tuple[bool, float]` sử dụng `HardwareDetector.get_vram_usage()` (truy vấn `nvcuda.dll` siêu tốc `< 0.05ms`):
     - Tính `ratio = used_gb / total_gb` (khi `total_gb > 0`).
     - Trả về `(ratio > threshold, ratio)`.
  2. **Trong `FasterWhisperService` (`load_model` và `transcribe_batch`):**
     - Trước khi nạp model hoặc trước khi chạy mỗi batch trong quá trình gen: Nếu `compute_type == "float16"` và `should_downgrade_to_int8_float16(0.65)` là `True`:
       - Tự động chuyển `compute_type` sang `"int8_float16"`.
       - Nếu model `"float16"` đang nạp trong VRAM, gọi `unload_model()` (kèm `gc.collect()` và `torch.cuda.empty_cache()`) rồi nạp lại với `"int8_float16"`.
       - In đúng 1 dòng log ngắn gọn: `print(f"[ASR] VRAM đạt {ratio*100:.0f}% (>65%) ➔ Tự động chuyển sang int8_float16.", flush=True)`.
     - Bắt thêm ngoại lệ `RuntimeError` chứa `"out of memory"` trong `transcribe_batch`: nếu đang ở `"float16"`, tự động hạ xuống `"int8_float16"`, nạp lại model và chạy lại batch đó.
  3. **Trong `TimingBatchWorker.run()`:**
     - Trước khi khởi tạo `WhisperModel` và trong vòng lặp trượt cửa sổ thời gian (`while len(all_final_segments) < ...`):
       - Kiểm tra nếu `compute_type == "float16"` và VRAM vượt **65%**:
         - Giải phóng model `float16` hiện tại, khởi tạo lại `WhisperModel` với `compute_type = "int8_float16"`.
         - Phát tín hiệu `self.effective_compute_signal.emit("int8_float16")` để UI cập nhật tức thì.
         - Ghi log: `self.log_signal.emit(f"[ASR] VRAM đạt {ratio*100:.0f}% (>65%) ➔ Tự động chuyển sang int8_float16.")`.

### Tác vụ 3: Rút gọn & Tách biệt Nhật ký Hoạt động (`[CAT]` vs `[ASR]`)
- **Vị trí can thiệp:**
  - [`core/translation/models/subtitle.py:210-230`](file:///d:/ai-subtitle-suite/core/translation/models/subtitle.py#L210-L230)
  - [`core/translation/controllers/translation_controller.py:671-678, 710-717`](file:///d:/ai-subtitle-suite/core/translation/controllers/translation_controller.py#L671-L717)
  - [`core/translation/llm/worker.py:168-174`](file:///d:/ai-subtitle-suite/core/translation/llm/worker.py#L168-L174)
  - [`core/translation/controllers/project_controller.py:852, 935`](file:///d:/ai-subtitle-suite/core/translation/controllers/project_controller.py#L852)
  - [`ui/activity_log.py:32-55`](file:///d:/ai-subtitle-suite/ui/activity_log.py#L32-L55)
  - [`ui/Gui.py:1632`](file:///d:/ai-subtitle-suite/ui/Gui.py#L1632)
- **Nội dung thực hiện:**
  1. **Xóa bỏ hoàn toàn các log trạng thái trung gian dư thừa:**
     - Xóa `print("[MODEL_COMMIT] ...")` và `print("[MODEL_AFTER] ...")` trong `subtitle.py`.
     - Xóa `print("[TRANSLATION_CALLBACK] ...")` và `print("[TRANSLATION_CALLBACK_AFTER] ...")` trong `translation_controller.py`.
  2. **Chuẩn hóa 1 dòng log dịch thuật duy nhất, hiển thị tiếng Việt trực tiếp (bỏ `!a`):**
     - Trong `worker.py:168`, thay bằng:
       `print(f"[CAT] Câu #{self.target_index + 1}: {final_clean}", flush=True)`
  3. **Chặn spam log lưu dự án rỗng:**
     - Trong `project_controller.py:852`, chỉ in log khi `len(clean_subtitles) > 0`:
       `if len(clean_subtitles) > 0: print(f"[PROJECT] Đã lưu {len(clean_subtitles)} câu vào {os.path.basename(file_path)}")`
  4. **Định danh nguồn `[CAT]` và `[ASR]` trên UI Activity Log & Lọc rác C++:**
     - Trong `ui/activity_log.py`: Thêm `"CAT": "CAT"`, `"DỊCH": "CAT"`, `"ASR": "ASR"`, `"PROJECT": "PROJECT"` vào `_SOURCE_ALIASES` và `_SOURCE_COLORS` để người dùng có thể lọc riêng log `CAT` hoặc `ASR` trên combobox nguồn log.
     - Trong `ui/Gui.py` (`append_log`): Bỏ qua các dòng log kỹ thuật cấp thấp từ `llama.cpp` (`llama_kv_cache`, `ggml_`, `llama_model_loader`) để không làm bẩn bảng nhật ký của người dùng.

### Tác vụ 4: Bộ Kiểm thử TDD Bảo vệ Tự động
- **Vị trí file mới:** `tests/core/test_rescan_vram_guard_and_log_compression.py`
- **Các ca kiểm thử bắt buộc:**
  1. `test_rescan_uses_large_v3_and_float16_by_default()`: Kiểm tra `_on_segment_scan_requested` khởi tạo `SubtitleGenerationRequest` với `model_size="large-v3"` và `compute_type="float16"` khi có GPU.
  2. `test_faster_whisper_auto_downgrades_to_int8_float16_when_vram_exceeds_65_percent()`: Giả lập `HardwareDetector.get_vram_usage()` trả về `(4.2, 6.0)` (`70% > 65%`), xác minh `FasterWhisperService` tự động chuyển từ `"float16"` sang `"int8_float16"` và reload model.
  3. `test_timing_batch_worker_downgrades_mid_generation_on_high_vram()`: Giả lập VRAM tăng lên `> 65%` giữa các bước trượt cửa sổ trong `TimingBatchWorker`, xác minh worker chuyển sang `"int8_float16"` và phát `effective_compute_signal`.
  4. `test_translation_log_is_concise_and_utf8_readable()`: Kiểm tra khi dịch xong 1 câu, không còn xuất hiện `[MODEL_COMMIT]`, `[MODEL_AFTER]`, `[TRANSLATION_CALLBACK]` hay chuỗi escape `\u0110`, chỉ xuất hiện 1 dòng `[CAT] Câu #...` ngắn gọn.
  5. `test_project_save_suppresses_zero_subtitle_log()`: Kiểm tra khi lưu dự án có `0` câu phụ đề, không in dòng `[PROJECT_SAVE] Saving 0 subtitles` ra stdout.

---

## 4. Tiêu chí Nghiệm thu (Definition of Done - DoD)

1. **Quét lại chuẩn xác:** Bấm nút Quét lại (đơn hoặc hàng loạt) tự động sử dụng `large-v3` + `float16`.
2. **Bảo vệ VRAM tự động (>65%):** Ngay khi VRAM vượt ngưỡng 65% trước hoặc trong quá trình gen, hệ thống tự động hạ cấp sang `int8_float16` mượt mà, không văng lỗi OOM.
3. **Log ngắn gọn, tách biệt:**
   - Không còn các dòng `[MODEL_COMMIT]`, `[MODEL_AFTER]`, `[TRANSLATION_CALLBACK]` hay mã Unicode `\u...`.
   - Không còn dòng `Saving 0 subtitles to project.aisrt`.
   - Mỗi câu dịch chỉ in đúng 1 dòng `[CAT] Câu #X: ...`, tách biệt rõ với nhãn `[ASR]` / `[TIMING]`.
4. **100% Green Test Suite:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/core/test_rescan_vram_guard_and_log_compression.py tests/ui/test_manual_timing_creation.py -v
   ```
