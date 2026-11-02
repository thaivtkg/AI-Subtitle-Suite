import pytest
from core.subtitle_controller import SubtitleController

def test_time_str_to_ms_supports_comma_and_dot():
    ctrl = SubtitleController()
    
    # SRT standard (comma)
    assert ctrl.time_str_to_ms("00:01:23,456") == 83456
    assert ctrl.time_str_to_ms("01:00:00,000") == 3600000
    
    # WebVTT standard (dot)
    assert ctrl.time_str_to_ms("00:01:23.456") == 83456
    assert ctrl.time_str_to_ms("01:00:00.000") == 3600000
    
    # Whitespace and short hours
    assert ctrl.time_str_to_ms("  0:01:23.456  ") == 83456
    
    # Invalid strings fallback to 0 safely without crashing
    assert ctrl.time_str_to_ms("") == 0
    assert ctrl.time_str_to_ms("invalid") == 0
    assert ctrl.time_str_to_ms(None) == 0
