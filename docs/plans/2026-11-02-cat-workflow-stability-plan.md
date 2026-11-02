# Kế hoạch Triển khai: Ổn định Luồng Dịch CAT Studio & Loại trừ Ảo giác ASR (PLAN-CAT-WORKFLOW-STABILITY-001)

> **Dành cho Agent/Developer thực thi:** BẮT BUỘC thực hiện từng tác vụ tuần tự theo chuẩn Test-Driven Development (TDD). Các bước sử dụng cú pháp checkbox (`- [ ]`) để theo dõi tiến độ. Tuyệt đối không nhảy cóc các bước kiểm thử.

**Mục tiêu:** Khắc phục triệt để lỗi treo đứng tiến trình dịch ở 85% hoặc 0%, bổ sung tùy chọn hủy dịch (Cancel Translation) với phím tắt Esc, thiết lập chốt chặn khóa an toàn khi hàng đợi dịch trống, và triệt tiêu từ ảo giác ngoại lai (như "Diyorlar.") trong nhận diện ASR.

**Kiến trúc:** 
1. Loại bỏ điểm dừng chết timer trong `TranslationController`, cho phép tiệm cận tiến trình liên tục tới khi nhận token đầu tiên.
2. Mở rộng slot `cancelTranslation()` liên luồng kết nối trực tiếp `worker.cancel()` và `model_manager.cancel()`, kèm nút bấm visual `btnCancelTranslation` trên QML.
3. Loại bỏ điều kiện `self._current_index < 0` trong các slot nhận kết quả worker, đồng thời tự động hủy tác vụ nền khi hàng đợi về 0.
4. Bổ sung từ khóa ảo giác vào `SubtitleGenerationValidator` và kế thừa ngôn ngữ gốc của dự án khi quét ASR đoạn âm thanh ngắn.

**Ngăn xếp công nghệ:** Python 3.11, PySide6 (Qt Quick / QML), Faster-Whisper, Pytest.

**Tài liệu đặc tả:** `PLAN-CAT-WORKFLOW-STABILITY-001`

---

## Các ràng buộc toàn cục (Global Constraints)
* **Bất biến hàng đợi CAT Studio:** `SubtitleModel` chỉ chứa các tác vụ chưa duyệt. Khi hàng đợi có 0 câu, workspace luôn hiển thị `EmptyWorkspace.qml`, không cho phép bất kỳ worker nền nào cập nhật trạng thái làm sống lại giao diện dịch.
* **Thời gian đáp ứng hủy dịch:** Lệnh hủy (`cancelTranslation`) phải trả quyền điều khiển về giao diện ngay lập tức (< 100ms) và trả trạng thái câu về `PENDING`.
* **Zero Regression:** Toàn bộ 76 test specs hiện hành của hệ thống phải duy trì trạng thái 100% Green.

---

## Trọng tâm đánh giá (Review Focus)
1. Bấm hủy dịch khi mô hình LLM đang trong pha sinh token sâu: Luồng `QThread` phải dừng an toàn, không rò rỉ bộ nhớ hoặc gây crash C++ `llama.cpp`.
2. Khi hàng đợi có 2 câu, người dùng duyệt hết câu 1 rồi duyệt câu 2 (queue về 0): Workspace phải chuyển ngay sang Empty Workspace, không nhấp nháy câu cũ.
3. Người dùng chuyển chọn qua lại giữa câu đang dịch và câu khác: Tiến trình dịch không được nhảy về 0%.
4. Đoạn âm thanh không có lời nói hoặc có nhạc nền: Nhận diện ASR phải trả về chuỗi rỗng thay vì sinh từ ảo giác.

---

## Cấu trúc các tác vụ (Tasks Breakdown)

### Tác vụ 1: Khắc phục Treo đứng Tiến trình Dịch (85% & 0%)
**Files:**
* Sửa đổi: `core/translation/controllers/translation_controller.py:105-125, 320-335`
* Kiểm thử: `tests/translation/test_cat_workflow_stability.py`

- [ ] **Bước 1.1: Viết test thất bại kiểm tra tiến trình không bị dừng ở 85% và không bị reset về 0% khi chọn lại câu**
  Tạo `tests/translation/test_cat_workflow_stability.py` với test case:
  `test_tc_stab_01_continuous_progress_beyond_85` và `test_tc_stab_01_selection_preserves_translating_progress`.
