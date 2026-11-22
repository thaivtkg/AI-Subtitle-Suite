import unittest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication, QProgressBar
import sys

from core.subtitle_generation.generation_service import SubtitleGenerationService
from ui.subtitle_generation_panel import SubtitleGenerationPanel

# Ensure QApplication exists
if not QApplication.instance():
    _app = QApplication(sys.argv)


class TestTimingAndGenerationProgressBar(unittest.TestCase):
    def test_extract_progress_bar_format_timing_messages(self):
        """Kiểm tra trích xuất text hiển thị trên thanh tiến trình cho các thông điệp Tạo Timing."""
        fmt1 = SubtitleGenerationPanel._extract_progress_bar_format(
            30, "Đang tạo Timing · Đã gen 3/10 câu (30%)"
        )
        self.assertEqual(fmt1, "30% · Đã gen 3/10 câu")

        fmt2 = SubtitleGenerationPanel._extract_progress_bar_format(
            40, "Đang tiếp tục từ câu 17 · Đã gen 4/10 câu (40%) · Tổng 20 câu"
        )
        self.assertEqual(fmt2, "40% · Đã gen 4/10 câu (Tổng 20 câu)")

        fmt3 = SubtitleGenerationPanel._extract_progress_bar_format(
            100, "Hoàn tất Batch Timing · Đã gen 10/10 câu (100%)"
        )
        self.assertEqual(fmt3, "100% · Đã gen 10/10 câu")

    def test_extract_progress_bar_format_subtitle_gen_messages(self):
        """Kiểm tra trích xuất text hiển thị trên thanh tiến trình cho Tạo Phụ đề (ASR)."""
        fmt1 = SubtitleGenerationPanel._extract_progress_bar_format(
            50, "Đang tạo phụ đề: Đã gen 5/10 câu (50%)"
        )
        self.assertEqual(fmt1, "50% · Đã gen 5/10 câu")

        fmt2 = SubtitleGenerationPanel._extract_progress_bar_format(
            75, "Đang tạo phụ đề (Batch 2/4) · Đã gen 15 câu (75%)"
        )
        self.assertEqual(fmt2, "75% · Đã gen 15 câu")

        fmt3 = SubtitleGenerationPanel._extract_progress_bar_format(
            100, "Hoàn tất tạo phụ đề · Đã gen 20/20 câu (100%)."
        )
        self.assertEqual(fmt3, "100% · Đã gen 20/20 câu")

    def test_extract_progress_bar_format_preliminary_stages(self):
        """Kiểm tra các giai đoạn ban đầu (tải model, trích xuất audio, sẵn sàng)."""
        fmt1 = SubtitleGenerationPanel._extract_progress_bar_format(
            2, "Đang tải Model (base) · Đã gen 0/10 câu (2%)"
        )
        self.assertEqual(fmt1, "2% · Đã gen 0/10 câu")

        fmt2 = SubtitleGenerationPanel._extract_progress_bar_format(0, "Đang trích xuất âm thanh")
        self.assertEqual(fmt2, "Đang trích xuất âm thanh")

        fmt3 = SubtitleGenerationPanel._extract_progress_bar_format(0, "Ready")
        self.assertEqual(fmt3, "0%")

        fmt4 = SubtitleGenerationPanel._extract_progress_bar_format(0, "")
        self.assertEqual(fmt4, "0%")

    def test_unfilled_timing_text_variations(self):
        """Kiểm tra nhận diện câu sub trống/chưa có nội dung theo mọi định dạng viết hoa, thường, khoảng trắng."""
        unfilled_samples = [
            "",
            None,
            "   ",
            "[chưa có nội dung]",
            "[Chưa có nội dung]",
            "[CHƯA CÓ NỘI DUNG]",
            "[ Chưa có nội dung ]",
            "[  Chưa có nội dung  ]",
            "[chua co noi dung]",
            "[chưa có phụ đề]",
            "[empty]",
            "[]",
            "[no content]",
        ]
        for s in unfilled_samples:
            self.assertTrue(
                SubtitleGenerationService._is_unfilled_timing_text(s),
                f"Phải nhận diện '{s}' là câu timing trống!",
            )

        filled_samples = [
            "Xin chào các bạn",
            "チャンスをくれて ...",
            "Hello world",
            "123",
        ]
        for s in filled_samples:
            self.assertFalse(
                SubtitleGenerationService._is_unfilled_timing_text(s),
                f"'{s}' là câu có nội dung, không được coi là trống!",
            )

    def test_panel_progress_bar_attributes_and_update(self):
        """Kiểm tra thanh tiến trình của SubtitleGenerationPanel hiển thị text rõ ràng và không bị che lấp."""
        mock_svc = MagicMock()
        mock_svc.project_service = MagicMock()
        panel = SubtitleGenerationPanel(mock_svc)

        # Kiểm tra kích thước và tính năng hiển thị text
        self.assertTrue(panel.progress_bar.isTextVisible())
        self.assertGreaterEqual(panel.progress_bar.height(), 18)

        # Cập nhật tiến trình Timing
        panel._update_progress(45, "Đang tiếp tục từ câu 10 · Đã gen 9/20 câu (45%)")
        self.assertEqual(panel.progress_bar.value(), 45)
        self.assertIn("45%", panel.progress_bar.format())
        self.assertIn("Đã gen 9/20 câu", panel.progress_bar.format())

    def test_spin_box_limits_with_timing_segments(self):
        """Kiểm tra Spin Box không được vượt quá tổng số câu timing có sẵn."""
        mock_svc = MagicMock()
        mock_svc.project_service = MagicMock()
        panel = SubtitleGenerationPanel(mock_svc)

        # Giả lập có 15 câu sub (trong đó 7 câu trống)
        fake_segments = [
            {"id": i, "start_ms": i * 1000, "end_ms": (i + 1) * 1000, "text": "" if i < 7 else f"Sub {i}"}
            for i in range(15)
        ]
        panel._get_current_segments = lambda: fake_segments

        # Chuyển sang batch_mode = segments
        idx = panel.cmb_batch_mode.findData("segments")
        if idx >= 0:
            panel.cmb_batch_mode.setCurrentIndex(idx)
        panel._sync_batch_spin_limits(reset_default=True)

        # Giới hạn trên của Spin box phải là 15 (tổng số câu)
        self.assertEqual(panel.spin_batch_val.maximum(), 15)
        self.assertEqual(panel.spin_batch_val.minimum(), 1)
        # Giá trị mặc định phải là min(5, pending=7) = 5
        self.assertEqual(panel.spin_batch_val.value(), 5)

    def test_main_window_timing_state_changed_running_updates_progress_bar(self):
        """Kiểm tra MainWindow._on_timing_state_changed khi RUNNING sẽ cập nhật tức thì thanh tiến trình về 0% có kèm số câu."""
        from ui.Gui import MainWindow
        win = MainWindow.__new__(MainWindow)
        win.generation_panel = MagicMock()
        win.page_dashboard = MagicMock()
        win.progress_bar = QProgressBar()
        win.lbl_speed_eta = MagicMock()

        # Giả lập MainWindow._on_timing_progress
        win._on_timing_progress = lambda pct, msg: (
            win.progress_bar.setValue(pct),
            win.progress_bar.setFormat(SubtitleGenerationPanel._extract_progress_bar_format(pct, msg)),
            win.generation_panel._update_progress(pct, msg),
        )

        # Gọi _on_timing_state_changed khi bắt đầu chạy Timing tiếp tục từ câu 17
        msg = "Đang tiếp tục từ câu 17 · Đã gen 0/10 câu (0%)"
        MainWindow._on_timing_state_changed(win, "RUNNING", msg)

        # Thanh tiến trình phải được định dạng ngay lập tức với số câu
        self.assertEqual(win.progress_bar.value(), 0)
        self.assertEqual(win.progress_bar.format(), "0% · Đã gen 0/10 câu")
        win.generation_panel._update_progress.assert_called_with(0, msg)


if __name__ == "__main__":
    unittest.main()
