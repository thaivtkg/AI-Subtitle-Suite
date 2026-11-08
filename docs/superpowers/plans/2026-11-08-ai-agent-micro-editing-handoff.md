# KẾ HOẠCH BÀN GIAO TRIỂN KHAI CHO DEVELOPER (PHASE B / v1.1 MICRO-EDITING)
**Dự án:** AI Subtitle Suite (`D:\ai-subtitle-suite`)  
**Tài liệu tham chiếu:** `QA_HANDOFF_PLAN_PHASE_A_AND_PHASE_B_ROADMAP.md`  
**Nhánh Git:** `feature/ai-agent-micro-editing`  
**Mục tiêu:** Mở rộng năng lực AI Agent Copilot hỗ trợ các câu lệnh điều khiển vi mô phụ đề (Micro-Editing & Timeline Manipulation) qua ngôn ngữ tự nhiên.

---

## 1. PHẠM VI 4 CÔNG CỤ VI MÔ (MICRO-EDITING TOOLS)

### TOOL-01: `run_asr(limit: Optional[int] = None)`
- **Mục đích:** Cho phép nhận diện giọng nói có giới hạn (ví dụ: *"gen sub 5 câu đầu"*).
- **Hành vi:** Cắt tỉa mảng kết quả từ Faster-Whisper chỉ giữ lại đúng `limit` câu đầu tiên.

### TOOL-02: `create_timing(count: int = 5, duration_per_block_ms: int = 2500, gap_ms: int = 500)`
- **Mục đích:** Khởi tạo $N$ câu timing mẫu liên tiếp khi người dùng muốn dựng cấu trúc subtitle thủ công mà chưa có audio.
- **Hành vi:** Tạo các đoạn `00:00:00,500 --> 00:00:03,000`, `00:00:03,500 --> 00:00:06,000`...

### TOOL-03: `adjust_subtitle_bounds(delta_start_ms: int, delta_end_ms: int, scope: str = "all")`
- **Mục đích:** Tinh chỉnh mốc thời gian đầu hoặc cuối của phụ đề (ví dụ: *"tăng 100ms mốc cuối và giảm 100ms mốc đầu"*).
- **Hành vi:** Cộng/trừ mili-giây vào `start_ms` và `end_ms` của từng câu.

### TOOL-04: `shift_subtitles(offset_ms: int, scope: str = "all")`
- **Mục đích:** Dịch chuyển tịnh tiến cả đoạn phụ đề (ví dụ: *"đưa cả đoạn sub lên 1s"*, *"lùi sub 500ms"*).
- **Hành vi:** Dịch chuyển đồng thời cả `start_ms + offset_ms` và `end_ms + offset_ms`.

---

## 2. NGUYÊN TẮC AN TOÀN BẮT BUỘC (CRITICAL SAFETY GUARDS)

1. **Chống đè chữ (`auto_resolve_overlaps`)**:
   Khi tăng thời lượng (`delta_end_ms > 0`), nếu `end_ms` của câu hiện tại vượt qua `start_ms` của câu kế tiếp, tự động cắt tỉa `end_ms = next_start` để tránh lỗi đè viền đỏ.
2. **Kẹp biên không âm & Thời lượng tối thiểu**:
   - `start_ms = max(0, start_ms + offset_ms)`.
   - Nếu `end_ms - start_ms < 200`: Tự động gán `end_ms = start_ms + 200` để đảm bảo câu không bị co biến mất.

---

## 3. DANH MỤC 8 CA KIỂM THỬ BÀN GIAO QA (`tests/agent/test_agent_micro_editing.py`)

- `test_synthesize_plan_gen_sub_n_segments`: Nhận diện limit N câu.
- `test_synthesize_plan_create_timing`: Nhận diện tạo timing N câu.
- `test_synthesize_plan_adjust_duration_bounds`: Phân tích đúng mốc đầu/cuối.
- `test_synthesize_plan_shift_subtitles`: Phân tích tiến/lùi thời gian.
- `test_tool_create_timing_execution`: Kiểm tra thực thi tạo timing mẫu.
- `test_tool_adjust_subtitle_bounds_execution`: Kiểm tra co dãn thời lượng.
- `test_tool_shift_subtitles_execution`: Kiểm tra dịch chuyển tịnh tiến.
- `test_controller_hitl_lifecycle_with_micro_editing`: Vòng đời 3 lệnh liên tiếp dừng chờ duyệt HITL.

---

## 4. QUY TRÌNH BÀN GIAO
Sau khi Developer hoàn tất code và chạy `pytest tests/agent/test_agent_micro_editing.py -v` đạt 8/8 PASS, gửi Báo cáo Bàn giao Handoff Report để Hội đồng QA tiến hành nghiệm thu Feature Acceptance Gate trước khi merge vào `main`.
