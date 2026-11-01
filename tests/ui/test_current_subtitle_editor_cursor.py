import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from ui.SubEditor import SubtitleEditorWidget
from core.subtitle_editing.global_undo_manager import GlobalUndoManager


class TestCurrentSubtitleEditorCursor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = SubtitleEditorWidget()
        self.undo_manager = GlobalUndoManager()
        self.editor.undo_manager = self.undo_manager
        # Simulating Gui.py line 626 connection:
        self.undo_manager.state_changed.connect(self.editor.render_page)
        self.editor.all_segments = [
            {"stt": "1", "start": "00:00:01,000", "end": "00:00:02,500", "text": "Câu một ban đầu"},
            {"stt": "2", "start": "00:00:03,000", "end": "00:00:04,500", "text": "Câu hai"},
        ]
        self.editor.render_page()
        self.editor.select_segment(0)

    def tearDown(self):
        self.editor.deleteLater()

    def test_tc_edt_01_continuous_typing_preserves_cursor(self):
        """TC-EDT-01: User types and after debounce emission, cursor must NOT reset to 0."""
        self.editor.current_editor.text_edit.setFocus()
        self.editor.current_editor.text_edit.setPlainText("Kiểm tra gõ tiếng Việt")
        cursor = self.editor.current_editor.text_edit.textCursor()
        cursor.setPosition(len("Kiểm tra gõ tiếng Việt"))
        self.editor.current_editor.text_edit.setTextCursor(cursor)

        self.editor.current_editor._emit_changed()

        actual_pos = self.editor.current_editor.text_edit.textCursor().position()
        self.assertEqual(actual_pos, len("Kiểm tra gõ tiếng Việt"))
        self.assertEqual(self.editor.all_segments[0]["text"], "Kiểm tra gõ tiếng Việt")

    def test_tc_edt_02_rapid_backspacing_preserves_cursor(self):
        """TC-EDT-02: Rapid backspacing preserves cursor position instead of jumping to index 0."""
        self.editor.current_editor.text_edit.setFocus()
        self.editor.current_editor.text_edit.setPlainText("0123456789")
        cursor = self.editor.current_editor.text_edit.textCursor()
        cursor.setPosition(10)
        self.editor.current_editor.text_edit.setTextCursor(cursor)
        self.editor.current_editor._emit_changed()

        # Simulate backspaces down to 5 chars
        self.editor.current_editor.text_edit.setPlainText("01234")
        cursor = self.editor.current_editor.text_edit.textCursor()
        cursor.setPosition(5)
        self.editor.current_editor.text_edit.setTextCursor(cursor)
        self.editor.current_editor._emit_changed()

        actual_pos = self.editor.current_editor.text_edit.textCursor().position()
        self.assertEqual(actual_pos, 5)
        self.assertEqual(self.editor.all_segments[0]["text"], "01234")

    def test_tc_edt_03_mid_sentence_edit_preserves_cursor(self):
        """TC-EDT-03: Editing in the middle of a sentence preserves cursor position."""
        self.editor.current_editor.text_edit.setFocus()
        self.editor.current_editor.text_edit.setPlainText("Câu ban đầu")
        cursor = self.editor.current_editor.text_edit.textCursor()
        cursor.setPosition(4)
        self.editor.current_editor.text_edit.setTextCursor(cursor)

        # Insert "chèn " -> "Câu chèn ban đầu"
        self.editor.current_editor.text_edit.setPlainText("Câu chèn ban đầu")
        cursor.setPosition(9)
        self.editor.current_editor.text_edit.setTextCursor(cursor)

        self.editor.current_editor._emit_changed()

        actual_pos = self.editor.current_editor.text_edit.textCursor().position()
        self.assertEqual(actual_pos, 9)
        self.assertEqual(self.editor.all_segments[0]["text"], "Câu chèn ban đầu")

    def test_tc_edt_04_undo_redo_syncs_current_editor_and_table(self):
        """TC-EDT-04: Undo/Redo reflects in both CurrentSubtitleEditor and table."""
        self.editor.current_editor.text_edit.setPlainText("Nội dung mới")
        self.editor.current_editor._emit_changed()
        self.assertEqual(self.editor.all_segments[0]["text"], "Nội dung mới")
        self.assertEqual(self.editor.table.item(0, self.editor.COL_TEXT).text(), "Nội dung mới")

        self.undo_manager.undo()
        self.assertEqual(self.editor.all_segments[0]["text"], "Câu một ban đầu")
        self.assertEqual(self.editor.current_editor.text_edit.toPlainText(), "Câu một ban đầu")
        self.assertEqual(self.editor.table.item(0, self.editor.COL_TEXT).text(), "Câu một ban đầu")

        self.undo_manager.redo()
        self.assertEqual(self.editor.all_segments[0]["text"], "Nội dung mới")
        self.assertEqual(self.editor.current_editor.text_edit.toPlainText(), "Nội dung mới")
        self.assertEqual(self.editor.table.item(0, self.editor.COL_TEXT).text(), "Nội dung mới")

    def test_tc_edt_05_row_navigation_loads_correct_segment(self):
        """TC-EDT-05: Row navigation updates CurrentSubtitleEditor title and text."""
        self.editor.select_segment(1)
        self.assertEqual(self.editor.current_editor.text_edit.toPlainText(), "Câu hai")
        self.assertEqual(self.editor.current_editor.lbl_title.text(), "#2")

        self.editor.select_segment(0)
        self.assertEqual(self.editor.current_editor.text_edit.toPlainText(), "Câu một ban đầu")
        self.assertEqual(self.editor.current_editor.lbl_title.text(), "#1")
