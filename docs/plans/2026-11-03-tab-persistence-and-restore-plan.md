# Kế hoạch Triển khai: Khắc phục Triệt để Lỗi Không Mở Lại Tab Đã Lưu/Autosave (PLAN-TAB-PERSISTENCE-RESTORE-001)

> **Dành cho Developer thực thi:** BẮT BUỘC thực hiện từng tác vụ tuần tự theo chuẩn Test-Driven Development (TDD). Các bước sử dụng cú pháp checkbox (`- [ ]`) để theo dõi tiến độ. Tuyệt đối không nhảy cóc các bước kiểm thử. Không tự ý sửa đổi logic nghiệp vụ ngoài phạm vi đồng bộ tab/trang giao diện.

**Mục tiêu:**
Khắc phục triệt để lỗi khi người dùng đang làm việc ở bất kỳ Tab nào (Studio Workspace, Dịch thuật AI, Queue & Output, Draft Center, Export Center, Settings, Help) mà có thao tác Save (Ctrl+S) hoặc Autosave, khi mở lại dự án hệ thống phải phục hồi chính xác 100% về đúng Tab đó, không bao giờ bị nhảy nhầm về Dashboard hoặc Tab khác.

---

## 1. Phân tích Nguyên nhân Gốc rễ (Root Cause Analysis)

1. **Khuyết thiếu và Sai lệch trong Bảng Ánh xạ Tab (`WorkspaceService.page_map`):**
   - Tại `core/services/workspace_service.py:23-25` (`capture_workspace`):
     ```python
     original_idx = getattr(self.ui, '_active_nav_index', 0)
     page_map = {0: "dashboard", 1: "workspace", 2: "editor", 3: "queue", 4: "draft", 5: "export", 6: "settings"}
     workspace.active_page = page_map.get(original_idx, "dashboard")
     ```
     Khi người dùng đang ở **Tab Dịch thuật AI (`index: 8`)** hoặc **Help (`index: 7`)**, `page_map.get(...)` không tìm thấy nên trả về mặc định `"dashboard"`! Tệp `workspace.json` bị ghi đè thành `"active_page": "dashboard"`.
   - Tại `core/services/workspace_service.py:73-75` (`restore_workspace`):
     ```python
     page_map = {"dashboard": 0, "workspace": 1, "editor": 2, "queue": 3, "draft": 4, "export": 5}
     target_idx = page_map.get(workspace.active_page, 0)
     self.ui.switch_page(target_idx)
     ```
     Bảng khôi phục không hề có mục `"translation": 8`, `"settings": 6`, `"help": 7`. Nếu dữ liệu là `"translation"`, `"settings"` hoặc `"help"`, nó rơi vào fallback `0` (Dashboard).
2. **Nghịch lý Mở Dự án bị Văng về Dashboard:**
   Khi mở một dự án từ Dashboard, nếu `workspace.active_page` là `"dashboard"` (do lỗi ghi đè ở trên), hàm `restore_workspace()` gọi `self.ui.switch_page(0)`, khiến ứng dụng sau khi nạp xong dự án lại lập tức nhảy ngược trở lại Dashboard!
3. **Thiếu Cơ chế Lưu Trạng thái Tab Tức thì khi Chuyển Tab (`switch_page`):**
   Tại `ui/Gui.py:2548` (`switch_page`), khi người dùng bấm chuyển tab trên thanh Liquid Navigation (ví dụ từ Workspace sang Dịch, hoặc sang Queue, Export), hệ thống chỉ cập nhật biến cục bộ `_active_nav_index` mà không gọi `capture_workspace()` và không cập nhật nhanh `workspace.json`. Nếu người dùng không sửa text (không kích hoạt Autosave), trạng thái tab mới không được lưu xuống đĩa.

---

## Các ràng buộc toàn cục (Global Constraints)
* **Nguyên tắc Mở Dự án Luôn ở trong Dự án (No Kickback to Dashboard):** Khi một dự án được mở hợp lệ, giao diện TUYỆT ĐỐI KHÔNG BAO GIỜ hiển thị trang Dashboard (0). Nếu `workspace.active_page` là `"dashboard"`, rỗng hoặc không xác định, trang mặc định khi mở dự án phải là **Studio Workspace (1)**.
* **Đồng bộ Đầy đủ Toàn bộ 8 Tab Hợp lệ:** Mọi Tab thuộc `LiquidNavWidget` và `NAV_TO_STACK` (`0: dashboard`, `1: workspace`, `3: queue`, `4: draft`, `5: export`, `6: settings`, `7: help`, `8: translation`) phải có ánh xạ 2 chiều chính xác tuyệt đối.
* **Tự động Cập nhật Workspace khi Chuyển Tab (Instant Tab Persistence):** Mỗi khi người dùng chuyển trang qua `switch_page()`, nếu có dự án đang mở, `project.state.workspace.active_page` phải được cập nhật ngay lập tức và đồng bộ xuống `workspace.json`.
* **Zero Regression:** Toàn bộ 47 test specs hiện hành của hệ thống phải tiếp tục duy trì trạng thái 100% Green.

