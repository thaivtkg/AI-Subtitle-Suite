# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication
from tests.gui.conftest import timeline_driver

VIDEO_FILE = os.path.abspath("sample_test_data/sample_video_25s.mp4")

def test_seek_while_playing_in_mainwindow(timeline_driver, qtbot):
    win, driver, timeline_page, sub_page = timeline_driver
    win.video_player.load_video(VIDEO_FILE)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=5000)
    player = win.video_player.player

    # 1. Start playback
    print("\n[STEP 1] Starting playback...")
    win.video_player.btn_play.click()
    qtbot.waitUntil(lambda: player.isPlaying() is True, timeout=2000)
    qtbot.wait(500)
    print(f"Playing at pos={player.position()}ms, isPlaying={player.isPlaying()}")

    # 2. Seek via timeline while playing!
    print("\n[STEP 2] Seeking to 15000ms via timeline while playing...")
    win.timeline_widget.seek_requested.emit(15000)
    qtbot.wait(200)
    print(f"After seek_requested: pos={player.position()}ms, isPlaying={player.isPlaying()}, state={player.playbackState()}, mediaStatus={player.mediaStatus()}")

    # 3. Does it continue playing?
    qtbot.wait(600)
    print(f"After 600ms: pos={player.position()}ms, isPlaying={player.isPlaying()}, state={player.playbackState()}, mediaStatus={player.mediaStatus()}")
    
    # 4. Now what if user presses Space or clicks Play button?
    print("\n[STEP 3] User clicks Play button (btn_play)...")
    win.video_player.btn_play.click()
    qtbot.wait(300)
    print(f"After btn_play.click(): pos={player.position()}ms, isPlaying={player.isPlaying()}, state={player.playbackState()}")

    # 5. User clicks Play button AGAIN to play...
    print("\n[STEP 4] User clicks Play button AGAIN to play...")
    win.video_player.btn_play.click()
    qtbot.wait(300)
    print(f"After second btn_play.click(): pos={player.position()}ms, isPlaying={player.isPlaying()}, state={player.playbackState()}")
    
    qtbot.wait(600)
    print(f"After 600ms: pos={player.position()}ms, isPlaying={player.isPlaying()}, state={player.playbackState()}")
