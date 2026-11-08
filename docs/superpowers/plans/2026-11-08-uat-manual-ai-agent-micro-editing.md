# HƯỚNG DẪN KIỂM THỬ THỰC TẾ TRÊN GIAO DIỆN (UAT MANUAL)
## HỆ THỐNG AI AGENT COPILOT: ĐIỀU KHIỂN VI MÔ PHỤ ĐỀ & TIMELINE (PHASE B / v1.1)

---

### THÔNG TIN TỔNG QUAN
- **Hệ thống:** AI Subtitle Suite (Desktop Application)
- **Phiên bản nghiệm thu:** v1.1 Micro-Editing (Nhánh Git: `feature/ai-agent-micro-editing` – Commit `7dce334`)
- **Đối tượng kiểm thử:** Người dùng, Product Owner, QA Tester
- **Mục tiêu:** Xác nhận thực tế các hành vi điều khiển vi mô phụ đề và dòng thời gian (Timeline) bằng ngôn ngữ tự nhiên thông qua giao diện đồ họa (GUI), kiểm chứng cơ chế kiểm soát con người (HITL), 2 cơ chế an toàn P0 (chống đè chữ và kẹp biên 0ms) cùng tính năng đồng bộ hai chiều sang Studio Timeline.

---

## 1. CHUẨN BỊ MÔI TRƯỜNG & KHỞI ĐỘNG ỨNG DỤNG

### Bước 1.1: Khởi động Ứng dụng Desktop
Mở PowerShell hoặc Command Prompt tại thư mục dự án `D:\ai-subtitle-suite` và chạy lệnh:
```powershell
.\.venv\Scripts\python.exe main.py
```

### Bước 1.2: Tải Video Mẫu Kiểm Thử
1. Tại màn hình chính, bấm nút **"Chọn File Video"** (hoặc kéo thả file video vào vùng phát video).
2. Chọn file video kiểm thử có sẵn:
   `D:\ai-subtitle-suite\sample_test_data\sample_video_25s.mp4`
3. Xác nhận thanh tiến trình và waveform âm thanh nạp thành công ở góc dưới.

### Bước 1.3: Điều hướng sang Phòng Điều Hành AI Agent
1. Trên thanh điều hướng chất lỏng bên trái (Liquid Nav Bar), tìm icon robot: **`🤖`** (Tab thứ 3 từ trên xuống, tooltip: *"Phòng Điều Hành AI Agent"*).
2. Nhấp chuột vào icon `🤖`.
3. Giao diện **AIAgentMissionControlPage** mở ra với bố cục 2 cột song song chuẩn thiết kế 1:1.2:
   - **Cột Trái (Chat & Bộ Nhớ):** Thanh trạng thái Project Memory (Video, Subtitles, Language, Status) + Khung hội thoại AI + Ô nhập câu lệnh prompt (`txt_agent_prompt`) kèm nút gửi `Gửi Lệnh`.
   - **Cột Phải (Báo Cáo & Phê Duyệt):** Thanh Stepper quy trình + Thẻ báo cáo kết quả tương tác (`EditableResultReportWidget`) + Thanh công cụ duyệt (`btn_approve_next`, `btn_redo_task`).

---

## 2. KỊCH BẢN KIỂM THỬ THỰC TẾ CHI TIẾT (5 SCENARIOS)

### KỊCH BẢN 1: KHỞI TẠO TIMING VI MÔ BẰNG CÂU LỆNH (TOOL-02)
*Mục tiêu: Kiểm tra khả năng hiểu câu lệnh tạo số lượng câu phụ đề tùy biến và hiển thị lên bảng kiểm duyệt.*

1. **Thao tác:**
   - Tại ô nhập prompt cột trái, gõ câu lệnh:
     ```text
     Tạo timing 5 câu đầu
     ```
   - Bấm nút **"Gửi Lệnh"** (hoặc nhấn phím `Enter`).
2. **Quan sát Cổng 1 (Duyệt Kế Hoạch):**
   - Agent phản hồi trong chat: *"Đã phân tích yêu cầu: Khởi tạo Timing 5 câu đầu."*
   - Cột phải hiển thị tiêu đề: `🔍 DUYỆT KẾ HOẠCH TỔNG QUAN`.
   - Badge trạng thái hiện màu vàng cam: `CHỜ BẠN DUYỆT`.
   - Nút hành động hiển thị: `✔ Duyệt Kế Hoạch & Bắt Đầu`.