---

## Cấu trúc các tác vụ (Tasks Breakdown)

### Tác vụ 1: Chuẩn hóa Bảng Ánh xạ 2 Chiều Toàn diện trong `WorkspaceService`
**Files:**
* Sửa đổi: `core/services/workspace_service.py:20-85`
* Kiểm thử: `tests/core/test_workspace_tab_persistence.py`

- [ ] **Bước 1.1: Viết test thất bại kiểm tra capture và restore cho toàn bộ các tab**
  Tạo `tests/core/test_workspace_tab_persistence.py`:
  - Test capture: Kiểm tra khi `_active_nav_index` là 8 (Dịch), `workspace.active_page == "translation"`.
  - Test capture: Kiểm tra khi `_active_nav_index` là 6 (Settings), `workspace.active_page == "settings"`.
  - Test capture: Kiểm tra khi `_active_nav_index` là 7 (Help), `workspace.active_page == "help"`.
  - Test capture: Kiểm tra khi `_active_nav_index` là 3 (Queue), 4 (Draft), 5 (Export), 1 (Workspace).
  - Test restore: Kiểm tra khi `active_page == "translation"`, gọi `switch_page(8)`.
  - Test restore: Kiểm tra khi `active_page == "settings"`, gọi `switch_page(6)`.
  - Test restore: Kiểm tra khi `active_page == "help"`, gọi `switch_page(7)`.
  - Test restore: Kiểm tra khi `active_page == "dashboard"` hoặc giá trị lạ, gọi `switch_page(1)` (Studio Workspace), không bao giờ văng về 0.
- [ ] **Bước 1.2: Chạy test để xác nhận test thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/core/test_workspace_tab_persistence.py -v`.
- [ ] **Bước 1.3: Cập nhật `core/services/workspace_service.py`**
  Định nghĩa bảng ánh xạ chuẩn ở cấp độ class hoặc module:
  ```python
  NAV_TO_PAGE_MAP = {
      0: "dashboard",
      1: "workspace",
      2: "queue",
      3: "queue",
      4: "draft",
      5: "export",
      6: "settings",
      7: "help",
      8: "translation",
  }

  PAGE_TO_NAV_MAP = {
      "dashboard": 1,  # Dự án đang mở không hiển thị dashboard, mở Workspace
      "workspace": 1,
      "editor": 1,     # Hỗ trợ backward compatibility dữ liệu cũ
      "queue": 3,
      "draft": 4,
      "export": 5,
      "settings": 6,
      "help": 7,
      "translation": 8,
  }
  ```
  - Trong `capture_workspace()`: Sử dụng `NAV_TO_PAGE_MAP.get(original_idx, "workspace")`.
  - Trong `restore_workspace()`: Sử dụng `PAGE_TO_NAV_MAP.get(workspace.active_page, 1)`.
- [ ] **Bước 1.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/core/test_workspace_tab_persistence.py -v`.
- [ ] **Bước 1.5: Commit mã nguồn Tác vụ 1**
  `git commit -m "fix(workspace): support 2-way tab mapping for all 8 nav pages with dashboard safeguard (PLAN-TAB-PERSISTENCE-RESTORE-001)"`

---

### Tác vụ 2: Tự động Ghi nhận Tab Hiện hành khi Chuyển Trang & Lưu Dự án
**Files:**
* Sửa đổi: `ui/Gui.py:2560-2625, 4980-4995`
* Kiểm thử: `tests/ui/test_tab_switch_persistence_integration.py`

- [ ] **Bước 2.1: Viết test thất bại kiểm tra chuyển trang tự cập nhật workspace**
  Tạo `tests/ui/test_tab_switch_persistence_integration.py`:
  - Khởi tạo MainWindow với một Project đang mở.
  - Gọi `gui.switch_page(8)`.
  - Xác nhận `project.state.workspace.active_page == "translation"`.
  - Gọi `gui.switch_page(5)`.
  - Xác nhận `project.state.workspace.active_page == "export"`.
  - Gọi `gui.action_save_project()`.
  - Đọc tệp `workspace.json` trên đĩa cứng và xác nhận `"active_page": "export"`.
