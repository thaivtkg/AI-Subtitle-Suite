# -*- coding: utf-8 -*-
"""
Chụp ảnh minh chứng giao diện thực tế 100% của Phase 2: Audio-Visual Engineering (FR-04, FR-05, AC-06).
Lưu vào thư mục Artifact để phục vụ nghiệm thu theo quy chuẩn Mandatory Deep QA Review.
"""
import os
import sys
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QFrame
from PySide6.QtGui import QPainter, QColor, QFont, QPixmap

from ui.theme import Theme
from ui.timeline.waveform_view import WaveformView
from ui.timeline.timeline_widget import TimelineWidget
from core.waveform.waveform_service import WaveformService
from core.audio.jog_audio_engine import JogAudioEngine

ARTIFACT_DIR = r"C:\Users\Kuroberus\.gemini\antigravity\brain\d7d2d74d-59ec-4d54-8751-7d91438bdf1d"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)
app.setStyleSheet(Theme.get_global_stylesheet())

# =========================================================================
# 1. Chụp ảnh FR-04: VAD Speech Density Heatmap Waveform (3 dải màu)
# =========================================================================
duration_ms = 10000
num_chunks = duration_ms // 10  # 1000 chunks

# Sinh mảng sóng âm giả lập
np.random.seed(42)
peaks = np.zeros((num_chunks, 2), dtype=np.float32)
# Tạo nhịp biên độ
t = np.linspace(0, 50 * np.pi, num_chunks)
envelope = np.abs(np.sin(t * 0.1)) * 0.7 + 0.1
peaks[:, 0] = -envelope * (0.5 + np.random.rand(num_chunks) * 0.4)
peaks[:, 1] = envelope * (0.5 + np.random.rand(num_chunks) * 0.4)

# Sinh mảng VAD mật độ giọng nói
speech_intervals = [
    {"start_ms": 1000, "end_ms": 3500},
    {"start_ms": 5000, "end_ms": 8500},
]
vad_array = WaveformService.build_vad_density_from_intervals(duration_ms, speech_intervals)

waveform_view = WaveformView()
waveform_view.resize(1100, 75)
waveform_view.set_data(peaks, duration_ms, vad_data=vad_array)
waveform_view.show()
app.processEvents()

pixmap_vad = QPixmap(waveform_view.size())
waveform_view.render(pixmap_vad)
pixmap_vad.save(os.path.join(ARTIFACT_DIR, "phase2_01_vad_speech_density_waveform.png"))
print("Saved phase2_01_vad_speech_density_waveform.png")

# =========================================================================
# 2. Chụp ảnh FR-05: Jog-Audio Micro-Scrubbing Active & Timeline Context
# =========================================================================
timeline_widget = TimelineWidget()
timeline_widget.resize(1100, 220)
dummy_segments = [
    type("Seg", (), {"segment_id": "seg_1", "start_ms": 1000, "end_ms": 3500, "text": "Phân đoạn lời thoại 1"})(),
    type("Seg", (), {"segment_id": "seg_2", "start_ms": 5000, "end_ms": 8500, "text": "Phân đoạn lời thoại 2"})(),
]
timeline_widget.load_project_data(duration_ms, dummy_segments, peaks_normalized=peaks, vad_data=vad_array)
# Nạp 5 giây audio PCM giả lập
raw_pcm = (np.sin(np.linspace(0, 100 * np.pi, 80000)) * 10000).astype(np.int16)
timeline_widget.set_audio_pcm(raw_pcm, sample_rate=8000)

# Kích hoạt jog engine tại mốc 2500ms
timeline_widget.jog_engine.play_slice(2500, 40)
timeline_widget.container.playhead.set_position(int((2500 / 1000.0) * timeline_widget.pixels_per_second))
timeline_widget.show()
app.processEvents()

pixmap_timeline = QPixmap(timeline_widget.size())
timeline_widget.render(pixmap_timeline)
pixmap_timeline.save(os.path.join(ARTIFACT_DIR, "phase2_02_jog_audio_scrubbing_timeline.png"))
print("Saved phase2_02_jog_audio_scrubbing_timeline.png")

# Ngắt an toàn
timeline_widget.jog_engine.stop()
app.processEvents()

pixmap_cutoff = QPixmap(timeline_widget.size())
timeline_widget.render(pixmap_cutoff)
pixmap_cutoff.save(os.path.join(ARTIFACT_DIR, "phase2_03_jog_cutoff_idle.png"))
print("Saved phase2_03_jog_cutoff_idle.png")