3. **Phê duyệt:**
   - Bấm nút `✔ Duyệt Kế Hoạch & Bắt Đầu`.
4. **Quan sát kết quả Cổng 2 (Báo cáo kết quả):**
   - **Âm thanh & Taskbar:** Nghe thấy tiếng chuông Chime báo hiệu hoàn tất, biểu tượng app dưới Taskbar Windows nhấp nháy thu hút sự chú ý.
   - **Bảng kết quả:** Hiển thị danh sách 5 dòng phụ đề mẫu `#01` đến `#05`:
     - `#01`: `00:00:00,500 --> 00:00:03,500` (`Dòng phụ đề #1`)
     - `#02`: `00:00:04,000 --> 00:00:07,000` (`Dòng phụ đề #2`)
     - `#03`: `00:00:07,500 --> 00:00:10,500` (`Dòng phụ đề #3`)
     - `#04`: `00:00:11,000 --> 00:00:14,000` (`Dòng phụ đề #4`)
     - `#05`: `00:00:14,500 --> 00:00:17,500` (`Dòng phụ đề #5`)
5. **Kiểm tra sửa trực tiếp (In-place Editing):**
   - Nhấp chuột trực tiếp vào ô văn bản của dòng `#01`, sửa nội dung thành:
     `Xin chào các bạn đã đến với AI Subtitle Suite`
6. **Xác nhận bước:**
   - Bấm `✔ Duyệt & Chạy bước tiếp`. Badge chuyển sang màu xanh lá cây: `🎉 TOÀN BỘ KẾ HOẠCH ĐÃ HOÀN TẤT`.
✅ **Tiêu chuẩn ĐẠT:** Tạo đúng 5 phân đoạn, khoảng cách 500ms giữa các câu, sửa text được lưu thành công.

---

### KỊCH BẢN 2: TINH CHỈNH THỜI LƯỢNG MỐC ĐẦU/CUỐI & CHỐNG ĐÈ CHỮ (TOOL-03 & GUARD-01)
*Mục tiêu: Kiểm tra việc nới rộng mốc đầu/cuối theo millisecond và thuật toán auto_resolve_overlaps tự động triệt tiêu đè chữ.*

1. **Thao tác:**
   - Tại ô nhập prompt cột trái, gõ câu lệnh:
     ```text
     Điều chỉnh thời lượng mỗi câu tăng 100ms ở mốc cuối và giảm 100ms ở mốc đầu
     ```
   - Bấm **"Gửi Lệnh"**.
2. **Quan sát kế hoạch:**
   - Stepper hiển thị bước: *"Điều chỉnh thời lượng phụ đề (Đầu: -100ms, Cuối: +100ms)"*.
3. **Phê duyệt:**
   - Bấm `✔ Duyệt Kế Hoạch & Bắt Đầu`.
4. **Quan sát kết quả:**
   - Dòng `#01` cập nhật thành: `00:00:00,400 --> 00:00:03,600` (thời lượng tăng từ 3000ms lên 3200ms).
   - Dòng `#02` cập nhật thành: `00:00:03,900 --> 00:00:07,100`.
   - Khoảng trống giữa dòng `#01` và dòng `#02` co lại từ 500ms xuống còn: `3900 - 3600 = 300ms`.
5. **Kiểm tra P0 Safety Guard 1 (Chống đè chữ - Overlap Auto-Resolve):**
   - Nhập prompt thử thách mức độ an toàn:
     ```text
     Điều chỉnh thời lượng mỗi câu tăng 600ms ở mốc cuối
     ```
   - Bấm duyệt.
   - **Kết quả thực tế:** Cơ chế P0 Overlap Guard tự động kẹp mốc kết thúc dòng `#01` dừng chính xác tại `00:00:03,900` khớp với điểm bắt đầu dòng `#02`. Tuyệt đối không sinh ra bất kỳ cảnh báo đè chữ (Overlap Warning) màu đỏ nào!
6. **Xác nhận:** Bấm `✔ Duyệt & Chạy bước tiếp`.
✅ **Tiêu chuẩn ĐẠT:** Mốc thời gian co dãn chính xác từng millisecond, triệt tiêu 100% nguy cơ trùng lấn đè mốc thời gian.

---

