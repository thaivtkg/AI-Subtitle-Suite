from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.services.batch_translation_service import BatchTranslationService

from tests.translation.batch.test_sequential_runner import ControlledTranslationPort


def completed_job_with_failed_items():
    return BatchJob(
        job_id="retry-failed-test",
        project_id="project-1",
        state=BatchJobState.COMPLETED,
        items={
            0: BatchItem(
                target_index=0,
                source_hash="hash-0",
                state=BatchItemState.COMPLETED,
            ),
            1: BatchItem(
                target_index=1,
                source_hash="hash-1",
                state=BatchItemState.FAILED,
                error_msg="old error 1",
            ),
            2: BatchItem(
                target_index=2,
                source_hash="hash-2",
                state=BatchItemState.COMPLETED,
            ),
            3: BatchItem(
                target_index=3,
                source_hash="hash-3",
                state=BatchItemState.FAILED,
                error_msg="old error 3",
            ),
        },
    )


def test_tc_p3a3_03_retry_dispatches_frozen_failed_snapshot_in_order():
    port = ControlledTranslationPort()
    job = completed_job_with_failed_items()
    service = BatchTranslationService(port)

    service.retry_failed(job)

    assert job.state is BatchJobState.RUNNING
    assert port.calls == [1]
    assert job.items[1].state is BatchItemState.RUNNING
    assert job.items[3].state is BatchItemState.FAILED
    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[2].state is BatchItemState.COMPLETED

    port.complete_current()

    assert port.calls == [1, 3]
    assert job.items[1].state is BatchItemState.COMPLETED
    assert job.items[3].state is BatchItemState.RUNNING

    port.complete_current()

    assert job.state is BatchJobState.COMPLETED
    assert job.items[3].state is BatchItemState.COMPLETED
    assert port.calls == [1, 3]
    assert port.max_concurrent == 1


def test_tc_p3a3_04_retry_clears_error_only_when_item_is_dispatched():
    port = ControlledTranslationPort()
    job = completed_job_with_failed_items()
    service = BatchTranslationService(port)

    service.retry_failed(job)

    assert job.items[1].error_msg is None
    assert job.items[3].error_msg == "old error 3"

    port.complete_current()

    assert job.items[3].error_msg is None

    port.complete_current()


def test_tc_p3a3_05_retry_failure_does_not_loop_and_continues_snapshot():
    port = ControlledTranslationPort()
    job = completed_job_with_failed_items()
    service = BatchTranslationService(port)

    service.retry_failed(job)
    assert port.calls == [1]

    port.fail_current("retry failed")

    assert job.items[1].state is BatchItemState.FAILED
    assert job.items[1].error_msg == "retry failed"
    assert port.calls == [1, 3]
    assert job.items[3].state is BatchItemState.RUNNING
    assert port.active_count == 1
    assert port.max_concurrent == 1

    port.complete_current()

    assert job.items[3].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.FAILED
    assert job.state is BatchJobState.COMPLETED
    assert port.calls == [1, 3]
    assert port.active_count == 0
    assert port.max_concurrent == 1


def test_tc_p3a3_06_mixed_retry_results_finalize_job_after_snapshot():
    port = ControlledTranslationPort()
    job = BatchJob(
        job_id="retry-mixed-test",
        project_id="project-1",
        state=BatchJobState.COMPLETED,
        items={
            index: BatchItem(
                target_index=index,
                source_hash=f"hash-{index}",
                state=state,
                error_msg=f"old error {index}" if state is BatchItemState.FAILED else None,
            )
            for index, state in {
                0: BatchItemState.COMPLETED,
                1: BatchItemState.FAILED,
                2: BatchItemState.FAILED,
                3: BatchItemState.COMPLETED,
                4: BatchItemState.FAILED,
            }.items()
        },
    )
    service = BatchTranslationService(port)

    service.retry_failed(job)
    assert port.calls == [1]

    port.complete_current()
    assert port.calls == [1, 2]
    assert job.items[1].state is BatchItemState.COMPLETED
    assert job.items[2].state is BatchItemState.RUNNING

    port.fail_current("retry error 2")
    assert port.calls == [1, 2, 4]
    assert job.items[2].state is BatchItemState.FAILED
    assert job.items[2].error_msg == "retry error 2"
    assert job.items[4].state is BatchItemState.RUNNING
    assert job.state is BatchJobState.RUNNING

    port.complete_current()

    assert job.items[4].state is BatchItemState.COMPLETED
    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[3].state is BatchItemState.COMPLETED
    assert job.state is BatchJobState.COMPLETED
    assert port.calls == [1, 2, 4]
    assert port.active_count == 0
    assert port.max_concurrent == 1


