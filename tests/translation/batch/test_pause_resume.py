import pytest

from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.checkpoint import CheckpointStore
from core.translation.batch.fingerprint import compute_job_fingerprint, compute_source_hash
from core.translation.services.batch_translation_service import BatchTranslationService
from tests.translation.batch.test_sequential_runner import ControlledTranslationPort


def make_job(item_states, job_state=BatchJobState.IDLE):
    return BatchJob(
        job_id="pause-test",
        project_id="project-1",
        state=job_state,
        items={
            index: BatchItem(
                target_index=index,
                source_hash=compute_source_hash(f"source-{index}"),
                state=item_state,
                error_msg=f"old error {index}" if item_state is BatchItemState.FAILED else None,
            )
            for index, item_state in enumerate(item_states)
        },
    )


def test_tc_p3a6_02_pause_eligibility_and_job_identity():
    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING])
    service = BatchTranslationService(port)

    with pytest.raises(RuntimeError):
        service.request_pause(job)

    service.start(job)
    service.request_pause(job)

    with pytest.raises(RuntimeError):
        service.request_pause(BatchJob("other-job", "project-1", state=BatchJobState.RUNNING))

    with pytest.raises(RuntimeError):
        service.request_pause(job)


def test_tc_p3a6_03_graceful_pause_after_success():
    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_pause(job)

    assert job.state is BatchJobState.PAUSING
    assert job.items[0].state is BatchItemState.RUNNING
    assert job.items[1].state is BatchItemState.PENDING
    assert port.calls == [0]

    port.complete_current()

    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.PENDING
    assert job.state is BatchJobState.PAUSED
    assert port.calls == [0]
    assert port.active_count == 0


def test_tc_p3a6_04_graceful_pause_after_failure():
    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_pause(job)
    port.fail_current("pause failure")

    assert job.items[0].state is BatchItemState.FAILED
    assert job.items[0].error_msg == "pause failure"
    assert job.items[1].state is BatchItemState.PENDING
    assert job.state is BatchJobState.PAUSED
    assert port.calls == [0]


def test_tc_p3a6_05_resume_continues_normal_queue():
    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING, BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_pause(job)
    port.complete_current()
    assert job.state is BatchJobState.PAUSED

    service.resume(job)
    assert job.state is BatchJobState.RUNNING
    assert job.items[1].state is BatchItemState.RUNNING
    assert port.calls == [0, 1]

    port.complete_current()
    assert job.items[2].state is BatchItemState.RUNNING
    port.complete_current()

    assert job.state is BatchJobState.COMPLETED
    assert all(item.state is BatchItemState.COMPLETED for item in job.items.values())
    assert port.calls == [0, 1, 2]
    assert port.max_concurrent == 1


def test_tc_p3a6_06_resume_preserves_retry_snapshot_and_cursor():
    port = ControlledTranslationPort()
    job = make_job(
        [
            BatchItemState.COMPLETED,
            BatchItemState.FAILED,
            BatchItemState.COMPLETED,
            BatchItemState.FAILED,
            BatchItemState.COMPLETED,
            BatchItemState.FAILED,
        ],
        job_state=BatchJobState.COMPLETED,
    )
    service = BatchTranslationService(port)

    service.retry_failed(job)
    port.complete_current()
    assert port.calls == [1, 3]

    service.request_pause(job)
    assert job.state is BatchJobState.PAUSING
    port.complete_current()

    assert job.state is BatchJobState.PAUSED
    assert job.items[5].state is BatchItemState.FAILED
    assert service._retry_targets == (1, 3, 5)
    assert service._retry_cursor == 2

    service.resume(job)
    assert port.calls == [1, 3, 5]
    assert job.items[5].state is BatchItemState.RUNNING
    port.complete_current()

    assert job.state is BatchJobState.COMPLETED
    assert port.calls == [1, 3, 5]
    assert port.max_concurrent == 1


def test_tc_p3a6_07_pause_resume_keeps_single_active_target():
    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING, BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_pause(job)
    assert port.calls == [0]
    port.complete_current()

    service.resume(job)
    service.request_pause(job)
    assert port.calls == [0, 1]
    port.complete_current()

    service.resume(job)
    assert port.calls == [0, 1, 2]
    port.complete_current()

    assert job.state is BatchJobState.COMPLETED
    assert port.active_count == 0
    assert port.max_concurrent == 1


def test_tc_p3a6_08_pause_cancel_conflict_first_request_wins():
    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_cancel(job)
    with pytest.raises(RuntimeError):
        service.request_pause(job)
    assert job.state is BatchJobState.RUNNING

    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)
    service.start(job)
    service.request_pause(job)
    with pytest.raises(RuntimeError):
        service.request_cancel(job)
    assert job.state is BatchJobState.PAUSING


def test_tc_p3a6_09_paused_checkpoint_does_not_resume(tmp_path):
    job = make_job(
        [BatchItemState.COMPLETED, BatchItemState.PENDING],
        job_state=BatchJobState.PAUSED,
    )
    path = tmp_path / "paused-checkpoint.json"

    CheckpointStore.save(path, job)
    loaded = CheckpointStore.load(
        path,
        expected_project_id=job.project_id,
        expected_fingerprint=compute_job_fingerprint(job),
    )

    assert loaded.state is BatchJobState.PAUSED
    assert loaded.items[0].state is BatchItemState.COMPLETED
    assert loaded.items[1].state is BatchItemState.PENDING


def test_tc_p3a6_10_pause_on_last_active_item_then_resume_completes():
    port = ControlledTranslationPort()
    job = make_job([BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_pause(job)
    port.complete_current()

    assert job.state is BatchJobState.PAUSED
    assert port.calls == [0]

    service.resume(job)

    assert job.state is BatchJobState.COMPLETED
    assert port.calls == [0]
    assert port.active_count == 0


