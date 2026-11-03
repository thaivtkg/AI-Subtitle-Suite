# Kế hoạch Triển khai: Khắc phục Triệt để Lỗi Mất Nút Dịch (PLAN-CAT-TRANSLATE-BUTTON-RESTORE-001)

> **Dành cho Developer thực thi:** BẮT BUỘC thực hiện từng tác vụ tuần tự theo chuẩn Test-Driven Development (TDD). Các bước sử dụng cú pháp checkbox (`- [ ]`) để theo dõi tiến độ. Tuyệt đối không nhảy cóc các bước kiểm thử. Không tự ý sửa đổi logic nghiệp vụ ngoài phạm vi tài liệu này.

**Mục tiêu:**
Khắc phục triệt để lỗi mất nút dịch (`btnTranslate` biến mất trên thanh công cụ dưới đáy của Không gian Dịch thuật `TranslationWorkspace.qml`), bảo đảm nút bấm "⚡ Dịch (Ctrl+T)" hoặc "⚡ Dịch lại" luôn hiển thị trực quan và khả dụng cho người dùng trong mọi trạng thái phụ đề.

**Nguyên nhân gốc rễ (Root Cause Analysis):**
1. **Xung đột trường trạng thái (Status Pollution):**  
   Tại `ui/pages/translation_studio_page.py:146-147` (`load_subtitles_from_studio`):
   ```python
   raw_status = s.get("translation_status") or s.get("status")
   status = raw_status if raw_status else ("PENDING" if not s.get("translation") else "TRANSLATED")
   ```
   Khi một phân đoạn phụ đề được nạp từ Timeline/SubEditor, trường `translation_status` là `None`, nhưng trường `status` lưu trạng thái của luồng ASR/Timing (`"draft"`, `"final"`, `"timing"`, `"timing_only"`). Biểu thức fallback `s.get("translation_status") or s.get("status")` đã lấy giá trị `"draft"` gán vào trạng thái dịch thuật!
2. **`TranslationController` nhận trạng thái dị bản:**  
   Khi gọi `loadSubtitle(0)`, `self._status = "DRAFT"` (hoặc `"FINAL"` / `"IDLE"`).
3. **Điều kiện hiển thị quá hẹp trong QML:**  
   Tại `ui/qml_translation/components/TranslationWorkspace.qml:1162`:
   ```qml
   AppButton {
       objectName: "btnTranslate"
       visible: translationController.status === "PENDING"
   ```
   Khi `status` là `"DRAFT"`, `"FINAL"`, `"IDLE"` hoặc bất kỳ chuỗi nào khác ngoài `"PENDING"`:
   - `btnTranslate` bị ẩn (`"DRAFT" === "PENDING"` là `false`).
   - `btnRetry` bị ẩn (`["ERROR", "TRANSLATED", "EDITED", "ACCEPTED"].indexOf("DRAFT") >= 0` là `false`).
   - `btnCancelTranslation` bị ẩn (`"DRAFT" === "TRANSLATING"` là `false`).
   **Kết quả:** Toàn bộ các nút dịch thuật đều biến mất hoàn toàn, người dùng chỉ nhìn thấy nút `[ ⌨ Phím tắt (F1) ]` và `[ ✓ Chấp nhận (Accept... ]`.

---

## Các ràng buộc toàn cục (Global Constraints)
* **Khử nhiễm Trạng thái Dịch (Translation Status Isolation):** Trạng thái dịch thuật trong CAT Studio (`SubtitleModel`) TUYỆT ĐỐI chỉ nhận một trong 6 giá trị chuẩn: `{"PENDING", "TRANSLATING", "TRANSLATED", "EDITED", "ACCEPTED", "ERROR"}`. Mọi giá trị trạng thái ASR/Timing ngoài luồng (`draft`, `final`, `timing_only`, v.v.) phải được chuẩn hóa thành `PENDING` (hoặc `TRANSLATED` nếu đã có nội dung dịch).
* **Nút Dịch Luôn Khả Dụng (Button Fallback Guarantee):** Ngoại trừ khi đang chạy dịch (`TRANSLATING` - hiển thị nút Hủy dịch) hoặc đã có bản dịch (`TRANSLATED`, `EDITED`, `ACCEPTED` - hiển thị nút Dịch lại), nút `btnTranslate` ("⚡ Dịch (Ctrl+T)") PHẢI LUÔN HIỂN THỊ cho mọi trạng thái khác.
* **Zero Regression:** Toàn bộ 47 test specs hiện hành của hệ thống phải tiếp tục duy trì trạng thái 100% Green.

---

## Cấu trúc các tác vụ (Tasks Breakdown)

### Tác vụ 1: Khử nhiễm Trạng thái khi Nạp Phụ đề vào CAT Studio
**Files:**
* Sửa đổi: `ui/pages/translation_studio_page.py:145-155`
* Sửa đổi: `core/translation/models/subtitle.py:190-205`
* Kiểm thử: `tests/translation/test_cat_status_sanitization.py`