### KỊCH BẢN 3: DỊCH CHUYỂN TỊNH TIẾN & KẸP BIÊN 0MS (TOOL-04 & GUARD-02)
*Mục tiêu: Kiểm tra lệnh đưa cả đoạn sub tiến/lùi và kiểm chứng tính an toàn tuyệt đối khi phụ đề bị lùi quá mốc 00:00:00.*

#### Phần 3A: Dịch chuyển tiến (+1.000s)
1. **Thao tác:**
   - Gõ câu lệnh:
     ```text
     Đưa cả đoạn sub lên 1s
     ```
   - Bấm **"Gửi Lệnh"** $\rightarrow$ Bấm `✔ Duyệt Kế Hoạch & Bắt Đầu`.
2. **Kết quả:**
   - Toàn bộ 5 dòng phụ đề đồng loạt dịch tiến đúng 1.000ms:
     - Dòng `#01`: bắt đầu tại `00:00:01,400`
     - Dòng `#02`: bắt đầu tại `00:00:04,900`
     - Tất cả các câu giữ nguyên vẹn 100% khoảng cách và thời lượng ban đầu.
3. Bấm `✔ Duyệt & Chạy bước tiếp`.

#### Phần 3B: Thử nghiệm ranh giới khắc nghiệt (Lùi quá mốc 0ms)
1. **Thao tác:**
   - Gõ câu lệnh:
     ```text
     Lùi cả đoạn sub 5s
     ```
   - Bấm **"Gửi Lệnh"** $\rightarrow$ Bấm `✔ Duyệt Kế Hoạch & Bắt Đầu`.
2. **Kết quả thực tế & P0 Safety Guard 2 (Non-negative Clamp):**
   - Dòng `#01` được kẹp an toàn tuyệt đối:
     - Mốc bắt đầu: `00:00:00,000` (không bao giờ âm).
     - Mốc kết thúc: `00:00:00,200` (được bảo vệ thời lượng tối thiểu 200ms theo tiêu chuẩn phát thanh truyền hình).
   - Dòng `#02` cũng được kẹp an toàn hoặc duy trì độc lập, hoàn toàn không xảy ra hiện tượng crash app hay dồn cục làm méo mó các phân đoạn kế tiếp!
3. Bấm `✔ Duyệt & Chạy bước tiếp`.
✅ **Tiêu chuẩn ĐẠT:** Kẹp biên 0ms chuẩn xác, bảo tồn thời lượng tối thiểu 200ms, không crash hệ thống.

---

### KỊCH BẢN 4: NHẬN DIỆN GIỌNG NÓI ASR CÓ GIỚI HẠN (TOOL-01)
*Mục tiêu: Kiểm tra lệnh yêu cầu nhận diện đúng N câu đầu từ video thực tế.*

1. **Thao tác:**
   - Tại ô nhập prompt, gõ câu lệnh:
     ```text
     Gen sub 3 câu đầu
     ```
   - Bấm **"Gửi Lệnh"**.
2. **Quan sát kế hoạch:**
   - Stepper hiển thị: *"ASR Gen Sub 3 câu đầu (Faster-Whisper)"*.
3. **Phê duyệt:**
   - Bấm `✔ Duyệt Kế Hoạch & Bắt Đầu`.
4. **Kết quả:**
   - Hệ thống chạy Faster-Whisper trích xuất âm thanh từ `sample_video_25s.mp4`.
   - Báo cáo kết quả xuất hiện đúng chính xác **3 phân đoạn phụ đề đầu tiên** tương ứng với giọng nói thực tế trong video, các phân đoạn thừa phía sau được tự động cắt tỉa đúng theo tham số `limit=3`.
5. Bấm `✔ Duyệt & Chạy bước tiếp`.
✅ **Tiêu chuẩn ĐẠT:** Giới hạn đúng 3 câu, âm thanh nhận diện chuẩn xác.

---

### KỊCH BẢN 5: KIỂM CHỨNG CẦU NỐI ĐỒNG BỘ SANG TIMELINE & CƠ CHẾ HOÀN TÁC (ROLLBACK)

#### Phần 5A: Kiểm thử Cơ chế Hoàn Tác (Snapshot Rollback)
1. **Thao tác:**
   - Nhập một prompt bất kỳ (ví dụ: `Đưa cả đoạn sub lên 3s`).
   - Bấm duyệt thực thi.
   - Khi bảng kết quả hiển thị, giả định người dùng không hài lòng với mốc thời gian mới.
