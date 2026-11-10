# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent
from tests.gui.conftest import timeline_driver

VIDEO_FILE = os.path.abspath("sample_test_data/sample_video_25s.mp4")

def test_mainwindow_seek_and_play(timeline_driver, qtbot):
    win, driver, timeline_page, sub_page = timeline_driver
    
    # Load video
    win.video_player.load_video(VIDEO_FILE)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=5000)
    player = win.video_player.player
    
    # Load subtitles
    seg1 = {
        "id": "seg1",
        "stt": "1",
        "start": "00:00:01,000",
        "end": "00:00:05,000",
        "start_ms": 1000,
        "end_ms": 5000,
        "text": "Sub 1",
        "style_preset": "normal",
    }
    seg2 = {
        "id": "seg2",
        "stt": "2",
        "start": "00:00:08,000",
        "end": "00:00:15,000",
        "start_ms": 8000,
        "end_ms": 15000,
        "text": "Sub 2",
        "style_preset": "normal",
    }
    win.sub_editor.all_segments = [seg1, seg2]
    win.sub_editor.render_page()
    win.timeline_widget.duration_ms = win.video_player.player.duration()
    
    # 1. Test clicking timeline at 3000ms
    print("\n--- Test 1: Seek on timeline to 3000ms ---")
    win.timeline_widget.seek_requested.emit(3000)
    qtbot.wait(100)
    print(f"After seek_requested(3000): pos={player.position()}, isPlaying={player.isPlaying()}")
    
    # Now click play button or press space
    print("Clicking play button...")
    win.video_player.btn_play.click()
    qtbot.wait(300)
    print(f"After btn_play.click(): pos={player.position()}, isPlaying={player.isPlaying()}")
    
    # Let's see if pos advances
    pos_1 = player.position()
    qtbot.wait(500)
    pos_2 = player.position()
    print(f"Pos after 500ms: pos_1={pos_1}, pos_2={pos_2}, diff={pos_2 - pos_1}")
    
    # Pause
    win.video_player.btn_play.click()
    qtbot.wait(100)
    
    # 2. Test selecting row in table (SubEditor)
    print("\n--- Test 2: Select row 1 in SubEditor ---")
    win.sub_editor.select_segment(0)
    qtbot.wait(100)
    print(f"After select_segment(0): pos={player.position()}, bounds={getattr(win.video_player, '_segment_bounds', None)}, active={getattr(win.video_player, '_segment_playback_active', False)}")
    
    # Now click timeline at 10000ms (seek to 10000ms)
    print("\n--- Test 3: Seek to 10000ms after segment focused ---")
    win.timeline_widget.seek_requested.emit(10000)
    qtbot.wait(100)
    print(f"After seek to 10000: pos={player.position()}, bounds={getattr(win.video_player, '_segment_bounds', None)}, active={getattr(win.video_player, '_segment_playback_active', False)}")
    
    # Try to play with space or btn_play
    win.video_player.btn_play.click()
    qtbot.wait(300)
    print(f"After btn_play.click(): pos={player.position()}, isPlaying={player.isPlaying()}")
    pos_3 = player.position()
    qtbot.wait(500)
    pos_4 = player.position()
    print(f"Pos after 500ms: pos_3={pos_3}, pos_4={pos_4}, diff={pos_4 - pos_3}")
