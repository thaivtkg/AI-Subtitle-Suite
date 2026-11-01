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
# TC-P3B3-11  .aisrt round-trip
# ---------------------------------------------------------------------------
def test_tc_p3b3_11_aisrt_roundtrip_preserves_translation_memory(tmp_path):
    path = tmp_path / "project.aisrt"
    controller, model = make_controller()
    model.load_data([
        {"index": 1, "original": "Good morning.", "translation": "Chào buổi sáng.", "status": "ACCEPTED"}
    ])
    controller.translation_memory.add("  Good morning.  ", "  Chào buổi sáng.  ")
    save(controller, path)

    loaded, loaded_model = make_controller()
    loaded.loadProject(file_url(path))
    assert loaded.translation_memory.to_payload() == {
        "  Good morning.  ": {
            "target_text": "  Chào buổi sáng.  ",
        }
    }
    assert loaded_model.get_all_data() == model.get_all_data()


# ---------------------------------------------------------------------------
# TC-P3B3-12  Canonical empty save
# ---------------------------------------------------------------------------
def test_tc_p3b3_12_empty_save_writes_canonical_namespace(tmp_path):
    path = tmp_path / "empty.aisrt"
    controller, _ = make_controller()
    save(controller, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["intelligence"] == {
        "glossary": {},
        "entities": {},
        "translation_memory": {},
    }


# ---------------------------------------------------------------------------
# TC-P3B3-13  Legacy load
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "intelligence",
    [
        None,
        {},
        {"glossary": {}},
        {"glossary": {}, "entities": {}},
    ],
)
def test_tc_p3b3_13_legacy_missing_tm_loads_empty_without_rewrite(tmp_path, intelligence):
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
    controller.translation_memory.add("Old", "Cũ")

    controller.loadProject(file_url(path))
    assert controller.translation_memory.to_payload() == {}
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# TC-P3B3-14  Atomic invalid load
# ---------------------------------------------------------------------------
def test_tc_p3b3_14_invalid_tm_load_is_atomic(tmp_path):
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
            },
            "translation_memory": {
                "ValidSource": {"target_text": "Hợp lệ"},
                "InvalidSource": {"invalid_key": "Không có target_text"},
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
    controller.translation_memory.add("PriorSource", "Bản dịch cũ")

    before_model = model.get_all_data().copy()
    before_glossary = controller.glossary.to_payload()
    before_entities = controller.entity_dictionary.to_payload()
    before_tm = controller.translation_memory.to_payload()

    controller.loadProject(file_url(path))

    # All prior state preserved — no partial commit
    assert model.get_all_data() == before_model
    assert controller.glossary.to_payload() == before_glossary
    assert controller.entity_dictionary.to_payload() == before_entities
    assert controller.translation_memory.to_payload() == before_tm


# ---------------------------------------------------------------------------
# TC-P3B3-15  Checkpoint isolation
# ---------------------------------------------------------------------------
def test_tc_p3b3_15_checkpoint_has_no_translation_memory_data(tmp_path):
    job = BatchJob(
        job_id="job",
        project_id="project",
        state=BatchJobState.RUNNING,
        items={
            0: BatchItem(
                target_index=0,
                source_hash=compute_source_hash("Hello"),
                state=BatchItemState.PENDING,
            )
        },
    )
    path = tmp_path / "checkpoint.json"
    CheckpointStore.save(path, job)
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = json.dumps(payload, ensure_ascii=False)
    assert "intelligence" not in payload
    assert "translation_memory" not in raw


# ---------------------------------------------------------------------------
# TC-P3B3-16  Three-way intelligence coexistence
# ---------------------------------------------------------------------------
def test_tc_p3b3_16_glossary_entities_tm_coexist_independently(tmp_path):
    path = tmp_path / "coexist_all.aisrt"
    controller, model = make_controller()
    model.load_data([
        {"index": 1, "original": "Captain Stark is here.", "translation": "", "status": "PENDING"}
    ])
    controller.glossary.add("Captain", "Đại úy", ["Thuyền trưởng"])
    controller.entity_dictionary.add("Stark", "CHARACTER", "Stark", ["Tony"])
    controller.translation_memory.add("Captain Stark is here.", "Đại úy Stark đang ở đây.")
    save(controller, path)

    # Verify all three namespaces in saved file
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "glossary" in raw["intelligence"]
    assert "entities" in raw["intelligence"]
    assert "translation_memory" in raw["intelligence"]
    assert "Captain" in raw["intelligence"]["glossary"]
    assert "Stark" in raw["intelligence"]["entities"]
    assert "Captain Stark is here." in raw["intelligence"]["translation_memory"]

    # Load and verify independence
    loaded, _ = make_controller()
    loaded.loadProject(file_url(path))
    assert loaded.glossary.to_payload() == {
        "Captain": {
            "preferred_translation": "Đại úy",
            "forbidden_alternatives": ["Thuyền trưởng"],
        }
    }
    assert loaded.entity_dictionary.to_payload() == {
        "Stark": {
            "entity_type": "CHARACTER",
            "canonical_translation": "Stark",
            "aliases": ["Tony"],
        }
    }
    assert loaded.translation_memory.to_payload() == {
        "Captain Stark is here.": {
            "target_text": "Đại úy Stark đang ở đây.",
        }
    }

