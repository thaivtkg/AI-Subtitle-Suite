# KẾ HOẠCH BÀN GIAO KỸ THUẬT & KHẮC PHỤC KHUYẾT TẬT QA
## GIẢI QUYẾT TRIỆT ĐỂ CÁC KHOẢNG TRỐNG TỰ NHIÊN (STYLE, RESCAN, GEN SUB LẺ & UX ERROR)

---

**Người gửi:** Hội đồng Thẩm định QA Độc lập & Trưởng Bộ Phận Đảm Bảo Chất Lượng (Principal QA Lead)  
**Người nhận:** Principal Python Developer & Senior Qt Development Team  
**Hệ thống:** AI Subtitle Suite (`D:\ai-subtitle-suite`)  
**Tài liệu đối chiếu:** `USER_ACCEPTANCE_TEST_REPORT_STYLE_RESCAN_GEN_ODD_PROMPTS.md`  
**Trạng thái mã nguồn:** ĐÓNG BĂNG KIỂM SOÁT (STRICT NO-CODE MODE – WORKING TREE SẠCH 100%)  
**Mục tiêu bàn giao:** Phân tích nguyên nhân gốc rễ (Root Cause), quy hoạch kiến trúc, đặc tả chi tiết 4 Module cần khắc phục và ma trận kiểm thử nghiệm thu để Đội ngũ Dev triển khai mã nguồn.  

---

## I. TỔNG QUAN PHÂN LOẠI KHUYẾT TẬT (DEFECT CLASSIFICATION MATRIX)

Hội đồng QA chính thức thẩm định và công nhận **100% tính xác thực (ACCEPTED)** của 4 vấn đề do phiên kiểm thử người dùng thực tế phát hiện:

| Mã Khuyết Tật | Mức Độ | Module Ảnh Hưởng | Tóm Tắt Lỗi | Phân Loại QA | Hành Động Yêu Cầu |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **FIND-AGENT-STYLE-001** | **P0 - Critical** | `core/agent/agent_tool_registry.py`<br>`core/agent/agent_copilot_controller.py` | Tool `apply_subtitle_style` chưa được đăng ký; parser gán cứng Arial vàng #FFFF00, bỏ qua font size, viền, bóng đổ. | **ACCEPTED** | Đăng ký tool `apply_subtitle_style`, xây dựng bộ bóc tách style đa tham số và kết nối với overlay renderer. |
| **FIND-AGENT-RESCAN-001** | **P0 - Critical** | `core/agent/agent_copilot_controller.py`<br>`core/agent/agent_tool_registry.py` | Không nhận diện intent "quét lại" / "rescan", rơi vào `process_general_task` (tool chưa đăng ký gây crash). | **ACCEPTED** | Thêm intent parser cho "quét lại" (câu đơn, dải câu, khoảng thời gian) và đăng ký tool `rescan_subtitles`. |
| **FIND-AGENT-GEN-ODD-001** | **P0 - Critical** | `core/agent/agent_copilot_controller.py`<br>`core/agent/agent_tool_registry.py` | Nhầm lẫn ngữ pháp "3 câu đầu" (count) vs "câu 3" (index/range); tool `run_asr` chưa được đăng ký trong runtime. | **ACCEPTED** | Phân nhánh ngữ pháp "N câu" vs "câu N"; đăng ký tool `run_asr` hỗ trợ cả toàn bộ và lọc theo `indices`. |
| **FIND-AGENT-UX-FAILED-STATE-001** | **P1 - High** | `ui/components/agent_report_inspector_widget.py`<br>`ui/pages/ai_agent_mission_control_page.py` | Khi task thất bại, Badge vẫn hiện `CHỜ BẠN DUYỆT`, kết quả trống rỗng, không hiển thị nguyên nhân lỗi gây ngõ cụt UX. | **ACCEPTED** | Bổ sung trạng thái `failed` (badge đỏ `THẤT BẠI`), render thẻ chi tiết lỗi và cho phép người dùng bấm Retry/Redo. |

---

## II. PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ & ĐẶC TẢ GIẢI PHÁP KỸ THUẬT CHO DEV

### 1. Module Style Subtitle (`FIND-AGENT-STYLE-001`)
- **Root Cause:** `register_default_tools()` trong `agent_tool_registry.py` thiếu `apply_subtitle_style`; parser trong `agent_copilot_controller.py` gán cứng màu vàng Arial.
- **Yêu cầu triển khai:**
  1. Viết hàm `apply_subtitle_style(...)` nhận các tham số: `font_name`, `font_size`, `font_color`, `outline_color`, `outline_width`, `shadow`, `position`.
  2. Bóc tách regex màu (Hex hoặc tên tiếng Việt), font (Roboto, Arial, v.v.), size (`cỡ chữ 24`), viền (`viền đen`), bóng đổ (`shadow=True`).
  3. Cầu nối gọi `main_window._on_subtitle_style_changed(applied_style)` để làm mới ngay video player overlay.

### 2. Module Quét Lại / Rescan (`FIND-AGENT-RESCAN-001`)
- **Root Cause:** Thiếu intent parser cho các từ khóa "quét lại", "rescan", "scan lại".
- **Yêu cầu triển khai:**
  1. Thêm nhánh bóc tách:
     - Câu đơn: `quét lại câu 1` $\rightarrow$ `segment_indices=[1]`
     - Dải câu: `quét lại từ câu 2 đến câu 4` $\rightarrow$ `segment_indices=[2, 3, 4]`
     - Thời gian: `từ giây 10 đến 20` $\rightarrow$ `start_ms=10000, end_ms=20000`
     - Toàn bộ: `scope="all"`
  2. Đăng ký tool `rescan_subtitles(...)` trong `agent_tool_registry.py`.
  3. Đăng ký tool fallback `process_general_task(...)` để ngăn ngừa `ValueError`.

