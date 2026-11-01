import os


class SRTExporter:
    VALID_EXPORT_STATUSES = {"ACCEPTED", "EDITED", "TRANSLATED"}

    @staticmethod
    def _format_timestamp(ts) -> str:
        """Bảo toàn nguyên vẹn chuỗi timestamp gốc, chuẩn hóa sang HH:MM:SS,mmm nếu là số."""
        if isinstance(ts, (int, float)):
            total_ms = int(round(ts))
            ms = total_ms % 1000
            total_s = total_ms // 1000
            s = total_s % 60
            total_m = total_s // 60
            m = total_m % 60
            h = total_m // 60
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        s = str(ts).strip()
        if "." in s and "," not in s:
            s = s.replace(".", ",")
        return s

    @staticmethod
    def export(subtitles: list, output_path: str) -> tuple[bool, str]:
        """Xuất dữ liệu ra file SRT. Ưu tiên bản dịch hợp lệ, fallback an toàn về câu gốc."""
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                for sub in subtitles:
                    start_str = SRTExporter._format_timestamp(sub.get('start_time', '00:00:00,000'))
                    end_str = SRTExporter._format_timestamp(sub.get('end_time', '00:00:00,000'))
                    f.write(f"{sub['index']}\n")
                    f.write(f"{start_str} --> {end_str}\n")

                    status = str(sub.get("status") or "PENDING").upper()
                    clean_trans = str(sub.get("translation") or "").strip()
                    clean_orig = str(sub.get("original") or "").strip()

                    if status in SRTExporter.VALID_EXPORT_STATUSES and clean_trans:
                        text = clean_trans
                    else:
                        text = clean_orig

                    f.write(f"{text}\n\n")
            return True, f"Thành công! Đã lưu tại: {os.path.abspath(output_path)}"
        except Exception as e:
            return False, f"Lỗi: {str(e)}"
