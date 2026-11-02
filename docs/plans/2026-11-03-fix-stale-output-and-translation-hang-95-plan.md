# Kế hoạch Kỹ thuật: Khắc phục Lỗi Hiển thị Output Cũ & Treo Dịch ở 95%
**Mã kế hoạch:** `PLAN-CAT-PROGRESS-AND-OUTPUT-STABILITY-001`  
**Ngày lập:** 2026-11-03  
**Vai trò:** Principal QA Lead / Software Quality Architect  
**Đối tượng thực thi:** AI Developer  
**Tiêu chuẩn:** Tuân thủ triệt để nguyên tắc **Ponytail** (Diff tối thiểu, xử lý tận gốc tại code dùng chung, TDD 100% green, cô lập hoàn toàn môi trường test khỏi production).

---

## 1. Bản chất & Nguyên nhân Gốc rễ 2 Lỗi

### Lỗi 1: Giao diện hiển thị Output cũ từ thư mục Pytest
- **Hiện tượng:** Trên thẻ Pipeline Overview hiển thị đường dẫn: `Output: C:\Users\Kuroberus\AppData\Local\Temp\pytest-of-Kuroberus\pytest-273\test_softsub_chains_hardsub_wh0`.
- **Nguyên nhân gốc rễ:** 
  1. Trong [`tests/export/test_export_center_remediation.py`](file:///d:/ai-subtitle-suite/tests/export/test_export_center_remediation.py), các test case gán `win.page_export.out_edit.setText(str(tmp_path))`. Thao tác này kích hoạt tín hiệu `textChanged` $\rightarrow$ gọi [`_persist_canonical_setting("output_dir", cleaned)`](file:///d:/ai-subtitle-suite/ui/Gui.py#L2832) $\rightarrow$ ghi đè đường dẫn tạm của pytest vào tệp `%LOCALAPPDATA%\AI Subtitle Suite\settings.json` thật của người dùng.
  2. Tại [`ui/Gui.py:2791-2793`](file:///d:/ai-subtitle-suite/ui/Gui.py#L2791-L2793), logic kiểm tra thư mục tạm cũ:
     ```python
     is_stale_temp = "Temp" in saved_dir or saved_dir.startswith(tempfile.gettempdir())
     if not os.path.exists(saved_dir) and is_stale_temp:
         saved_dir = ""
     ```
     Điều kiện này **chỉ xóa nếu thư mục tạm KHÔNG CÒN TỒN TẠI**. Vì Windows Temp chưa xóa thư mục của pytest-273 nên `os.path.exists(saved_dir)` vẫn là `True`, dẫn tới việc app nạp lại đường dẫn rác của test vào giao diện chính.

---

### Lỗi 2: Dịch thuật AI bị treo cứng ở mốc 95% (0 từ • 0 ký tự)
- **Hiện tượng:** Huy hiệu trạng thái dừng ở `⚡ ĐANG DỊCH 95%`, hiển thị `0 từ • 0 ký tự` và thông báo `"Bản dịch sẽ xuất hiện trực tiếp ngay khi có token đầu tiên"`.
- **Nguyên nhân gốc rễ:**
  1. **Xung đột Prompt DeepSeek-R1:** Tại [`core/translation/core/prompt_builder.py:136`](file:///d:/ai-subtitle-suite/core/translation/core/prompt_builder.py#L136), khi dùng DeepSeek, template ép prefill mở: `<｜Assistant｜><think>\n`. Trong khi đó, system prompt yêu cầu non-thinking: `DO NOT use reasoning, thinking processes, or <think> tags. You are operating in non-thinking mode.` Do `<think>` bị mở dở dang, DeepSeek-R1 bị ép buộc suy luận hàng trăm token bên trong `<think>`.
  2. **Worker nuốt toàn bộ token khi đang think:** Tại [`core/translation/llm/worker.py:153-156`](file:///d:/ai-subtitle-suite/core/translation/llm/worker.py#L153-L156), khi `is_prefilled_think` và chưa có `</think>`, `display_text = ""` nên worker **hoàn toàn không emit signal `progress` nào** về UI.
  3. **Timer đứng khựng ở 95%:** Tại [`core/translation/controllers/translation_controller.py:114`](file:///d:/ai-subtitle-suite/core/translation/controllers/translation_controller.py#L114), hàm `_on_thinking_progress_tick()` chạy mỗi 250ms tăng dần từ 10% đến 95%. Khi đạt đúng 95%, nhánh `elif self._translation_progress < 95:` ngừng hoạt động. Vì model vẫn đang suy luận trong `<think>` hoặc bị nghẽn CPU, UI đứng im vĩnh viễn ở 95%.
  4. **Thiếu Watchdog Timeout:** Không có bộ đếm timeout cho tiến trình dịch đơn câu; nếu model C++ inference lâu hoặc cạn `max_tokens` bên trong `<think>`, hệ thống treo vĩnh viễn mà không tự phục hồi.

---

## 2. Kế hoạch Triển khai 4 Tác vụ Kỹ thuật

### Tác vụ 1: Vệ sinh Triệt để Thư mục Tạm & Cô lập Test khỏi Settings Thật
- **File can thiệp:** 
  - [`ui/Gui.py`](file:///d:/ai-subtitle-suite/ui/Gui.py) (dòng 2790-2795)
  - [`tests/export/test_export_center_remediation.py`](file:///d:/ai-subtitle-suite/tests/export/test_export_center_remediation.py)
  - [`%LOCALAPPDATA%\AI Subtitle Suite\settings.json`](file:///C:/Users/Kuroberus/AppData/Local/AI%20Subtitle%20Suite/settings.json)
- **Giải pháp kỹ thuật:**
  1. Trong `ui/Gui.py`: Đổi logic kiểm tra `is_stale_temp`: Bất kể thư mục có tồn tại hay không, nếu đường dẫn chứa `temp`, `pytest`, `tmp` hoặc nằm trong thư mục tạm hệ điều hành thì **luôn luôn reset về rỗng** `""` khi khởi động app:
     ```python
     is_stale_temp = (
         "temp" in saved_dir.lower()
         or "pytest" in saved_dir.lower()
         or saved_dir.startswith(tempfile.gettempdir())
     )
     if is_stale_temp or not os.path.exists(saved_dir):
         saved_dir = ""
     ```
  2. Trong `test_export_center_remediation.py`: Patch `_persist_canonical_setting` để unit test không bao giờ ghi đè vào file `settings.json` thật của máy người dùng.
  3. Dọn sạch giá trị `"output_dir": ""` trong `settings.json` hiện hành.

---

### Tác vụ 2: Đóng Khối `<think>` cho Chế độ Non-Thinking của DeepSeek
- **File can thiệp:** [`core/translation/core/prompt_builder.py`](file:///d:/ai-subtitle-suite/core/translation/core/prompt_builder.py) (dòng 134-137)
- **Giải pháp kỹ thuật:**
  System prompt đã chỉ định: `CRITICAL INSTRUCTION: DO NOT use reasoning, thinking processes, or <think> tags. You are operating in non-thinking mode.`  
  Để DeepSeek-R1 tuân thủ và xuất bản dịch ngay lập tức (không tốn 30-60s suy nghĩ vô ích), format assistant phải đóng ngay thẻ think:
  ```python
  elif "deepseek" in family:
      return (
          f"{system_prompt}\n\n<｜User｜>{user_prompt}<｜Assistant｜><think>\n</think>\n"
      )
  ```
  Nhờ đó, DeepSeek-R1 sẽ bỏ qua giai đoạn suy nghĩ lan man và stream trực tiếp bản dịch tiếng Việt ngay từ token đầu tiên.

---

### Tác vụ 3: Dải Tiệm Cận Mềm $95\% \rightarrow 98\%$ & Watchdog Timeout Tự Phục Hồi
- **File can thiệp:** [`core/translation/controllers/translation_controller.py`](file:///d:/ai-subtitle-suite/core/translation/controllers/translation_controller.py) (dòng 114-121 và `translateSubtitle`)
- **Giải pháp kỹ thuật:**
  1. Trong `_on_thinking_progress_tick()`: Bổ sung dải bò siêu chậm $95\% \rightarrow 98\%$ (mỗi 3 giây tăng 1%) để giao diện luôn có cảm giác sống và đang xử lý, không bao giờ bị dừng cứng ngắc ở một con số:
     ```python
     elif self._translation_progress < 98:
         if getattr(self, "_progress_tick_count", 0) % 12 == 0:
             self._translation_progress = min(98, self._translation_progress + 1)
     ```
  2. Bổ sung Watchdog Timeout trong `TranslationController`: Đặt `QTimer.singleShot(90000, self._check_translation_timeout)`. Nếu sau 90 giây mà worker vẫn chưa trả về kết quả hoặc bị đơ C++, tự động hủy worker an toàn (`cancelTranslation()`), chuyển trạng thái về `ERROR` và thông báo `"Thời gian suy luận vượt quá 90s. Vui lòng kiểm tra tải mô hình hoặc cấu hình GPU"`.

---

### Tác vụ 4: Kiểm thử TDD Bảo vệ
- **File can thiệp:** `tests/translation/test_cat_progress_timeout_remediation.py`
- **Kịch bản kiểm thử:**
  1. Test khởi động GUI không nạp lại đường dẫn chứa `pytest` hoặc `Temp` vào `out_input`.
  2. Test DeepSeek prompt builder tạo thẻ đóng `<think>\n</think>\n`.
  3. Test progress timer tiếp tục bò động qua mốc 95% lên đến 98%.
  4. Test watchdog timeout tự động giải phóng UI khi worker không phản hồi.

---

## 3. Tiêu chí Nghiệm thu (Acceptance Criteria)
- `Pipeline Overview` hiển thị `Output: Default` hoặc thư mục dự án chuẩn, không bao giờ xuất hiện chuỗi `pytest-of-Kuroberus`.
- Khi bấm Dịch, model phản hồi token dịch ngay lập tức mà không bị giữ trong `<think>`.
- Huy hiệu tiến trình không bao giờ bị đóng băng cố định ở 95%.
