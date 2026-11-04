# Kế Hoạch Triển Khai Kỹ Thuật: Phase 2 – Audio-Visual Engineering (DEV-SPEC-PHASE2-AV-001)

## 1. Mục Tiêu
Triển khai Phase 2 thuộc Bản quy hoạch kiến trúc 8 tính năng nâng tầm trải nghiệm AI Subtitle Suite:
- **Khắc phục lỗi runtime:** Bọc lỗi toàn diện `MainWindow.eventFilter()` trong `ui/Gui.py` ngăn ngừa văng exception ra Qt C++ runtime khi xử lý phím tắt trên các định dạng media cũ (.wmv / .asf).
- **FR-04: VAD Speech Density Heatmap Waveform:** Nâng cấp `WaveformView` thành bản đồ nhiệt thể hiện chính xác xác suất tiếng người nói từ Silero VAD (Xanh ngọc $\ge 0.65$, Vàng cam $0.35 - 0.65$, Xám sẫm $< 0.35$) với bộ đệm tính trước và Viewport Culling 60 FPS.
- **FR-05: Jog-Audio Micro-Scrubbing (`Alt + Drag`):** Phát lát cắt âm thanh vi mô 40ms PCM không khóa UI khi giữ `Alt` kéo chuột trên Timeline, cơ chế ngắt tức thì $< 10$ms khi nhả chuột/phím và bộ đệm phòng vệ container WMV/ASF.

---

## 2. Phân Rã 4 Tác Vụ Kỹ Thuật (Tasks)

### Task 1: Exception Shielding Cho `MainWindow.eventFilter` & Legacy WMV (AC-06)
- **Tập tin tác động:** `ui/Gui.py`
- **Tập tin kiểm thử:** `tests/ui/test_event_filter_exception_shield.py` (Mới)
- **Chi tiết kỹ thuật:**
  1. Bọc toàn bộ thân hàm `MainWindow.eventFilter` (từ `L2541` đến cuối hàm) trong khối `try...except Exception as e:` trả về `False` (hoặc delegate `super().eventFilter`), tuyệt đối không để exception thoát ra C++ event loop của Qt.
  2. Bổ sung log chẩn đoán an toàn (`debug_log` hoặc silent pass) khi bắt gặp các sự kiện phím tua/phát trong điều kiện đối tượng media đang bận hoặc ném lỗi PTS.
  3. Viết test giả lập exception trong video player hoặc phím tắt và xác nhận `eventFilter` trả về `False` không gây crash hay in lỗi C++ override.

### Task 2: VAD Speech Density Heatmap Waveform (FR-04 / AC-04)
- **Tập tin tác động:** `ui/timeline/waveform_view.py`, `ui/timeline/timeline_widget.py`, `core/waveform/waveform_service.py`, `ui/Gui.py`
- **Tập tin kiểm thử:** `tests/ui/test_vad_speech_density_waveform.py` (Mới)
- **Chi tiết kỹ thuật:**
  1. Mở rộng `WaveformView`:
     - Bổ sung thuộc tính `self.vad_data: Optional[np.ndarray] = None` lưu mảng xác suất giọng nói (0.0 đến 1.0) theo độ phân giải 10ms đồng bộ với `waveform_data`.
     - Cập nhật hàm `get_heatmap_color(min_peak, max_peak, speech_prob=None)`:
       - `speech_prob >= 0.65`: `#2DD4BF` (Sapphire Teal / Cyan - Giọng nói rõ nét).
       - `0.35 <= speech_prob < 0.65`: `#F59E0B` (Amber - Tạp âm, nói đè, thì thầm).
       - `speech_prob < 0.35`: `#334155` (Obsidian Gray - Im lặng / nhạc nền).
       - `speech_prob is None`: Giữ nguyên fallback biên độ cũ để bảo toàn tương thích ngược.
     - Trong `paintEvent()`: Truy xuất `self.vad_data[chunk_idx]` với chi phí $\mathcal{O}(1)$, vẽ cột sóng âm với Viewport Culling, bảo đảm $\ge 58$ FPS.
     - Cung cấp method `set_vad_data(speech_probs: np.ndarray)`.
  2. Cập nhật `TimelineWidget`:
     - Bổ sung tham số `vad_data=None` vào `load_project_data(...)` và forward tới `container.waveform.set_vad_data(...)`.
  3. Mở rộng `WaveformService` / `Gui.py`:
     - Bổ sung tính toán/tạo mảng VAD density từ Silero VAD (hoặc speech timestamps) trong tiến trình nền khi tải video/audio và emit về UI cùng waveform peaks.

