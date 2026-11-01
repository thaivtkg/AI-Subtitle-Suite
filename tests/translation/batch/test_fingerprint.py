from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.fingerprint import compute_job_fingerprint, compute_source_hash


def make_job(project_id="project-1"):
    return BatchJob(
        job_id="fingerprint-job",
        project_id=project_id,
        state=BatchJobState.RUNNING,
        items={
            1: BatchItem(
                target_index=1,
                source_hash=compute_source_hash("Hello"),
                state=BatchItemState.RUNNING,
            ),
            0: BatchItem(
                target_index=0,
                source_hash=compute_source_hash("World"),
                state=BatchItemState.COMPLETED,
                error_msg="old error",
            ),
        },
    )


def test_tc_p3a5_01_source_hash_is_exact_utf8_sha256():
    assert compute_source_hash("Hello") == compute_source_hash("Hello")
    assert compute_source_hash("Hello") != compute_source_hash("hello")
    assert compute_source_hash("Hello") != compute_source_hash("Hello ")
    assert compute_source_hash("Hello").startswith("sha256:")
    assert len(compute_source_hash("Hello")) == len("sha256:") + 64


def test_tc_p3a5_02_job_fingerprint_uses_ordered_source_identity_only():
    job = make_job()
    same_identity = BatchJob(
        job_id="different-job",
        project_id=job.project_id,
        state=BatchJobState.COMPLETED,
        items={
            0: BatchItem(0, compute_source_hash("World"), BatchItemState.FAILED, "new error"),
            1: BatchItem(1, compute_source_hash("Hello"), BatchItemState.PENDING),
        },
    )

    assert compute_job_fingerprint(job) == compute_job_fingerprint(same_identity)
    assert compute_job_fingerprint(job) != compute_job_fingerprint(make_job("project-2"))

    changed_source = make_job()
    changed_source.items[1].source_hash = compute_source_hash("Changed")
    assert compute_job_fingerprint(job) != compute_job_fingerprint(changed_source)


