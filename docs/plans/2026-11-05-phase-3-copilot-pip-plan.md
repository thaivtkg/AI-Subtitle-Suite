# Kế Hoạch Triển Khai Kỹ Thuật: Phase 3 – AI Copilot & PiP Video Workflow (DEV-SPEC-PHASE3-COPILOT-001)

> **Mục tiêu:** Nâng tầm trải nghiệm biên dịch CAT Studio và kiểm soát phụ đề video với gợi ý dịch thuật thông minh inline (Ghost-Text Translation Copilot truy vấn SQLite FTS5 < 50ms) và cửa sổ xem trước video tách rời luôn nổi (Floating Always-On-Top PiP Player đồng bộ 2 chiều 60 FPS).  
> **Quy chuẩn tuân thủ:** [Requirement-Driven Implementation & Feature Fidelity Protocol](file:///d:/ai-subtitle-suite/GEMINI.md#L247) & [Feature Acceptance Gate (10/10)](file:///d:/ai-subtitle-suite/GEMINI.md#L413).  
> **Trạng thái Gate:** 03/10 (Developer xác nhận hiểu yêu cầu & lập Implementation Mapping) $\rightarrow$ Đệ trình phê duyệt để mở khóa Gate 04/10.

---

## 1. Danh Mục Yêu Cầu & Ràng Buộc Kỹ Thuật Bắt Buộc

### A. FR-06: Ghost-Text Translation Copilot
- **Vị trí tác động:**
  - `core/database/tm_manager.py`: Mở rộng khả năng truy vấn tiền tố siêu tốc của `TranslationMemoryManager`.
  - `core/translation/controllers/translation_controller.py`: Quản lý reactive property `ghostText`, slots `acceptGhostText()`, `acceptNextWord()`.
  - `ui/qml_translation/components/TranslationWorkspace.qml`: Hiển thị văn bản mờ `#64748B` ngay sau con trỏ nhập liệu trong `translationInput`, xử lý phím tắt `Tab` và `Ctrl + Right`.
- **Cơ chế truy vấn & Hiệu năng (< 50ms):**
  - Sử dụng SQLite FTS5 prefix match (`target_text MATCH 'query*'`) kết hợp index lookup trên `tm_segments` (`target_text LIKE 'query%'`).
  - Khi người dùng nhập `current_typed` ($\ge 1$ ký tự), truy vấn trả về kết quả tốt nhất trong $< 5$ms.
  - Tính toán phần đuôi gợi ý: $\text{remainder} = \text{suggestion}[\text{len(current\_typed)}:]$.
  - Nếu `remainder` không rỗng: gán `ghostText = remainder`.
- **Quy tắc phím tắt & Thao tác:**
  - Phím `Tab`: Chèn toàn bộ phần gợi ý còn lại vào ô nhập liệu (`text = text + ghostText`), làm rỗng `ghostText`, giữ focus con trỏ tại cuối văn bản.
  - Phím `Ctrl + Right`: Chèn từng từ tiếp theo của gợi ý (tính đến khoảng trắng hoặc ranh giới từ kế tiếp).
  - Khi người dùng gõ ký tự lệch khỏi gợi ý hoặc xóa ô nhập liệu: Tự động ẩn `ghostText`.
  - Khi trạng thái hệ thống đang dịch tự động (`status === "TRANSLATING"`): Ẩn hoàn toàn `ghostText`.

---

### B. FR-07: Floating Always-On-Top PiP Player
- **Vị trí tác động:**
  - `player/pip_player.py` (Module mới): Cửa sổ `PiPPlayerWindow(QWidget)` kế thừa giao diện Liquid Obsidian.
  - `player/video_player.py`: Bổ sung nút `btn_pip` trên thanh điều khiển, kết nối tín hiệu 2 chiều với cửa sổ PiP.
  - `ui/Gui.py`: Đăng ký phím tắt toàn cục `Ctrl + P` trong `MainWindow.eventFilter` với Exception Shielding bảo vệ an toàn.
- **Cơ chế Cửa sổ & Trọng lượng:**
  - Window Flags: `Qt.WindowStaysOnTopHint | Qt.Tool | Qt.FramelessWindowHint` (hoặc minimal title bar tùy chọn).
  - Tỷ lệ khung hình: Khởi tạo mặc định $360 \times 202$ px (tỷ lệ chuẩn 16:9), hỗ trợ co giãn cạnh viền và kéo rê di chuyển (drag-to-move).
  - Thuộc tính an toàn: `setAttribute(Qt.WA_DeleteOnClose, False)` để hỗ trợ toggle ẩn/hiện lặp đi lặp lại mà không gây lỗi đối tượng C++ bị xóa.
- **Đồng bộ 2 chiều (Zero Dual-Decode Overhead):**
  - Tận dụng `QGraphicsVideoItem.videoSink().videoFrameChanged` của player chính để chuyển tiếp trực tiếp từng frame sang `QVideoSink` của cửa sổ PiP (`pip_widget.videoSink().setVideoFrame(frame)`).
  - Tuyệt đối không tạo đối tượng `QMediaPlayer` thứ hai chạy ngầm gây hao tốn CPU/RAM và xung đột âm thanh.
  - Tương tác 2 chiều:
    - Khi video chính chạy/tạm dừng/seek $\rightarrow$ PiP cập nhật tức thời theo nhịp 60 FPS.
    - Khi người dùng bấm Play/Pause, bấm phím Space, hoặc tua slider trên PiP $\rightarrow$ Video player chính và Timeline cập nhật tương ứng.

---

## 2. Kế Hoạch 4 Tác Vụ Triển Khai (4-Task Breakdown)

### Task 1: Hiện Thực Ghost-Text Translation Copilot Core & Controller (FR-06 Core)
- **Tập tin tác động:**
  - `core/database/tm_manager.py`
  - `core/translation/controllers/translation_controller.py`
- **Tập tin kiểm thử:**
  - `tests/ui/test_ghost_text_copilot.py` (Mới)
- **Chi tiết triển khai:**
  1. Viết bộ kiểm thử TDD `tests/ui/test_ghost_text_copilot.py`:
     - Test truy vấn tiền tố `query_copilot_prefix`: khớp chính xác tiền tố, thời gian thực thi $< 50$ms.
     - Test tính toán `ghostText` trong `TranslationController` khi `currentTranslation` thay đổi.
     - Test slot `acceptGhostText()`: chèn toàn bộ câu.
     - Test slot `acceptNextWord()`: chèn từng từ một theo đúng khoảng trắng.
     - Test tự động làm rỗng `ghostText` khi xóa ô nhập hoặc khi chuỗi nhập lệch khỏi gợi ý.
  2. Bổ sung method `query_copilot_prefix(typed_prefix: str, source_text: str = "", lang_pair: str = "") -> Optional[str]` trong `TranslationMemoryManager`.
  3. Cập nhật `TranslationController`:
     - Khai báo reactive property `ghostText` kèm signal `ghostTextChanged`.
     - Thêm slot `acceptGhostText()`, slot `acceptNextWord()`.
     - Tự động gọi `_update_ghost_text()` khi `updateCurrentTranslation()` được kích hoạt.

---

### Task 2: Hiện Thực Ghost-Text UI Trong QML CAT Studio (FR-06 UI)
- **Tập tin tác động:**
  - `ui/qml_translation/components/TranslationWorkspace.qml`
- **Chi tiết triển khai:**
  1. Thêm thành phần hiển thị `ghostTextOverlay` (`Text`) nằm ngay bên dưới `translationInput` trong `transScroll`:
     - Màu sắc: `#64748B` (WCAG Liquid Obsidian Slate Gray).
     - Định dạng: Khớp hoàn toàn font, pixelSize (15), weight, wrapMode, margins của `translationInput`.
     - Cơ chế hiển thị: Dùng rich text với phần văn bản đã gõ trong suốt (`color: transparent`) và phần còn lại màu `#64748B`.
  2. Bắt sự kiện bàn phím trong `translationInput`:
     - `Keys.onTabPressed`: Nếu `translationController.ghostText` có dữ liệu $\rightarrow$ gọi `translationController.acceptGhostText()`, `event.accepted = true`. Ngược lại cho phép Tab chuyển focus bình thường.
     - `Keys.onRightPressed`: Nếu giữ phím `Ctrl` và có `ghostText` $\rightarrow$ gọi `translationController.acceptNextWord()`, `event.accepted = true`.
  3. Kiểm tra tính mượt mà khi gõ phím nhanh không bị giật lag hay khựng giao diện.

---

### Task 3: Hiện Thực Floating Always-On-Top PiP Player (FR-07)
- **Tập tin tác động:**
  - `player/pip_player.py` (Tạo mới)
  - `player/video_player.py` (Cập nhật)
  - `ui/Gui.py` (Cập nhật phím tắt `Ctrl + P`)
- **Tập tin kiểm thử:**
  - `tests/ui/test_floating_pip_player.py` (Mới)
- **Chi tiết triển khai:**
  1. Viết bộ kiểm thử TDD `tests/ui/test_floating_pip_player.py`:
     - Test khởi tạo `PiPPlayerWindow` với window flags `Qt.WindowStaysOnTopHint | Qt.Tool`.
     - Test nhận video frame chuyển tiếp từ player chính qua `setVideoFrame`.
     - Test đồng bộ 2 chiều: thay đổi vị trí từ PiP phát tín hiệu về player chính; player chính seek thì PiP slider cập nhật.
     - Test toggle hiển thị PiP qua nút `btn_pip` và phím tắt `Ctrl + P`.
     - Test đóng mở an toàn không hủy đối tượng C++.
  2. Xây dựng lớp `PiPPlayerWindow(QWidget)` trong `player/pip_player.py`:
     - Khung hiển thị `QVideoWidget` tối ưu.
     - Thanh điều khiển mini (Play/Pause, Slider, Timecode, Dock/Close).
     - Kéo thả di chuyển cửa sổ (Window Dragging) và bo góc bo viền phong cách Liquid Obsidian.
  3. Tích hợp vào `VideoPlayerWidget` trong `player/video_player.py`:
     - Thêm nút `btn_pip` (`📺 PiP`) trên `controls_layout`.
     - Kết nối tín hiệu video frame: `self.video_item.videoSink().videoFrameChanged.connect(self.pip_window.set_video_frame)`.
     - Đồng bộ playhead và trạng thái play/pause.
  4. Đăng ký phím tắt `Ctrl + P` trong `MainWindow.eventFilter()` (`ui/Gui.py`) với bảo vệ Exception Shielding.

---

### Task 4: Kiểm Thử Tích Hợp Toàn Diện, Chụp Ảnh Minh Chứng & Nghiệm Thu Gate Phase 3
- **Tập tin tác động:**
  - `tests/e2e/test_capture_phase3_evidence.py` (Mới)
- **Chi tiết triển khai:**
  1. Chạy toàn bộ test suites mới:
     - `tests/ui/test_ghost_text_copilot.py`
     - `tests/ui/test_floating_pip_player.py`
  2. Chạy toàn bộ regression test suite (127 specs cũ + specs mới, bảo đảm $\ge 140$ tests PASS 100%).
  3. Chạy script chụp ảnh runtime thực tế `test_capture_phase3_evidence.py` tạo các ảnh minh chứng:
     - `phase3_01_ghost_text_suggestion.png`
     - `phase3_02_floating_pip_player_active.png`
     - `phase3_03_pip_bidirectional_sync.png`
  4. Hoàn tất báo cáo kỹ thuật đối chiếu 10/10 tiêu chí của **Feature Acceptance Gate** gửi Principal QA Lead.

---

## 3. Ma Trận Đánh Giá Rủi Ro Kỹ Thuật (Risk Assessment Matrix)

| Rủi Ro Kỹ Thuật | Mức Độ | Tác Động Tiềm Tàng | Giải Pháp Phòng Ngừa Kiến Trúc |
| :--- | :---: | :--- | :--- |
| **Trễ truy vấn FTS5 khi database lớn** | Medium | Gây giật lag (frame drop) khi người dùng gõ văn bản nhanh | Truy vấn tiền tố với `LIMIT 1` và truy cập index `target_text LIKE ?%`. Bộ đệm LRU cache cho các truy vấn lặp lại. Thời gian đo đạc < 5ms. |
| **Xung đột phím Tab điều hướng của QML** | High | Người dùng không thể nhấn Tab để chuyển focus giữa các ô nhập liệu khi không có ghost text | Kiểm tra cẩn mật: chỉ `event.accepted = true` khi `ghostText.length > 0`. Khi không có gợi ý, trả `event.accepted = false` để giữ trọn vẹn hành vi gốc của hệ thống. |
| **Xung đột bộ giải mã video khi mở PiP** | Critical | Tràn bộ nhớ, crash driver đồ họa hoặc treo ứng dụng | Tuyệt đối không tạo `QMediaPlayer` thứ hai. Dùng cơ chế Frame Forwarding từ `QGraphicsVideoItem.videoSink()` sang `QVideoSink` của PiP. |
| **Lỗi C++ Object Deleted khi toggle PiP** | High | Crash ứng dụng khi người dùng bấm tắt PiP rồi mở lại bằng `Ctrl + P` | Thiết lập `setAttribute(Qt.WA_DeleteOnClose, False)` và ghi đè `closeEvent` thành `hide()`. Giữ nguyên lifecycle instance trong suốt phiên làm việc. |
| **Orphan Window khi đóng ứng dụng chính** | Medium | Cửa sổ PiP vẫn nổi trên desktop sau khi người dùng tắt AI Subtitle Suite | Kết nối `app.aboutToQuit` hoặc `MainWindow.closeEvent` tự động gọi `pip_window.close()` dọn dẹp triệt để. |
