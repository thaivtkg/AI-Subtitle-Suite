import json

import pytest

from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.checkpoint import CheckpointStore
from core.translation.batch.errors import (
    CheckpointError,
    CheckpointFormatError,
    CheckpointIdentityError,
)
from core.translation.batch.fingerprint import compute_job_fingerprint, compute_source_hash


def make_job():
    return BatchJob(
        job_id="checkpoint-job",
        project_id="project-1",
        state=BatchJobState.RUNNING,
        items={
            0: BatchItem(
                target_index=0,
                source_hash=compute_source_hash("Original 0"),
                state=BatchItemState.COMPLETED,
            ),
            1: BatchItem(
                target_index=1,
                source_hash=compute_source_hash("Original 1"),
                state=BatchItemState.RUNNING,
            ),
            2: BatchItem(
                target_index=2,
                source_hash=compute_source_hash("Original 2"),
                state=BatchItemState.PENDING,
            ),
            3: BatchItem(
                target_index=3,
                source_hash=compute_source_hash("Original 3"),
                state=BatchItemState.FAILED,
                error_msg="model failure",
            ),
        },
    )


def load_for(job, path):
    return CheckpointStore.load(
        path,
        expected_project_id=job.project_id,
        expected_fingerprint=compute_job_fingerprint(job),
    )


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_tc_p3a5_03_checkpoint_roundtrip_preserves_execution_snapshot(tmp_path):
    job = make_job()
    path = tmp_path / "checkpoint.json"

    CheckpointStore.save(path, job)
    loaded = load_for(job, path)

    assert loaded.job_id == job.job_id
    assert loaded.project_id == job.project_id
    assert loaded.state is BatchJobState.RUNNING
    assert [(index, item.state, item.error_msg) for index, item in loaded.items.items()] == [
        (0, BatchItemState.COMPLETED, None),
        (1, BatchItemState.RUNNING, None),
        (2, BatchItemState.PENDING, None),
        (3, BatchItemState.FAILED, "model failure"),
    ]
    assert not any("translation" in item for item in json.loads(path.read_text(encoding="utf-8"))["job"]["items"])


def test_tc_p3a5_04_failed_atomic_replacement_keeps_previous_checkpoint(tmp_path, monkeypatch):
    import core.translation.batch.checkpoint as checkpoint_module

    path = tmp_path / "checkpoint.json"
    original = make_job()
    replacement = make_job()
    replacement.items[0].error_msg = "replacement"
    CheckpointStore.save(path, original)

    def fail_replace(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(checkpoint_module.os, "replace", fail_replace)

    with pytest.raises(CheckpointError):
        CheckpointStore.save(path, replacement)

    assert load_for(original, path).items[0].error_msg is None


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 999},
        {"schema_version": 1, "fingerprint": "sha256:" + "0" * 64, "job": {}},
        {
            "schema_version": 1,
            "fingerprint": "sha256:" + "0" * 64,
            "job": {
                "job_id": "job",
                "project_id": "project-1",
                "state": "UNKNOWN",
                "items": [],
            },
        },
        {
            "schema_version": 1,
            "fingerprint": "sha256:" + "0" * 64,
            "job": {
                "job_id": "job",
                "project_id": "project-1",
                "state": "RUNNING",
                "items": [
                    {"target_index": 0, "source_hash": "sha256:" + "0" * 64, "state": "PENDING"},
                    {"target_index": 0, "source_hash": "sha256:" + "1" * 64, "state": "PENDING"},
                ],
            },
        },
    ],
)
def test_tc_p3a5_05_rejects_invalid_checkpoint_format(tmp_path, payload):
    path = tmp_path / "checkpoint.json"
    write_json(path, payload)

    with pytest.raises(CheckpointFormatError):
        CheckpointStore.load(path)


def test_tc_p3a5_05_rejects_invalid_json(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(CheckpointFormatError):
        CheckpointStore.load(path)


def test_tc_p3a5_06_rejects_internal_fingerprint_tampering(tmp_path):
    job = make_job()
    path = tmp_path / "checkpoint.json"
    CheckpointStore.save(path, job)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["job"]["project_id"] = "tampered-project"
    write_json(path, payload)

    with pytest.raises(CheckpointIdentityError):
        CheckpointStore.load(path)


def test_tc_p3a5_07_rejects_external_identity_mismatch(tmp_path):
    job = make_job()
    path = tmp_path / "checkpoint.json"
    CheckpointStore.save(path, job)

    with pytest.raises(CheckpointIdentityError):
        CheckpointStore.load(
            path,
            expected_project_id="other-project",
            expected_fingerprint=compute_job_fingerprint(job),
        )

    with pytest.raises(CheckpointIdentityError):
        CheckpointStore.load(
            path,
            expected_project_id=job.project_id,
            expected_fingerprint="sha256:" + "0" * 64,
        )


def test_tc_p3a5_08_roundtrip_does_not_normalize_or_resume(tmp_path):
    job = make_job()
    path = tmp_path / "checkpoint.json"

    CheckpointStore.save(path, job)
    loaded = load_for(job, path)

    assert loaded.state is BatchJobState.RUNNING
    assert loaded.items[0].state is BatchItemState.COMPLETED
    assert loaded.items[1].state is BatchItemState.RUNNING
    assert loaded.items[2].state is BatchItemState.PENDING
    assert loaded.items[3].state is BatchItemState.FAILED


