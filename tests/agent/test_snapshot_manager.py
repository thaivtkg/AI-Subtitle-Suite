import pytest
from core.agent.snapshot_manager import SnapshotManager
from core.project.project_state import ProjectState

def test_snapshot_manager_clean_rollback():
    state = ProjectState()
    state.subtitle_source_segments = [{"id": 1, "text": "Before ASR"}]
    state.subtitle_style = {"font_name": "Arial", "font_size": 24}
    
    sm = SnapshotManager(state)
    snap_id = sm.take_snapshot("pre_task_1")
    assert snap_id.startswith("pre_task_1_")
    assert sm.has_snapshot(snap_id)
    
    # Mutate state
    state.subtitle_source_segments = [{"id": 1, "text": "Mutated Text"}]
    state.subtitle_style = {"font_name": "Roboto", "font_size": 32}
    assert state.subtitle_source_segments[0]["text"] == "Mutated Text"
    assert state.subtitle_style["font_name"] == "Roboto"
    
    # Rollback
    restored = sm.restore_snapshot(snap_id)
    assert restored is True
    assert state.subtitle_source_segments[0]["text"] == "Before ASR"
    assert state.subtitle_style["font_name"] == "Arial"
    assert state.subtitle_style["font_size"] == 24

def test_snapshot_manager_restore_nonexistent():
    state = ProjectState()
    sm = SnapshotManager(state)
    assert sm.restore_snapshot("invalid_id") is False
