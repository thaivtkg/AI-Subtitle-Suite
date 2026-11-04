# Kế Hoạch Triển Khai: Tinh Chỉnh Giao Diện & Sửa Lỗi Hộp Thoại Tạo Dự Án Từ Thư Mục (DEV-SPEC-FOLDER-PROJECT-002)

> **Mục tiêu:** Tinh chỉnh bố cục giao diện, chuẩn hóa biểu tượng tiêu đề, áp dụng chính sách mặc định bỏ chọn toàn bộ video (Phương án B), và khắc phục triệt để lỗi nút đóng/thoát của hộp thoại `QuickFolderProjectDialog`.

---

## 1. Yêu Cầu Kỹ Thuật Chi Tiết

1. **Bố cục Hàng Nút Dưới Cùng (Unified Bottom Bar):**
   - Hợp nhất 2 hàng nút (`action_layout` và `footer_layout`) thành 1 hàng ngang duy nhất (`QHBoxLayout`).
   - Căn lề trái: Nút `Chọn tất cả`, `Bỏ chọn`, nhãn `Đã chọn: X / Y video`.
   - Khoảng dãn cách (`addStretch`): Đẩy nhóm hành động sang phải.
   - Căn lề phải: Nút `Hủy` và nút chính `🚀 Khởi Tạo Dự Án & Mở Workspace`.
   - Giảm lề dưới (`contentsMargins` đáy từ 16px xuống 10px) và loại bỏ khoảng cách dọc thừa.

2. **Chính Sách Tích Chọn Mặc Định (Phương Án B):**
   - Khi quét thư mục video và nạp vào bảng, toàn bộ checkbox được đặt về `Qt.Unchecked` (0 video được chọn).
   - Nút `🚀 Khởi Tạo Dự Án & Mở Workspace` ở trạng thái mờ (`disabled`) khi chưa có video nào được tích chọn.
   - Khi người dùng tích chọn ít nhất 1 video hoặc bấm `Chọn tất cả`, nút sẽ tự động kích hoạt (`enabled`).

3. **Chuẩn Hóa Biểu Tượng Tiêu Đề (Single Icon):**
   - Loại bỏ ký tự emoji `📁` ở đầu chuỗi `setWindowTitle()`, đổi thành:  
     `"Tạo Dự Án Nhanh Từ Thư Mục Video - AI Subtitle Suite"`.
   - Đảm bảo thanh tiêu đề Windows chỉ hiển thị 1 biểu tượng duy nhất là icon chính thức của ứng dụng.

4. **Khắc Phục Nút Đóng / Thoát (`X` Exit Button):**
   - Khai báo tường minh cờ cửa sổ độc lập với cửa sổ cha không viền:  
     `self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)`.
   - Bổ sung nút đóng `✕` tinh gọn trên thanh tiêu đề nội bộ (Header Bar) của Dialog kết nối trực tiếp slot `self.reject()`.
   - Hỗ trợ đầy đủ 4 cơ chế đóng/thoát: Nút `X` Windows, nút `✕` header, nút `Hủy`, và phím `Esc`.

5. **Nghiệm Thu Trực Quan & Kiểm Thử Hồi Quy:**
   - Cập nhật unit test và chạy toàn bộ bộ kiểm thử hồi quy tự động.
   - Chạy kịch bản E2E chụp ảnh giao diện thực tế và cập nhật artifact báo cáo nghiệm thu trực quan.

---

## 2. Kế Hoạch Thực Hiện Theo Từng Tác Vụ

### Task 1: Cập Nhật Unit Tests Kiểm Thử Hành Vi Mới
**Files:**
- Modify: `tests/ui/test_quick_folder_project_dialog.py`

- [ ] **Step 1.1:** Cập nhật kiểm thử hành vi checkbox mặc định:
  - Khi mở hộp thoại lần đầu, `dialog.get_selected_videos()` trả về danh sách rỗng `[]`.
  - Nút `btn_create` có `isEnabled() == False`.
  - Nhãn `lbl_summary` hiển thị: `"Đã chọn: 0 / N video"`.
- [ ] **Step 1.2:** Thêm kiểm thử cho nút đóng `btn_close_header` và cờ `WindowCloseButtonHint`.
- [ ] **Step 1.3:** Chạy pytest để xác nhận các test mới phản ánh đúng hành vi cần chỉnh sửa.

---

### Task 2: Tinh Chỉnh Mã Nguồn `QuickFolderProjectDialog`
**Files:**
- Modify: `ui/dialogs/quick_folder_project_dialog.py`

- [ ] **Step 2.1:** Cập nhật `setWindowTitle()` loại bỏ emoji `📁`.
- [ ] **Step 2.2:** Thiết lập cờ `self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)`.
- [ ] **Step 2.3:** Bổ sung nút `btn_close_header` ("✕") vào layout Header.
- [ ] **Step 2.4:** Thiết lập `check_item.setCheckState(Qt.Unchecked)` trong `_populate_table()`.
- [ ] **Step 2.5:** Hợp nhất hàng nút dưới cùng thành một `QHBoxLayout` duy nhất và tinh chỉnh margin đáy.
- [ ] **Step 2.6:** Chạy kiểm thử đơn vị `tests/ui/test_quick_folder_project_dialog.py` xác nhận 100% Pass.

---

### Task 3: Chạy Kiểm Thử Toàn Diện & Xuất Ảnh Giao Diện Thực Tế
**Files:**
- Modify/Run: `tests/e2e/test_capture_quick_folder_screenshots.py`

- [ ] **Step 3.1:** Chạy toàn bộ regression test suite:
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/core/test_folder_project_scanner.py tests/ui/test_quick_folder_project_dialog.py tests/ui/test_gui_quick_folder_project.py -v
  ```
- [ ] **Step 3.2:** Chạy E2E screenshot capture trên thư mục thực tế `D:\Video` để ghi lại:
  - Bố cục 1 hàng nút mới phẳng, không còn khoảng trống thừa.
  - Trạng thái mặc định bỏ tick toàn bộ và nút Khởi tạo mờ.
  - Thanh tiêu đề chỉ còn 1 icon duy nhất và nút đóng `✕` trên header.
- [ ] **Step 3.3:** Cập nhật tài liệu nghiệm thu trực quan tại artifact `visual_acceptance_quick_folder_project.md`.
