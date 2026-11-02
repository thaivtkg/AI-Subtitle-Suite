import os
from core.utils.file_utils import atomic_save_text

class SubtitleExportService:
    """
    Dịch vụ độc lập chuyên chịu trách nhiệm xuất file phụ đề.
    Tuyệt đối không can thiệp hay làm biến đổi dữ liệu Subtitle Model gốc.
    """

    @staticmethod
    def ms_to_srt_time(ms):
        """ Chuyển đổi Milliseconds sang định dạng thời gian SRT (HH:MM:SS,mmm) """
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def ms_to_vtt_time(ms):
        """ Chuyển đổi Milliseconds sang định dạng thời gian VTT (HH:MM:SS.mmm) """
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    @classmethod
    def validate_output_path(cls, output_path):
        """ 
        [S5-T2] Output Validation: 
        Đảm bảo đường dẫn hợp lệ và thư mục cha có quyền ghi. 
        """
        if not output_path:
            raise ValueError("Đường dẫn xuất file không được để trống.")
        
        output_dir = os.path.dirname(output_path)
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
            except PermissionError:
                raise PermissionError(f"Từ chối truy cập: Không có quyền ghi vào thư mục '{output_dir}'. Vui lòng chọn thư mục khác hoặc cấp quyền Administrator.")
            except Exception as e:
                raise RuntimeError(f"Không thể khởi tạo thư mục Output: {str(e)}")
        return True

    @classmethod
    def export_srt(cls, subtitles, output_path):
        """ Xuất danh sách Subtitle ra định dạng chuẩn .srt bằng atomic_save_text """
        cls.validate_output_path(output_path)
        try:
            lines = []
            for i, (start, end, text) in enumerate(subtitles, 1):
                start_str = cls.ms_to_srt_time(start)
                end_str = cls.ms_to_srt_time(end)
                lines.append(f"{i}\n{start_str} --> {end_str}\n{text}\n\n")
            atomic_save_text(output_path, "".join(lines))
            return True
        except Exception as e:
            raise RuntimeError(f"Lỗi khi xuất file SRT: {str(e)}")

    @classmethod
    def export_vtt(cls, subtitles, output_path):
        """ Xuất danh sách Subtitle ra định dạng WebVTT (.vtt) bằng atomic_save_text """
        cls.validate_output_path(output_path)
        try:
            lines = ["WEBVTT\n\n"]
            for i, (start, end, text) in enumerate(subtitles, 1):
                start_str = cls.ms_to_vtt_time(start)
                end_str = cls.ms_to_vtt_time(end)
                lines.append(f"{i}\n{start_str} --> {end_str}\n{text}\n\n")
            atomic_save_text(output_path, "".join(lines))
            return True
        except Exception as e:
            raise RuntimeError(f"Lỗi khi xuất file VTT: {str(e)}")

    @classmethod
    def export_txt(cls, subtitles, output_path):
        """ Xuất Transcript (.txt) bằng atomic_save_text """
        cls.validate_output_path(output_path)
        try:
            lines = []
            for _, _, text in subtitles:
                if text.strip():
                    lines.append(f"{text}\n")
            atomic_save_text(output_path, "".join(lines))
            return True
        except Exception as e:
            raise RuntimeError(f"Lỗi khi xuất file TXT: {str(e)}")


# Bí danh tương thích ngược
SubtitleExporter = SubtitleExportService
