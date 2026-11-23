from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

from core.artifacts.artifact_store import ArtifactStore
from core.services.project_service import ProjectService
from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_generation.generation_service import SubtitleGenerationService
from core.timing.timing_batch_service import TimingBatchService
from ui.SubEditor import SubtitleEditorWidget
from ui.subtitle_generation_panel import SubtitleGenerationPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def project(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    service = ProjectService(ArtifactStore())
    service.create_project(str(tmp_path / "project.ai-subtitle"), "QA", str(video))
    return service


def panel_for(history, parent=None):
    with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
        return SubtitleGenerationPanel(history, parent)


def test_timing_commit_publishes_history_and_reopens(app, project):
    history = SubtitleGenerationService(None, project)
    timing = TimingBatchService(project)
    timing.history_service = history
    panel = panel_for(history)
    timing._on_worker_finished([{"start_ms": 1000, "end_ms": 2000}], False)
    assert history.initial_state is not None
    assert history.initial_state.generated_count == 0
    assert [cp.generated_count for cp in history.checkpoint_history] == [1]
    assert panel.history_list.count() == 2
    timing._execute_run = lambda **kwargs: None
    timing.continue_timing(1, {}, existing_segments=[
        {"start": 1200, "end": 2200, "text": "edited"}
    ])
    timing._on_worker_finished([{"start_ms": 3000, "end_ms": 4000}], False)
    assert [cp.generated_count for cp in history.checkpoint_history] == [1, 2]
    assert panel.history_list.count() == 3
    assert history.checkpoint_history[-1].segments_snapshot[0]["text"] == "edited"
    reopened = ProjectService(ArtifactStore())
    reopened.open_project(project.project_dir)
    restored = panel_for(SubtitleGenerationService(None, reopened))
    assert restored.history_list.count() == 3


def test_refresh_history_ui_populates_selectable_list(app, project):
    history = SubtitleGenerationService(None, project)
    history.create_history_checkpoint([], is_initial=True)
    history.create_history_checkpoint([{"start_ms": 1000, "end_ms": 2000, "text": "A"}])
    panel = panel_for(history)
    panel.refresh_history_ui()
    assert panel.history_list.count() == 2
    panel.history_list.setCurrentRow(0)
    assert panel.btn_rollback.isEnabled()
    assert panel.history_list.item(0).data(Qt.UserRole) == history.checkpoint_history[0].checkpoint_id


def test_project_switch_does_not_reuse_other_project_history(app, project, tmp_path):
    history = SubtitleGenerationService(None, project)
    history.create_history_checkpoint([], is_initial=True)
    history.create_history_checkpoint([{"start": 1000, "end": 2000, "text": "A"}])
    other_dir = tmp_path / "other.ai-subtitle"
    project.create_project(str(other_dir), "Other", str(tmp_path / "video.mp4"))
    history._ensure_history_loaded()
    assert history.initial_state is None
    assert history.checkpoint_history == []


def test_quick_and_selected_rollback_use_parent_window(app, project):
    history = SubtitleGenerationService(None, project)
    history.create_history_checkpoint([], is_initial=True)
    window = QMainWindow()
    editor = SubtitleEditorWidget()
    editor.all_segments = [{"id": "old", "stt": "1", "start": 1000, "end": 2000, "text": "A"}]
    window.sub_editor = editor
    window.undo_manager = GlobalUndoManager(window)
    panel = panel_for(history, window)
    window.setCentralWidget(panel)
    with patch("ui.dialogs.restore_preview_dialog.RestorePreviewDialog.exec", return_value=1), \
            patch.object(QApplication, "activeWindow", return_value=None), \
            patch.object(panel, "_on_error") as error:
        panel._on_quick_rollback_clicked("Initial")
    error.assert_not_called()
    assert editor.all_segments == []
    assert window.undo_manager.undo()
    assert len(editor.all_segments) == 1
    assert window.undo_manager.redo()
    assert editor.all_segments == []


def test_asr_checkpoint_rollback_has_editor_times_and_preserves_metadata(app, project):
    history = SubtitleGenerationService(None, project)
    snapshot = [{"id": "stable", "start_ms": 1500, "end_ms": 2500,
                 "text": "A", "translation": "B", "metadata": {"approved": True}}]
    history.create_history_checkpoint(snapshot)
    rows = []
    manager = GlobalUndoManager()
    history.execute_rollback(1, rows, manager)
    assert rows[0]["start"] == 1500
    assert rows[0]["end"] == 2500
    assert rows[0]["stt"] == "1"
    assert rows[0]["metadata"] == {"approved": True}
    assert rows[0]["translation"] == "B"
    rows[0]["metadata"]["approved"] = False
    assert history.checkpoint_history[0].segments_snapshot == snapshot
    assert manager.undo()
    assert rows == []
    assert manager.redo()
    assert rows[0]["metadata"]["approved"] is True


def test_rollback_rebuilds_timeline_even_when_editor_becomes_empty(app):
    from ui.Gui import MainWindow
    from unittest.mock import MagicMock
    window = MainWindow.__new__(MainWindow)
    window.sub_editor = SimpleNamespace(all_segments=[])
    window.timeline_controller = MagicMock()
    window.video_player = MagicMock()
    MainWindow._sync_live_subtitle_on_undo_redo(window)
    window.timeline_controller.sync_from_editor_segments.assert_called_once_with([])


@pytest.fixture
def window(app, project):
    from ui.Gui import MainWindow
    from unittest.mock import MagicMock
    from PySide6.QtCore import QEvent
    from PySide6.QtTest import QTest

    with patch("core.services.model_manager.ModelManager.is_installed", return_value=False):
        win = MainWindow(project_service=project, media_import_service=MagicMock())
    video_path = project.current_project.source.path
    item = win.queue_mgr.ensure_project_binding(
        video_path, project_id=project.current_project.project_id,
        project_root=project.project_dir,
    )
    win.queue_mgr.active_vid = video_path
    win.queue_mgr.active_item_key = item
    win.generation_panel.video_duration_ms = 60000
    win.timeline_data_provider.load_runtime_data([], 60000)
    win.timeline_widget.load_project_data(60000, [])
    win.timing_service._execute_run = MagicMock()
    win.autosave_coordinator.dispose()
    win.canonical_save_coordinator.dispose()
    yield win
    QTest.qWait(850)
    win._canonical_status_timer.stop()
    project.close_project()
    win.undo_manager.clear()
    win.revision_tracker.reset_for_new_document()
    if hasattr(win, "tm_manager") and win.tm_manager is not None:
        win.tm_manager.close()
    win.close()
    win.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()


@pytest.mark.parametrize("target_count", [0, 2])
def test_window_rollback_undo_redo_continue_and_save(window, project, target_count):
    win = window
    win._start_timing_draft(2, {})
    win.timing_service._on_worker_finished([
        {"start_ms": 1000, "end_ms": 2000},
        {"start_ms": 3000, "end_ms": 4000},
    ], False)
    win._resume_timing_draft(1, {})
    win.timing_service._on_worker_finished([{"start_ms": 5000, "end_ms": 6000}], False)
    panel = win.generation_panel
    assert len(win.sub_editor.all_segments) == 3
    assert panel.history_list.count() == 3
    cp = win.subtitle_generation_service.get_rollback_checkpoint(target_count=target_count)
    for index in range(panel.history_list.count()):
        if panel.history_list.item(index).data(Qt.UserRole) == cp.checkpoint_id:
            panel.history_list.setCurrentRow(index)
            break
    with patch("ui.dialogs.restore_preview_dialog.RestorePreviewDialog.exec", return_value=1):
        panel.btn_rollback.click()
    assert len(win.sub_editor.all_segments) == target_count
    assert len(win.timeline_data_provider.get_all_segments()) == target_count
    assert len(win.timeline_widget.container.track.segments) == target_count
    assert win.undo_manager.undo()
    assert len(win.sub_editor.all_segments) == 3
    assert len(win.timeline_widget.container.track.segments) == 3
    assert win.undo_manager.redo()
    assert len(win.sub_editor.all_segments) == target_count
    assert len(win.timeline_widget.container.track.segments) == target_count
    assert project.current_project.state.dirty
    assert win._save_current_project()
    reopened = ProjectService(ArtifactStore())
    reopened.open_project(project.project_dir)
    from core.timing.timing_batch_service import TimingBatchService
    timing_id = reopened.current_project.state.timing.timing_artifact_id
    path = reopened.artifact_store.get(timing_id).path
    assert len(TimingBatchService(reopened)._parse_draft_segments(path)) == target_count
    win._resume_timing_draft(1, {})
    run = win.timing_service._execute_run.call_args.kwargs
    assert run["start_ms"] == (4000 if target_count else 0)
    assert project.load_timing_checkpoint().next_segment_index == target_count + 1


def test_failed_timing_write_does_not_add_history(app, project):
    history = SubtitleGenerationService(None, project)
    timing = TimingBatchService(project)
    timing.history_service = history
    with patch.object(timing, "_commit_transaction", side_effect=OSError("disk full")):
        timing._on_worker_finished([{"start_ms": 1000, "end_ms": 2000}], False)
    assert history.checkpoint_history == []
    assert history.initial_state is None
