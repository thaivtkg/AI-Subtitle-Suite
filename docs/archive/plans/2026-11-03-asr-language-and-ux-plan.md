# Kế hoạch Triển khai: Chuẩn hóa Ngôn ngữ ASR Nhật Bản, Triệt tiêu Tự động Đẩy Sub sang Tab Dịch & UX Mở Dự án Gần đây (PLAN-ASR-LANG-UX-001)

> **Dành cho Developer thực thi:** BẮT BUỘC thực hiện từng tác vụ tuần tự theo chuẩn Test-Driven Development (TDD). Các bước sử dụng cú pháp checkbox (`- [ ]`) để theo dõi tiến độ. Tuyệt đối không nhảy cóc các bước kiểm thử. Không tự ý thêm bớt các tính năng nằm ngoài phạm vi tài liệu này.

**Mục tiêu:**
1. Khắc phục triệt để lỗi từ lạ/ảo giác (như `"Diyorlar."`) khi nhận diện ASR video tiếng Nhật: chuẩn hóa mã ngôn ngữ chuẩn ISO-639-1 (`"ja"`), bổ sung `initial_prompt` hội thoại tiếng Nhật (các từ cảm thán ngắn 1-4 âm tiết như *Hai, Dewa, Un, Sō, Chigau, Yatta, Yosh, Ano, Eto, Iku, Miru, Suru...*), và kích hoạt bộ lọc ảo giác trong `SegmentScanWorker`.
2. Chấm dứt hoàn toàn hiện tượng tự ý đẩy câu vừa gen/quét hoặc các câu đang chọn sang Tab Dịch khi người dùng chưa có thao tác chủ động yêu cầu.
3. Cải tiến UX Dashboard Recent Projects: Cho phép click vào bất kỳ đâu trên thẻ/dòng dự án gần đây (tên, đường dẫn, icon) để mở dự án ngay lập tức thay vì chỉ bấm nút "Mở".
4. Dọn sạch dữ liệu ảo giác câu #21 trong tệp `JMSZ_timing.srt`.

**Kiến trúc:**
1. `core/subtitle_generation/language_utils.py`: Bộ chuẩn hóa mã ngôn ngữ ISO-639-1 (`normalize_to_iso_code`) và kho từ điển mồi `get_initial_prompt_for_language(lang_code)`.
2. `workers/SegmentScanWorker.py`: Tích hợp `SubtitleGenerationValidator.validate()` vào cả `SegmentScanWorker` và `BatchSegmentScanWorker`.
3. `core/subtitle_generation/generation_validator.py`: Thêm bộ lọc ngôn ngữ bất đồng nhất (Latin text rejection when project language is Japanese).
4. `ui/Gui.py`: Loại bỏ các điểm tự ý gán `_pending_translation_indices` trong `_on_batch_scan_requested`, `_on_timing_artifact_ready`, và loại bỏ fallback cưỡng ép nạp phụ đề trong `switch_page(8)`.
5. `ui/pages/dashboard_page.py`: Gán `setCursor(Qt.PointingHandCursor)` và `mousePressEvent` cho card dòng dự án gần đây.

---

## Các ràng buộc toàn cục (Global Constraints)
* **Nguyên tắc Chủ quyền Người dùng (Explicit User Action Only):** Tuyệt đối KHÔNG tự động chuyển bất kỳ phân đoạn phụ đề nào sang Tab Dịch thuật ngoại trừ khi người dùng chủ động kích hoạt lệnh từ menu/nút "Chuyển sang Dịch" (`_on_send_selected_to_translation`).
* **Chuẩn hóa Ngôn ngữ ASR Tuyệt đối:** Faster-Whisper BẮT BUỘC nhận mã ISO-639-1 2 ký tự (ví dụ: `"ja"` thay vì `"Japanese"`, `"vi"` thay vì `"Vietnamese"`). Nếu không thể xác định, phải dùng `None` (để Whisper tự dò), không bao giờ truyền tên tiếng Anh đầy đủ.
* **Bảo tồn Tương tác Xóa (Delete Isolation):** Khi click vào nút xóa dự án `btn_remove` ("✕"), sự kiện mở dự án KHÔNG được phép kích hoạt.
* **Zero Regression:** Toàn bộ 84 test specs hiện hành của hệ thống phải duy trì trạng thái 100% Green.

