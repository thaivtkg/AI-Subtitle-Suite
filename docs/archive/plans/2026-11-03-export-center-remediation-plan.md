# Kế hoạch Kỹ thuật: Khắc phục Toàn diện & Tối ưu Tab Export & Delivery Center
**Mã kế hoạch:** `PLAN-EXPORT-DELIVERY-REMEDIATION-001`  
**Ngày lập:** 2026-11-03  
**Vai trò:** Principal QA Lead / Software Quality Architect  
**Đối tượng thực thi:** AI Developer  
**Tiêu chuẩn:** Tuân thủ triệt để nguyên tắc **Ponytail** (Diff tối thiểu, tái sử dụng service có sẵn, TDD 100% green).

---

## 1. Bối cảnh & Mục tiêu

Qua quá trình rà soát chất lượng kỹ thuật chuyên sâu trên Tab **Export & Delivery Center** (`ExportCenterPage`), hệ thống phát hiện 5 điểm nghẽn và lỗi hành vi nghiêm trọng:
1. **Lỗi chặn Hardsub (Blocker):** Nút `Render Video Hardsub` từ chối thực thi nếu chưa từng xuất thủ công tệp `.srt` ra đĩa, dù dữ liệu phụ đề đã có đầy đủ trong RAM (`self.sub_editor.all_segments`).
2. **Widget "bù nhìn":** Checkbox `chk_hardsub` trên thẻ cấu hình không được kết nối với bất kỳ logic xử lý nào trong `Gui.py`.
3. **Thiếu Fallback thư mục lưu cho Softsub:** Ô thư mục lưu để trống khiến xuất Softsub bị lỗi chặn, trong khi Hardsub có thể tự động fallback về thư mục chứa video.
4. **Mất câu gốc khi nạp bản dịch ngoài (Data Loss):** Nạp bản dịch từ tệp SRT ngoài ghi đè trường `text` mà không bảo lưu `original_text`.
5. **Xuất nhầm câu đã dịch:** Tính năng xuất đợt dịch (`_on_export_batch_translation_requested`) lấy trường `text` (có thể đã là tiếng Việt) thay vì câu gốc `original_text`.

---

## 2. Danh sách 5 Tác vụ Kỹ thuật Triển khai

### Tác vụ 1: Tháo gỡ Rào cản Hardsub & Tự động sinh nguồn phụ đề in-memory
- **File can thiệp:** `ui/Gui.py` (hàm `_trigger_export_hardsub`)
- **Vấn đề:** Dòng 3397-3404 kiểm tra `_, srt_path = self.queue_mgr.get_active_data()` và ném lỗi nếu `not srt_path or not os.path.exists(srt_path)`.
- **Giải pháp kỹ thuật:**
  1. Kiểm tra nguồn dữ liệu: Nếu `self.sub_editor.all_segments` có dữ liệu (độ dài > 0), coi đây là nguồn phụ đề hợp lệ.
  2. Nếu `srt_path` chưa tồn tại trên đĩa, tự động dùng `OutputPathService.build_subtitle_path(out_dir, self.queue_mgr.active_vid, ".srt")` để xuất nhanh một bản `.srt` hoặc truyền trực tiếp `segments` cho `HardsubWorker` (vì backend `Backend.py:246` đã hỗ trợ tạo phụ đề ASS trực tiếp từ `segments`).
  3. Chỉ báo lỗi `"Không có dữ liệu phụ đề để render hardsub"` khi cả `srt_path` lẫn `all_segments` đều rỗng.
- **Tiêu chuẩn kiểm thử TDD:** Viết test kiểm tra gọi `_trigger_export_hardsub` khi `queue_mgr` không có srt_path nhưng `sub_editor.all_segments` có 24 câu -> `HardsubWorker` được khởi tạo thành công.

---

### Tác vụ 2: Tự động Fallback thư mục lưu & Hiển thị đường dẫn mặc định
- **File can thiệp:** `ui/Gui.py` (hàm `_trigger_export_softsub` và `_sync_translation_batch_ui`)
- **Vấn đề:** `_trigger_export_softsub` đòi hỏi `out_dir` phải được nhập thủ công, nếu trống sẽ báo lỗi Toast `Vui lòng chọn thư mục lưu`.
- **Giải pháp kỹ thuật:**
  1. Trong `_trigger_export_softsub`: Tái sử dụng `OutputPathService.get_root_dir(configured_dir, self.queue_mgr.active_vid)` để tự động lấy thư mục chứa video làm fallback mặc định nếu `out_dir` để trống.
  2. Trong `switch_page` / `_sync_translation_batch_ui`: Khi người dùng chuyển sang trang Export Center, nếu ô `self.page_export.out_edit` đang trống và dự án đã có video, tự động điền đường dẫn thư mục video vào ô này làm gợi ý hiển thị.
