# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtCore import Qt
from player.video_player import VideoPlayerWidget

VIDEO_FILE = os.path.abspath("sample_test_data/sample_video_25s.mp4")

def test_investigate_seek_freeze(qtbot):
    widget = VideoPlayerWidget()
    widget.resize(800, 600)
    qtbot.addWidget(widget)
    widget.show()
    widget.load_video(VIDEO_FILE)
    
    qtbot.waitUntil(lambda: widget.player.duration() > 0, timeout=5000)
    player = widget.player
    
    print("\n--- Initial State ---")
    print(f"duration={player.duration()}, pos={player.position()}, isPlaying={player.isPlaying()}, playbackState={player.playbackState()}, mediaStatus={player.mediaStatus()}, error={player.error()}, errorString={player.errorString()}")
    
    # Listen to all signals
    signals_log = []
    player.positionChanged.connect(lambda p: signals_log.append(f"positionChanged({p})"))
    player.playbackStateChanged.connect(lambda s: signals_log.append(f"playbackStateChanged({s})"))
    player.mediaStatusChanged.connect(lambda s: signals_log.append(f"mediaStatusChanged({s})"))
    player.errorOccurred.connect(lambda err, err_str: signals_log.append(f"errorOccurred({err}, {err_str})"))
    
    middle_val = player.duration() // 2 # 12500
    print(f"\n--- Calling set_position({middle_val}) ---")
    widget.set_position(middle_val)
    print(f"After set_position: pos={player.position()}, isPlaying={player.isPlaying()}, playbackState={player.playbackState()}, mediaStatus={player.mediaStatus()}")
    
    print(f"Signals so far:\n" + "\n".join(signals_log))
    signals_log.clear()
    
    print("\n--- Calling toggle_playback() ---")
    widget.toggle_playback()
    print(f"After toggle_playback: pos={player.position()}, isPlaying={player.isPlaying()}, playbackState={player.playbackState()}, mediaStatus={player.mediaStatus()}")
    
    for i in range(10):
        qtbot.wait(200)
        print(f"Tick {i+1} ({(i+1)*200}ms): pos={player.position()}, isPlaying={player.isPlaying()}, playbackState={player.playbackState()}, mediaStatus={player.mediaStatus()}")
        if signals_log:
            print(f"  Signals in tick: {signals_log}")
            signals_log.clear()
            
    widget.cleanup()
    widget.close()
