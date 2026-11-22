import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.Backend import _build_multistyle_ass
from core.database.glossary_manager import GlossaryManager
from core.database.tm_manager import TranslationMemoryManager
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
from core.translation.batch_translator import TranslationBatchWorker
from core.translation.controllers.project_controller import ProjectController
from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel
from ui.pages.translation_studio_page import TranslationStudioPage


def test_cat_update_current_translation_and_tm_hit_reset(qapp):
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "original": "Hello", "translation": "", "status": "PENDING", "studio_index": 0},
        {"index": 2, "original": "World", "translation": "", "status": "PENDING", "studio_index": 1},
    ])
    tc = TranslationController(subtitle_model=model)
    tc.loadSubtitle(0)

    # Idle manual edit must persist into current row (0)
    tc.updateCurrentTranslation("Xin chao")
    assert model.get_item(0)["translation"] == "Xin chao"
    assert model.get_item(0)["status"] == "EDITED"

    # Simulate row 1 translating while user edits row 0: must not clobber row 1
    tc._active_translation_index = 1
    tc.updateCurrentTranslation("Chao ban")
    assert model.get_item(1)["translation"] == ""

    # TM exact match must clear _active_translation_index so revisiting row 0 does not lock as TRANSLATING
    tc._active_translation_index = -1
    tc.bind_intelligence(translation_memory=SimpleNamespace(lookup=lambda text: SimpleNamespace(target_text="The gioi")))
    tc.loadSubtitle(1)
    tc.requestTranslation(1, "English", "Vietnamese", "")
    assert tc._active_translation_index == -1
    tc.loadSubtitle(0)
    tc.loadSubtitle(1)
    assert tc.status == "TRANSLATED"


def test_request_translation_gate_emits_failed_and_preserves_explicit_source_lang(qapp):
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "original": "", "translation": "", "status": "PENDING"},
        {"index": 2, "original": "Go to the café", "translation": "", "status": "PENDING"},
    ])
    tc = TranslationController(subtitle_model=model)
    failed = []
    tc.translationFailed.connect(lambda idx, msg: failed.append((idx, msg)))

    # Gate 1 empty segment must emit translationFailed
    tc.requestTranslation(0, "English", "Vietnamese", "")
    assert failed and failed[-1][0] == 0

    # Gate 2 explicit source_lang="English" must not be overwritten by Vietnamese diacritic detection on "café"
    tc.loadSubtitle(1)
    assert tc._current_source_language == "Vietnamese"
    tc._model_controller = SimpleNamespace(hasValidModel=False)
    tc.requestTranslation(1, "English", "Vietnamese", "")
    assert failed[-1][0] == 1
    assert "Ngôn ngữ nguồn" not in failed[-1][1]


def test_translation_studio_sync_no_tier4_collision_and_preserves_studio_index(qapp, tmp_path):
    page = TranslationStudioPage()
    studio = [
        {"id": "1", "stt": 1, "start": 0, "end": 1000, "text": "Done", "original_text": "Done", "translation": "Xong", "translation_status": "ACCEPTED"},
        {"id": "2", "stt": 2, "start": 1000, "end": 2000, "text": "Second", "original_text": "Second", "translation": "Hai", "translation_status": "TRANSLATED"},
    ]
    page.load_subtitles_from_studio(studio)
    # Segment #1 was skipped (ACCEPTED), so CAT row 0 is segment #2 with studio_index=1
    assert page._find_cat_index("1") == -1

    # Splitting segment #2 keeps base studio_index=1 (and second child gets 2)
    page.handle_segment_split(
        "2",
        {"id": "2a", "stt": 2, "start": 1000, "end": 1500, "text": "Sec"},
        {"id": "2b", "stt": 3, "start": 1500, "end": 2000, "text": "ond"},
    )
    assert page.subtitle_model.get_item(0)["studio_index"] == 1
    assert page.subtitle_model.get_item(1)["studio_index"] == 2

    # Deleting segment 2a in Studio -> export must NOT re-append stale CAT items
    small_studio = [studio[0]]
    page.export_subtitles_to_studio(small_studio)
    assert len(small_studio) == 1

    # Guard 2 protects rescanned Studio segment whose original_text changed
    page2 = TranslationStudioPage()
    s2 = [{"id": "s1", "stt": 1, "start": 0, "end": 1000, "text": "Old speech", "original_text": "Old speech"}]
    page2.load_subtitles_from_studio(s2)
    page2.subtitle_model.update_translation(0, "Ban dich cu", "TRANSLATED")
    live_studio = [{"id": "s1", "stt": 1, "start": 0, "end": 1000, "text": "Rescanned speech", "original_text": "Rescanned speech"}]
    page2.export_subtitles_to_studio(live_studio)
    assert live_studio[0].get("translation", "") == ""

    # save_translation_project uses detected source_language instead of hardcoded English
    page2.project_controller._source_language = "Japanese"
    aisrt = tmp_path / "proj.aisrt"
    page2.save_translation_project(str(aisrt))
    saved = json.loads(aisrt.read_text(encoding="utf-8"))
    assert saved["metadata"]["source_language"] == "Japanese"


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


