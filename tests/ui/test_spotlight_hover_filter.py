# -*- coding: utf-8 -*-
"""
Tests for FR-03: 3 Dynamic Hover Interactions & Spotlight Event Filter (DEV-SPEC-PHASE1-HUD-001).
Validates:
1. SpotlightEventFilter: 60 FPS throttling (>= 16.6ms intervals between repaint updates).
2. Event Filter Transparency: Mouse click, double click, mouse wheel, and key events return False
   (never blocked or consumed), ensuring full interaction preservation for underlying widgets.
3. Hover & Leave Lifecycle: Tracks mouse position on Enter/MouseMove, resets to None on Leave.
4. apply_spotlight_effect utility installs the filter on a target widget cleanly.
"""
import os
import unittest
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLineEdit

from ui.core.liquid_theme_engine import SpotlightEventFilter, apply_spotlight_effect


app = QApplication.instance() or QApplication([])


class TestSpotlightHoverFilter(unittest.TestCase):
    def setUp(self):
        self.widget = QWidget()
        self.widget.resize(300, 200)
        self.filter = apply_spotlight_effect(self.widget)

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def test_apply_spotlight_effect_attaches_filter(self):
        self.assertIsNotNone(self.filter)
        self.assertIsInstance(self.filter, SpotlightEventFilter)
        self.assertTrue(self.widget.hasMouseTracking())
        self.assertIs(getattr(self.widget, "_spotlight_filter", None), self.filter)

    def test_mouse_move_tracks_position(self):
        event = QMouseEvent(
            QEvent.MouseMove,
            QPointF(50, 75),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        consumed = self.filter.eventFilter(self.widget, event)
        # Transparency check: must return False
        self.assertFalse(consumed)
        self.assertTrue(self.filter.is_hovered)
        self.assertEqual(self.filter.hover_pos, QPoint(50, 75))

    def test_mouse_leave_resets_hover_state(self):
        # First hover
        move_event = QMouseEvent(
            QEvent.MouseMove,
            QPointF(100, 100),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        self.filter.eventFilter(self.widget, move_event)
        self.assertTrue(self.filter.is_hovered)
        self.assertIsNotNone(self.filter.hover_pos)

        # Leave event
        leave_event = QEvent(QEvent.Leave)
        consumed = self.filter.eventFilter(self.widget, leave_event)
        self.assertFalse(consumed)
        self.assertFalse(self.filter.is_hovered)
        self.assertIsNone(self.filter.hover_pos)

    def test_transparency_rule_never_consumes_clicks_or_wheels(self):
        """Tất cả các sự kiện nhấn chuột, nhả chuột, cuộn chuột đều phải trả về False."""
        press_event = QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(20, 20),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        self.assertFalse(self.filter.eventFilter(self.widget, press_event))

        release_event = QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(20, 20),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        self.assertFalse(self.filter.eventFilter(self.widget, release_event))

        wheel_event = QWheelEvent(
            QPointF(20, 20),
            QPointF(20, 20),
            QPoint(0, 120),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False,
        )
        self.assertFalse(self.filter.eventFilter(self.widget, wheel_event))

        key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier, "a")
        self.assertFalse(self.filter.eventFilter(self.widget, key_event))

    def test_throttling_60fps_prevents_excessive_repaints(self):
        """Kiểm tra tần suất cập nhật không vượt quá 60 FPS (khoảng cách giữa các repaint >= 16ms)."""
        self.filter.last_update_ms = 0
        self.filter.timer.restart()

        # Giả lập 10 sự kiện chuột liên tiếp siêu nhanh (0 delay)
        repaints = 0
        for i in range(10):
            event = QMouseEvent(
                QEvent.MouseMove,
                QPointF(10 + i, 10 + i),
                Qt.NoButton,
                Qt.NoButton,
                Qt.NoModifier,
            )
            # Giả định last_update_ms được gán trong filter
            prev_last = self.filter.last_update_ms
            self.filter.eventFilter(self.widget, event)
            if self.filter.last_update_ms != prev_last:
                repaints += 1

        # Trong một burst micro-second, repaints phải bị throttle chặt chẽ (tối đa 1-2 lần thay vì 10)
        self.assertLessEqual(repaints, 2)


if __name__ == "__main__":
    unittest.main()