### Task 3: Jog-Audio Micro-Scrubbing (`Alt + Drag`) (FR-05 / AC-05)
- **Tập tin tác động:** `core/audio/jog_audio_engine.py` (Mới), `ui/timeline/timeline_widget.py`, `ui/timeline/waveform_view.py`
- **Tập tin kiểm thử:** `tests/ui/test_jog_audio_micro_scrubbing.py` (Mới)
- **Chi tiết kỹ thuật:**
  1. Xây dựng `JogAudioEngine` trong `core/audio/jog_audio_engine.py`:
     - Quản lý bộ đệm PCM âm thanh gốc đã trích xuất từ video (hoặc streaming non-blocking).
     - Sử dụng `QAudioSink` từ `PySide6.QtMultimedia` (hoặc mockable sink khi chạy trên CI không có card âm thanh).
     - Cung cấp hàm `play_slice(center_ms: int, duration_ms: int = 40)`: Trích xuất đoạn PCM $[current\_ms - 20ms, current\_ms + 20ms]$ và phát tức thì phi chặn.
     - Bọc try-catch phòng vệ lỗi PTS/ASF của định dạng WMV cũ: Nếu trích xuất slice thất bại, im lặng bỏ qua, không làm gián đoạn UI.
     - Hàm `stop()`: Dừng ngay lập tức và làm rỗng buffer trong $< 10$ms.
  2. Tương tác trên `TimelineWidget` & `WaveformView`:
     - Lắng nghe sự kiện chuột `mousePressEvent`, `mouseMoveEvent` khi cờ `event.modifiers() & Qt.AltModifier` bật.
     - Khi di chuyển chuột kèm `Alt`: Phát audio slice 40ms tại tọa độ thời gian tương ứng và cập nhật playhead mượt mà.
     - Khi `mouseReleaseEvent` hoặc phím `Alt` được nhả (`keyReleaseEvent`): Kích hoạt ngắt an toàn `jog_engine.stop()`, triệt tiêu hoàn toàn hiện tượng dội âm.

### Task 4: Kiểm Thử Toàn Diện & Feature Acceptance Gate Phase 2 (10/10)
- **Tập tin tác động:** Toàn bộ test suite Phase 1 + Phase 2 + Regression.
- **Chi tiết kỹ thuật:**
  1. Chạy 3 bộ test mới của Phase 2:
     - `tests/ui/test_event_filter_exception_shield.py`
     - `tests/ui/test_vad_speech_density_waveform.py`
     - `tests/ui/test_jog_audio_micro_scrubbing.py`
  2. Chạy toàn bộ regression suite (bảo đảm 77/77 tests cũ tiếp tục PASS 100%).
  3. Hoàn tất đối chiếu 10/10 tiêu chí của **Feature Acceptance Gate** và bàn giao cho QA Lead.

---

## 3. Ma Trận Đánh Giá Rủi Ro & Giải Pháp Kỹ Thuật

| Rủi Ro Kỹ Thuật | Tác Động Tiềm Tàng | Giải Pháp Phòng Ngừa Trong Thiết Kế |
| :--- | :--- | :--- |
| **Xung đột audio device với QMediaPlayer** | Gây nghẽn luồng phát video chính hoặc vỡ âm thanh | Sử dụng `QAudioSink` độc lập trên kênh âm thanh riêng biệt; ngắt ngay sau 40ms. |
| **Tính lại VAD làm drop FPS trong paintEvent** | Gây khựng giật khi cuộn Timeline | **Cấm tính VAD trong paintEvent:** Pre-compute một lần khi nạp video thành numpy array, truy xuất $\mathcal{O}(1)$. |
| **Lỗi đọc PTS trên file WMV/ASF** | Treo giao diện hoặc văng console error | Bộ đệm phòng vệ `try...except` bọc kín toàn bộ luồng trích xuất audio slice, fallback silent pass. |
| **Không có thiết bị âm thanh trên máy ảo CI** | Test tự động bị fail do không có soundcard phần cứng | Thiết kế `JogAudioEngine` hỗ trợ chế độ Headless / Mock Sink tự động khi chạy môi trường không có output device. |
| **Rò rỉ âm thanh (Audio Stutter) khi rê chuột nhanh** | m thanh bị lặp lại hoặc rè khi dừng rê chuột | Hook cả `mouseReleaseEvent` và `keyReleaseEvent` với thời gian dập tắt buffer $< 10$ms. |
