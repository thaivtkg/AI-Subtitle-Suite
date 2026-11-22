from copy import deepcopy
import json
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from core.services.project_service import ProjectService
from ui.Gui import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch, qtbot):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "profile"))
    video = tmp_path / "source.mp4"
    video.write_bytes(b"test media")
    service = ProjectService()
    project = service.create_project(str(tmp_path / "project.ai-subtitle"), "Agent project", str(video))
    win = MainWindow(project_service=service, media_import_service=MagicMock())
    win.video_player.load_video = MagicMock()
    win.generation_panel.check_resumable_state = MagicMock()
    item = win.queue_mgr.ensure_project_binding(str(video), project_id=project.project_id,
                                                project_root=service.project_dir)
    with patch("ui.Gui.threading.Thread"):
        win.on_queue_item_clicked(item)
    win.canonical_save_coordinator.set_enabled(False)
    yield win
    # Let workspace playback restoration finish before destroying its widgets.
    qtbot.wait(550)
    win.autosave_coordinator.dispose()
    win.canonical_save_coordinator.dispose()
    win._canonical_status_timer.stop()
    service.close_project()
    win.undo_manager.clear()
    win.revision_tracker.reset_for_new_document()
    win.tm_manager.close()
    win.close()
    win.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()


def append_agent_timing(window):
    original = [
        {"id": str(i), "stt": str(i), "start": f"00:00:0{i},000", "end": f"00:00:0{i},800",
         "text": f"Original {i}", "original_text": f"Original {i}", "translation": ""}
        for i in range(1, 4)
    ]
    original[0]["metadata"] = {"source": "import", "extra": [1, 2]}
    window.sub_editor.all_segments = deepcopy(original)
    window.sub_editor.render_page()
    window.page_translation.load_subtitles_from_studio(deepcopy(original))
    window.page_translation.subtitle_model.update_translation(0, "Unsaved CAT draft", "EDITED")
    window.switch_page(9)
    controller = window.page_ai_agent.controller
    controller.context_ledger.video_path = None
    controller.submit_prompt("tạo timing 3 câu tiếp theo")
    controller.approve_plan()
    assert len(window.sub_editor.all_segments) == 6
    return deepcopy(window.sub_editor.all_segments)


@pytest.mark.parametrize("nav_index", [1, 9])
def test_agent_append_save_reopen_preserves_six_segments_and_cat_draft(window, nav_index):
    from pathlib import Path

    expected = append_agent_timing(window)
    window.switch_page(nav_index)
    assert window.action_save_project()
    project_dir = window.project_service.project_dir
    assert not window.revision_tracker.is_dirty, "save itself left the revision dirty"
    window._sync_from_ai_agent_page()
    assert not window.revision_tracker.is_dirty
    manifest = json.loads((Path(project_dir) / "artifacts/manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]
    # Simulate reopening with no rows left in memory; the real load path must restore all six.
    window.sub_editor.all_segments = []
    with patch("ui.Gui.threading.Thread"):
        assert window._open_project_by_path(project_dir)
    actual = window.sub_editor.all_segments
    assert len(actual) == 6
    assert [(s["start"], s["end"], s["text"]) for s in actual] == [
        (s["start"], s["end"], s["text"]) for s in expected
    ]
    assert actual[0]["translation"] == "Unsaved CAT draft"
    assert actual[0]["metadata"] == expected[0]["metadata"]


def test_agent_mutation_marks_dirty_and_revert_is_persisted(window):
    append_agent_timing(window)
    assert window.revision_tracker.is_dirty
    assert window.action_save_project()
    window.page_ai_agent._on_redo_clicked()
    assert len(window.sub_editor.all_segments) == 3
    assert window.revision_tracker.is_dirty
    assert window.action_save_project()
    project_dir = window.project_service.project_dir
    window.sub_editor.all_segments = []
    with patch("ui.Gui.threading.Thread"):
        assert window._open_project_by_path(project_dir)
    assert len(window.sub_editor.all_segments) == 3


def test_failed_artifact_write_does_not_report_save_success(window):
    append_agent_timing(window)
    with patch.object(window.subtitle_generation_service.artifact_service, "_save_atomic",
                      side_effect=OSError("disk full")), patch("ui.Gui.Toast.show_success") as success:
        assert window.action_save_project() is False
    success.assert_not_called()
    assert window.revision_tracker.is_dirty
    assert window.project_service.current_project.state.subtitle_artifact_id is None


def test_agent_revert_to_empty_is_saved(window):
    window.switch_page(9)
    controller = window.page_ai_agent.controller
    controller.context_ledger.video_path = None
    controller.submit_prompt("tạo timing 3 câu tiếp theo")
    controller.approve_plan()
    assert len(window.sub_editor.all_segments) == 3
    assert window.action_save_project()
    window.page_ai_agent._on_redo_clicked()
    assert window.sub_editor.all_segments == []
    assert window.revision_tracker.is_dirty
    assert window.action_save_project()
    project_dir = window.project_service.project_dir
    with patch("ui.Gui.threading.Thread"):
        assert window._open_project_by_path(project_dir)
    assert window.sub_editor.all_segments == []


def test_batch_scan_empty_result_preserves_rows_and_reports_failure(window):
    from core.subtitle_generation.subtitle_generation_result import SubtitleGenerationResult
    from workers.SegmentScanWorker import BatchSegmentScanWorker

    append_agent_timing(window)
    window.switch_page(1)
    before = deepcopy(window.sub_editor.all_segments)
    window.subtitle_whisper_service = MagicMock()
    window.subtitle_whisper_service.transcribe_batch.return_value = SubtitleGenerationResult("empty", [])
    progress = MagicMock()
    progress.wasCanceled.return_value = False
    with patch.object(window, "_resolve_rescan_model_and_compute", return_value=("tiny", "int8")), \
         patch.object(window.generation_panel, "_timing_settings", return_value={"language": "en"}), \
         patch.object(window, "_create_batch_scan_progress_dialog", return_value=progress), \
         patch.object(BatchSegmentScanWorker, "start", BatchSegmentScanWorker.run), \
         patch("ui.Gui.Toast.show_success") as success, patch("ui.Gui.Toast.show_error") as error:
        window._on_batch_segment_scan_requested([0, 1])
    assert window.sub_editor.all_segments == before
    success.assert_not_called()
    assert "0/2" in error.call_args.args[1]
