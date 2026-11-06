# HƯỚNG DẪN KIỂM THỬ THỰC TẾ TRỌN BỘ 8 TÍNH NĂNG MỚI
## AI Subtitle Suite (Đã hoàn thiện & Nghiệm thu 100%)

Thư mục dữ liệu mẫu: `D:\ai-subtitle-suite\sample_test_data\`
Bao gồm:
1. `sample_video_25s.mp4` (Video mẫu 25 giây, 720p 30fps có âm thanh đa tần số và ngắt nghỉ)
2. `test_subtitles_all_features.srt` (Phụ đề thiết kế riêng để kích hoạt toàn bộ tính năng mới)
3. `sample_external_en.srt` (Phụ đề tiếng Anh để test chuyển đổi nguồn Multi-Source)

---

### BÀI TEST 1: CẢNH BÁO TỐC ĐỘ ĐỌC CPS HUD & NÚT TÁCH CÂU THÔNG MINH (FR-01)
1. Mở app AI Subtitle Suite, vào **Studio Workspace**.
2. Nhập file video `sample_video_25s.mp4` và nạp phụ đề `test_subtitles_all_features.srt`.
3. Nhấp chọn **Câu #2**:
   - 👀 **Quan sát:** Thẻ biên tập chuyển sang viền đỏ cam nổi bật.
   - ⚠️ Nhìn thấy cảnh báo: `⚠️ 97.1 CPS (Quá nhanh)`.
   - ⚡ Nút bấm `⚡ Tách câu thông minh` xuất hiện cạnh cảnh báo.
4. Bấm vào nút `⚡ Tách câu thông minh`:
   - Câu #2 tự động tách đôi tại dấu phẩy/chấm gần nhất thành 2 câu có độ dài và mốc thời gian cân đối hoàn hảo!

---

### BÀI TEST 2: PHÁT HIỆN CHỒNG LẤN OVERLAP & NAM CHÂM SNAP VIỀN (FR-02)
1. Trên Timeline, quan sát khu vực giữa **Câu #3** và **Câu #4** (khoảng giây 10.0 -> 11.5):
   - 👀 **Quan sát:** Xuất hiện dải sọc chéo đỏ nhấp nháy nhẹ cảnh báo 2 câu đang đè lên nhau.
   - 🧲 Nút nam châm `🧲 Snap viền` xuất hiện ở thanh công cụ.
2. Bấm vào nút `🧲 Snap viền`:
   - Mép kết thúc của Câu #3 tự động thu về đúng giây `00:00:10,000`, khớp khít với mép bắt đầu của Câu #4, dải sọc đỏ biến mất!

---

### BÀI TEST 3: ĐÈN RỌI SPOTLIGHT CHUỘT 60 FPS TRÊN TOÀN BỘ CÁC TAB (FR-03)
1. Rê chuột trên giao diện Studio Workspace, qua các nút bấm, timeline, bảng phụ đề.
2. Chuyển sang các tab khác: `Dashboard`, `Queue & Output`, `Export Center`, `Settings`, `Dịch thuật AI`.
   - 👀 **Quan sát:** Quầng sáng radial gradient màu xanh sapphire dịu nhẹ (`#38BDF8`) bám theo con trỏ chuột mượt mà 60 FPS, không gây giật lag và không nuốt sự kiện click chuột.

---

