# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication
from tests.gui.conftest import timeline_driver

VIDEO_FILE = os.path.abspath("sample_test_data/sample_video_25s.mp4")

def test_slider_seek_in_mainwindow(timeline_driver, qtbot):
    win, driver, timeline_page, sub_page = timeline_driver
    win.video_player.load_video(VIDEO_FILE)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=5000)
    player = win.video_player.player
    slider = win.video_player.slider_seek

    # 1. Video is PAUSED at 0.
    # User clicks on slider at 50% (12500ms)
    print("\n[STEP 1] Video paused. Click slider at 50%...")
    click_x = slider.width() * 0.5
    ev_press = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(click_x, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    slider.mousePressEvent(ev_press)
    ev_rel = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(click_x, 5), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    slider.mouseReleaseEvent(ev_rel)
    qtbot.wait(200)

    print(f"After slider click: pos={player.position()}ms, isPlaying={player.isPlaying()}, focusWidget={QApplication.focusWidget()}")

    # 2. User presses Space to play!
    print("\n[STEP 2] User presses Space key to play...")
    space_ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    res = win.eventFilter(QApplication.focusWidget() or win, space_ev)
    print(f"Space key eventFilter handled={res}")
    qtbot.wait(300)
    print(f"After Space: pos={player.position()}ms, isPlaying={player.isPlaying()}, state={player.playbackState()}")

    # 2b. Start playing with btn_play explicitly
    win.video_player.btn_play.click()
    qtbot.waitUntil(lambda: player.isPlaying() is True, timeout=2000)
    print(f"Now playing: isPlaying={player.isPlaying()}, pos={player.position()}ms")

    # 3. User drags slider while PLAYING
    print("\n[STEP 3] User drags slider while PLAYING...")
    ev_press = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(slider.width() * 0.5, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    slider.mousePressEvent(ev_press)
    for frac in [0.55, 0.6, 0.65, 0.7]:
        ev_move = QMouseEvent(QMouseEvent.MouseMove, QPointF(slider.width() * frac, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        slider.mouseMoveEvent(ev_move)
        qtbot.wait(50)
    ev_rel = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(slider.width() * 0.7, 5), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    slider.mouseReleaseEvent(ev_rel)
    qtbot.wait(200)

    print(f"After dragging slider while playing: pos={player.position()}ms, isPlaying={player.isPlaying()}, state={player.playbackState()}")
    
    # 4. Wait to see if playback advances
    pos_before = player.position()
    qtbot.wait(500)
    print(f"500ms after dragging: pos={player.position()}ms, advanced={player.position() - pos_before}ms, isPlaying={player.isPlaying()}")

    # 5. User clicks Play button (btn_play)
    print("\n[STEP 4] User clicks btn_play...")
    win.video_player.btn_play.click()
    qtbot.wait(300)
    print(f"After btn_play: isPlaying={player.isPlaying()}, state={player.playbackState()}")
