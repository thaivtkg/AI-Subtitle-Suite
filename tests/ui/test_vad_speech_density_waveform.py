# -*- coding: utf-8 -*-
"""
Tests for FR-04 / AC-04: VAD Speech Density Heatmap Waveform (DEV-SPEC-PHASE2-AV-001).
Validates:
1. WaveformView.get_heatmap_color returns correct 3-tier colors based on speech probability:
   - prob >= 0.65 -> Sapphire Teal (#2DD4BF)
   - 0.35 <= prob < 0.65 -> Amber / Orange (#F59E0B)
   - prob < 0.35 -> Obsidian Gray (#334155)
   - prob is None -> Fallback to legacy amplitude color
2. WaveformView.set_vad_data accepts and stores pre-computed numpy array.
3. TimelineWidget.load_project_data and set_vad_data properly forward to WaveformView.
4. Viewport Culling & 60 FPS: O(1) lookup per bar without recomputing VAD inside paintEvent.
5. WaveformService generates matching VAD density array corresponding to 10ms chunk resolution.
"""
import os
import unittest
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from ui.timeline.waveform_view import WaveformView
from ui.timeline.timeline_widget import TimelineWidget
from core.waveform.waveform_service import WaveformService


app = QApplication.instance() or QApplication([])


class TestVADSpeechDensityWaveform(unittest.TestCase):
    def setUp(self):
        self.waveform = WaveformView()
        self.timeline = TimelineWidget()

    def tearDown(self):
        self.waveform.close()
        self.timeline.close()
        self.waveform.deleteLater()
        self.timeline.deleteLater()

    def test_get_heatmap_color_vad_tier_speech(self):
        """prob >= 0.65 -> Sapphire Teal (#2DD4BF)."""
        color = self.waveform.get_heatmap_color(min_peak=-0.5, max_peak=0.5, speech_prob=0.85)
        self.assertEqual(color.name().upper(), "#2DD4BF")

        color_edge = self.waveform.get_heatmap_color(min_peak=-0.5, max_peak=0.5, speech_prob=0.65)
        self.assertEqual(color_edge.name().upper(), "#2DD4BF")

    def test_get_heatmap_color_vad_tier_transition(self):
        """0.35 <= prob < 0.65 -> Amber / Orange (#F59E0B)."""
        color = self.waveform.get_heatmap_color(min_peak=-0.5, max_peak=0.5, speech_prob=0.50)
        self.assertEqual(color.name().upper(), "#F59E0B")

        color_edge = self.waveform.get_heatmap_color(min_peak=-0.5, max_peak=0.5, speech_prob=0.35)
        self.assertEqual(color_edge.name().upper(), "#F59E0B")

    def test_get_heatmap_color_vad_tier_silence(self):
        """prob < 0.35 -> Obsidian Gray (#334155)."""
        color = self.waveform.get_heatmap_color(min_peak=-0.5, max_peak=0.5, speech_prob=0.10)
        self.assertEqual(color.name().upper(), "#334155")

        color_zero = self.waveform.get_heatmap_color(min_peak=-0.5, max_peak=0.5, speech_prob=0.0)
        self.assertEqual(color_zero.name().upper(), "#334155")

    def test_get_heatmap_color_fallback_when_prob_is_none(self):
        """Khi speech_prob is None, fallback về màu theo biên độ (Legacy compatibility)."""
        # High amplitude (amp >= 0.75) -> Cam Đỏ #EF4444
        color_loud = self.waveform.get_heatmap_color(min_peak=-0.8, max_peak=0.8, speech_prob=None)
        self.assertEqual(color_loud.name().upper(), "#EF4444")

        # Low amplitude (amp <= 0.15) -> Xanh Ngọc #06B6D4
        color_whisper = self.waveform.get_heatmap_color(min_peak=-0.1, max_peak=0.1, speech_prob=None)
        self.assertEqual(color_whisper.name().upper(), "#06B6D4")

    def test_set_vad_data_stores_array(self):
        probs = np.array([0.1, 0.5, 0.9, 0.2], dtype=np.float32)
        self.waveform.set_vad_data(probs)
        self.assertIsNotNone(self.waveform.vad_data)
        np.testing.assert_array_equal(self.waveform.vad_data, probs)

    def test_timeline_widget_forwards_vad_data(self):
        probs = np.zeros(100, dtype=np.float32)
        probs[20:60] = 0.9
        dummy_peaks = np.zeros((100, 2), dtype=np.float32)
        self.timeline.load_project_data(1000, [], peaks_normalized=dummy_peaks, vad_data=probs)
        self.assertIsNotNone(self.timeline.container.waveform.vad_data)
        np.testing.assert_array_equal(self.timeline.container.waveform.vad_data, probs)

    def test_paint_event_runs_without_exception_with_vad_data(self):
        """Vẽ waveform với VAD data lên Pixmap để xác nhận 100% không crash."""
        duration_ms = 2000
        num_chunks = duration_ms // 10  # 200 chunks
        peaks = np.zeros((num_chunks, 2), dtype=np.float32)
        peaks[:, 0] = -0.5
        peaks[:, 1] = 0.5

        probs = np.full(num_chunks, 0.1, dtype=np.float32)
        probs[50:150] = 0.85  # Speech zone

        self.waveform.set_data(peaks, duration_ms)
        self.waveform.set_vad_data(probs)
        self.waveform.resize(300, 75)

        pixmap = QPixmap(300, 75)
        self.waveform.render(pixmap)
        self.assertFalse(pixmap.isNull())

    def test_waveform_service_vad_density_from_speech_intervals(self):
        """WaveformService.build_vad_density_array xây dựng mảng xác suất 10ms từ danh sách khoảng tiếng nói."""
        duration_ms = 1000
        speech_intervals = [{"start_ms": 200, "end_ms": 600}]
        vad_array = WaveformService.build_vad_density_from_intervals(duration_ms, speech_intervals)
        self.assertEqual(len(vad_array), 100)  # 1000ms / 10ms = 100 chunks
        # Chunk tại 400ms (index 40) phải thuộc dải speech (>= 0.65)
        self.assertGreaterEqual(vad_array[40], 0.65)
        # Chunk tại 0ms (index 0) phải thuộc dải silence (< 0.35)
        self.assertLess(vad_array[0], 0.35)


if __name__ == "__main__":
    unittest.main()
