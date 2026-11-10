# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication
from tests.gui.conftest import timeline_driver

VIDEO_FILE = os.path.abspath("sample_test_data/sample_video_25s.mp4")

def test_space_key_after_slider_seek(timeline_driver, qtbot):
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1) # Go to Workspace (page 1)
    win.activateWindow()
    qtbot.wait(100)

    win.video_player.load_video(VIDEO_FILE)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=5000)
    player = win.video_player.player
    slider = win.video_player.slider_seek

    print(f"Current stack index: {win.stack.currentIndex()}")
    print(f"Window isActive: {win.isActiveWindow()}")

    # Click slider at 50%
    click_x = slider.width() * 0.5
    ev_press = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(click_x, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    slider.mousePressEvent(ev_press)
    ev_rel = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(click_x, 5), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    slider.mouseReleaseEvent(ev_rel)
    qtbot.wait(200)

    print(f"After seek: pos={player.position()}ms, focusWidget={QApplication.focusWidget()}")

    # Now simulate pressing Space on the focused widget
    focused = QApplication.focusWidget() or win
    space_ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    
    # Send through eventFilter as Qt would
    res = win.eventFilter(focused, space_ev)
    print(f"eventFilter handled Space? {res}")
    qtbot.wait(300)
    print(f"Player isPlaying={player.isPlaying()}, state={player.playbackState()}")

    # Now what if user presses Space AGAIN to pause?
    res2 = win.eventFilter(focused, space_ev)
    print(f"Second Space handled? {res2}")
    qtbot.wait(300)
    print(f"Player isPlaying={player.isPlaying()}, state={player.playbackState()}")


def test_space_key_with_subtitle_segments(timeline_driver, qtbot):
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    win.activateWindow()
    qtbot.wait(100)

    win.video_player.load_video(VIDEO_FILE)
    qtbot.waitUntil(lambda: win.video_player.player.duration() > 0, timeout=5000)
    player = win.video_player.player
    sub_editor = win.sub_editor

    # Load subtitle segments
    seg1 = {
        "id": "seg_001",
        "start": "00:00:10,000",
        "end": "00:00:15,000",
        "start_ms": 10000,
        "end_ms": 15000,
        "text": "Subtitle 1",
    }
    win.sub_editor.all_segments = [seg1]
    win.timeline_controller.sync_from_editor_segments(win.sub_editor.all_segments)
    win.sub_editor.render_page()
    qtbot.wait(100)

    # Seek into Subtitle 1 at 12000ms via timeline controller
    win.timeline_controller._do_seek(win.timeline_widget.container.track.pixels_per_second * 12.0)
    qtbot.wait(200)

    focused = QApplication.focusWidget() or win
    # Check if Space toggles playback
    space_ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
    handled = win.eventFilter(focused, space_ev)
    with open("diagnostic_output.txt", "w", encoding="utf-8") as f:
        f.write(f"[DIAGNOSTIC] Focused widget after seek: {focused}\n")
        f.write(f"[DIAGNOSTIC] SubEditor current_editor text_edit: {getattr(sub_editor.current_editor, 'text_edit', None)}\n")
        f.write(f"[DIAGNOSTIC] Did text_edit steal focus? {focused is getattr(sub_editor.current_editor, 'text_edit', None)}\n")
        f.write(f"[DIAGNOSTIC] Was Space handled by eventFilter? {handled}\n")
        f.write(f"[DIAGNOSTIC] Is player playing? {player.isPlaying()}\n")

    # Strict Assertions
    assert focused is not getattr(sub_editor.current_editor, "text_edit", None), "SubEditor text_edit stole focus during timeline seek!"
    assert handled is True, "Space key event was blocked or not handled by eventFilter!"
    assert player.isPlaying() is True, "Video player did not start playing after pressing Space!"


def test_timeline_duration_sync_before_waveform(timeline_driver, qtbot):
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    win.timeline_widget.duration_ms = 0
    # Simulate duration change from player before waveform loads
    win._on_player_duration_changed(25000)
    assert win.timeline_widget.duration_ms == 25000


def test_slider_seek_lifecycle_and_throttle(timeline_driver, qtbot):
    win, driver, timeline_page, sub_page = timeline_driver
    win.switch_page(1)
    vp = win.video_player
    vp.load_video(VIDEO_FILE)
    qtbot.waitUntil(lambda: vp.player.duration() > 0, timeout=5000)

    # 1. Start playback
    vp.player.play()
    qtbot.waitUntil(lambda: vp.player.isPlaying(), timeout=3000)

    # 2. Press seek slider (should pause and record _was_playing_before_scrub)
    vp.slider_seek.setSliderDown(True)
    assert vp._was_playing_before_scrub is True
    qtbot.waitUntil(lambda: not vp.player.isPlaying(), timeout=3000)

    # 3. Simulate position_changed while slider is down (isSliderDown() True)
    vp.slider_seek.setValue(12000)
    vp.position_changed(5000)
    # The slider value must NOT be overwritten by playback position
    assert vp.slider_seek.value() == 12000

    # 4. Release seek slider (should commit position and resume playing)
    vp.slider_seek.setSliderDown(False)
    assert vp._current_pos_ms == 12000
    qtbot.waitUntil(lambda: vp.player.isPlaying(), timeout=5000)
    assert vp.player.isPlaying() is True

