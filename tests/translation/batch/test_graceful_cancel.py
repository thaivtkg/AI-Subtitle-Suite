import pytest

from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.services.batch_translation_service import BatchTranslationService
from tests.translation.batch.test_sequential_runner import ControlledTranslationPort


def make_running_job(item_states):
    return BatchJob(
        job_id="cancel-test",
        project_id="project-1",
        state=BatchJobState.IDLE,
        items={
            index: BatchItem(
                target_index=index,
                source_hash=f"hash-{index}",
                state=item_state,
            )
            for index, item_state in enumerate(item_states)
        },
    )


def test_tc_p3a4_01_cancel_eligibility():
    port = ControlledTranslationPort()
    job = make_running_job([BatchItemState.PENDING])
    service = BatchTranslationService(port)

    with pytest.raises(RuntimeError):
        service.request_cancel(job)

    service.start(job)
    service.request_cancel(job)

    with pytest.raises(RuntimeError):
        service.request_cancel(BatchJob(
            job_id="other-job",
            project_id="project-1",
            state=BatchJobState.RUNNING,
        ))


def test_tc_p3a4_03_graceful_current_success():
    port = ControlledTranslationPort()
    job = make_running_job([BatchItemState.PENDING, BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_cancel(job)

    assert job.state is BatchJobState.RUNNING
    assert job.items[0].state is BatchItemState.RUNNING
    assert port.calls == [0]

    port.complete_current()

    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.CANCELLED
    assert job.items[2].state is BatchItemState.CANCELLED
    assert job.state is BatchJobState.CANCELLED
    assert port.calls == [0]
    assert port.max_concurrent == 1


def test_tc_p3a4_04_graceful_current_failure_preserves_error():
    port = ControlledTranslationPort()
    job = make_running_job([BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_cancel(job)
    port.fail_current("cancelled inference failed")

    assert job.items[0].state is BatchItemState.FAILED
    assert job.items[0].error_msg == "cancelled inference failed"
    assert job.items[1].state is BatchItemState.CANCELLED
    assert job.state is BatchJobState.CANCELLED
    assert port.calls == [0]


def test_tc_p3a4_05_no_dispatch_after_cancel_request():
    port = ControlledTranslationPort()
    job = make_running_job([BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_cancel(job)
    assert port.calls == [0]

    port.complete_current()

    assert port.calls == [0]
    assert port.active_count == 0


def test_tc_p3a4_06_preserve_existing_terminal_states():
    port = ControlledTranslationPort()
    job = BatchJob(
        job_id="cancel-terminal-test",
        project_id="project-1",
        items={
            0: BatchItem(0, "hash-0", BatchItemState.PENDING),
            1: BatchItem(1, "hash-1", BatchItemState.FAILED, "old error"),
            2: BatchItem(2, "hash-2", BatchItemState.SKIPPED),
            3: BatchItem(3, "hash-3", BatchItemState.PENDING),
        },
    )
    service = BatchTranslationService(port)

    service.start(job)
    service.request_cancel(job)
    port.complete_current()

    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.FAILED
    assert job.items[1].error_msg == "old error"
    assert job.items[2].state is BatchItemState.SKIPPED
    assert job.items[3].state is BatchItemState.CANCELLED
    assert job.state is BatchJobState.CANCELLED


def test_tc_p3a4_07_repeated_cancel_is_in_flight_idempotent():
    port = ControlledTranslationPort()
    job = make_running_job([BatchItemState.PENDING, BatchItemState.PENDING])
    service = BatchTranslationService(port)

    service.start(job)
    service.request_cancel(job)
    service.request_cancel(job)
    service.request_cancel(job)

    assert port.calls == [0]
    port.complete_current()

    assert job.state is BatchJobState.CANCELLED
    assert port.calls == [0]

    with pytest.raises(RuntimeError):
        service.request_cancel(job)


def test_tc_p3a4_08_cancel_during_retry_preserves_unretried_failed_items():
    port = ControlledTranslationPort()
    job = BatchJob(
        job_id="cancel-retry-test",
        project_id="project-1",
        state=BatchJobState.COMPLETED,
        items={
            index: BatchItem(
                target_index=index,
                source_hash=f"hash-{index}",
                state=BatchItemState.FAILED if index in (1, 3, 5) else BatchItemState.COMPLETED,
                error_msg=f"old error {index}" if index in (1, 3, 5) else None,
            )
            for index in range(6)
        },
    )
    service = BatchTranslationService(port)

    service.retry_failed(job)
    port.complete_current()
    assert port.calls == [1, 3]
    assert job.items[5].state is BatchItemState.FAILED

    service.request_cancel(job)
    port.complete_current()

    assert job.items[3].state is BatchItemState.COMPLETED
    assert job.items[5].state is BatchItemState.FAILED
    assert job.items[5].error_msg == "old error 5"
    assert job.state is BatchJobState.CANCELLED
    assert port.calls == [1, 3]
    assert port.active_count == 0
    assert port.max_concurrent == 1


