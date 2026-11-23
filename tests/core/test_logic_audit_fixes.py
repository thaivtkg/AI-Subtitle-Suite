import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.Backend import _build_multistyle_ass
from core.project.source_fingerprint import SourceInfo
from core.recovery.recovery_models import RecoveryManifest, RecoveryWorkingState
from core.recovery.recovery_validator import RecoveryValidator
from core.runtime.runtime_paths import RuntimePaths
from core.services.model_manager import ModelManager
from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_editing.selection_controller import SubtitleSelectionController
from core.subtitle_generation.generation_range import validate_generation_range, GenerationRangeStatus
from core.subtitle_generation.generation_service import SubtitleGenerationService
from core.subtitle_generation.range_validation import ConflictStrategy
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_placement import SubtitlePlacementState
from core.timeline.timeline_controller import TimelineController
from core.timeline.timeline_data_provider import TimelineDataProvider


def test_recovery_validator_accepts_srt_timestamps():
    manifest = RecoveryManifest(
        schema_version=1,
        session_id="s1",
        app_version="test",
        project_id="p1",
        project_file_path="C:/p",
        video_path="C:/v.mp4",
        source_fingerprint="fp",
        source_modified_at=1.0,
        created_at="2026-01-01T00:00:00",
        last_snapshot_at="2026-01-01T00:00:01",
        edit_revision=1,
        snapshot_revision=1,
        last_saved_revision=0,
        last_clean_revision=0,
    )
    snap = RecoveryWorkingState(
        schema_version=2.0,
        session_id="s1",
        project_id="p1",
        project_file_path="C:/p",
        video_path="C:/v.mp4",
        source_fingerprint="fp",
        edit_revision=1,
        segments=[{"id": "1", "stt": "1", "start": "00:00:01,000", "end": "00:00:03,500", "text": "hi"}],
        workspace_state={"active_page": "editor"},
    )
    assert RecoveryValidator().validate_data(manifest, snap).is_valid is True

    bad = RecoveryWorkingState(**{**snap.__dict__, "segments": [{"id": "1", "stt": "1", "start": "bad", "end": "00:00:03,000"}]})
    assert RecoveryValidator().validate_data(manifest, bad).is_valid is False


def test_model_manager_exact_match_does_not_delete_large_v3_turbo(tmp_path, monkeypatch):
    turbo_dir = tmp_path / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
    snap = turbo_dir / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(RuntimePaths, "get_models_dir", staticmethod(lambda: tmp_path))
    assert ModelManager.is_installed("large-v3-turbo") is True
    assert ModelManager.is_installed("large-v3") is False
    assert ModelManager.delete_model("large-v3") is False
    assert turbo_dir.exists()


def test_selection_controller_clear_after_multi_select():
    sc = SubtitleSelectionController()
    changed = []
    multi = []
    sc.selection_changed.connect(lambda idx, sid, src: changed.append((idx, sid)))
    sc.multi_selection_changed.connect(lambda idxs, ids, src: multi.append(list(idxs)))
    sc.select_multiple([0, 1], {"s1", "s2"})
    changed.clear()
    multi.clear()
    sc.clear_selection()
    assert changed == [(-1, None)]
    assert multi == [[]]


def test_backend_multistyle_ass_coordinates_and_mode():
    segs = [{"start_ms": 0, "end_ms": 1000, "text": "Hello"}]
    ass_default = _build_multistyle_ass(segs, 1920, 1080, None, {"font_size": 24})
    assert r"\pos(960,918)" in ass_default

    ass_top = _build_multistyle_ass(segs, 1920, 1080, SubtitlePlacementState(mode="top", x=0.2, y=0.8), {"font_size": 24})
    assert r"\pos(960,130)" in ass_top


