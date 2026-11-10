# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication
from player.video_player import VideoPlayerWidget

VIDEO_FILE = os.path.abspath("sample_test_data/sample_video_25s.mp4")

@pytest.fixture
def video_widget(qtbot):
    widget = VideoPlayerWidget()
    widget.resize(800, 600)
    qtbot.addWidget(widget)
    widget.show()
    widget.load_video(VIDEO_FILE)
    
    # Wait until loaded
    qtbot.waitUntil(lambda: widget.player.duration() > 0, timeout=5000)
    yield widget
    widget.cleanup()
    widget.close()


def test_seek_and_play_from_slider_click(video_widget, qtbot):
    player = video_widget.player
    slider = video_widget.slider_seek
    
    # Seek to middle
    middle_val = player.duration() // 2
    slider.setValue(middle_val)
    slider.sliderMoved.emit(middle_val)
    
    qtbot.waitUntil(lambda: abs(player.position() - middle_val) < 200, timeout=3000)
    
    # Try to play
    video_widget.toggle_playback()
    assert player.isPlaying() is True
    
    # Wait for position to advance
    pos_before = player.position()
    qtbot.waitUntil(lambda: player.position() > pos_before, timeout=3000)
    assert player.position() > pos_before


def test_seek_while_playing(video_widget, qtbot):
    player = video_widget.player
    
    # Start playback
    video_widget.toggle_playback()
    assert player.isPlaying() is True
    
    # Seek while playing
    target_pos = 10000
    video_widget.set_position(target_pos)
    
    # Should still be playing
    assert player.isPlaying() is True
    
    # Position should advance beyond target_pos
    qtbot.waitUntil(lambda: player.position() > target_pos, timeout=3000)
    assert player.isPlaying() is True