- [ ] **Bước 1.2: Chạy test để xác nhận test thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_01" -v`.
- [ ] **Bước 1.3: Điều chỉnh thuật toán tiến trình trong `translation_controller.py`**
  - Trong `_on_thinking_progress_tick()`: Bỏ `self._progress_timer.stop()` ở mốc 85%. Thiết lập dải tiệm cận mở rộng: từ 85% đến 95% (tăng 1% mỗi 6 ticks ~ 1.5s).
  - Trong `loadSubtitle(index)`: Thêm điều kiện bảo vệ: nếu `self._active_translation_index >= 0 and index == self._active_translation_index`, giữ nguyên `_translation_progress` hiện tại, không gán về 0.
- [ ] **Bước 1.4: Chạy lại test để xác nhận 100% PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_01" -v`.
- [ ] **Bước 1.5: Commit mã nguồn Tác vụ 1**
  `git commit -m "fix(cat-progress): prevent thinking progress freeze at 85% and preserve progress on selection (PLAN-CAT-WORKFLOW-STABILITY-001)"`

---

### Tác vụ 2: Bổ sung Tùy chọn HỦY DỊCH (Backend Slot + Frontend QML)
**Files:**
* Sửa đổi: `core/translation/controllers/translation_controller.py:130-160`
* Sửa đổi: `ui/qml_translation/components/TranslationWorkspace.qml:1140-1170`
* Sửa đổi: `ui/qml_translation/TranslationStudioView.qml:140-160`
* Kiểm thử: `tests/translation/test_cat_workflow_stability.py`

- [ ] **Bước 2.1: Viết test thất bại cho slot `cancelTranslation()`**
  Bổ sung `test_tc_stab_02_cancel_translation_resets_state` trong `test_cat_workflow_stability.py`.
- [ ] **Bước 2.2: Chạy test xác nhận thất bại do chưa có slot `cancelTranslation`**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_02" -v`.
- [ ] **Bước 2.3: Triển khai slot `cancelTranslation()` trong `translation_controller.py`**
  - Dừng `self._progress_timer`.
  - Gọi `self.worker.cancel()` nếu worker đang chạy và dọn dẹp worker an toàn.
  - Reset `self._status = "PENDING"`, `_translation_progress = 0`, phát tín hiệu `statusChanged` và `translationProgressChanged`.
  - Cập nhật trạng thái câu trong `_subtitle_model` về `"PENDING"`.
- [ ] **Bước 2.4: Bổ sung nút `[ 🛑 Hủy dịch ]` và phím tắt `Esc` trong `TranslationWorkspace.qml`**
  - Thêm `AppButton` với `objectName: "btnCancelTranslation"`, hiển thị khi `translationController.status === "TRANSLATING"`.
  - Thêm `Shortcut { sequence: "Escape"; enabled: translationController.status === "TRANSLATING"; onActivated: translationController.cancelTranslation() }`.
- [ ] **Bước 2.5: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_02" -v`.
- [ ] **Bước 2.6: Commit mã nguồn Tác vụ 2**
  `git commit -m "feat(cat-studio): implement cancel translation slot, action button and Esc shortcut (PLAN-CAT-WORKFLOW-STABILITY-001)"`

---

### Tác vụ 3: Khóa An toàn Tuyệt đối khi Hàng đợi Rỗng (Empty Queue Guard)
**Files:**
* Sửa đổi: `core/translation/controllers/translation_controller.py:485-535, 275-300`
* Sửa đổi: `ui/qml_translation/components/SubtitleListView.qml:915-930`
* Kiểm thử: `tests/translation/test_cat_workflow_stability.py`

- [ ] **Bước 3.1: Viết test thất bại mô phỏng worker phát tín hiệu khi queue đã về 0**
  Bổ sung `test_tc_stab_03_empty_queue_guard_blocks_stale_worker` trong `test_cat_workflow_stability.py`.
