# BỘ KỊCH BẢN KIỂM THỬ THỰC TẾ TRÊN GIAO DIỆN (UAT TEST MANUAL v1.4)
## TÍNH NĂNG: AI DYNAMIC REASONING, DETAILED TASK PLANNING & STRICT GATE ISOLATION

---

### MỤC TIÊU KIỂM THỬ (TEST OBJECTIVES)
1. **Xác thực Động Hóa Suy Luận (FR-01 - Anti-Repetition CoT):** Kiểm chứng AI Copilot không còn trả lời máy móc dập khuôn; mỗi câu trả lời đều phân tích bối cảnh kỹ thuật sâu sắc và luân phiên mở đầu/kết bài khác biệt 100%.
2. **Xác thực Phân Lập Hai Cổng Nghiêm Ngặt (FR-02 & FR-03 - Strict Gate Isolation):**
   - **Cổng 1 (Trước khi duyệt):** Bảng bên phải hiển thị thẻ kế hoạch `PlanBriefingCardWidget` (Mục tiêu, Chiến lược, Tham số, An toàn); tuyệt đối **KHÔNG** rò rỉ trước kết quả (0 dòng phụ đề, 0 ô màu swatch).
   - **Cổng 2 (Sau khi duyệt):** Kết xuất kết quả thật (Style Card / Bảng phụ đề click sửa chữ) kèm chuông báo Chime và chớp taskbar.
3. **Xác thực Câu Lệnh Phức Tạp & Fall-back:** Kiểm tra câu lẻ, dải câu, style đa tham số và kịch bản an toàn.

---

## I. CHUẨN BỊ MÔI TRƯỜNG & KHỞI ĐỘNG

1. Mở PowerShell tại thư mục dự án và chạy ứng dụng:
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```
2. Tại màn hình chính, nạp video kiểm thử:
   `sample_test_data/sample_video_25s.mp4`
3. Nhấp vào icon robot **`🤖`** (Tab thứ 3 từ trên xuống trên thanh Liquid Navigation) để vào **Phòng Điều Hành AI Agent**.

---

## II. MA TRẬN 4 BỘ KỊCH BẢN KIỂM THỬ THỰC TẾ (UAT SCENARIOS)

### BỘ KỊCH BẢN 1: ĐO KIỂM TÍNH PHI TRÙNG LẶP & SUY LUẬN ĐỘNG (ANTI-REPETITION CoT)
*Thực hiện gõ liên tiếp 4 câu lệnh sau vào ô prompt và quan sát khung chat bên trái:*

#### Lượt 1: Tạo Timing VAD
- **Câu lệnh (Prompt):**
  ```text
  Tạo timing 5 câu đầu
  ```
- **Hành vi kỳ vọng:**
  - Mở đầu: `🔍 **Phân tích bối cảnh:** Tôi đã xem xét yêu cầu...`
  - Suy luận CoT: Đề cập đến video nguồn 25.0s, giải thích việc sử dụng engine VAD cấu hình chuyên sâu (**CFG-9 Anime JA**) với ngưỡng 0.35 và trích xuất âm thanh 16kHz qua PyAV để lọc sạch tạp âm/intro.
  - Kết bài: Hướng dẫn kiểm tra **Thẻ Kế Hoạch (Cổng 1)** ở cột bên phải.

#### Lượt 2: Tinh chỉnh Style Đa Tham Số
- **Câu lệnh (Prompt):**
  ```text
  Đổi style sub chữ vàng viền đen cỡ 26 font Roboto bóng đổ
  ```
- **Hành vi kỳ vọng:**
  - Mở đầu chuyển sang: `⚡ **Phương án kỹ thuật:** Dựa trên hiện trạng dự án...` *(Khác biệt 100% so với Lượt 1)*.
  - Suy luận CoT: Giải thích lý do chọn font Roboto (cỡ 26px) kết hợp màu `#FFFF00`, viền đen `#000000` (2px) và bóng đổ để tăng độ tương phản, đồng bộ hóa 5 câu hiện có.
  - Kết bài: `👉 Thông số kỹ thuật dự kiến đã được tóm tắt tại Thẻ Duyệt bên phải...`

#### Lượt 3: Tinh chỉnh thời lượng Micro-editing
- **Câu lệnh (Prompt):**
  ```text
  Điều chỉnh thời lượng mỗi câu tăng 150ms ở mốc cuối và giảm 100ms ở mốc đầu
  ```
- **Hành vi kỳ vọng:**
  - Mở đầu chuyển sang: `🎯 **Chiến lược thực hiện:** Tôi hiểu rõ mục đích...`
  - Suy luận CoT: Phân tích mốc đầu (-100ms), mốc cuối (+150ms) và xác nhận tự động bật cơ chế **Overlap Guard** bảo vệ khoảng cách giữa các câu.
  - Kết bài: `👉 Bạn vui lòng xem qua các cam kết an toàn ở khung bên phải...`

#### Lượt 4: Quét lại câu đơn lẻ
- **Câu lệnh (Prompt):**
  ```text
  Quét lại câu 2
  ```
- **Hành vi kỳ vọng:**
  - Mở đầu chuyển sang: `🛠️ **Thiết lập tác vụ:** Tôi đã hoàn thành tính toán...`
  - Suy luận CoT: Xác định tập trung quét lại sóng âm riêng cho câu `#2` mà không làm ảnh hưởng các câu khác.
  - Kết bài: `👉 Hãy xác nhận chiến lược tại Thẻ Kế Hoạch bên phải...`