### BÀI TEST 4: BẢN ĐỒ NHIỆT MẬT ĐỘ TIẾNG NÓI VAD TRÊN WAVEFORM (FR-04)
1. Nhìn vào thanh dạng sóng (Waveform) của video `sample_video_25s.mp4`:
   - 🟢 Vùng 0s - 5s & 8s - 14s: Dạng sóng có dải màu **Teal (#2DD4BF)** (Giọng nói rõ ràng, $p \ge 0.6$).
   - 🟡 Vùng biên chuyển tiếp: Dải màu **Amber (#F59E0B)** ($0.3 \le p < 0.6$).
   - ⚪ Vùng 5s - 8s & 14s - 17s: Dạng sóng dải màu **Slate Gray (#334155)** (Khoảng lặng yên tĩnh).

---

### BÀI TEST 5: RÀ ĐĨA ÂM THANH JOG-AUDIO VỚI NGẮT ÂM TỨC THÌ (FR-05)
1. Giữ phím **`Alt`** trên bàn phím.
2. Nhấn và kéo chuột (**`Alt + Drag`**) trên dạng sóng Waveform hoặc Timeline:
   - 🔊 Bạn sẽ nghe thấy lát cắt âm thanh 40ms cọ xoẹt liên tục theo đúng vị trí con trỏ chuột (tương tự bàn xoay DJ).
3. Nhả chuột hoặc nhả phím `Alt`:
   - Âm thanh ngắt tức thì ($<10$ms), không bị rè hay phát dư thừa.

---

### BÀI TEST 6: GỢI Ý DỊCH THUẬT MỜ GHOST-TEXT TRONG CAT STUDIO (FR-06)
1. Chuyển sang Tab **`🌐 Dịch thuật AI`**.
2. Chọn Câu #1 và đặt con trỏ vào ô nhập bản dịch:
3. Gõ chữ: **`Chào`**
   - 👀 **Quan sát:** Ngay sau chữ `Chào`, xuất hiện phần gợi ý mờ màu xám xanh `#64748B`: ` mừng bạn đến với nền tảng biên dịch AI Subtitle Suite chuyên nghiệp.`
   - Xuất hiện huy hiệu: `💡 Tab: Nhận gợi ý | Ctrl + →: Nhận từng từ`.
4. Nhấn phím **`Ctrl + Mũi tên phải`**: Từng từ một được nhận vào ô văn bản.
5. Nhấn phím **`Tab`**: Nhận toàn bộ câu gợi ý ngay lập tức!

---

### BÀI TEST 7: TRUE DETACHABLE PIP & CHIA ĐÔI MÀN HÌNH WINDOWS 11 (FR-07)
1. Ở Studio Workspace, nhấn phím **`Ctrl + P`** (hoặc bấm nút `📺 Tách Video (PiP)` trên thanh điều khiển video):
   - 🗗 Cửa sổ Video tách rời thành một cửa sổ Windows độc lập riêng biệt!
   - 📌 Nhấn nút `📌 Đang nổi` để ghim luôn nổi trên các ứng dụng khác.
   - Thử kéo cửa sổ video sang màn hình thứ 2 hoặc nhấn **`Win + Phím Mũi Tên Trái`** để chia nửa màn hình.
   - 👀 **Quan sát ô Video trong app chính:** Được thay thế bằng thẻ `PiPWorkspacePlaceholderWidget` màu tối sang trọng với nút `🗗 Gắn video trở lại đây (Ctrl + P)`.
2. Thử chuyển sang các Tab khác (`Dịch thuật AI`, `Settings`, `Export`):
   - Kích thước ứng dụng và cửa sổ PiP giữ nguyên 100%, không bị co cụm hay giật layout!
3. Nhấn **`Ctrl + P`** lần nữa: Video thu hồi trở lại vị trí cũ trong app chính.

---

### BÀI TEST 8: BẢO VỆ DỮ LIỆU ĐA NGUỒN SUBTITLE SOURCE (BUG-DATA-002 ĐÃ FIX)
1. Mở `✨ Bảng Điều Khiển AI` $ightarrow$ Tab `Generate`.
2. Bấm `+ Add External SRT...` và chọn file `sample_external_en.srt` (3 câu tiếng Anh).
   - Editor hiển thị 3 câu tiếng Anh.
3. Mở combobox `Subtitle Source` và chọn lại `Auto-detected SRT`:
   - 👀 **Quan sát:** Toàn bộ 6 câu phụ đề tiếng Việt ban đầu khôi phục đầy đủ 100%, **KHÔNG BỊ XÓA TRẮNG (0/0)** như lỗi cũ!