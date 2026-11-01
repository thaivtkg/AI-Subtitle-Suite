import json

import pytest
from PySide6.QtCore import QUrl

from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.checkpoint import CheckpointStore
from core.translation.batch.fingerprint import compute_source_hash
from core.translation.controllers.project_controller import ProjectController
from core.translation.models.subtitle import SubtitleModel


def file_url(path):
    return QUrl.fromLocalFile(str(path)).toString()


def make_controller():
    model = SubtitleModel()
    controller = ProjectController(model)
    controller._set_project_state(True, True)
    return controller, model


def save(controller, path):
    controller.saveProject(file_url(path), "story", "English", "Vietnamese")


# ---------------------------------------------------------------------------
# TC-P3B2-18  .aisrt round-trip
# ---------------------------------------------------------------------------
def test_tc_p3b2_18_aisrt_roundtrip_preserves_entities(tmp_path):
    path = tmp_path / "project.aisrt"
    controller, model = make_controller()
    model.load_data([
        {"index": 1, "original": "Tony", "translation": "Tony", "status": "ACCEPTED"}
    ])
    controller.entity_dictionary.add(
        "  Tony Stark  ", "CHARACTER", "  Tony Stark  ", ["  Iron Man  ", "Stark"]
    )
    save(controller, path)

    loaded, loaded_model = make_controller()
    loaded.loadProject(file_url(path))
    assert loaded.entity_dictionary.to_payload() == {
        "  Tony Stark  ": {
            "entity_type": "CHARACTER",
            "canonical_translation": "  Tony Stark  ",
            "aliases": ["  Iron Man  ", "Stark"],
        }
    }
    assert loaded_model.get_all_data() == model.get_all_data()


# ---------------------------------------------------------------------------
# TC-P3B2-19  Canonical empty save
# ---------------------------------------------------------------------------
def test_tc_p3b2_19_empty_save_writes_canonical_namespace(tmp_path):
    path = tmp_path / "empty.aisrt"
    controller, _ = make_controller()
    save(controller, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["intelligence"]["entities"] == {}


# ---------------------------------------------------------------------------
# TC-P3B2-20  Legacy load
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("intelligence", [None, {}, {"glossary": {}}])
def test_tc_p3b2_20_legacy_missing_entities_loads_empty_without_rewrite(
    tmp_path, intelligence
):
    path = tmp_path / "legacy.aisrt"
    payload = {
        "metadata": {"source_file": "source.srt"},
        "story_summary": "legacy",
        "subtitles": [
            {"index": 1, "original": "old", "translation": "", "status": "PENDING"}
        ],
    }
    if intelligence is not None:
        payload["intelligence"] = intelligence
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    before = path.read_bytes()

    controller, _ = make_controller()
    controller.entity_dictionary.add("Old", "OTHER", "Cũ", [])

    controller.loadProject(file_url(path))
    assert controller.entity_dictionary.to_payload() == {}
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# TC-P3B2-21  Atomic invalid load
# ---------------------------------------------------------------------------
def test_tc_p3b2_21_invalid_entity_load_is_atomic(tmp_path):
    path = tmp_path / "invalid.aisrt"
    payload = {
        "metadata": {"source_file": "new.srt"},
        "story_summary": "new",
        "subtitles": [
            {"index": 2, "original": "new", "translation": "", "status": "PENDING"}
        ],
        "intelligence": {
            "glossary": {
                "Good": {"preferred_translation": "Tốt", "forbidden_alternatives": []},
            },
            "entities": {
                "ValidEntity": {
                    "entity_type": "CHARACTER",
                    "canonical_translation": "OK",
                    "aliases": [],
                },
                "BadEntity": {
                    "entity_type": "INVALID_TYPE",
                    "canonical_translation": "Bad",
                    "aliases": [],
                },
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    controller, model = make_controller()
    model.load_data([
        {"index": 1, "original": "old", "translation": "Cũ", "status": "ACCEPTED"}
    ])
    controller.glossary.add("Old", "Cũ", [])
    controller.entity_dictionary.add("Prior", "LOCATION", "Trước", [])

    before_model = model.get_all_data().copy()
    before_glossary = controller.glossary.to_payload()
    before_entities = controller.entity_dictionary.to_payload()

    controller.loadProject(file_url(path))

    # All prior state preserved — no partial commit
    assert model.get_all_data() == before_model
    assert controller.glossary.to_payload() == before_glossary
    assert controller.entity_dictionary.to_payload() == before_entities


# ---------------------------------------------------------------------------
# TC-P3B2-22  Checkpoint isolation
# ---------------------------------------------------------------------------
def test_tc_p3b2_22_checkpoint_has_no_entity_data(tmp_path):
    job = BatchJob(
        job_id="job",
        project_id="project",
        state=BatchJobState.RUNNING,
        items={
            0: BatchItem(
                target_index=0,
                source_hash=compute_source_hash("Tony"),
                state=BatchItemState.PENDING,
            )
        },
    )
    path = tmp_path / "checkpoint.json"
    CheckpointStore.save(path, job)
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = json.dumps(payload, ensure_ascii=False)
    assert "intelligence" not in payload
    assert "entities" not in raw
    assert "entity" not in raw


# ---------------------------------------------------------------------------
# TC-P3B2-23  Glossary coexistence
# ---------------------------------------------------------------------------
def test_tc_p3b2_23_glossary_and_entities_coexist_independently(tmp_path):
    path = tmp_path / "coexist.aisrt"
    controller, model = make_controller()
    model.load_data([
        {"index": 1, "original": "King Tony", "translation": "", "status": "PENDING"}
    ])
    controller.glossary.add("King", "Vua", ["Monarch"])
    controller.entity_dictionary.add("Tony Stark", "CHARACTER", "Tony Stark", ["Iron Man"])
    save(controller, path)

    # Verify both namespaces in saved file
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "glossary" in raw["intelligence"]
    assert "entities" in raw["intelligence"]
    assert "King" in raw["intelligence"]["glossary"]
    assert "Tony Stark" in raw["intelligence"]["entities"]

    # Load and verify independence
    loaded, _ = make_controller()
    loaded.loadProject(file_url(path))
    assert loaded.glossary.to_payload() == {
        "King": {
            "preferred_translation": "Vua",
            "forbidden_alternatives": ["Monarch"],
        }
    }
    assert loaded.entity_dictionary.to_payload() == {
        "Tony Stark": {
            "entity_type": "CHARACTER",
            "canonical_translation": "Tony Stark",
            "aliases": ["Iron Man"],
        }
    }

