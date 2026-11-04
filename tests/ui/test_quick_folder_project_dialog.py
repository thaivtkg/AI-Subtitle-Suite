import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
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

    def test_window_title_and_flags_and_close_button(self):
        """Tiêu đề không chứa emoji, cờ WindowCloseButtonHint được thiết lập, và có nút đóng ✕ trên header."""
        self.assertEqual(
            self.dialog.windowTitle(),
            "Tạo Dự Án Nhanh Từ Thư Mục Video - AI Subtitle Suite"
        )
        flags = self.dialog.windowFlags()
        self.assertTrue(bool(flags & Qt.WindowCloseButtonHint))

        self.assertTrue(hasattr(self.dialog, "btn_close_header"))
        self.assertEqual(self.dialog.btn_close_header.text(), "✕")

    def test_button_defaults_and_escaped_ampersand(self):
        """FINDING-QFP-001 & FINDING-UI-001: Nút close không autoDefault, nút Create là default và dấu & được escape."""
        self.assertFalse(self.dialog.btn_close_header.autoDefault())
        self.assertEqual(self.dialog.btn_close_header.focusPolicy(), Qt.NoFocus)
        self.assertTrue(self.dialog.btn_create.isDefault())
        self.assertIn("&&", self.dialog.btn_create.text())

    def test_dialog_populates_scanned_videos_default_unchecked(self):
        """Hộp thoại nạp đủ video, trạng thái cũ/mới, mặc định bỏ chọn 100% (Phương án B) và nút Tạo bị mờ."""
        table = self.dialog.table
        self.assertEqual(table.rowCount(), 3)

        # Episode 01 đã có dự án
        self.assertEqual(table.item(0, 1).text(), "episode_01.mp4")
        self.assertIn("Đã có dự án", table.item(0, 3).text())
        # Mặc định chưa tích chọn
        self.assertEqual(table.item(0, 0).checkState(), Qt.Unchecked)

        # Episode 02 là video mới
        self.assertEqual(table.item(1, 1).text(), "episode_02.mkv")
        self.assertIn("Mới", table.item(1, 3).text())
        self.assertEqual(table.item(1, 0).checkState(), Qt.Unchecked)

        # Teaser trailer là video mới
        self.assertEqual(table.item(2, 1).text(), "teaser_trailer.mov")
        self.assertEqual(table.item(2, 0).checkState(), Qt.Unchecked)

        # Mặc định danh sách chọn rỗng
        self.assertEqual(len(self.dialog.get_selected_videos()), 0)

        # Label đếm hiển thị 0 / 3
        self.assertIn("0 / 3", self.dialog.lbl_summary.text())

        # Nút Tạo Dự Án phải bị vô hiệu hóa (disabled)
        self.assertFalse(self.dialog.btn_create.isEnabled())

    def test_select_all_and_deselect_all_buttons(self):
        """Bấm 'Chọn tất cả' tích lại toàn bộ và kích hoạt nút Tạo; bấm 'Bỏ chọn' hủy toàn bộ và vô hiệu hóa nút Tạo."""
        # Khởi điểm: 0/3 và disabled
        self.assertEqual(len(self.dialog.get_selected_videos()), 0)
        self.assertFalse(self.dialog.btn_create.isEnabled())

        # Bấm Chọn tất cả
        self.dialog.btn_select_all.click()
        self.assertEqual(len(self.dialog.get_selected_videos()), 3)
        self.assertIn("3 / 3", self.dialog.lbl_summary.text())
        self.assertTrue(self.dialog.btn_create.isEnabled())

        # Bấm Bỏ chọn
        self.dialog.btn_deselect_all.click()
        self.assertEqual(len(self.dialog.get_selected_videos()), 0)
        self.assertIn("0 / 3", self.dialog.lbl_summary.text())
        self.assertFalse(self.dialog.btn_create.isEnabled())

    def test_select_all_respects_filter(self):
        """FINDING-EDGE-001: Khi lọc tìm kiếm, 'Chọn tất cả' chỉ chọn các hàng đang hiển thị."""
        self.dialog.search_input.setText("episode")
        self.assertEqual(self.dialog.table.rowCount(), 3)
        self.assertTrue(self.dialog.table.isRowHidden(2))  # teaser hidden

        # Bấm chọn tất cả trong khi đang filter
        self.dialog.btn_select_all.click()
        selected = self.dialog.get_selected_videos()
        self.assertEqual(len(selected), 2)
        filenames = [s["filename"] for s in selected]
        self.assertIn("episode_01.mp4", filenames)
        self.assertIn("episode_02.mkv", filenames)
        self.assertNotIn("teaser_trailer.mov", filenames)

        # Bấm bỏ chọn trong khi đang filter
        self.dialog.btn_deselect_all.click()
        self.assertEqual(len(self.dialog.get_selected_videos()), 0)

    def test_checkbox_toggle_updates_summary_and_selected_list(self):
        """Tích chọn thủ công từng dòng cập nhật danh sách chọn, nhãn đếm và trạng thái kích hoạt nút Tạo."""
        self.assertFalse(self.dialog.btn_create.isEnabled())

        # Tích chọn dòng thứ 0 (episode_01.mp4)
        item0 = self.dialog.table.item(0, 0)
        item0.setCheckState(Qt.Checked)

        selected = self.dialog.get_selected_videos()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["filename"], "episode_01.mp4")
        self.assertIn("1 / 3", self.dialog.lbl_summary.text())
        self.assertTrue(self.dialog.btn_create.isEnabled())

        # Tích thêm dòng thứ 1 (episode_02.mkv)
        item1 = self.dialog.table.item(1, 0)
        item1.setCheckState(Qt.Checked)

        selected = self.dialog.get_selected_videos()
        self.assertEqual(len(selected), 2)
        self.assertIn("2 / 3", self.dialog.lbl_summary.text())
        self.assertTrue(self.dialog.btn_create.isEnabled())

        # Bỏ chọn cả 2 dòng
        item0.setCheckState(Qt.Unchecked)
        item1.setCheckState(Qt.Unchecked)

        self.assertEqual(len(self.dialog.get_selected_videos()), 0)
        self.assertIn("0 / 3", self.dialog.lbl_summary.text())
        self.assertFalse(self.dialog.btn_create.isEnabled())

    def test_enter_key_behavior(self):
        """FINDING-QFP-001: Nhấn Enter khi chưa chọn video không đóng dialog; khi có chọn thì accept()."""
        accepted = []
        self.dialog.accepted.connect(lambda: accepted.append(True))

        # 1. Chưa chọn video (btn_create disabled) -> nhấn Enter không accept
        key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
        self.dialog.keyPressEvent(key_event)
        self.assertEqual(len(accepted), 0)

        # 2. Chọn 1 video -> nhấn Enter kích hoạt accept
        self.dialog.btn_select_all.click()
        self.assertTrue(self.dialog.btn_create.isEnabled())
        self.dialog.keyPressEvent(key_event)
        self.assertEqual(len(accepted), 1)

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
