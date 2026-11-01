import unittest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton
from ui.dialogs.hotkeys_cheatsheet_dialog import HotkeysCheatsheetDialog
from ui.pages.help_center_page import HelpCenterPage


class TestHotkeysDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hotkeys_dialog_initialization(self):
        """HotkeysCheatsheetDialog khởi tạo thành công với kích thước chuẩn và layout."""
        dialog = HotkeysCheatsheetDialog()
        self.assertEqual(dialog.width(), 580)
        self.assertEqual(dialog.height(), 610)
        self.assertFalse(dialog.isModal())

        # Kiểm tra nút close ✕ và thuộc tính padding: 0px chống xung đột
        btn_close = dialog.findChild(QPushButton)
        self.assertIsNotNone(btn_close)
        self.assertEqual(btn_close.text(), "✕")
        self.assertEqual(btn_close.width(), 30)
        self.assertEqual(btn_close.height(), 26)
        self.assertIn("padding: 0px", btn_close.styleSheet())

        dialog.close()

    def test_hotkeys_dialog_header_drag(self):
        """Kéo chuột trên header (y <= 48) kích hoạt di chuyển cửa sổ."""
        dialog = HotkeysCheatsheetDialog()
        pos = QPointF(100, 20)
        event = QMouseEvent(QEvent.Type.MouseButtonPress, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        dialog.mousePressEvent(event)
        self.assertIsNotNone(dialog._drag_pos)

        # Thả chuột đặt lại _drag_pos
        rel_event = QMouseEvent(QEvent.Type.MouseButtonRelease, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        dialog.mouseReleaseEvent(rel_event)
        self.assertIsNone(dialog._drag_pos)
        dialog.close()

    def test_help_center_shortcuts_hidden(self):
        """Đảm bảo phím tắt đã được ẩn khỏi trang Help Center."""
        page = HelpCenterPage()
        self.assertTrue(page._shortcuts.isHidden())

    def test_hotkeys_dialog_cat_studio_group(self):
        """AUD-UX-003: Kiểm tra Nhóm 4 CAT Translation Studio tồn tại đầy đủ trong bảng phím tắt."""
        from PySide6.QtWidgets import QLabel
        dialog = HotkeysCheatsheetDialog()
        labels = [lbl.text() for lbl in dialog.findChildren(QLabel)]
        self.assertTrue(any("CAT TRANSLATION STUDIO" in t for t in labels))
        self.assertTrue(any("AI Translate" in t for t in labels))
        self.assertTrue(any("Add to Glossary" in t for t in labels))
        dialog.close()


if __name__ == "__main__":
    unittest.main()