---

## Cấu trúc các tác vụ (Tasks Breakdown)

### Tác vụ 1: Chuẩn hóa Mã Ngôn ngữ ISO-639-1 & Hội thoại Mồi (Initial Prompt) cho Whisper ASR
**Files:**
* Tạo mới: `core/subtitle_generation/language_utils.py`
* Sửa đổi: `ui/Gui.py:1665-1688, 1965-1973`
* Kiểm thử: `tests/subtitle_generation/test_language_code_normalization.py`

- [x] **Bước 1.1: Viết test thất bại kiểm tra chuẩn hóa mã ngôn ngữ và initial prompt**
  Tạo `tests/subtitle_generation/test_language_code_normalization.py` kiểm tra:
  - `normalize_to_iso_code("Japanese") == "ja"`
  - `normalize_to_iso_code("ja") == "ja"`
  - `normalize_to_iso_code("Vietnamese") == "vi"`
  - `normalize_to_iso_code("Auto Detect") is None`
  - `get_initial_prompt_for_language("ja")` chứa các từ cảm thán thông dụng: `はい`, `うん`, `そう`, `あの`, `えっと`, `よし`, `では`, `違う`.
- [x] **Bước 1.2: Chạy test để xác nhận test thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/subtitle_generation/test_language_code_normalization.py -v`.
- [x] **Bước 1.3: Triển khai `core/subtitle_generation/language_utils.py`**
  ```python
  from typing import Optional

  _LANGUAGE_MAP = {
      "japanese": "ja",
      "english": "en",
      "vietnamese": "vi",
      "korean": "ko",
      "chinese": "zh",
      "ja": "ja",
      "en": "en",
      "vi": "vi",
      "ko": "ko",
      "zh": "zh",
  }

  _INITIAL_PROMPTS = {
      "ja": "こんにちは。はい、そうですね。うん、あの、ええと、よし、では、違う、わかった、なるほど。",
  }

  def normalize_to_iso_code(lang: Optional[str]) -> Optional[str]:
      if not lang or lang.strip().lower() in ("auto detect", "none", ""):
          return None
      return _LANGUAGE_MAP.get(lang.strip().lower(), lang.strip().lower())

  def get_initial_prompt_for_language(lang_code: Optional[str]) -> str:
      if not lang_code:
          return ""
      return _INITIAL_PROMPTS.get(lang_code.lower(), "")
  ```
- [x] **Bước 1.4: Cập nhật `ui/Gui.py` áp dụng chuẩn hóa mã ngôn ngữ**
  - Tại `_on_segment_scan_requested` (dòng 1665-1688):
    Kế thừa ngôn ngữ từ project controller hoặc translation controller, sau đó gọi `scan_lang = normalize_to_iso_code(scan_lang)`.
    Nếu `scan_lang == "ja"` và không có `prompt_context`: gán `prompt_context = get_initial_prompt_for_language("ja")`.
  - Tại `_on_batch_scan_requested` (dòng 1968-1973):
    Chuẩn hóa `language=normalize_to_iso_code(settings.get("language", None))`.
- [x] **Bước 1.5: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/subtitle_generation/test_language_code_normalization.py -v`.
- [x] **Bước 1.6: Commit mã nguồn Tác vụ 1**
  `git commit -m "fix(asr): normalize language codes to ISO-639-1 and inject Japanese initial prompt (PLAN-ASR-LANG-UX-001)"`

---

### Tác vụ 2: Tích hợp `SubtitleGenerationValidator` vào Workers & Lọc Ảo giác Latinh trong Video Tiếng Nhật
**Files:**
* Sửa đổi: `core/subtitle_generation/generation_validator.py:20-52`
* Sửa đổi: `workers/SegmentScanWorker.py:80-86, 155-162`
* Kiểm thử: `tests/subtitle_generation/test_segment_scan_hallucination_filter.py`