- **Tiêu chuẩn kiểm thử TDD:** Viết test gọi `_trigger_export_softsub` khi `out_edit` để trống -> file phụ đề được xuất an toàn vào thư mục chứa video thay vì văng thông báo lỗi.

---

### Tác vụ 3: Kết nối Logic Checkbox `chk_hardsub` & Đồng bộ Trạng thái
- **File can thiệp:** `ui/pages/export_center_page.py`, `ui/Gui.py`
- **Vấn đề:** Checkbox `self.chk_hardsub` là widget độc lập không kết nối logic, tạo hiểu lầm với 2 nút hành động riêng biệt ở thanh công cụ dưới đáy.
- **Giải pháp kỹ thuật:**
  - Đồng bộ trạng thái: Khi người dùng bấm `💾 Xuất file Phụ đề (Softsub)`:
    - Nếu `self.page_export.chk_hardsub.isChecked()`: Sau khi xuất thành công các định dạng Softsub đã chọn, tự động gọi tiếp `_trigger_export_hardsub()` trong chuỗi liên hoàn.
    - Nếu không tích: Chỉ xuất Softsub như bình thường.
  - Vẫn giữ nút `🎬 Render Video Hardsub` độc lập để người dùng có thể kích hoạt riêng lẻ bất cứ lúc nào.
- **Tiêu chuẩn kiểm thử TDD:** Test kiểm tra khi `chk_hardsub` được bật, bấm `export_srt_requested` sẽ kích hoạt cả hai luồng Softsub và Hardsub.

---

### Tác vụ 4: Bảo vệ Câu gốc (Overwrite Guard) khi Nạp Bản dịch Ngoài
- **File can thiệp:** `ui/Gui.py` (hàm `_on_import_batch_translation_requested`)
- **Vấn đề:** Dòng 4713 gán thẳng `all_segs[best_idx]["text"] = new_text` làm mất câu gốc nếu `original_text` chưa được thiết lập.
- **Giải pháp kỹ thuật:**
  Trước khi ghi đè bản dịch vào `text`, áp dụng Overwrite Guard:
  ```python
  if not all_segs[best_idx].get("original_text"):
      all_segs[best_idx]["original_text"] = all_segs[best_idx].get("text", "")
  all_segs[best_idx]["text"] = new_text
  ```
- **Tiêu chuẩn kiểm thử TDD:** Viết test nạp file SRT bản dịch tiếng Việt vào segment có `text="こんにちは"` và `original_text=""` -> sau khi nạp, `text="Xin chào"` và `original_text="こんにちは"`.

---

### Tác vụ 5: Xuất Đợt dịch Ưu tiên Câu gốc (`original_text`)
- **File can thiệp:** `ui/Gui.py` (hàm `_on_export_batch_translation_requested`)
- **Vấn đề:** Dòng 4658 lấy `text = seg.get("text", "")`, có nguy cơ xuất câu đã dịch tiếng Việt cho app dịch ngoài.
- **Giải pháp kỹ thuật:**
  Cập nhật dòng 4658:
  ```python
  text = seg.get("original_text") or seg.get("text", "")
  ```
- **Tiêu chuẩn kiểm thử TDD:** Viết test xuất đợt dịch cho segment có `original_text="Hello world"` và `text="Chào thế giới"` -> file SRT xuất ra phải chứa `"Hello world"`.

---

## 3. Kế hoạch Kiểm thử Toàn diện (Acceptance Matrix)

| Test File | Kịch bản kiểm thử | Kỳ vọng |
| :--- | :--- | :--- |
| `tests/export/test_export_center_remediation.py` | 1. Test Hardsub in-memory khi không có file SRT trên đĩa | `HardsubWorker` được tạo với `segments` hợp lệ |
| `tests/export/test_export_center_remediation.py` | 2. Test Softsub tự động fallback về thư mục video | Xuất SRT thành công mà không đòi hỏi user nhập đường dẫn |
| `tests/export/test_export_center_remediation.py` | 3. Test `chk_hardsub` liên hoàn khi bấm xuất Softsub | Gọi cả xuất Softsub và kích hoạt Hardsub |
| `tests/export/test_export_center_remediation.py` | 4. Test Overwrite Guard bảo vệ `original_text` khi nạp batch | `original_text` được bảo lưu 100% |
| `tests/export/test_export_center_remediation.py` | 5. Test xuất batch lấy đúng `original_text` thay vì câu tiếng Việt | File SRT xuất ra chứa ngôn ngữ gốc |