- [ ] **Bước 2.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_tab_switch_persistence_integration.py -v`.
- [ ] **Bước 2.3: Cập nhật `switch_page` trong `ui/Gui.py`**
  - Tại cuối hàm `switch_page(self, original_index)` (khoảng dòng 2615-2625):
    ```python
    if hasattr(self, 'workspace_service') and getattr(getattr(self, 'project_service', None), 'current_project', None):
        self.workspace_service.capture_workspace()
        # Lưu nhẹ workspace.json để ghi nhận tab lập tức
        try:
            import os
            from dataclasses import asdict
            from core.storage.atomic_saver import atomic_save_json
            proj_dir = getattr(self.project_service, 'project_dir', None)
            if proj_dir and os.path.exists(proj_dir):
                ws_file = os.path.join(proj_dir, "workspace.json")
                ws_data = asdict(self.project_service.current_project.state.workspace)
                atomic_save_json(ws_file, ws_data)
        except Exception as e:
            pass
    ```
- [ ] **Bước 2.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_tab_switch_persistence_integration.py -v`.
- [ ] **Bước 2.5: Commit mã nguồn Tác vụ 2**
  `git commit -m "feat(ui): persist active tab to workspace.json immediately on page switch (PLAN-TAB-PERSISTENCE-RESTORE-001)"`

---

### Tác vụ 3: Đảm bảo Luồng Mở Dự án (`_open_project_by_path`) Phục hồi Chính xác Tab Đã Lưu
**Files:**
* Sửa đổi: `ui/Gui.py:5190-5215`
* Kiểm thử: `tests/ui/test_open_project_restores_saved_tab.py`

- [ ] **Bước 3.1: Viết test thất bại kiểm tra mở dự án phục hồi đúng tab**
  Tạo `tests/ui/test_open_project_restores_saved_tab.py`:
  - Tạo project mẫu có `workspace.json` với `"active_page": "translation"`.
  - Gọi `gui._open_project_by_path(project_dir)`.
  - Xác nhận sau khi nạp xong: `gui._active_nav_index == 8` và stack hiển thị trang Dịch.
  - Tạo project mẫu có `workspace.json` với `"active_page": "export"`.
  - Gọi `gui._open_project_by_path(project_dir)`.
  - Xác nhận: `gui._active_nav_index == 5`.
- [ ] **Bước 3.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_open_project_restores_saved_tab.py -v`.
- [ ] **Bước 3.3: Hiệu chỉnh luồng mở dự án trong `ui/Gui.py`**
  - Tại `_open_project_by_path()` (dòng 5190-5210):
    Đảm bảo lệnh `self.workspace_service.restore_workspace()` được thực thi sau khi hoàn tất nạp dữ liệu và chuyển trang đúng theo `workspace.active_page` mà không bị ghi đè bởi bất kỳ lệnh `switch_page(1)` nào sau đó.
- [ ] **Bước 3.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/ui/test_open_project_restores_saved_tab.py -v`.
- [ ] **Bước 3.5: Commit mã nguồn Tác vụ 3**
  `git commit -m "fix(ui): ensure open project restores saved active tab seamlessly (PLAN-TAB-PERSISTENCE-RESTORE-001)"`

---

### Tác vụ 4: Kiểm định Hồi quy Toàn diện Toàn bộ Hệ thống
**Files:**
* Kiểm thử: Toàn bộ suite Desktop GUI Flow Specs & Translation/Core Tests

- [ ] **Bước 4.1: Chạy kiểm định toàn bộ các bộ test hệ thống**
  ```powershell
  # 1. Bộ test phục hồi tab workspace & switch page
  .\.venv\Scripts\python.exe -m pytest tests/core/test_workspace_tab_persistence.py tests/ui/test_tab_switch_persistence_integration.py tests/ui/test_open_project_restores_saved_tab.py -v

  # 2. Bộ test ổn định luồng CAT Studio & Persistence Filter
  .\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py tests/translation/test_cat_persistence_filter.py tests/translation/test_cat_status_sanitization.py -v

  # 3. Bộ test cô lập tab dịch & UX dashboard
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_translation_transfer_isolation.py tests/ui/test_recent_projects_ui.py -v

  # 4. Toàn bộ Desktop GUI Flow Specs (POM Triad: CAT Studio, SubEditor, Timeline)
  .\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v
  ```
- [ ] **Bước 4.2: Commit hoàn tất kế hoạch**
  `git commit -m "chore: verify tab persistence across save/autosave and full regression suite (PLAN-TAB-PERSISTENCE-RESTORE-001)"`