- [x] **Bước 1.1: Viết test thất bại kiểm tra chuẩn hóa trạng thái phụ đề**
  Tạo `tests/translation/test_cat_status_sanitization.py`:
  - Kiểm tra khi segment có `status="draft"` và `translation_status=None`, khi nạp qua `load_subtitles_from_studio()` trạng thái trong `SubtitleModel` phải là `"PENDING"`.
  - Kiểm tra khi segment có `status="final"` và `translation_status=None`, trạng thái phải là `"PENDING"`.
  - Kiểm tra khi segment có `status="draft"` nhưng đã có `translation="Bản dịch"`, trạng thái phải là `"TRANSLATED"`.
  - Kiểm tra `translationController.status` nhận đúng `"PENDING"`, không bao giờ nhận `"DRAFT"` hay `"FINAL"`.
- [x] **Bước 1.2: Chạy test để xác nhận test thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_status_sanitization.py -v`.
- [x] **Bước 1.3: Sửa đổi `ui/pages/translation_studio_page.py`**
  Tại dòng 146-151, thay thế đoạn mã đọc `raw_status`:
  ```python
  VALID_CAT_STATUSES = {"PENDING", "TRANSLATING", "TRANSLATED", "EDITED", "ACCEPTED", "ERROR"}
  trans_status = str(s.get("translation_status") or "").strip().upper()
  if trans_status in VALID_CAT_STATUSES:
      status = trans_status
  else:
      status = "TRANSLATED" if str(s.get("translation", "")).strip() else "PENDING"
  ```
- [x] **Bước 1.4: Thêm cơ chế chuẩn hóa trạng thái trong `core/translation/models/subtitle.py`**
  Trong `SubtitleModel.load_data()` và `update_translation()`:
  Bảo đảm mọi item được nạp vào model đều có `status` thuộc `VALID_CAT_STATUSES`. Nếu không hợp lệ, gán mặc định `"PENDING"`.
- [x] **Bước 1.5: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_status_sanitization.py -v`.
- [x] **Bước 1.6: Commit mã nguồn Tác vụ 1**
  `git commit -m "fix(cat-status): sanitize subtitle translation status on studio import (PLAN-CAT-TRANSLATE-BUTTON-RESTORE-001)"`

---

### Tác vụ 2: Cải tiến Điều kiện Hiển thị Nút Dịch trên `TranslationWorkspace.qml`
**Files:**
* Sửa đổi: `ui/qml_translation/components/TranslationWorkspace.qml:1160-1175`
* Kiểm thử: `tests/gui/specs/test_cat_studio_flow.py`

- [x] **Bước 2.1: Bổ sung test kiểm thử hiển thị nút dịch khi trạng thái bất thường**
  Trong `tests/gui/specs/test_cat_studio_flow.py`, thêm test case:
  `test_flow_cat_studio_translate_button_visible_under_draft_or_idle_status`:
  - Giả lập `translationController.status` mang giá trị `"DRAFT"`, `"IDLE"` hoặc rỗng.
  - Kiểm tra `driver.find_qml_item("btnTranslate")` có thuộc tính `visible == True`.
- [x] **Bước 2.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/gui/specs/test_cat_studio_flow.py -k "test_flow_cat_studio_translate_button_visible" -v`.
- [x] **Bước 2.3: Điều chỉnh điều kiện `visible` của `btnTranslate` trong `TranslationWorkspace.qml`**
  Tại dòng 1162 của `TranslationWorkspace.qml`:
  ```qml
  AppButton {
      objectName: "btnTranslate"
      visible: translationController.status !== "TRANSLATING" &&
               ["TRANSLATED", "EDITED", "ACCEPTED"].indexOf(translationController.status) < 0
      text: "⚡ Dịch (Ctrl+T)"
      Layout.alignment: Qt.AlignVCenter
      Layout.preferredWidth: 112
      Layout.minimumWidth: 80
      isPrimary: true
      enabled: !workspace.executionLocked && translationController.engineStatus !== "Translating" &&
               translationController.status !== "TRANSLATING"
      onClicked: translateRequested((typeof translationController !== "undefined" && translationController.currentSourceLanguage) ? translationController.currentSourceLanguage : langSelector.sourceLang)
  }
  ```
- [x] **Bước 2.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/gui/specs/test_cat_studio_flow.py -k "test_flow_cat_studio_translate_button_visible" -v`.
- [x] **Bước 2.5: Commit mã nguồn Tác vụ 2**
  `git commit -m "fix(qml): ensure btnTranslate is always visible when not translating or already translated (PLAN-CAT-TRANSLATE-BUTTON-RESTORE-001)"`

---

### Tác vụ 3: Kiểm định Hồi quy Toàn diện
**Files:**
* Kiểm thử: Toàn bộ suite Desktop GUI Flow Specs & Translation Tests

- [x] **Bước 3.1: Chạy kiểm định toàn bộ các bộ test hệ thống**
  ```powershell
  # 1. Bộ test chuẩn hóa trạng thái CAT Studio
  .\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_status_sanitization.py -v

  # 2. Bộ test ổn định luồng CAT Studio & Persistence Filter
  .\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py tests/translation/test_cat_persistence_filter.py -v

  # 3. Toàn bộ Desktop GUI Flow Specs (POM Triad: CAT Studio, SubEditor, Timeline)
  .\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v
  ```
- [x] **Bước 3.2: Commit hoàn tất kế hoạch**
  `git commit -m "chore: verify translate button restore and full regression suite (PLAN-CAT-TRANSLATE-BUTTON-RESTORE-001)"`