- [x] **Bước 2.1: Viết test thất bại cho bộ lọc ảo giác của SegmentScanWorker**
  Tạo `tests/subtitle_generation/test_segment_scan_hallucination_filter.py`:
  - Kiểm tra kết quả chứa `"Diyorlar."` hoặc `"thank you for watching"` bị loại bỏ.
  - Kiểm tra đối với ngôn ngữ tiếng Nhật (`"ja"`): từ ảo giác chỉ gồm ký tự Latinh (không chứa Kana/Kanji) trên đoạn âm thanh ngắn (< 3s) bị đánh dấu rỗng hoặc `[Không nhận diện được giọng nói]`.
- [x] **Bước 2.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/subtitle_generation/test_segment_scan_hallucination_filter.py -v`.
- [x] **Bước 2.3: Nâng cấp `generation_validator.py` và tích hợp vào `SegmentScanWorker.py`**
  - Trong `generation_validator.py`: Thêm phương thức `filter_inconsistent_language(text: str, expected_lang: str) -> str`. Nếu `expected_lang == "ja"` và văn bản chỉ có chữ cái Latin không thuộc danh sách cho phép (như mã hiệu), loại bỏ chuỗi.
  - Trong `SegmentScanWorker.py` (dòng 80-86) & `BatchSegmentScanWorker.py` (dòng 155-162):
    Gọi `valid_segs = SubtitleGenerationValidator.validate(result.segments, self.start_ms, self.end_ms)`.
    Lấy `text = " ".join([seg.text.strip() for seg in valid_segs])`.
    Nếu rỗng, trả về `"[Không nhận diện được giọng nói]"`.
- [x] **Bước 2.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/subtitle_generation/test_segment_scan_hallucination_filter.py -v`.
- [x] **Bước 2.5: Commit mã nguồn Tác vụ 2**
  `git commit -m "fix(asr): integrate hallucination validation and language consistency check into segment scan workers (PLAN-ASR-LANG-UX-001)"`

---

### Tác vụ 3: Triệt tiêu Hoàn toàn Hành vi Tự động Đẩy Phụ đề sang Tab Dịch thuật
**Files:**
* Sửa đổi: `ui/Gui.py:1925, 2548-2553, 3821-3825`
* Kiểm thử: `tests/ui/test_translation_transfer_isolation.py`

- [x] **Bước 3.1: Viết test thất bại kiểm tra tính cô lập khi chuyển trang Dịch**
  Tạo `tests/ui/test_translation_transfer_isolation.py`:
  - Thiết lập `Gui` với nhiều phân đoạn phụ đề được chọn (`sub_editor.selected_rows = [0, 1, 2]`).
  - Gọi `gui.switch_page(8)`.
  - Xác nhận: `page_translation.load_subtitles_from_studio` KHÔNG được tự động gọi nếu `_pending_translation_indices` rỗng.
  - Xác nhận: Sau khi quét Batch Scan âm thanh hoặc sau khi load file Timing Artifact, `_pending_translation_indices` vẫn là danh sách rỗng `[]`.
- [x] **Bước 3.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_translation_transfer_isolation.py -v`.
- [x] **Bước 3.3: Loại bỏ các điểm tự ý nạp phụ đề trong `ui/Gui.py`**
  - Xóa dòng 1925 trong `_on_batch_scan_requested`: `self._pending_translation_indices = list(selected_indices)` -> BỎ.
  - Xóa các dòng 3821-3824 trong `_on_timing_artifact_ready`: Bỏ việc tự động gán `_pending_translation_indices`.
  - Trong `switch_page(8)` (dòng 2548-2553):
    Xóa nhánh:
    ```python
    else:
        sel = self.sub_editor._get_selected_source_indices() if hasattr(self.sub_editor, "_get_selected_source_indices") else []
        if len(sel) > 1:
            target_indices = sel
    ```
    Chỉ giữ nguyên logic nạp khi `target_indices = list(self._pending_translation_indices)` tồn tại do người dùng bấm lệnh explicitly.
- [x] **Bước 3.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_translation_transfer_isolation.py -v`.
- [x] **Bước 3.5: Commit mã nguồn Tác vụ 3**
  `git commit -m "fix(ui): eliminate rogue auto-transfer of subtitles on tab switch and batch scan (PLAN-ASR-LANG-UX-001)"`

