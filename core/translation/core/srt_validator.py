import re


class SRTValidator:
    TIME_PATTERN = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")
    ACTIVE_STATUSES = {"ACCEPTED", "EDITED", "TRANSLATED"}

    @staticmethod
    def _time_to_ms(time_str: str) -> int:
        match = SRTValidator.TIME_PATTERN.match(time_str)
        if not match:
            return -1
        h, m, s, ms = map(int, match.groups())
        return h * 3600000 + m * 60000 + s * 1000 + ms

    @staticmethod
    def validate_for_export(subtitles: list) -> tuple[bool, str]:
        if not subtitles:
            return False, "Không có dữ liệu subtitle để xuất."

        ids = set()
        prev_start_ms = -1
        translated_count = 0
        untranslated_indices = []
        echo_warning_indices = []
        out_of_order_indices = []

        for i, sub in enumerate(subtitles):
            # 1. KIỂM TRA CẤU TRÚC INDEX (Fatal Blockers)
            idx = sub.get("index")
            if not isinstance(idx, int) or isinstance(idx, bool):
                return False, f"Dòng {i+1}: Index không hợp lệ."
            if idx in ids:
                return False, f"Trùng lặp Index #{idx}."
            ids.add(idx)

            # 2. KIỂM TRA LOGIC TIMESTAMP (Fatal Blockers - Áp dụng cho mọi câu)
            start = str(sub.get("start_time") or "").strip()
            end = str(sub.get("end_time") or "").strip()
            start_ms = SRTValidator._time_to_ms(start)
            end_ms = SRTValidator._time_to_ms(end)

            if start_ms == -1 or end_ms == -1:
                return False, f"Subtitle #{idx}: Timestamp sai định dạng."
            if start_ms >= end_ms:
                return False, f"Subtitle #{idx}: Start Time phải nhỏ hơn End Time."
            if start_ms < prev_start_ms:
                out_of_order_indices.append(idx)
            prev_start_ms = max(prev_start_ms, start_ms)

            # 3. KIỂM TRA TRẠNG THÁI & NỘI DUNG DỊCH (Business Rules Matrix)
            status = str(sub.get("status") or "PENDING").upper()
            trans = str(sub.get("translation") or "").strip()
            orig = str(sub.get("original") or "").strip()

            if status in SRTValidator.ACTIVE_STATUSES and trans:
                translated_count += 1
                # Nếu do AI dịch (chưa qua người sửa/duyệt) mà giống hệt câu gốc dài > 3 từ -> Cảnh báo Echo
                if status == "TRANSLATED" and trans == orig and len(orig.split()) > 3:
                    echo_warning_indices.append(idx)
            else:
                untranslated_indices.append(idx)

        # 4. CHẶN CỨNG NẾU 100% TOÀN BỘ FILE CHƯA DỊCH CÂU NÀO
        if translated_count == 0:
            return False, "Chưa có câu phụ đề nào được dịch. Vui lòng dịch ít nhất 1 câu trước khi xuất file."

        # 5. TỔNG HỢP CẢNH BÁO (Không chặn xuất file)
        warnings = []
        if untranslated_indices:
            warnings.append(f"{len(untranslated_indices)} câu chưa dịch (sẽ giữ nguyên câu gốc)")
        if echo_warning_indices:
            warnings.append(f"{len(echo_warning_indices)} câu AI giữ nguyên câu gốc dài")
        if out_of_order_indices:
            warnings.append(f"{len(out_of_order_indices)} câu có thời gian bắt đầu trước câu trước (lồng tiếng/chèn lời)")

        if warnings:
            return True, f"Hợp lệ (Lưu ý: {'; '.join(warnings)})."

        return True, "Hợp lệ."