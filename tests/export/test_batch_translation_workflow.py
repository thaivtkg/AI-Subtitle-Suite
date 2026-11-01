import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from ui.Gui import MainWindow
from ui.pages.export_center_page import ExportCenterPage
from ui.SubEditor import SubtitleEditorWidget


class TestBatchTranslationWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _sample_segments(self, count=10):
        segs = []
        for i in range(1, count + 1):
            start_sec = (i - 1) * 2
            end_sec = start_sec + 2
            segs.append({
                "stt": str(i),
                "id": f"seg_id_{i}",
                "start": f"00:00:{start_sec:02d},000",
                "end": f"00:00:{end_sec:02d},000",
                "text": f"Original line {i}" if i > 5 else "[ Chưa có nội dung ]",
            })
        return segs

    def test_tc_batch_01_export_partial_slice(self):
        win = MainWindow.__new__(MainWindow)
        win.sub_editor = SubtitleEditorWidget()
        win.sub_editor.all_segments = self._sample_segments(10)
        win.page_export = ExportCenterPage()
        win.queue_mgr = MagicMock(active_vid="test_movie.mp4")
        win.output_dir = tempfile.gettempdir()

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_srt = os.path.join(tmp_dir, "batch_1_to_5.srt")
            with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(out_srt, "SRT Files (*.srt)")):
                win._on_export_batch_translation_requested(1, 5)

            self.assertTrue(os.path.exists(out_srt), "File SRT đợt dịch phải được tạo.")
            with open(out_srt, "r", encoding="utf-8") as f:
                content = f.read().strip()

            blocks = content.split("\n\n")
            self.assertEqual(len(blocks), 5, "Phải xuất chính xác 5 câu theo đợt.")
            # Check first block
            lines = blocks[0].split("\n")
            self.assertEqual(lines[0], "1")
            self.assertEqual(lines[1], "00:00:00,000 --> 00:00:02,000")
            # Placeholder text should be empty
            self.assertEqual(len(lines), 2)  # 1 and timestamp, empty text

    def test_tc_batch_02_import_updates_text_preserves_timing(self):
        win = MainWindow.__new__(MainWindow)
        win.sub_editor = SubtitleEditorWidget()
        win.sub_editor.all_segments = self._sample_segments(10)
        win.page_export = ExportCenterPage()
        win.output_dir = tempfile.gettempdir()
        win.project_service = MagicMock()
        win.sub_editor.render_page = MagicMock()
        win.sub_editor.live_edit_applied = MagicMock()

        # Create translated SRT content for first 5 segments
        translated_srt = (
            "1\n00:00:00,000 --> 00:00:02,000\nXin chào câu 1\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nXin chào câu 2\n\n"
            "3\n00:00:04,000 --> 00:00:06,000\nXin chào câu 3\n\n"
            "4\n00:00:06,000 --> 00:00:08,000\nXin chào câu 4\n\n"
            "5\n00:00:08,000 --> 00:00:10,000\nXin chào câu 5\n"
        )

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".srt", delete=False) as tf:
            tf.write(translated_srt)
            tf_path = tf.name

        try:
            with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(tf_path, "SRT Files (*.srt)")):
                win._on_import_batch_translation_requested()

            # Verify segments 1..5 are updated to Vietnamese
            for i in range(5):
                self.assertEqual(win.sub_editor.all_segments[i]["text"], f"Xin chào câu {i + 1}")
                self.assertEqual(win.sub_editor.all_segments[i]["id"], f"seg_id_{i + 1}")
                self.assertEqual(win.sub_editor.all_segments[i]["start"], f"00:00:{i * 2:02d},000")

            # Verify segments 6..10 remain untouched
            for i in range(5, 10):
                self.assertEqual(win.sub_editor.all_segments[i]["text"], f"Original line {i + 1}")
                self.assertEqual(win.sub_editor.all_segments[i]["id"], f"seg_id_{i + 1}")

            win.sub_editor.render_page.assert_called_once()
            win.sub_editor.live_edit_applied.emit.assert_called_once()
            win.project_service.mark_dirty.assert_called_once()
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_tc_batch_03_auto_advance_cursor(self):
        win = MainWindow.__new__(MainWindow)
        win.sub_editor = SubtitleEditorWidget()
        win.sub_editor.all_segments = self._sample_segments(10)
        win.page_export = ExportCenterPage()
        win.output_dir = tempfile.gettempdir()
        win.project_service = MagicMock()
        win.sub_editor.render_page = MagicMock()
        win.sub_editor.live_edit_applied = MagicMock()

        # Import 5 segments
        translated_srt = (
            "1\n00:00:00,000 --> 00:00:02,000\nĐoạn dịch 1\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nĐoạn dịch 2\n\n"
            "3\n00:00:04,000 --> 00:00:06,000\nĐoạn dịch 3\n\n"
            "4\n00:00:06,000 --> 00:00:08,000\nĐoạn dịch 4\n\n"
            "5\n00:00:08,000 --> 00:00:10,000\nĐoạn dịch 5\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".srt", delete=False) as tf:
            tf.write(translated_srt)
            tf_path = tf.name

        try:
            with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(tf_path, "SRT Files (*.srt)")):
                win._on_import_batch_translation_requested()

            # Cursor should advance to segment #6
            self.assertEqual(win.page_export.spin_batch_start.value(), 6)
            self.assertIn("Câu #6", win.page_export.lbl_batch_progress.text())
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_tc_batch_04_ui_elements_and_signals(self):
        page = ExportCenterPage()
        self.assertTrue(hasattr(page, "spin_batch_start"))
        self.assertTrue(hasattr(page, "spin_batch_count"))
        self.assertTrue(hasattr(page, "btn_export_batch"))
        self.assertTrue(hasattr(page, "btn_import_batch"))
        self.assertTrue(hasattr(page, "lbl_batch_progress"))

        captured_export = []
        page.export_batch_translation_requested.connect(lambda s, c: captured_export.append((s, c)))

        page.spin_batch_start.setValue(7)
        page.spin_batch_count.setValue(10)
        page.btn_export_batch.click()
        self.assertEqual(captured_export, [(7, 10)])

        captured_import = []
        page.import_batch_translation_requested.connect(lambda: captured_import.append(True))
        page.btn_import_batch.click()
        self.assertEqual(captured_import, [True])

    def test_tc_batch_05_sync_skips_vietnamese_and_targets_cjk(self):
        """Khi 1-5 là tiếng Việt và 6-10 là tiếng Nhật, hệ thống gợi ý đợt tiếp theo từ câu #6."""
        win = MainWindow.__new__(MainWindow)
        segs = []
        for i in range(1, 11):
            text = f"Đã dịch câu số {i}" if i <= 5 else "どんな暗闇でも"
            segs.append({"stt": str(i), "id": f"seg_{i}", "start": "00:00:00,000", "end": "00:00:02,000", "text": text})
        win.sub_editor = SimpleNamespace(all_segments=segs)
        win.page_export = ExportCenterPage()
        try:
            win._sync_translation_batch_ui()

            self.assertEqual(win.page_export.spin_batch_start.value(), 6)
            self.assertIn("Đã dịch 5/10 câu", win.page_export.lbl_batch_progress.text())
            self.assertIn("Câu #6 đến #10", win.page_export.lbl_batch_progress.text())
        finally:
            win.page_export.deleteLater()

    def test_tc_batch_06_fully_translated_completed_state(self):
        """Khi toàn bộ câu đều là Tiếng Việt, UI hiển thị huy hiệu hoàn thành và giữ max value."""
        win = MainWindow.__new__(MainWindow)
        segs = [
            {"stt": str(i), "id": f"seg_{i}", "start": "00:00:00,000", "end": "00:00:02,000", "text": f"Đoạn dịch tiếng Việt {i}"}
            for i in range(1, 11)
        ]
        win.sub_editor = SimpleNamespace(all_segments=segs)
        win.page_export = ExportCenterPage()
        try:
            win._sync_translation_batch_ui()

            self.assertIn("Đã hoàn thành dịch toàn bộ (10/10 câu)", win.page_export.lbl_batch_progress.text())
            self.assertEqual(win.page_export.spin_batch_start.value(), 10)
        finally:
            win.page_export.deleteLater()

    def test_tc_batch_07_export_preflight_guard(self):
        """Xuất dải câu đã dịch 100% tiếng Việt sẽ kích hoạt hộp thoại cảnh báo."""
        from PySide6.QtWidgets import QMessageBox

        win = MainWindow.__new__(MainWindow)
        win.sub_editor = SimpleNamespace(all_segments=[
            {"stt": "1", "id": "seg_1", "start": "00:00:00,000", "end": "00:00:02,000", "text": "Câu một đã dịch"},
            {"stt": "2", "id": "seg_2", "start": "00:00:02,000", "end": "00:00:04,000", "text": "Câu hai đã dịch"},
        ])
        win.page_export = ExportCenterPage()
        win.queue_mgr = MagicMock(active_vid="video.mp4")
        win.output_dir = tempfile.gettempdir()

        try:
            with patch("PySide6.QtWidgets.QMessageBox.warning", return_value=QMessageBox.No) as mock_warn, \
                 patch("PySide6.QtWidgets.QFileDialog.getSaveFileName") as mock_save:
                # Chọn No -> Hủy xuất
                win._on_export_batch_translation_requested(1, 2)
                mock_warn.assert_called_once()
                mock_save.assert_not_called()

            with tempfile.TemporaryDirectory() as tmp_dir:
                out_file = os.path.join(tmp_dir, "batch.srt")
                with patch("PySide6.QtWidgets.QMessageBox.warning", return_value=QMessageBox.Yes) as mock_warn, \
                     patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(out_file, "SRT Files (*.srt)")):
                    # Chọn Yes -> Vẫn tiếp tục xuất
                    win._on_export_batch_translation_requested(1, 2)
                    mock_warn.assert_called_once()
                    self.assertTrue(os.path.exists(out_file))
        finally:
            win.page_export.deleteLater()

    def test_tc_batch_08_remaining_sentences_clamped_batch_count(self):
        """Khi còn 4 câu chưa dịch (15..18/18), spin_batch_count tự động hạ về 4 và max=4."""
        page = ExportCenterPage()
        try:
            page.update_translation_progress(current_start=15, total_count=18, translated_count=14)
            self.assertEqual(page.spin_batch_start.value(), 15)
            self.assertEqual(page.spin_batch_count.value(), 4)
            self.assertEqual(page.spin_batch_count.maximum(), 4)
            self.assertIn("Câu #15 đến #18", page.lbl_batch_progress.text())
        finally:
            page.deleteLater()

    def test_tc_batch_09_start_change_dynamically_adjusts_max_count_and_label(self):
        """Khi đổi câu bắt đầu trên UI, trần số câu xuất và nhãn hiển thị tự động cập nhật."""
        page = ExportCenterPage()
        try:
            page.update_translation_progress(current_start=1, total_count=18, translated_count=0)
            self.assertEqual(page.spin_batch_count.value(), 5)
            self.assertEqual(page.spin_batch_count.maximum(), 18)

            # Đổi câu bắt đầu lên 16 -> chỉ còn 3 câu (16, 17, 18)
            page.spin_batch_start.setValue(16)
            self.assertEqual(page.spin_batch_count.maximum(), 3)
            self.assertEqual(page.spin_batch_count.value(), 3)
            self.assertIn("Câu #16 đến #18", page.lbl_batch_progress.text())
        finally:
            page.deleteLater()
