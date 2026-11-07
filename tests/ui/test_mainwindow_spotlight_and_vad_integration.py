# -*- coding: utf-8 -*-
"""
Kiểm thử tích hợp cho DEFECT-FEAT-006 (Global Spotlight Overlay 60 FPS)
và DEFECT-FEAT-003 (Bản đồ nhiệt VAD trên Waveform & Đa hình Wrapper).
"""
import os
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent, QColor
from PySide6.QtWidgets import QApplication, QWidget

from ui.core.liquid_theme_engine import GlobalSpotlightOverlay
from core.waveform.waveform_service import WaveformService
from core.timeline.gaps import find_timeline_gaps


class DummySegmentWrapper:
    """Giả lập đối tượng wrapper không có method .get() như TimelineSegmentWrapper"""
    def __init__(self, start_ms, end_ms, segment_id="seg_1"):
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.segment_id = segment_id


def test_defect_feat_006_global_spotlight_overlay_attributes(qapp):
    """Kiểm tra overlay có đúng các thuộc tính xuyên thấu chuột và cờ nền trong suốt"""
    overlay = GlobalSpotlightOverlay()
    
    assert overlay.testAttribute(Qt.WA_TransparentForMouseEvents) is True
    assert overlay.testAttribute(Qt.WA_NoSystemBackground) is True
    assert overlay.testAttribute(Qt.WA_TranslucentBackground) is True
    assert overlay.focusPolicy() == Qt.NoFocus
    assert overlay.radius == 120
    assert overlay.spotlight_color == QColor(56, 189, 248, 25)
    
    # Kiểm tra cập nhật tọa độ chuột
    overlay.update_cursor_pos(QPoint(150, 200))
    assert overlay.cursor_pos == QPoint(150, 200)
    
    # Kiểm tra xóa tọa độ khi chuột rời
    overlay.clear_cursor_pos()
    assert overlay.cursor_pos is None


def test_defect_feat_006_spotlight_integrated_in_mainwindow(qapp, tmp_path):
    """Kiểm tra MainWindow đã tích hợp GlobalSpotlightOverlay và đồng bộ qua eventFilter"""
    from ui.Gui import MainWindow
    from tests.uat.conftest import MockProjectService

    win = MainWindow(project_service=MockProjectService(str(tmp_path)))
    win.resize(1000, 700)
    win.show()

    assert hasattr(win, "spotlight_overlay")
    assert isinstance(win.spotlight_overlay, GlobalSpotlightOverlay)
    assert win.spotlight_overlay.isVisible()

    # Giả lập sự kiện MouseMove toàn cục qua eventFilter
    mouse_event = QMouseEvent(
        QEvent.MouseMove,
        QPointF(200, 300),
        QPointF(200, 300),
        Qt.NoButton,
        Qt.NoButton,
        Qt.NoModifier
    )
    win.eventFilter(win, mouse_event)
    assert win.spotlight_overlay.cursor_pos is not None

    # Giả lập sự kiện Leave
    leave_event = QEvent(QEvent.Leave)
    win.eventFilter(win, leave_event)
    assert win.spotlight_overlay.cursor_pos is None

    # Đổi tab vẫn giữ overlay trên cùng
    win.switch_page(8)
    assert win.spotlight_overlay.isVisible()

    win.close()


def test_defect_feat_003_waveform_service_polymorphic_input():
    """Kiểm tra WaveformService.build_vad_density_from_intervals hỗ trợ cả dict, wrapper object và string timecodes"""
    duration_ms = 10000

    # 1. Input kiểu dict
    dict_intervals = [
        {"start_ms": 1000, "end_ms": 3000},
        {"start": 5000, "end": 7000}
    ]
    vad_dict = WaveformService.build_vad_density_from_intervals(duration_ms, dict_intervals)
    assert isinstance(vad_dict, np.ndarray)
    assert len(vad_dict) == 1000  # 10s / 10ms
    assert vad_dict[200] >= 0.85  # tại 2000ms là giọng nói chuẩn

    # 2. Input kiểu wrapper object (không có .get)
    obj_intervals = [
        DummySegmentWrapper(1000, 3000),
        DummySegmentWrapper(5000, 7000)
    ]
    vad_obj = WaveformService.build_vad_density_from_intervals(duration_ms, obj_intervals)
    assert isinstance(vad_obj, np.ndarray)
    assert vad_obj[200] >= 0.85
    assert vad_obj[400] <= 0.15  # tại 4000ms là khoảng lặng

    # 3. Input kiểu string timecode
    str_intervals = [
        {"start": "00:00:01,000", "end": "00:00:03,000"}
    ]
    vad_str = WaveformService.build_vad_density_from_intervals(duration_ms, str_intervals)
    assert isinstance(vad_str, np.ndarray)
    assert vad_str[200] >= 0.85

    # 4. Input rỗng
    vad_empty = WaveformService.build_vad_density_from_intervals(duration_ms, [])
    assert isinstance(vad_empty, np.ndarray)
    assert np.all(vad_empty == 0.1)