---

### Tác vụ 4: Cải tiến UX Dashboard Recent Projects - Click Toàn bộ Hàng Thẻ để Mở Dự án
**Files:**
* Sửa đổi: `ui/pages/dashboard_page.py:297-350`
* Kiểm thử: `tests/ui/test_recent_projects_ui.py`

- [x] **Bước 4.1: Viết test thất bại kiểm tra sự kiện click vào thẻ dự án gần đây**
  Trong `tests/ui/test_recent_projects_ui.py`, thêm test `test_dashboard_recent_projects_row_click_emits_open`:
  - Mô phỏng click chuột trái vào widget `row` của một dự án gần đây.
  - Xác nhận `open_project_requested` phát tín hiệu với đúng đường dẫn dự án.
  - Kiểm tra `row.cursor().shape() == Qt.PointingHandCursor`.
  - Kiểm tra bấm nút `btn_remove` ("✕") phát tín hiệu xóa nhưng KHÔNG phát tín hiệu `open_project_requested`.
- [x] **Bước 4.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_recent_projects_ui.py -k "test_dashboard_recent_projects_row_click" -v`.
- [x] **Bước 4.3: Triển khai click toàn bộ thẻ dự án trong `ui/pages/dashboard_page.py`**
  - Gán `row.setCursor(Qt.PointingHandCursor)`.
  - Thiết lập cho các nhãn con: `lbl_icon`, `lbl_name`, `lbl_path` thuộc tính `setAttribute(Qt.WA_TransparentForMouseEvents, True)`.
  - Gán hàm xử lý `mousePressEvent` cho `row`:
    ```python
    def _on_row_clicked(event, path=item["path"]):
        if event.button() == Qt.LeftButton:
            self.open_project_requested.emit(path)
    row.mousePressEvent = _on_row_clicked
    ```
  - Trong `btn_remove.clicked`: Đảm bảo không lan truyền sự kiện click lên `row`.
- [x] **Bước 4.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_recent_projects_ui.py -v`.
- [x] **Bước 4.5: Commit mã nguồn Tác vụ 4**
  `git commit -m "feat(dashboard): allow opening recent project by clicking anywhere on the item card (PLAN-ASR-LANG-UX-001)"`

---

### Tác vụ 5: Làm sạch Dữ liệu Dị bản Câu #21 trong `JMSZ_timing.srt` & Kiểm định Hồi quy Toàn diện
**Files:**
* Sửa đổi: `D:\Projects\JMSZ.ai-subtitle\artifacts\timing\JMSZ_timing.srt`
* Kiểm thử: Toàn bộ suite Desktop GUI Specs & Unit Specs

- [x] **Bước 5.1: Làm sạch dữ liệu tệp `D:\Projects\JMSZ.ai-subtitle\artifacts\timing\JMSZ_timing.srt`**
  Xóa bỏ từ ảo giác `"Diyorlar."` tại câu 21, đưa về trạng thái trống hoặc quét lại chuẩn xác.
- [x] **Bước 5.2: Chạy kiểm định toàn bộ các bộ test trọng yếu**
  ```powershell
  # 1. Bộ test chuẩn hóa ngôn ngữ ASR
  .\.venv\Scripts\python.exe -m pytest tests/subtitle_generation/test_language_code_normalization.py tests/subtitle_generation/test_segment_scan_hallucination_filter.py -v

  # 2. Bộ test cô lập tab dịch & UX dashboard
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_translation_transfer_isolation.py tests/ui/test_recent_projects_ui.py -v

  # 3. Bộ test ổn định luồng CAT Studio
  .\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py tests/translation/test_cat_persistence_filter.py -v

  # 4. Toàn bộ Desktop GUI Flow Specs (POM Triad)
  .\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v
  ```
- [x] **Bước 5.3: Commit hoàn tất kế hoạch**
  `git commit -m "chore: clean corrupted hallucination in JMSZ sample and verify full regression suite (PLAN-ASR-LANG-UX-001)"`
