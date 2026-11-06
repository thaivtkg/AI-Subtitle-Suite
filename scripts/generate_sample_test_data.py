# -*- coding: utf-8 -*-
"""
Script tạo trọn bộ dữ liệu mẫu (Sample Test Data) phục vụ kiểm thử thực tế 8 tính năng mới:
1. Video mẫu 25s (MP4, 720p 30fps, âm thanh đa tần số có đoạn ngắt nghỉ cho VAD).
2. File phụ đề test_subtitles_all_features.srt: chứa các ca test CPS > 20, Overlap va chạm, Normal.
3. File phụ đề sample_external_en.srt: kiểm tra chuyển nguồn SRT không mất dữ liệu (BUG-DATA-002).
4. Khởi tạo sẵn dữ liệu mẫu trong Translation Memory (tm.db) để test Ghost-Text Copilot (FR-06).
5. File hướng dẫn chi tiết từng bước HUONG_DAN_TEST_CHI_TIET.md.
"""
import os
import sys
import wave
import struct
import math
import subprocess

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
OUT_DIR = os.path.join(PROJECT_ROOT, "sample_test_data")
os.makedirs(OUT_DIR, exist_ok=True)

# -------------------------------------------------------------
# 1. TẠO FILE ÂM THANH WAV ĐA PHÂN ĐOẠN (Speech tones + silence)
# -------------------------------------------------------------
wav_path = os.path.join(OUT_DIR, "temp_audio.wav")
mp4_path = os.path.join(OUT_DIR, "sample_video_25s.mp4")

sample_rate = 16000
duration_sec = 25
total_samples = sample_rate * duration_sec

with wave.open(wav_path, "w") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    
    # Tạo chuỗi âm thanh: 
    # 0-5s: Âm thanh 300Hz (Tone giả lập tiếng nói rõ -> VAD Teal #2DD4BF)
    # 5-8s: Yên lặng (Silence -> VAD Slate Gray #334155)
    # 8-14s: Âm thanh 600Hz vừa phải (VAD Amber/Teal)
    # 14-17s: Yên lặng (Silence)
    # 17-25s: Âm thanh 450Hz
    frames = bytearray()
    for i in range(total_samples):
        t = i / sample_rate
        val = 0.0
        if 0 <= t < 5:
            val = 0.7 * math.sin(2 * math.pi * 300 * t) + 0.3 * math.sin(2 * math.pi * 600 * t)
        elif 5 <= t < 8:
            val = 0.001 * math.sin(2 * math.pi * 100 * t)
        elif 8 <= t < 14:
            val = 0.5 * math.sin(2 * math.pi * 500 * t) + 0.2 * math.sin(2 * math.pi * 1000 * t)
        elif 14 <= t < 17:
            val = 0.0
        else:
            val = 0.6 * math.sin(2 * math.pi * 400 * t)
            
        sample_int = int(max(-32768, min(32767, val * 32767)))
        frames.extend(struct.pack("<h", sample_int))
        
    wav_file.writeframes(frames)

print(f"[OK] Đã tạo file WAV mẫu: {wav_path}")

# -------------------------------------------------------------
# 2. GHÉP HÌNH ẢNH VIDEO 720p 30FPS VÀ ÂM THANH BẰNG FFMPEG
# -------------------------------------------------------------
cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", "testsrc=duration=25:size=1280x720:rate=30",
    "-i", wav_path,
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "128k",
    "-shortest",
    mp4_path
]
subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if os.path.exists(wav_path):
    os.remove(wav_path)
print(f"[OK] Đã tạo video mẫu MP4 25s: {mp4_path}")

# -------------------------------------------------------------
# 3. TẠO FILE PHỤ ĐỀ CHÍNH test_subtitles_all_features.srt
# -------------------------------------------------------------
srt_content = """1
00:00:01,000 --> 00:00:04,500
Chào mừng các bạn đến với bộ dữ liệu kiểm thử của AI Subtitle Suite!

2
00:00:05,200 --> 00:00:06,600
Hôm nay chúng ta sẽ cùng kiểm thử tính năng cảnh báo tốc độ đọc rất nhanh này xem cảnh báo CPS viền đỏ cam và nút tách câu thông minh có xuất hiện không nhé!

3
00:00:07,000 --> 00:00:11,500
Đây là câu phụ đề thứ ba đang bị đè lên mốc thời gian của câu thứ tư bên dưới.

4
00:00:10,000 --> 00:00:14,000
Câu thứ tư này bắt đầu từ giây thứ 10, trong khi câu ba kết thúc ở giây 11.5 gây va chạm Overlap.

5
00:00:14,800 --> 00:00:18,500
Khoảng lặng này thích hợp để bạn thử kéo chuột kết hợp phím Alt (Alt + Drag) rà đĩa âm thanh Jog-Audio.

6
00:00:19,000 --> 00:00:24,000
Hãy thử bấm Ctrl + P để tách cửa sổ Video PiP rời và trải nghiệm chia đôi màn hình Windows 11 nhé!
"""