def test_tm_fts5_boolean_keywords_and_glossary_upsert_id(tmp_path):
    tm = TranslationMemoryManager(":memory:")
    try:
        tm.add_segment("NOW OR NEVER", "Ngay bây giờ hoặc không bao giờ", lang_pair="en-vi", domain="general")
        tm.add_segment("A AND B NOT C", "A và B", lang_pair="fr-vi", domain="other")
        matches = tm.find_matches("NOW OR NEVER!", lang_pair="en-vi", domain="general", threshold=0.5)
        assert len(matches) == 1
        assert matches[0].lang_pair == "en-vi"
        assert tm.find_matches("A AND B NOT C!", lang_pair="en-vi", domain="general", threshold=0.5) == []
    finally:
        tm.close()

    gm = GlossaryManager(str(tmp_path / "glossary.db"))
    id1 = gm.add_entry("Hero", "Anh hung")
    gm.add_entry("Villain", "Phan dien")
    id_upsert = gm.add_entry("Hero", "Nguoi hung")
    assert id1 > 0
    assert id_upsert == id1


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


def test_batch_translator_contract_and_project_controller_fixes(qapp, tmp_path):
    worker = TranslationBatchWorker(
        service=MagicMock(),
        tm_manager=MagicMock(),
        glossary_manager=MagicMock(),
        segments=[{"stt": "1", "start": 1000, "end": 2500, "text": "Hello"}],
        source_lang="English",
        target_lang="Vietnamese",
    )
    formatted = worker._format_srt_chunk(worker.segments)
    assert "00:00:01,000 --> 00:00:02,500" in formatted
    parsed = worker._parse_and_validate("1\n00:00:01,000 --> 00:00:02,500\nXin chao\n", worker.segments)
    assert parsed[0]["original_text"] == "Hello"
    assert parsed[0]["text"] == "Xin chao"

    sub_model = SubtitleModel()
    pc = ProjectController(sub_model)
    sub_model.load_data([{"index": 1, "original": "Foo bar", "translation": "", "status": "PENDING"}])
    pc.executeFindReplace("Foo", "Baz", scope="ORIGINAL")
    assert sub_model.get_item(0)["status"] == "PENDING"
    pc.entity_dictionary._entries["Hero"] = SimpleNamespace(canonical_translation="Anh hung")
    pc.closeProject()
    assert pc.entity_dictionary._entries == {}

    aisrt = tmp_path / "p.aisrt"
    aisrt.write_text(json.dumps({
        "metadata": {"source_language": "Japanese", "target_language": "Vietnamese"},
        "intelligence": {"archetype": "Pure", "pronoun_pair": "Em - Tiền bối"},
        "subtitles": [{"index": 1, "original": "こんにちは", "translation": "", "status": "PENDING"}],
    }), encoding="utf-8")
    pc.loadProject(str(aisrt))
    assert pc._active_pronoun_pair == "Em - Tiền bối"


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