### 3. Module Nhận Diện Giọng Nói Lẻ / Gen Sub Lẻ (`FIND-AGENT-GEN-ODD-001`)
- **Root Cause:** Regex cũ `(\d+)\s*câu` chỉ hỗ trợ "3 câu đầu", không hỗ trợ "câu 3"; tool `run_asr` chưa đăng ký.
- **Yêu cầu triển khai:**
  1. Tách biệt 2 dạng ngữ pháp: Số lượng từ đầu (`limit=N`) và Vị trí/Dải câu cụ thể (`indices=[...]`).
  2. Đăng ký tool `run_asr(limit=None, indices=None, language="auto", ...)` trong `agent_tool_registry.py`.

### 4. Module Trải Nghiệm Lỗi Trực Quan (`FIND-AGENT-UX-FAILED-STATE-001`)
- **Root Cause:** `_on_step_failed` gọi `set_badge_status("waiting")` ("CHỜ BẠN DUYỆT") khi lỗi; thiếu chế độ `"failed"` và thiếu thẻ hiển thị lỗi.
- **Yêu cầu triển khai:**
  1. Bổ sung trạng thái `"failed"` / `"error"` vào `set_badge_status` trong `agent_report_inspector_widget.py` (badge đỏ `THẤT BẠI`).
  2. Thêm phương thức `show_error_report(step_idx, step, error_msg)` vào `EditableResultReportWidget` hiển thị nguyên nhân lỗi và hướng dẫn xử lý.
  3. Kích hoạt nút `btn_redo_task` ("Yêu cầu làm lại task này") để người dùng thoát khỏi ngõ cụt UX.

---

## III. MA TRẬN KIỂM THỬ NGHIỆM THU CHO DEVELOPER (QA ACCEPTANCE CRITERIA)

| Mã Test | Phạm Vi Kiểm Thử | Dữ Liệu Đầu Vào (Prompt Mẫu) | Kết Quả Kỳ Vọng Bắt Buộc | Trạng Thái Gate |
| :---: | :--- | :--- | :--- | :---: |
| **TC-ACC-STYLE-01** | Bóc tách Font & Màu | `"đổi style sub chữ vàng viền đen cỡ 24 font Roboto"` | Plan sinh đúng `font_name="Roboto"`, `font_size=24`, `font_color="#FFFF00"`, `outline_color="#000000"`. Thực thi PASS. | **P0 Gate** |
| **TC-ACC-STYLE-02** | Đồng bộ Video Overlay | Bấm Duyệt style | `_on_subtitle_style_changed` được gọi, `video_player.subtitle_overlay` cập nhật đúng style. | **P0 Gate** |
| **TC-ACC-RESCAN-01** | Quét lại câu đơn | `"quét lại câu 1"` | Plan sinh bước `rescan_subtitles(scope="selected", segment_indices=[1])`. Thực thi PASS. | **P0 Gate** |
| **TC-ACC-RESCAN-02** | Quét lại dải câu | `"quét lại từ câu 2 đến câu 4"` | Plan sinh bước với `segment_indices=[2, 3, 4]`. Thực thi PASS. | **P0 Gate** |
| **TC-ACC-RESCAN-03** | Quét lại theo thời gian | `"quét lại từ giây 10 đến 20"` | Plan sinh bước với `start_ms=10000, end_ms=20000`. Thực thi PASS. | **P1 Gate** |
| **TC-ACC-GEN-01** | Gen sub câu chỉ định | `"gen sub câu 3"` | Nhận diện đúng câu 3 (không nhầm thành toàn bộ video). Thực thi PASS. | **P0 Gate** |
| **TC-ACC-GEN-02** | Gen sub dải câu | `"nhận diện từ câu 1 đến 3"` | Nhận diện đúng dải `[1, 2, 3]`. Thực thi PASS. | **P0 Gate** |
| **TC-ACC-UX-ERR-01** | Hiển thị Badge Lỗi | Cố tình nạp lệnh lỗi | Badge chuyển đỏ `THẤT BẠI`, không còn hiện `CHỜ BẠN DUYỆT`. | **P1 Gate** |
| **TC-ACC-UX-ERR-02** | Thoát Ngõ Cụt UX | Nhấn nút `Yêu cầu làm lại task này` | Khôi phục trạng thái ban đầu mượt mà, cho phép nhập lệnh mới. | **P1 Gate** |

---

## IV. QUY TRÌNH BÀN GIAO & CAM KẾT VAI TRÒ QA ĐỘC LẬP

Hội đồng QA duy trì vị thế thẩm định độc lập, **TUYỆT ĐỐI KHÔNG CAN THIỆP MÃ NGUỒN**. Working tree của dự án được bảo toàn nguyên trạng 100%. Hồ sơ kỹ thuật này được bàn giao trọn vẹn cho **Đội ngũ Developer** để lập kế hoạch chi tiết, tạo nhánh `feature/agent-prompt-gaps-resolution` và triển khai theo quy trình TDD.