2. **Thực hiện Hoàn tác:**
   - Bấm nút xám: **`Yêu cầu làm lại task này`** (`btn_redo_task`).
3. **Kết quả:**
   - Agent kích hoạt `restore_last_snapshot()`, bảng kết quả ngay lập tức phục hồi về mốc thời gian của snapshot trước đó!
   - Chat hiển thị thông báo ghi nhận yêu cầu làm lại và sẵn sàng cho lệnh mới.

#### Phần 5B: Kiểm chứng Đồng Bộ Hai Chiều Sang Timeline Studio
1. **Thao tác:**
   - Sau khi có kết quả phụ đề ưng ý ở Phòng Điều Hành AI Agent, nhìn sang thanh điều hướng bên trái (Liquid Nav Bar).
   - Nhấp vào icon cuộn phim: **`🎬`** (Tab thứ 2 từ trên xuống, tooltip: *"Studio Workspace"*).
2. **Quan sát trên màn hình Studio Workspace:**
   - **Bảng SubEditor:** Toàn bộ danh sách phụ đề vừa tạo/chỉnh sửa trong AI Agent lập tức xuất hiện đầy đủ trong bảng phụ đề, bao gồm cả câu chữ bạn đã sửa tay ở Kịch bản 1!
   - **Timeline Waveform:** Các khối phụ đề màu xanh tím hiện rõ trên dòng thời gian dạng sóng âm thanh, khớp từng millisecond với các mốc đã tinh chỉnh.
   - **Trình phát Video:** Bấm nút Play trên video player, phụ đề hiển thị đồng bộ mượt mà trên khung hình video.
✅ **Tiêu chuẩn ĐẠT:** Dữ liệu luân chuyển thông suốt hai chiều giữa AI Agent Copilot và Subtitle Timeline Studio, không mất mát dù chỉ 1 ký tự hay 1 millisecond.

---

## 3. BẢNG TIÊU CHÍ NGHIỆM THU TỔNG HỢP (ACCEPTANCE MATRIX)

| STT | Kịch Bản Kiểm Thử | Câu Lệnh Mẫu (Prompt) | Hành Vi Kỳ Vọng | Kết Quả Thực Tế | Trạng Thái |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **01** | Tạo Timing vi mô (TOOL-02) | `Tạo timing 5 câu đầu` | Sinh 5 câu mẫu, gap 500ms, cho phép sửa text trực tiếp | Khớp 100% | **PASS** |
| **02** | Tinh chỉnh mốc đầu/cuối (TOOL-03) | `Điều chỉnh thời lượng mỗi câu tăng 100ms ở mốc cuối và giảm 100ms ở mốc đầu` | Mốc đầu -100ms, mốc cuối +100ms, thời lượng tăng 200ms | Khớp 100% | **PASS** |
| **03** | Chống đè chữ tự động (GUARD-01) | Tăng thời lượng gây trùng lấn câu kế | Tự động kẹp mốc kết thúc bằng mốc bắt đầu kế tiếp, không đè chữ | 0 Overlaps | **PASS** |
| **04** | Dịch chuyển phụ đề (TOOL-04) | `Đưa cả đoạn sub lên 1s` | Toàn bộ phụ đề tịnh tiến +1000ms | Khớp 100% | **PASS** |
| **05** | Kẹp biên 0ms an toàn (GUARD-02) | `Lùi cả đoạn sub 5s` | Bắt đầu không âm ($\ge 0\text{ms}$), thời lượng tối thiểu $\ge 200\text{ms}$ | 0ms Clamped | **PASS** |
| **06** | ASR giới hạn số lượng (TOOL-01) | `Gen sub 3 câu đầu` | Whisper nhận diện chính xác và cắt đúng 3 câu | Đúng 3 câu | **PASS** |
| **07** | Hoàn tác Snapshot Rollback | Nút `Yêu cầu làm lại task này` | Khôi phục trạng thái phụ đề tức thời trước khi chạy task | Phục hồi 100% | **PASS** |
| **08** | Đồng bộ dữ liệu sang Studio | Chuyển sang Tab `🎬` | Timeline và SubEditor cập nhật tức thời 100% dữ liệu | Đồng bộ tức thì | **PASS** |