srt_path = os.path.join(OUT_DIR, "test_subtitles_all_features.srt")
with open(srt_path, "w", encoding="utf-8") as f:
    f.write(srt_content.strip())
print(f"[OK] Đã tạo file phụ đề chính: {srt_path}")

# -------------------------------------------------------------
# 4. TẠO FILE PHỤ ĐỀ NGOÀI sample_external_en.srt (Test Multi-Source)
# -------------------------------------------------------------
ext_srt_content = """1
00:00:01,000 --> 00:00:04,500
Welcome to AI Subtitle Suite - Next Generation Subtitle Platform!

2
00:00:08,000 --> 00:00:13,000
Testing Multi-Source subtitle switching without losing original data.

3
00:00:18,000 --> 00:00:23,000
Professional desktop video subtitle editing with local AI acceleration.
"""
ext_srt_path = os.path.join(OUT_DIR, "sample_external_en.srt")
with open(ext_srt_path, "w", encoding="utf-8") as f:
    f.write(ext_srt_content.strip())
print(f"[OK] Đã tạo file phụ đề ngoài: {ext_srt_path}")

# -------------------------------------------------------------
# 5. NẠP DỮ LIỆU MẪU VÀO TRANSLATION MEMORY (Test Ghost-Text FR-06)
# -------------------------------------------------------------
try:
    from core.database.tm_manager import TranslationMemoryManager
    tm = TranslationMemoryManager()
    sample_pairs = [
        ("Chào mừng các bạn đến với bộ dữ liệu kiểm thử của AI Subtitle Suite!", "Chào mừng bạn đến với nền tảng biên dịch AI Subtitle Suite chuyên nghiệp."),
        ("Chào mừng", "Chào mừng quý khán giả đang theo dõi chương trình."),
        ("Hôm nay chúng ta", "Hôm nay chúng ta sẽ cùng khám phá những tính năng đột phá nhất."),
        ("Đây là câu phụ đề", "Đây là câu phụ đề mẫu được trích xuất tự động từ bộ nhớ dịch thuật."),
        ("Xin chào", "Xin chào tất cả mọi người, chúc các bạn một ngày làm việc hiệu quả!"),
    ]
    for src, tgt in sample_pairs:
        tm.add_segment(source_text=src, target_text=tgt, lang_pair="ja-vi")
    print(f"[OK] Đã nạp thành công 5 cặp câu mẫu vào Translation Memory (tm.db)")
except Exception as e:
    print(f"[WARN] Không thể nạp tự động vào TM: {e}")

# -------------------------------------------------------------
# 6. TẠO FILE HƯỚNG DẪN TEST CHI TIẾT
# -------------------------------------------------------------
guide_content = """# HƯỚNG DẪN KIỂM THỬ THỰC TẾ TRỌN BỘ 8 TÍNH NĂNG MỚI
## AI Subtitle Suite (Đã hoàn thiện & Nghiệm thu 100%)

Thư mục dữ liệu mẫu: `D:\\ai-subtitle-suite\\sample_test_data\\`
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
1. Mở `✨ Bảng Điều Khiển AI` $\rightarrow$ Tab `Generate`.
2. Bấm `+ Add External SRT...` và chọn file `sample_external_en.srt` (3 câu tiếng Anh).
   - Editor hiển thị 3 câu tiếng Anh.
3. Mở combobox `Subtitle Source` và chọn lại `Auto-detected SRT`:
   - 👀 **Quan sát:** Toàn bộ 6 câu phụ đề tiếng Việt ban đầu khôi phục đầy đủ 100%, **KHÔNG BỊ XÓA TRẮNG (0/0)** như lỗi cũ!
"""

guide_path = os.path.join(OUT_DIR, "HUONG_DAN_TEST_CHI_TIET.md")
with open(guide_path, "w", encoding="utf-8") as f:
    f.write(guide_content.strip())
print(f"[OK] Đã tạo file hướng dẫn chi tiết: {guide_path}")

print("\n=== HOÀN TẤT TẠO TOÀN BỘ SAMPLE TEST DATA ===")
