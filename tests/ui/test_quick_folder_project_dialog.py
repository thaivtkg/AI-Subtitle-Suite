import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.services.project_service import ProjectService
from ui.dialogs.quick_folder_project_dialog import QuickFolderProjectDialog


class TestQuickFolderProjectDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.service = ProjectService()

        # Create dummy video files
        self.v1 = self._create_dummy_file("episode_01.mp4", 1024 * 1024)
        self.v2 = self._create_dummy_file("episode_02.mkv", 2 * 1024 * 1024)
        self.v3 = self._create_dummy_file("teaser_trailer.mov", 512 * 1024)
        # Create an existing project for episode_01
        self.service.create_project(
            str(self.root / "episode_01.ai-subtitle"),
            "episode_01",
            str(self.v1)
        )

        self.dialog = QuickFolderProjectDialog(
            folder_path=str(self.root),
            project_service=self.service
        )

    def tearDown(self):
        self.dialog.close()
        self.temp_dir.cleanup()

    def _create_dummy_file(self, filename: str, size_bytes: int = 1024) -> Path:
        p = self.root / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"0" * size_bytes)
        return p

    def test_dialog_populates_scanned_videos(self):
        """Hộp thoại nạp đầy đủ danh sách video, hiển thị đúng trạng thái cũ / mới và mặc định tích chọn tất cả."""
        table = self.dialog.table
        self.assertEqual(table.rowCount(), 3)

        # Episode 01 đã có dự án
        self.assertEqual(table.item(0, 1).text(), "episode_01.mp4")
        self.assertIn("Đã có dự án", table.item(0, 3).text())
        self.assertEqual(table.item(0, 0).checkState(), Qt.Checked)

        # Episode 02 là video mới
        self.assertEqual(table.item(1, 1).text(), "episode_02.mkv")
        self.assertIn("Mới", table.item(1, 3).text())

        # Teaser trailer là video mới
        self.assertEqual(table.item(2, 1).text(), "teaser_trailer.mov")

        # Label đếm hiển thị 3 / 3
        self.assertIn("3 / 3", self.dialog.lbl_summary.text())

    def test_select_all_and_deselect_all_buttons(self):
        """Bấm 'Bỏ chọn' bỏ tích toàn bộ; bấm 'Chọn tất cả' tích lại toàn bộ và cập nhật nhãn đếm."""
        self.dialog.btn_deselect_all.click()
        self.assertEqual(len(self.dialog.get_selected_videos()), 0)
        self.assertIn("0 / 3", self.dialog.lbl_summary.text())

        self.dialog.btn_select_all.click()
        self.assertEqual(len(self.dialog.get_selected_videos()), 3)
        self.assertIn("3 / 3", self.dialog.lbl_summary.text())

    def test_checkbox_toggle_updates_summary_and_selected_list(self):
        """Bỏ chọn 1 dòng thủ công thì danh sách trả về giảm và nhãn đếm cập nhật đúng."""
        # Bỏ chọn dòng thứ 3 (teaser_trailer.mov)
        item = self.dialog.table.item(2, 0)
        item.setCheckState(Qt.Unchecked)

        selected = self.dialog.get_selected_videos()
        self.assertEqual(len(selected), 2)
        filenames = [s["filename"] for s in selected]
        self.assertEqual(filenames, ["episode_01.mp4", "episode_02.mkv"])
        self.assertIn("2 / 3", self.dialog.lbl_summary.text())

    def test_realtime_search_filter(self):
        """Gõ từ khóa vào ô tìm kiếm thì chỉ hiển thị các dòng khớp tên file."""
        self.dialog.search_input.setText("episode")
        table = self.dialog.table

        # 2 dòng episode hiển thị, dòng teaser bị ẩn
        self.assertFalse(table.isRowHidden(0))
        self.assertFalse(table.isRowHidden(1))
        self.assertTrue(table.isRowHidden(2))

        # Xóa tìm kiếm -> hiển thị lại tất cả
        self.dialog.search_input.setText("")
        self.assertFalse(table.isRowHidden(2))


if __name__ == "__main__":
    unittest.main()
