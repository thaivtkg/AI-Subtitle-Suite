# Kế Hoạch Triển Khai Kỹ Thuật: Phase 3 – AI Copilot & PiP Video Workflow (DEV-SPEC-PHASE3-COPILOT-001)

> **Mục tiêu:** Nâng tầm trải nghiệm biên dịch CAT Studio và kiểm soát phụ đề video với gợi ý dịch thuật thông minh inline (Ghost-Text Translation Copilot truy vấn SQLite FTS5 < 50ms) và cửa sổ xem trước video tách rời hỗ trợ Windows Snap Assist 50/50 & Đa Màn Hình (True Detachable PiP Player đồng bộ 2 chiều 60 FPS).  
> **Quy chuẩn tuân thủ:** [Requirement-Driven Implementation & Feature Fidelity Protocol](file:///d:/ai-subtitle-suite/GEMINI.md#L247) & [Feature Acceptance Gate (10/10)](file:///d:/ai-subtitle-suite/GEMINI.md#L413).  
> **Trạng thái Gate:** 04/10 PASSED $\rightarrow$ BẬT ĐÈN XANH THỰC THI THEO QUY TRÌNH TDD.

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

### B. FR-07: True Detachable PiP & Dual-Window Split Workflow (Refined Spec)
- **Vị trí tác động:**
  - `player/pip_player.py` (Module mới): Cửa sổ `PiPPlayerWindow(QWidget)` hỗ trợ Windows 11 Snap Assist và đa màn hình.
  - `player/video_player.py`: Bổ sung nút `btn_pip` trên thanh điều khiển, kết nối tín hiệu 2 chiều với cửa sổ PiP.
  - `ui/Gui.py`: Cơ chế Undock/Dock vào `top_horizontal_splitter`, tự động mở rộng SubEditor 100% bề ngang, phím tắt toàn cục `Ctrl + P`, và bảo toàn kích thước cửa sổ khi chuyển tab (`switch_page`).
- **Ràng buộc 1: Cơ chế Detach / Undock & Tự động phóng to SubEditor (100% Width):**
  - Khi bấm nút `📺 Tách Video (PiP)` hoặc phím tắt `Ctrl + P`:
    - Lưu tỷ lệ thanh chia hiện tại: `self._saved_splitter_sizes = self.top_horizontal_splitter.sizes()`.
    - Ẩn `self.video_player` trên splitter: `self.video_player.hide()`.
    - `self.sub_editor` tự động bung chiếm trọn 100% bề ngang của khung soạn thảo phía trên.
    - Hiển thị cửa sổ `self.pip_window.show()`.
  - Khi đóng PiP hoặc bấm nút `🗗 Gắn lại vào App`:
    - Ẩn `self.pip_window.hide()`.
    - Hiện lại `self.video_player.show()`.
    - Phục hồi chính xác tỷ lệ phân chia ban đầu: `self.top_horizontal_splitter.setSizes(self._saved_splitter_sizes)`.
- **Ràng buộc 2: Cửa sổ PiP là Top-Level OS Window có hỗ trợ Windows Snap:**
  - Window Flags:
    ```python
    self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | 
                        Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
    ```
    (Tuyệt đối KHÔNG gán cờ `Qt.FramelessWindowHint` cố định làm mất tính năng Snap Assist của Windows 11).
  - Tên cửa sổ: `AI Subtitle Suite - Video Player (PiP)`.
  - Nút toggle `📌 Luôn nổi` (Always on Top): Cho phép linh hoạt bật/tắt cờ `Qt.WindowStaysOnTopHint`.
  - Nút `🗗 Gắn lại vào App` (Dock): 1-click đưa video trở lại giao diện chính.
  - Nút Play/Pause, Seek Slider, Timecode hiển thị trực quan dưới đáy cửa sổ PiP.
  - Viewport tự động scale vừa vặn khung cửa sổ nhưng luôn giữ nguyên tỷ lệ khung hình gốc (Aspect Ratio).
- **Ràng buộc 3: Khóa kích thước cửa sổ khi chuyển Tab (Tab Navigation Geometry Lock):**
  - Trong `MainWindow.switch_page()` (`ui/Gui.py`): Tuyệt đối KHÔNG gọi `resize()`, `showMaximized()` hay reset geometry của `MainWindow`.
  - Khi đang ở tab khác (như Dịch thuật AI), cửa sổ PiP bên ngoài vẫn tiếp tục hiển thị và phát mượt mà để đối chiếu video.
- **Ràng buộc 4: Chia sẻ Frame không tạo Dual-Decode:**
  - Sử dụng chia sẻ frame qua `self.video_item.videoSink().videoFrameChanged.connect(self.pip_window.set_video_frame)`. Tuyệt đối không tạo `QMediaPlayer` thứ hai chạy ngầm.

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
     - `Keys.onTabPressed`: Nếu `translationController.ghostText` có dữ liệu $\rightarrow$ gọi `translationController.acceptGhostText()`, `event.accepted = true`. Ngược lại cho phép Tab chuyển focus bình thường (`event.accepted = false`).
     - `Keys.onRightPressed`: Nếu giữ phím `Ctrl` và có `ghostText` $\rightarrow$ gọi `translationController.acceptNextWord()`, `event.accepted = true`.
  3. Kiểm tra tính mượt mà khi gõ phím nhanh không bị giật lag hay khựng giao diện.

---

### Task 3: Hiện Thực True Detachable PiP & Dual-Window Split Workflow (FR-07)
- **Tập tin tác động:**
  - `player/pip_player.py` (Tạo mới)
  - `player/video_player.py` (Cập nhật nút `btn_pip`)
  - `ui/Gui.py` (Cơ chế undock/dock splitter, phím tắt `Ctrl + P`, bảo toàn geometry khi `switch_page`)
- **Tập tin kiểm thử:**
  - `tests/ui/test_floating_pip_player.py` (Mới)
- **Chi tiết triển khai:**
  1. Viết bộ kiểm thử TDD `tests/ui/test_floating_pip_player.py`:
     - Test khởi tạo `PiPPlayerWindow` với window flags OS chuẩn (hỗ trợ min/max/close, Snap Assist).
     - Test nhận video frame chuyển tiếp từ player chính qua `setVideoFrame`.
     - Test đồng bộ 2 chiều: thay đổi vị trí từ PiP phát tín hiệu về player chính; player chính seek thì PiP slider cập nhật.
     - Test toggle hiển thị PiP qua nút `btn_pip` và phím tắt `Ctrl + P`.
     - Test cơ chế Undock: `video_player.hide()` $\rightarrow$ `sub_editor` mở rộng 100% width.
     - Test cơ chế Dock: phục hồi chính xác `_saved_splitter_sizes`.
     - Test tính năng 📌 Luôn nổi (toggle `Qt.WindowStaysOnTopHint`).
     - Test chuyển tab (`switch_page`) không làm biến động geometry của MainWindow.
  2. Xây dựng lớp `PiPPlayerWindow(QWidget)` trong `player/pip_player.py`:
     - Khung hiển thị `QVideoWidget` tối ưu scale giữ nguyên Aspect Ratio.
     - Thanh điều khiển trực quan: Play/Pause, Slider seek, Timecode, Toggle 📌 Luôn nổi, Nút 🗗 Gắn lại vào App.
  3. Tích hợp vào `VideoPlayerWidget` trong `player/video_player.py`:
     - Thêm nút `btn_pip` (`📺 Tách Video`) trên `controls_layout`.
     - Kết nối frame forwarding: `self.video_item.videoSink().videoFrameChanged.connect(self.pip_window.set_video_frame)`.
  4. Tích hợp vào `MainWindow` trong `ui/Gui.py`:
     - Quản lý `self.pip_window` và phương thức `toggle_pip_mode()`.
     - Lưu và phục hồi `self._saved_splitter_sizes`.
     - Đăng ký phím tắt `Ctrl + P` trong `MainWindow.eventFilter()` với Exception Shielding.
     - Đảm bảo `switch_page()` không làm thay đổi kích thước MainWindow.

---

### Task 4: Kiểm Thử Tích Hợp Toàn Diện, Chụp Ảnh Minh Chứng & Nghiệm Thu Gate Phase 3
- **Tập tin tác động:**
  - `tests/e2e/test_capture_phase3_evidence.py` (Mới)
- **Chi tiết triển khai:**
  1. Chạy 2 test suites mới:
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
| **Trễ truy vấn FTS5 khi database lớn** | Medium | Gây giật lag khi người dùng gõ văn bản nhanh | Truy vấn tiền tố với `LIMIT 1` và truy cập index `target_text LIKE ?%`. Bộ đệm cache cho truy vấn lặp lại. Thời gian đo đạc < 5ms. |
| **Xung đột phím Tab điều hướng của QML** | High | Người dùng không thể nhấn Tab để chuyển focus giữa các ô nhập liệu khi không có ghost text | Kiểm tra cẩn mật: chỉ `event.accepted = true` khi `ghostText.length > 0`. Khi không có gợi ý, trả `event.accepted = false` để giữ trọn vẹn hành vi gốc của hệ thống. |
| **Mất Windows 11 Snap Assist khi tách PiP** | High | Cửa sổ không thể chia đôi màn hình 50/50 với MainWindow | Dùng cờ chuẩn `Qt.Window \| Qt.CustomizeWindowHint \| Qt.WindowTitleHint \| Qt.WindowMinMaxButtonsHint \| Qt.WindowCloseButtonHint`. Tuyệt đối không dùng Frameless cố định. |
| **Xung đột bộ giải mã video khi mở PiP** | Critical | Tràn bộ nhớ, crash driver đồ họa hoặc treo ứng dụng | Tuyệt đối không tạo `QMediaPlayer` thứ hai. Dùng cơ chế Frame Forwarding từ `QGraphicsVideoItem.videoSink()` sang `QVideoSink` của PiP. |
| **Kích thước app bị co giãn ngoài ý muốn khi chuyển tab** | Critical | Gây vỡ bố cục chia đôi màn hình người dùng vừa sắp xếp | Khóa chặt `MainWindow.switch_page()`: không gọi `resize()`, `showMaximized()` hay đổi geometry. |
| **Orphan Window khi đóng ứng dụng chính** | Medium | Cửa sổ PiP vẫn nổi trên desktop sau khi người dùng tắt AI Subtitle Suite | Kết nối `app.aboutToQuit` hoặc `MainWindow.closeEvent` tự động gọi `pip_window.close()` dọn dẹp triệt để. |