---

### BỘ KỊCH BẢN 2: ĐO KIỂM PHÂN LẬP HAI CỔNG NGHIÊM NGẶT (STRICT GATE ISOLATION)

#### Thử nghiệm tại Cổng 1 (Plan Review - Trước khi bấm Duyệt):
1. Gõ câu lệnh:
   ```text
   Đổi style sub chữ xanh viền trắng cỡ 28 font Arial
   ```
   và bấm **Gửi Lệnh**.
2. **Quan sát bảng bên phải (Cột Inspector):**
   - Tiêu đề hiện: `🔍 DUYỆT KẾ HOẠCH TỔNG QUAN`.
   - Badge trạng thái hiện màu vàng cam: `CHỜ BẠN DUYỆT`.
   - Nút hành động mang nhãn: `✔ Duyệt Kế Hoạch & Bắt Đầu`.
   - **KHÔNG HIỂN THỊ THẺ STYLE CARD, KHÔNG CÓ Ô MÀU SWATCH, KHÔNG CÓ DÒNG PHỤ ĐỀ.**
   - Thay vào đó là **`PlanBriefingCardWidget`** với 4 khối rõ ràng:
     - 🎯 **Mục tiêu tác vụ:** Tinh Chỉnh Subtitle Style & Formatting.
     - 🛠️ **Chiến lược & Công cụ:** Chip cyan `apply_subtitle_style`.
     - ⚙️ **Thông số dự kiến:** `font_name: Arial`, `font_size: 28`, `font_color: #38BDF8`, `outline_color: #FFFFFF`.
     - 🛡️ **Cam kết an toàn:** Tự động tạo Snapshot dự phòng trước khi thay đổi.

#### Thử nghiệm tại Cổng 2 (Execution Report - Sau khi bấm Duyệt):
1. Bấm nút `✔ Duyệt Kế Hoạch & Bắt Đầu`.
2. **Phản hồi hệ thống:**
   - Nghe tiếng chuông báo nhẹ (Soft Chime) vang lên.
   - Biểu tượng ứng dụng dưới Taskbar Windows nhấp nháy thu hút sự chú ý.
3. **Kết quả hiển thị tại Cổng 2:**
   - Badge trạng thái chuyển màu xanh lá: `HOÀN TẤT`.
   - Thẻ đồ họa trực quan `SubtitleStyleCardWidget` kết xuất với các chip: Font Arial, Cỡ 28px, Ô màu xanh thực tế, Ô viền trắng thực tế.
   - Toàn bộ 5 dòng phụ đề hiển thị bên dưới với nhãn: *"📝 Danh sách câu phụ đề (click sửa trực tiếp trước khi duyệt):"*, cho phép nhấp chuột sửa text trực tiếp.

---

### BỘ KỊCH BẢN 3: CÂU LỆNH PHỤ ĐỀ LẺ & DẢI CÂU CHỈ ĐỊNH (SELECTIVE & RANGE ASR)

#### Kịch bản 3.1: Nhận diện câu chỉ định
- **Prompt:**
  ```text
  Gen sub câu 3
  ```
- **Kỳ vọng:** Agent bóc tách đúng vị trí câu số 3 (`indices=[3]`), không chạy toàn bộ video.

#### Kịch bản 3.2: Quét lại dải câu liên tục
- **Prompt:**
  ```text
  Quét lại từ câu 2 đến câu 4
  ```
- **Kỳ vọng:** Agent bóc tách đúng dải câu `[2, 3, 4]`. Cổng 1 tóm tắt phạm vi quét dải câu `#2, #3, #4`.

#### Kịch bản 3.3: Dịch chuyển thời gian tịnh tiến
- **Prompt:**
  ```text
  Đưa cả đoạn sub lên 1.5s
  ```
- **Kỳ vọng:** Tịnh tiến toàn bộ phụ đề $+1500\text{ms}$. Cổng 1 cam kết an toàn kẹp biên $\ge 0\text{ms}$. Sau khi duyệt, tất cả các mốc thời gian tăng đúng 1.500 giây.

---

### BỘ KỊCH BẢN 4: KHẢ NĂNG PHỤC HỒI & DỰ PHÒNG AN TOÀN (FAIL-SAFE & FALLBACK)

#### Kịch bản 4.1: Câu lệnh không xác định (Safe Fallback)
- **Prompt:**
  ```text
  Phân tích tổng hợp bối cảnh dự án này
  ```
- **Kỳ vọng:** Agent không bị văng lỗi crash `ValueError`. Tự động kích hoạt reasoning dự phòng an toàn, giải thích rõ phương án xử lý chung và đưa ra kế hoạch điều phối phù hợp.

#### Kịch bản 4.2: Thử nghiệm Nút Hoàn Tác (Rollback)
- **Thao tác:** Sau khi chạy một tác vụ đổi style hoặc dịch chuyển thời gian, bấm nút **`Yêu cầu làm lại task này`** (`btn_redo_task`).
- **Kỳ vọng:** Hệ thống kích hoạt Snapshot Rollback, phục hồi tức thì dữ liệu trước khi lệnh được chạy, đưa giao diện về trạng thái sẵn sàng cho lệnh mới.
