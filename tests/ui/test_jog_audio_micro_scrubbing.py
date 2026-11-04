# -*- coding: utf-8 -*-
"""
Tests for FR-05 / AC-05: Jog-Audio Micro-Scrubbing (Alt + Drag) (DEV-SPEC-PHASE2-AV-001).
Validates:
1. JogAudioEngine extracts exact 40ms PCM slice at mouse cursor timestamp ([current_ms - 20ms, current_ms + 20ms]).
2. Boundary protection: center at 0ms, near EOF, or corrupted data returns safely without throwing.
3. Instant Cutoff: stop() flushes audio buffer and halts playback in < 10ms.
4. Legacy Codec Shield: PTS errors/ASF skipped samples are caught silently.
5. TimelineController Alt+Drag interaction:
   - Holding Alt + Left Mouse Move triggers play_slice.
   - Releasing Left Mouse or releasing Alt key triggers stop().
"""
import os
import unittest
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication

from core.audio.jog_audio_engine import JogAudioEngine
from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_editing.selection_controller import SubtitleSelectionController
from core.timeline.timeline_controller import TimelineController
from core.timeline.timeline_data_provider import TimelineDataProvider
from ui.timeline.timeline_widget import TimelineWidget


app = QApplication.instance() or QApplication([])


class TestJogAudioMicroScrubbing(unittest.TestCase):
    def setUp(self):
        self.engine = JogAudioEngine(sample_rate=8000)
        # Create 5 seconds of 8000Hz 16-bit mono audio (40,000 samples)
        self.raw_samples = (np.sin(np.linspace(0, 100 * np.pi, 40000)) * 10000).astype(np.int16)
        self.engine.load_pcm_data(self.raw_samples, sample_rate=8000)

    def tearDown(self):
        self.engine.stop()

    def test_extract_slice_calculates_correct_bounds(self):
        """40ms tại mốc 1000ms = [980ms, 1020ms] -> 320 mẫu (640 bytes)."""
        raw_bytes = self.engine.extract_slice(center_ms=1000, duration_ms=40)
        self.assertEqual(len(raw_bytes), 320 * 2)  # 320 int16 samples * 2 bytes = 640 bytes

    def test_extract_slice_clamps_at_zero_and_eof(self):
        """Mốc 0ms được kẹp từ 0 đến 20ms (160 mẫu)."""
        raw_bytes_zero = self.engine.extract_slice(center_ms=0, duration_ms=40)
        self.assertEqual(len(raw_bytes_zero), 160 * 2)

        # Mốc vượt quá độ dài audio (10,000ms > 5000ms)
        raw_bytes_eof = self.engine.extract_slice(center_ms=10000, duration_ms=40)
        self.assertEqual(raw_bytes_eof, b"")

        # pcm_data rỗng
        self.engine.load_pcm_data(None)
        self.assertEqual(self.engine.extract_slice(1000, 40), b"")

    def test_play_slice_and_stop_lifecycle(self):
        """play_slice kích hoạt phát, stop() dừng ngay lập tức."""
        success = self.engine.play_slice(center_ms=1000, duration_ms=40)
        self.assertTrue(success)
        self.assertTrue(self.engine.is_playing)

        self.engine.stop()
        self.assertFalse(self.engine.is_playing)

    def test_stop_executes_within_ten_milliseconds(self):
        """Cơ chế ngắt an toàn phải hoàn tất trong < 10ms."""
        self.engine.play_slice(center_ms=1000, duration_ms=40)
        t0 = time.perf_counter()
        self.engine.stop()
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0
        self.assertLess(elapsed_ms, 10.0)

    def test_legacy_wmv_pts_exception_shield(self):
        """Khi trích xuất slice gặp lỗi PTS / buffer hỏng, engine nuốt lỗi im lặng và trả về False."""
        with patch.object(self.engine, "extract_slice", side_effect=RuntimeError("asf_read_pts failed")):
            success = self.engine.play_slice(center_ms=500, duration_ms=40)
            self.assertFalse(success)
            self.assertFalse(self.engine.is_playing)


class TestJogAudioTimelineIntegration(unittest.TestCase):
    def setUp(self):
        self.timeline = TimelineWidget()
        self.provider = TimelineDataProvider()
        self.rows = [
            {"id": "s1", "stt": "1", "start_ms": 1000, "end_ms": 3000, "text": "one", "status": "generated"}
        ]
        self.provider.load_runtime_data(self.rows, 10000)
        self.timeline.load_project_data(10000, self.provider.get_all_segments())
        self.undo = GlobalUndoManager()
        self.selection = SubtitleSelectionController()
        self.project = SimpleNamespace(
            current_project=SimpleNamespace(state=SimpleNamespace(active_artifact_id="sub")),
            artifact_store=SimpleNamespace(get=lambda _id: None),
            mark_dirty=lambda: None,
        )
        self.controller = TimelineController(
            self.project, self.timeline, self.provider, self.undo, self.selection
        )
        self.timeline.show()

    def tearDown(self):
        self.undo.undo_stack.cleanChanged.disconnect()
        self.timeline.close()
        self.timeline.deleteLater()

    def test_timeline_widget_has_jog_engine(self):
        """TimelineWidget phải sở hữu thuộc tính jog_engine."""
        self.assertTrue(hasattr(self.timeline, "jog_engine"))
        self.assertIsInstance(self.timeline.jog_engine, JogAudioEngine)

    def test_alt_drag_on_waveform_calls_jog_play_slice(self):
        """Kéo chuột kèm giữ Alt trên Waveform kích hoạt jog_engine.play_slice."""
        self.timeline.jog_engine.play_slice = MagicMock()
        ruler = self.timeline.container.ruler

        # Giả lập MouseMove với AltModifier và LeftButton
        move_event = QMouseEvent(
            QEvent.MouseMove,
            QPointF(200, 10),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.AltModifier,
        )
        self.controller.eventFilter(ruler, move_event)
        self.timeline.jog_engine.play_slice.assert_called()

    def test_mouse_release_calls_jog_stop(self):
        """Nhả chuột trái kích hoạt jog_engine.stop()."""
        self.timeline.jog_engine.stop = MagicMock()
        ruler = self.timeline.container.ruler

        release_event = QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(200, 10),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        self.controller.eventFilter(ruler, release_event)
        self.timeline.jog_engine.stop.assert_called()

    def test_alt_key_release_calls_jog_stop(self):
        """Thả phím Alt kích hoạt jog_engine.stop()."""
        self.timeline.jog_engine.stop = MagicMock()
        ruler = self.timeline.container.ruler

        key_event = QKeyEvent(QEvent.KeyRelease, Qt.Key_Alt, Qt.NoModifier)
        self.controller.eventFilter(ruler, key_event)
        self.timeline.jog_engine.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