- [ ] **Bước 3.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_03" -v`.
- [ ] **Bước 3.3: Triển khai khóa an toàn hàng đợi trong `translation_controller.py` và `SubtitleListView.qml`**
  - Trong `on_progress()` và `on_finished()`: Loại bỏ hoàn toàn điều kiện `self._current_index < 0`. Chỉ cho phép cập nhật UI khi `self._current_index >= 0 and index == self._current_index`.
  - Trong `loadSubtitle(index)` khi `index < 0`: Nếu `self.is_busy()`, chủ động gọi `self.cancelTranslation()` để triệt tiêu worker rác; gán `_active_translation_index = -1`, `_status = "IDLE"`.
  - Trong `SubtitleListView.qml:onCountChanged`: Khi `count === 0`, gán `currentIndex = -1`.
- [ ] **Bước 3.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_03" -v`.
- [ ] **Bước 3.5: Commit mã nguồn Tác vụ 3**
  `git commit -m "fix(cat-queue): enforce strict empty queue guard and cancel stale background workers (PLAN-CAT-WORKFLOW-STABILITY-001)"`

---

### Tác vụ 4: Lọc Ảo giác Faster-Whisper & Kế thừa Ngôn ngữ Gốc Dự án
**Files:**
* Sửa đổi: `core/subtitle_generation/generation_validator.py:8-25`
* Sửa đổi: `ui/Gui.py:1675-1685`
* Sửa đổi: `D:\Projects\JMSZ.ai-subtitle\artifacts\timing\JMSZ_timing.srt:81-85`
* Kiểm thử: `tests/translation/test_cat_workflow_stability.py`

- [ ] **Bước 4.1: Viết test thất bại kiểm tra lọc bỏ từ ảo giác "Diyorlar."**
  Bổ sung `test_tc_stab_04_hallucination_validator` trong `test_cat_workflow_stability.py`.
- [ ] **Bước 4.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_04" -v`.
- [ ] **Bước 4.3: Mở rộng `HALLUCINATIONS` và kế thừa ngôn ngữ dự án**
  - Trong `generation_validator.py`: Thêm `"diyorlar"`, `"diyorlar."`, `"thank you."`, `"watching!"` vào tuple `HALLUCINATIONS`.
  - Trong `ui/Gui.py:1679`: Khi `settings.get("language")` là `None` hoặc `"Auto Detect"`, kiểm tra và kế thừa ngôn ngữ gốc nếu dự án đã xác định (ví dụ `Japanese`).
  - Dọn sạch từ `"Diyorlar."` tại câu `#021` trong tệp `JMSZ_timing.srt`.
- [ ] **Bước 4.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -k "test_tc_stab_04" -v`.
- [ ] **Bước 4.5: Commit mã nguồn Tác vụ 4**
  `git commit -m "fix(asr): suppress whisper hallucinations and inherit project language for segment scan (PLAN-CAT-WORKFLOW-STABILITY-001)"`

---

### Tác vụ 5: Kiểm định Hồi quy Toàn diện Toàn hệ thống (Regression Gate)
**Files:**
* Chạy kiểm thử: Toàn bộ 8 suite kiểm thử của dự án

- [ ] **Bước 5.1: Chạy suite kiểm thử mới `test_cat_workflow_stability.py`**
  `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py -v`
- [ ] **Bước 5.2: Chạy suite kiểm thử Persistence Filter**
  `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_persistence_filter.py -v`
- [ ] **Bước 5.3: Chạy suite kiểm thử Empty Workspace & Queue Protection**
  `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_empty_workspace_and_badges.py tests/translation/test_cat_queue_and_autosave_protection.py -v`
- [ ] **Bước 5.4: Chạy suite Desktop GUI POM Triad**
  `.\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v`
- [ ] **Bước 5.5: Chạy suite Realtime Video Sync & Nudge Timing**
  `.\.venv\Scripts\python.exe -m pytest tests/ui/test_realtime_subtitle_video_sync.py tests/ui/test_nudge_timing_boundary_clamping.py -v`
- [ ] **Bước 5.6: Chạy suite E2E Visual Sync & Kịch bản JMSZ**
  `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_ui_visual_sync_cat_studio.py -v`
- [ ] **Bước 5.7: Chạy suite Batch UI Flow**
  `.\.venv\Scripts\python.exe -m pytest tests/translation/e2e/test_batch_ui.py -v`
- [ ] **Bước 5.8: Xác nhận 100% Green toàn bộ hệ thống**
  Xác nhận tổng số test đạt tối thiểu 80/80 Specs Green (bao gồm 4 specs mới).
