# KẾ HOẠCH TRIỂN KHAI CHI TIẾT (IMPLEMENTATION PLAN)
## PLAN-PONYTAIL-AUDIT-REMEDIATION-001
**Tệp kế hoạch:** `docs/plans/2026-11-03-ponytail-audit-remediation-plan.md`  
**Vai trò:** Senior Developer (Chế độ Ponytail: Tối thiểu mã nguồn mới, tối đa tính ổn định)  
**Tiêu chuẩn:** Test-Driven Development (TDD), không thêm abstraction thừa, bảo toàn 100% test hồi quy.

---

### MỤC TIÊU
Khắc phục dứt điểm 11 phát hiện kỹ thuật trong Báo cáo Rà soát Chất lượng Toàn diện (Ponytail Audit Report), đưa dự án `AI Subtitle Suite` đạt tiêu chuẩn xuất xưởng (production-ready).

---

### CÁC TÁC VỤ TRIỂN KHAI TUẦN TỰ

- [x] **Tác vụ 1: Triển khai Giai đoạn 1 - Must Fix (6 Lỗi Nghiêm Trọng)**
  - [x] **Bước 1.1**: Viết test và triển khai Ghi đè file phụ đề nguyên tử (`atomic_save_text`) trong [`core/utils/file_utils.py`](file:///d:/ai-subtitle-suite/core/utils/file_utils.py) & [`core/subtitle_exporter.py`](file:///d:/ai-subtitle-suite/core/subtitle_exporter.py).
  - [x] **Bước 1.2**: Viết test và chuẩn hóa timecode dấu chấm trong [`core/subtitle_controller.py`](file:///d:/ai-subtitle-suite/core/subtitle_controller.py).
  - [x] **Bước 1.3**: Bọc try-except an toàn tránh crash UI khi gõ dở timecode trong [`ui/SubEditor.py:898`](file:///d:/ai-subtitle-suite/ui/SubEditor.py#L898).
  - [x] **Bước 1.4**: Viết test và triển khai fallback phẳng 0dB cho video câm trong [`core/waveform/waveform_service.py`](file:///d:/ai-subtitle-suite/core/waveform/waveform_service.py).
  - [x] **Bước 1.5**: Sửa lỗi nhận `db_path`, bổ sung `check_same_thread=False` và `threading.Lock()` trong [`core/database/tm_manager.py`](file:///d:/ai-subtitle-suite/core/database/tm_manager.py).
  - [x] **Bước 1.6**: Viết test và tích hợp `SubtitleGenerationValidator.validate()` trong [`core/subtitle_generation/faster_whisper_service.py`](file:///d:/ai-subtitle-suite/core/subtitle_generation/faster_whisper_service.py).
  - [x] **Bước 1.7**: Chạy bộ test kiểm định Giai đoạn 1 và commit mã nguồn (`58500cc`).

- [x] **Tác vụ 2: Triển khai Giai đoạn 2 - Should Fix & Tinh gọn (5 Mục Còn Lại)**
  - [x] **Bước 2.1**: Áp dụng `atomic_save_json` và `atomic_save_text` trong [`core/batch/batch_manager.py`](file:///d:/ai-subtitle-suite/core/batch/batch_manager.py).
  - [x] **Bước 2.2**: Cập nhật mặc định `server_name = "ai-subtitle-suite"` trong [`core/runtime/single_instance_guard.py`](file:///d:/ai-subtitle-suite/core/runtime/single_instance_guard.py).
  - [x] **Bước 2.3**: Nới lỏng regex giờ `(\d+)` trong [`core/subtitle_editing/hydration.py:14`](file:///d:/ai-subtitle-suite/core/subtitle_editing/hydration.py#L14).
  - [x] **Bước 2.4**: Escape dấu phẩy font FFmpeg trong [`core/Backend.py:276`](file:///d:/ai-subtitle-suite/core/Backend.py#L276).
  - [x] **Bước 2.5**: Xóa mã chết `bottom_tabs` trong [`core/services/workspace_service.py`](file:///d:/ai-subtitle-suite/core/services/workspace_service.py).
  - [x] **Bước 2.6**: Chạy bộ test kiểm định Giai đoạn 2 và commit mã nguồn (`96e109f`).

- [x] **Tác vụ 3: Kiểm định Hồi quy Toàn diện & Bàn giao**
  - [x] **Bước 3.1**: Chạy toàn bộ các test suite core (48 passed), translation (26 passed), ui & gui (40 passed) -> 114 passed 100%.
  - [x] **Bước 3.2**: Commit hoàn tất kế hoạch và push lên `origin/main`.
