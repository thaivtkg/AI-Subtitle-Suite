# Kế Hoạch Triển Khai Kỹ Thuật: Phase 1 – Dynamic & HUD (DEV-SPEC-PHASE1-HUD-001)

> **Mục tiêu:** Nâng cấp trải nghiệm người dùng với hệ thống cảnh báo thông minh thời gian thực (Live CPS Sentinel HUD), nam châm khớp viền phụ đề chồng lấn (Overlap Snap Magnet với Eco-Timer 1Hz & QUndoStack), và bộ lọc hiệu ứng hover bắt sáng con trỏ (Spotlight Event Filter 60 FPS phi cản trở).  
> **Quy chuẩn tuân thủ:** [Requirement-Driven Implementation & Feature Fidelity Protocol](file:///d:/ai-subtitle-suite/GEMINI.md#L247) & [Feature Acceptance Gate (10/10)](file:///d:/ai-subtitle-suite/GEMINI.md#L413).  
> **Trạng thái Gate:** 04/10 PASSED $\rightarrow$ Khởi động triển khai TDD.

---

## 1. Danh Mục Yêu Cầu & Ràng Buộc Kỹ Thuật Bắt Buộc

### A. FR-01: Live CPS Sentinel HUD & Smart Natural Split
- **Vị trí:** `ui/SubEditor.py` (`CurrentSubtitleEditor`) và `ui/qml_translation/components/TranslationWorkspace.qml`.
- **Công thức CPS:**
  $$\text{CPS} = \frac{\text{len(text)}}{\max(0.1, (\text{end\_ms} - \text{start\_ms}) / 1000.0)}$$
  *Bảo vệ:* Xử lý an toàn trường hợp `end_ms <= start_ms`, không chia cho 0, không ném exception.
- **Hành vi hiển thị:**
  - Khi $\text{CPS} \le 20.0$: Ẩn huy hiệu và nút tách.
  - Khi $\text{CPS} > 20.0$: Hiển thị huy hiệu viền đỏ cam `⚠️ {cps:.1f} CPS` và hiển thị nút `⚡ Tách câu thông minh`.
- **Thuật toán ngắt câu tự nhiên (`_split_text_at_natural_boundary`):**
  1. *Dấu câu chính:* Tìm các dấu ngắt câu `[. , ! ? ... \n 。 ！ ？ …]` gần vị trí giữa câu (`len(text) // 2`) nhất.
  2. *Dấu câu phụ:* Tìm dấu phẩy / chấm phẩy `[, ; : 、 ， ；]`.
  3. *Khoảng trắng:* Tìm ký tự space gần giữa câu nhất.
  4. *Fallback CJK / Chuỗi liền mạch không dấu:* Tự động cắt ngay tại Midpoint Index (`len(text) // 2`). Tuyệt đối không ném Exception.
- **Tách phân đoạn:**
  - Tính thời điểm cắt: $\text{split\_ms} = \text{start\_ms} + \text{int}\left(\frac{\text{split\_idx}}{\text{len(text)}} \times (\text{end\_ms} - \text{start\_ms})\right)$ (kẹp tối thiểu cách biên 100ms).
  - Đẩy lệnh chia qua `SplitSegmentCommand` để đảm bảo Undo/Redo hoàn hảo.
- **Nguyên tắc bất biến (Soft Warning):**
  - Cảnh báo CPS chỉ mang tính hỗ trợ biên tập, **tuyệt đối không chặn hoặc hiển thị modal cản trở việc xuất file** trong `ui/export/`.

---

### B. FR-02: Overlap Snap Magnet & Eco-Timer 1Hz
- **Vị trí:** `ui/timeline/subtitle_track.py` và `ui/timeline/timeline_widget.py`.
- **Cơ chế phát hiện:**
  - Khi tồn tại phân đoạn $A$ và $B$ kề nhau mà $A.\text{end\_ms} > B.\text{start\_ms}$.
  - Vẽ vân sọc chéo `Qt.DiagCrossPattern` màu đỏ cảnh báo.
- **Cơ chế Tiết Kiệm Năng Lượng Cho Timer 1Hz (Eco-Timer):**
  - Bộ đếm `_overlap_timer` (nhịp 500ms on/off = 1Hz) **chỉ được `start()`** khi quét thấy trên track có ít nhất 1 cặp phụ đề giao nhau (`overlap_count > 0`).
  - Khi `overlap_count == 0` hoặc khi widget Timeline bị ẩn (`hideEvent`), timer bắt buộc phải gọi `stop()` ngay lập tức để triệt tiêu tải CPU nhàn rỗi.
- **Hành vi Snap Viền (`🧲 Snap viền`):**
  - Nút Snap trên thanh công cụ Timeline tự động điều chỉnh $A.\text{end\_ms} = B.\text{start\_ms} - 20\text{ms}$ (chừa 20ms khoảng nghỉ tiêu chuẩn).
  - Sử dụng `ResizeEndCommand` kết nối với `QUndoStack` của Timeline, bảo đảm khôi phục nguyên vẹn mốc thời gian cũ khi nhấn `Ctrl+Z`.

---

### C. FR-03: 3 Dynamic Hover Interactions (Spotlight 60 FPS)
- **Vị trí:** `ui/core/liquid_theme_engine.py` và các Event Filter dùng chung.
- **Spotlight Gradient (120px):**
  - Lớp phủ gradient xuyên thấu bán kính 120px theo con trỏ chuột.
  - Sử dụng `QElapsedTimer` áp dụng cơ chế Throttling cứng $\le 60$ FPS (chu kỳ tối thiểu $\ge 16.6$ms giữa 2 lần repaint).
- **Nguyên tắc Xuyên Thấu Sự Kiện (Event Filter Transparency):**
  - `SpotlightEventFilter` chỉ bắt sự kiện `QEvent.Enter`, `QEvent.Leave`, `QEvent.MouseMove` để cập nhật tọa độ vẽ.
  - **Tuyệt đối `return False`** cho mọi sự kiện chuột và phím cốt lõi (`MouseButtonPress`, `MouseButtonRelease`, `MouseButtonDblClick`, `Wheel`, `KeyPress`, `KeyRelease`) để không gây liệt trỏ soạn thảo hoặc cản trở thao tác kéo thả trên Timeline.
- **Magnetic Elevation & Button Ripple:**
  - Nâng nhẹ bề mặt card/bảng khi hover (Z-index ảo qua stylesheet dynamic state).

---

## 2. Kế Hoạch 4 Tác Vụ Triển Khai (4-Task Breakdown)

### Task 1: Triển Khai Live CPS Sentinel HUD & Smart Split (FR-01)
**Files liên quan:**
- Modify: `ui/SubEditor.py` (`CurrentSubtitleEditor`, `SubEditor`)
- Test: `tests/ui/test_live_cps_sentinel.py` (Mới)

**Các bước thực hiện:**
1. Viết bộ kiểm thử TDD `test_live_cps_sentinel.py`:
   - Kiểm tra công thức CPS chính xác và an toàn khi `end <= start` hoặc `duration < 0.1s`.
   - Kiểm tra hiển thị `lbl_cps` và nút `btn_smart_split` khi CPS > 20 và ẩn khi CPS <= 20.
   - Kiểm tra thuật toán `_split_text_at_natural_boundary` với dấu câu tiếng Việt/Anh, dấu câu CJK (`。`, `！`), khoảng trắng, và chuỗi CJK liền mạch không dấu (midpoint fallback).
   - Kiểm tra luồng tách phân đoạn và đảm bảo không chặn export.
2. Thêm `lbl_cps` (badge viền cam/đỏ `#F97316`) và `btn_smart_split` (`QPushButton("⚡ Tách câu")`) vào `CurrentSubtitleEditor`.
3. Kết nối sự kiện gõ chữ `textChanged` và sửa thời gian `editingFinished` để cập nhật CPS real-time.
4. Hiện thực hàm `_split_text_at_natural_boundary(text)` và liên kết slot tách câu vào `SplitSegmentCommand`.

---

### Task 2: Triển Khai Overlap Snap Magnet & Eco-Timer 1Hz (FR-02)
**Files liên quan:**
- Modify: `ui/timeline/subtitle_track.py`, `ui/timeline/timeline_widget.py`, `core/timeline/timeline_controller.py`
- Test: `tests/ui/test_overlap_snap_magnet.py` (Mới)

**Các bước thực hiện:**
1. Viết bộ kiểm thử TDD `test_overlap_snap_magnet.py`:
   - Kiểm tra phát hiện vùng chồng lấn giữa 2 segment liên tiếp.
   - Kiểm tra cơ chế Eco-Timer: timer 1Hz chỉ chạy khi có overlap và dừng khi hết overlap hoặc widget bị hide.
   - Kiểm tra thao tác `snap_overlap`: thu mốc `end_ms` của segment trước về `next_seg.start_ms - 20ms`.
   - Kiểm tra tích hợp `QUndoStack`: nhấn Undo (`Ctrl+Z`) phục hồi lại mốc chồng lấn ban đầu.
2. Cập nhật `SubtitleTrack`:
   - Bổ sung `_overlap_timer` (500ms nhịp đảo cờ blink `_overlap_blink_on`).
   - Tối ưu hóa điều kiện start/stop timer: chỉ chạy khi `overlap_count > 0` và widget `isVisible()`.
   - Bổ sung xử lý `hideEvent` và `showEvent`.
3. Bổ sung nút bấm `btn_snap_overlap` (`🧲 Snap viền`) trên thanh điều khiển Timeline:
   - Kích hoạt snap cho phân đoạn đang chọn hoặc phân đoạn va chạm đầu tiên.
   - Đẩy lệnh qua `ResizeEndCommand` của `QUndoStack`.

---

### Task 3: Triển Khai 3 Dynamic Hover Interactions & Spotlight Event Filter (FR-03)
**Files liên quan:**
- Modify: `ui/core/liquid_theme_engine.py`
- Test: `tests/ui/test_spotlight_hover_filter.py` (Mới)

**Các bước thực hiện:**
1. Viết bộ kiểm thử TDD `test_spotlight_hover_filter.py`:
   - Kiểm tra `SpotlightEventFilter`: Throttling 60 FPS ($\ge 16.6$ms).
   - Kiểm tra tính xuyên thấu: Mouse press/release/wheel đều trả về `False` để widget con xử lý bình thường.
   - Kiểm tra khi chuột rời widget (`QEvent.Leave`) thì xóa trạng thái hover/spotlight.
2. Hiện thực `SpotlightEventFilter` trong `ui/core/liquid_theme_engine.py`:
   - Sử dụng `QElapsedTimer` kiểm soát tần suất repaint.
   - Cung cấp hàm tiện ích `apply_spotlight_effect(widget)`.
3. Cập nhật CSS tokens cho hiệu ứng Elevation trên Card/Table và Ripple trên Button.

---

### Task 4: Kiểm Thử Tích Hợp Toàn Diện & Feature Acceptance Gate (10/10)
**Files liên quan:**
- Chạy: Toàn bộ suite kiểm thử `tests/ui/`, `tests/core/`, `tests/gui/specs/`

**Các bước thực hiện:**
1. Chạy 3 bộ test mới của Phase 1:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/ui/test_live_cps_sentinel.py tests/ui/test_overlap_snap_magnet.py tests/ui/test_spotlight_hover_filter.py -v
   ```
2. Chạy toàn bộ regression suite (bảo đảm 53/53 test cũ không bị ảnh hưởng).
3. Đối chiếu 10/10 tiêu chí của **Feature Acceptance Gate** và chuẩn bị biên bản nghiệm thu chuyển giao cho Principal QA Lead.

---

## 3. Ma Trận Đánh Giá Rủi Ro & Giải Pháp Phòng Ngừa

| Rủi Ro Kỹ Thuật | Tác Động Tiềm Tàng | Giải Pháp Phòng Ngừa Trong Thiết Kế |
| :--- | :--- | :--- |
| **Timer 1Hz chiếm dụng CPU** | Làm tăng nhiệt độ máy và ngốn pin khi để app chạy ngầm | **Eco-Timer Guard:** Quét đếm overlap trước; nếu `overlap_count == 0` hoặc widget `hideEvent`, ngắt timer ngay lập tức. |
| **Spotlight nuốt sự kiện chuột** | Liệt con trỏ soạn thảo hoặc đơ thanh cuộn bảng | **Transparency Rule:** Event Filter chỉ hook `Enter/Leave/MouseMove`, luôn `return False` cho mọi sự kiện click/phím/cuộn. |
| **Tách câu CJK lỗi** | Tiếng Nhật/Trung không có khoảng trắng gây crash hoặc từ chối tách | **Midpoint Fallback:** Tự động cắt tại `len(text) // 2` khi không tìm thấy dấu câu. |
| **Chặn luồng xuất file** | Người dùng không thể xuất phụ đề nếu còn câu CPS cao | **Soft Warning Only:** CPS HUD chỉ là giao diện nhắc nhở trên Editor, không can thiệp vào module `ui/export/`. |
