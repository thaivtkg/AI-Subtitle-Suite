# -*- coding: utf-8 -*-
"""
Tests for AC-06: Exception Shielding for QMainWindow::eventFilter & Legacy WMV.
Validates:
1. When key events (Space, Delete, Insert, [, ], etc.) trigger exceptions in video player,
   sub_editor, or internal handlers, eventFilter catches the exception cleanly and returns False.
2. No unhandled Python exception escapes to the Qt C++ event loop.
3. Normal shortcuts function properly without exception.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ui.Gui import MainWindow

app = QApplication.instance() or QApplication([])


class TestEventFilterExceptionShield(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Instantiate MainWindow in offscreen mode
        cls.win = MainWindow()
        cls.win.show()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        cls.win.deleteLater()

    def test_space_key_exception_in_video_player_is_shielded(self):
        """Khi video_player.toggle_playback() ném lỗi (ví dụ lỗi PTS stream WMV/ASF),
        eventFilter phải bọc bắt và không được ném ra ngoài."""
        # Giả lập video_player.toggle_playback() quăng RuntimeError
        self.win.stack.setCurrentIndex(1)
        with patch.object(self.win.video_player, "toggle_playback", side_effect=RuntimeError("asf_read_pts failed: skipped samples")):
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
            try:
                result = self.win.eventFilter(self.win, event)
                # Phải bắt được exception và trả về False hoặc True an toàn, KHÔNG được crash
                self.assertIn(result, [True, False])
            except Exception as e:
                self.fail(f"eventFilter để lộ exception ra ngoài: {e}")

    def test_delete_key_exception_in_sub_editor_is_shielded(self):
        """Khi sub_editor.trigger_delete() ném lỗi, eventFilter phải nuốt lỗi an toàn."""
        self.win.stack.setCurrentIndex(1)
        with patch.object(self.win.sub_editor, "trigger_delete", side_effect=ValueError("Corrupted subtitle row")):
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
            try:
                result = self.win.eventFilter(self.win, event)
                self.assertIn(result, [True, False])
            except Exception as e:
                self.fail(f"eventFilter để lộ exception khi nhấn Delete: {e}")

    def test_arbitrary_exception_in_event_filter_returns_false(self):
        """Khi xảy ra bất kỳ ngoại lệ nào trong thân hàm eventFilter (kể cả lỗi focusWidget), trả về False."""
        self.win.stack.setCurrentIndex(1)
        with patch("PySide6.QtWidgets.QApplication.focusWidget", side_effect=RuntimeError("Internal C++ object already deleted")):
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
            try:
                result = self.win.eventFilter(self.win, event)
                self.assertFalse(result)
            except Exception as e:
                self.fail(f"eventFilter để lộ exception khi focusWidget bị hủy: {e}")

    def test_normal_navigation_and_resize_without_exception(self):
        """Kiểm tra hoạt động bình thường không ném ngoại lệ."""
        resize_event = QEvent(QEvent.Resize)
        result = self.win.eventFilter(self.win.centralWidget(), resize_event)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