def test_range_generation_preserves_history_and_conflict_strategies(tmp_path):
    res = validate_generation_range(500, 1500, 10000, [{"start": "00:00:00,000", "end": "00:00:02,000", "id": "1"}])
    assert res.status == GenerationRangeStatus.OVERLAPS_SUBTITLE

    proj_dir = tmp_path / "proj"
    art_dir = proj_dir / "artifacts" / "subtitles"
    art_dir.mkdir(parents=True)
    art_path = art_dir / "sub.json"
    art_path.write_text(json.dumps({
        "version": 1,
        "segments": [{"id": "old-1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Old"}],
    }), encoding="utf-8")

    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"v")
    artifact = SimpleNamespace(artifact_id="art-1", path=str(art_path), revision=1, updated_at=0.0)
    project = SimpleNamespace(
        project_id="p1",
        project_dir=str(proj_dir),
        source=SimpleNamespace(path=str(vid), fingerprint="fp"),
        state=SimpleNamespace(subtitle_artifact_id="art-1", active_artifact_id="art-1"),
    )
    proj_svc = SimpleNamespace(
        current_project=project,
        project_dir=str(proj_dir),
        artifact_store=SimpleNamespace(get=lambda _id: artifact),
        mark_dirty=lambda: None,
    )
    whisper = MagicMock()
    svc = SubtitleGenerationService(whisper, proj_svc)
    svc._range_conflict_strategy = ConflictStrategy.REPLACE_OVERLAP
    req = SubtitleGenerationRequest(
        request_id="req-1",
        project_id="p1",
        source_fingerprint="fp",
        video_path=str(vid),
        model_size="tiny",
        compute_type="int8",
        language=None,
        use_vad=True,
        min_silence_ms=500,
        word_timestamps=False,
        range_start_ms=1500,
        range_end_ms=4000,
    )

    with patch("core.subtitle_generation.generation_service.SubtitleGenerationWorker") as mock_w:
        mock_w.return_value = MagicMock()
        svc.start_generation(
            req,
            10000,
            existing_segments=[{"id": "old-1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Old"}],
            conflict_strategy=ConflictStrategy.REPLACE_OVERLAP,
        )
        assert any(getattr(cp, "checkpoint_type", "") == "INITIAL" for cp in svc.all_checkpoints)

        batch = svc.current_batches[0]
        svc._commit_range_batch(batch, SimpleNamespace(segments=[SimpleNamespace(start_ms=1600, end_ms=3500, text="New", words=[])]))
        assert svc._range_committed is True
        saved_segs = json.loads(art_path.read_text(encoding="utf-8"))["segments"]
        assert [s["text"] for s in saved_segs] == ["New"]


def test_timeline_delete_syncs_before_undo_state_changed(qapp):
    sub_editor_segments = [
        {"id": "s1", "stt": "1", "start": "00:00:00,000", "end": "00:00:02,000", "text": "A"},
        {"id": "s2", "stt": "2", "start": "00:00:03,000", "end": "00:00:05,000", "text": "B"},
    ]
    provider = TimelineDataProvider()
    provider.load_runtime_data(sub_editor_segments, 10000)
    undo_mgr = GlobalUndoManager()
    ui_mock = MagicMock()
    ui_mock.container.track = MagicMock()
    ui_mock.container.waveform.waveform_data = None
    ui_mock.duration_ms = 10000
    ui_mock.window.return_value = SimpleNamespace()
    proj_svc = SimpleNamespace(
        current_project=SimpleNamespace(
            state=SimpleNamespace(
                active_artifact_id="a1",
                timing=SimpleNamespace(timing_artifact_id="a1"),
                edit_revision=0,
            )
        ),
        artifact_store=SimpleNamespace(get=lambda _id: SimpleNamespace(revision=1)),
        mark_dirty=lambda: None,
    )
    ctrl = TimelineController(proj_svc, ui_mock, provider, undo_manager=undo_mgr)

    # Simulate Gui.py ordering where editor sync runs BEFORE timeline_controller._refresh_ui
    from core.timeline.timeline_commands import DeleteSegmentCommand
    undo_mgr.state_changed.connect(lambda: ctrl.sync_from_editor_segments(sub_editor_segments))
    undo_mgr.state_changed.connect(ctrl._refresh_ui)

    ctrl._push_command(DeleteSegmentCommand(ctrl.project, provider, {"s1"}))
    assert [s["id"] for s in sub_editor_segments] == ["s2"]
    undo_mgr.undo()
    assert [s["id"] for s in sub_editor_segments] == ["s1", "s2"]


def test_mock_project_dir_does_not_create_magicmock_folder(tmp_path, monkeypatch):
    from pathlib import Path
    from core.subtitle_generation.generation_checkpoint_manager import SubtitleGenerationCheckpointManager
    from core.subtitle_generation.subtitle_artifact_service import SubtitleArtifactService

    monkeypatch.chdir(tmp_path)
    mock_svc = MagicMock()
    assert SubtitleGenerationCheckpointManager(mock_svc)._get_checkpoint_path() is None
    assert SubtitleArtifactService(mock_svc).get_or_create_artifact() is None
    assert SubtitleGenerationService(MagicMock(), mock_svc)._get_history_path() is None
    assert not (Path(tmp_path) / "MagicMock").exists()
