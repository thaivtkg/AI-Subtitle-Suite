import unittest
from unittest.mock import MagicMock
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel

from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_editing.selection_controller import SubtitleSelectionController
from ui.SubEditor import SubtitleEditorWidget
from ui.dialogs.hotkeys_cheatsheet_dialog import HotkeysCheatsheetDialog


class TestSubEditorArrowNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.undo_manager = GlobalUndoManager()
        self.selection_controller = SubtitleSelectionController()

        self.editor = SubtitleEditorWidget()
        self.editor.undo_manager = self.undo_manager
        self.editor.selection_controller = self.selection_controller
        self.selection_controller.selection_changed.connect(self.editor.sync_selection)

        self.editor.all_segments = [
            {
                "id": "s1",
                "stt": "1",
                "start": "00:00:01,000",
                "end": "00:00:04,000",
                "start_ms": 1000,
                "end_ms": 4000,
                "text": "Câu một ban đầu",
            },
            {
                "id": "s2",
                "stt": "2",
                "start": "00:00:05,000",
                "end": "00:00:08,000",
                "start_ms": 5000,
                "end_ms": 8000,
                "text": "Câu hai tiếp theo",
            },
            {
                "id": "s3",
                "stt": "3",
                "start": "00:00:09,000",
                "end": "00:00:12,000",
                "start_ms": 9000,
                "end_ms": 12000,
                "text": "Câu ba kết thúc",
            },
        ]
        self.editor.render_page()
        self.editor.select_segment(0)

    def tearDown(self):
        self.editor.close()

    def test_tc_arrow_001_alt_down_commits_and_navigates_to_next(self):
        """TC-ARROW-001: Bấm Alt+Down trong ô text_edit tự động commit câu 1 và chuyển sang câu 2 với text được bôi đen."""
        text_edit = self.editor.current_editor.text_edit
        text_edit.setFocus()
        text_edit.setPlainText("Câu một đã sửa")

        # Gửi sự kiện Alt+Down vào text_edit
        key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.AltModifier)
        res = self.editor.eventFilter(text_edit, key_event)
        self.assertTrue(res)

        # Kiểm tra câu 1 đã được commit vào all_segments
        self.assertEqual(self.editor.all_segments[0]["text"], "Câu một đã sửa")
        # Đã chuyển sang câu 2
        self.assertEqual(self.editor.current_index, 1)
        self.assertEqual(self.editor.current_editor.text_edit.toPlainText(), "Câu hai tiếp theo")
        # Toàn bộ text câu 2 được bôi đen sẵn sàng gõ đè
        self.assertTrue(self.editor.current_editor.text_edit.textCursor().hasSelection())

    def test_tc_arrow_002_alt_up_commits_and_navigates_to_prev(self):
        """TC-ARROW-002: Bấm Alt+Up trong ô text_edit câu 2 tự động commit và lùi về câu 1."""
        self.editor.select_segment(1)
        text_edit = self.editor.current_editor.text_edit
        text_edit.setFocus()
        text_edit.setPlainText("Câu hai sửa dở")

        # Gửi sự kiện Alt+Up
        key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.AltModifier)
        res = self.editor.eventFilter(text_edit, key_event)
        self.assertTrue(res)

        # Kiểm tra câu 2 đã được lưu
        self.assertEqual(self.editor.all_segments[1]["text"], "Câu hai sửa dở")
        # Đã lùi về câu 1
        self.assertEqual(self.editor.current_index, 0)
        self.assertEqual(self.editor.current_editor.text_edit.toPlainText(), "Câu một ban đầu")
        self.assertTrue(self.editor.current_editor.text_edit.textCursor().hasSelection())

    def test_tc_arrow_003_table_focus_preservation_on_arrow_navigation(self):
        """TC-ARROW-003: Khi duyệt trên bảng phụ đề, bảng giữ nguyên focus (không bị cướp về text_edit)."""
        self.editor.show()
        self.editor.activateWindow()
        self.app.processEvents()
        self.editor.table.setFocus()
        self.app.processEvents()
        self.assertTrue(self.editor.table.hasFocus())

        # Chọn câu 1 khi bảng đang có focus
        self.editor.select_segment(1)
        self.app.processEvents()

        # Bảng phải GIỮ NGUYÊN FOCUS để người dùng tiếp tục bấm mũi tên Up/Down duyệt liên tục
        self.assertTrue(self.editor.table.hasFocus())
        self.assertFalse(self.editor.current_editor.text_edit.hasFocus())

        # Tiếp tục chọn câu 2
        self.editor.select_segment(2)
        self.app.processEvents()
        self.assertTrue(self.editor.table.hasFocus())

    def test_tc_arrow_004_shortcuts_registration(self):
        """TC-ARROW-004: Kiểm tra các phím tắt Alt+Up / Alt+Down đã được đăng ký đầy đủ trên SubEditor."""
        self.assertTrue(hasattr(self.editor, "shortcut_prev_alt_up"))
        self.assertTrue(hasattr(self.editor, "shortcut_next_alt_down"))
        self.assertEqual(self.editor.shortcut_prev_alt_up.key().toString(), "Alt+Up")
        self.assertEqual(self.editor.shortcut_next_alt_down.key().toString(), "Alt+Down")

    def test_tc_arrow_005_hotkeys_cheatsheet_sync(self):
        """TC-ARROW-005: Bảng cheatsheet F1 hiển thị đồng bộ phím tắt Alt + ▲ / ▼."""
        dialog = HotkeysCheatsheetDialog()
        labels = [lbl.text() for lbl in dialog.findChildren(QLabel)]
        text_content = " ".join(labels)
        self.assertIn("Alt", text_content)
        self.assertIn("▲ / ▼", text_content)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