def test_defect_feat_003_gaps_polymorphic_input():
    """Kiểm tra find_timeline_gaps hỗ trợ cả dict và wrapper object"""
    duration_ms = 5000

    # Dict segments
    dict_segs = [{"start_ms": 1000, "end_ms": 2000, "segment_id": "s1"}]
    gaps_dict = find_timeline_gaps(duration_ms, dict_segs)
    assert len(gaps_dict) == 2
    assert gaps_dict[0].start_ms == 0 and gaps_dict[0].end_ms == 1000
    assert gaps_dict[1].start_ms == 2000 and gaps_dict[1].end_ms == 5000

    # Object wrapper segments
    obj_segs = [DummySegmentWrapper(1000, 2000, "s1")]
    gaps_obj = find_timeline_gaps(duration_ms, obj_segs)
    assert len(gaps_obj) == 2
    assert gaps_obj[0].start_ms == 0 and gaps_obj[0].end_ms == 1000
    assert gaps_obj[1].start_ms == 2000 and gaps_obj[1].end_ms == 5000


def test_defect_feat_003_timeline_widget_auto_derives_vad(qapp):
    """Kiểm tra TimelineWidget.load_project_data tự động suy biến VAD khi caller truyền vad_data=None"""
    from ui.timeline.timeline_widget import TimelineWidget

    widget = TimelineWidget()
    duration_ms = 5000
    segs = [DummySegmentWrapper(1000, 3000)]
    peaks = np.zeros((500, 2), dtype=np.float32)

    # Gọi load_project_data không truyền vad_data
    widget.load_project_data(duration_ms, segs, peaks_normalized=peaks, vad_data=None)

    # Xác minh waveform đã nhận vad_data được tự suy biến
    waveform = widget.container.waveform
    assert waveform.vad_data is not None
    assert len(waveform.vad_data) == 500
    # Tại 2000ms (index 200) là speech (>= 0.65) -> màu Teal #2DD4BF
    color_speech = waveform.get_heatmap_color(0.0, 0.5, speech_prob=waveform.vad_data[200])
    assert color_speech.name().upper() == "#2DD4BF"

    # Tại 500ms (index 50) là silence (< 0.35) -> màu Slate #334155
    color_silence = waveform.get_heatmap_color(0.0, 0.5, speech_prob=waveform.vad_data[50])
    assert color_silence.name().upper() == "#334155"


def test_defect_feat_003_mainwindow_waveform_ready_slot_integration(qapp, tmp_path):
    """Kiểm tra luồng _on_waveform_ready_slot nạp đầy đủ 3 phân tầng VAD cho waveform"""
    from ui.Gui import MainWindow
    from tests.uat.conftest import MockProjectService

    win = MainWindow(project_service=MockProjectService(str(tmp_path)))
    duration_ms = 4000
    peaks = np.zeros((400, 2), dtype=np.float32)

    win.sub_editor.all_segments = [
        {"start_ms": 1000, "end_ms": 2500, "text": "Segment 1"}
    ]
    video_path = str(tmp_path / "test.mp4")
    win.queue_mgr.active_vid = video_path

    # Kích hoạt slot khi waveform hoàn tất
    win._on_waveform_ready_slot(video_path, duration_ms, peaks)

    waveform = win.timeline_widget.container.waveform
    assert waveform.vad_data is not None
    # Đoạn nói từ 1000ms -> 2500ms (index 100..250)
    prob_speech = waveform.vad_data[150]
    assert prob_speech >= 0.65
    assert waveform.get_heatmap_color(0.0, 0.5, speech_prob=prob_speech).name().upper() == "#2DD4BF"
    win.close()
