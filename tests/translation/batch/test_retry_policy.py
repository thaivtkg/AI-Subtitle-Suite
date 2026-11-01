import pytest

from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.errors import InvalidStateTransitionError
from core.translation.batch.retry_policy import (
    ensure_item_retry_transition,
    ensure_job_retry_transition,
    ensure_retry_eligible,
)


def make_job(job_state, item_states):
    return BatchJob(
        job_id="retry-policy-test",
        project_id="project-1",
        state=job_state,
        items={
            index: BatchItem(
                target_index=index,
                source_hash=f"hash-{index}",
                state=item_state,
            )
            for index, item_state in enumerate(item_states)
        },
    )


def test_tc_p3a3_01_completed_job_with_failed_item_is_retry_eligible():
    job = make_job(
        BatchJobState.COMPLETED,
        [BatchItemState.COMPLETED, BatchItemState.FAILED],
    )

    ensure_retry_eligible(job)


@pytest.mark.parametrize(
    "job_state,item_states",
    [
        (BatchJobState.IDLE, [BatchItemState.FAILED]),
        (BatchJobState.RUNNING, [BatchItemState.FAILED]),
        (BatchJobState.FAILED, [BatchItemState.FAILED]),
        (BatchJobState.CANCELLED, [BatchItemState.FAILED]),
        (BatchJobState.PAUSING, [BatchItemState.FAILED]),
        (BatchJobState.PAUSED, [BatchItemState.FAILED]),
        (BatchJobState.COMPLETED, [BatchItemState.COMPLETED]),
    ],
)
def test_tc_p3a3_01_rejects_ineligible_retry_jobs(job_state, item_states):
    job = make_job(job_state, item_states)

    with pytest.raises(InvalidStateTransitionError):
        ensure_retry_eligible(job)


def test_tc_p3a3_02_retry_policy_allows_specialized_transitions():
    ensure_job_retry_transition(BatchJobState.COMPLETED, BatchJobState.RUNNING)
    ensure_item_retry_transition(BatchItemState.FAILED, BatchItemState.RUNNING)


def test_tc_p3a3_02_generic_guard_still_rejects_retry_transitions():
    from core.translation.batch.transition_guard import ensure_item_transition, ensure_job_transition

    with pytest.raises(InvalidStateTransitionError):
        ensure_job_transition(BatchJobState.COMPLETED, BatchJobState.RUNNING)

    with pytest.raises(InvalidStateTransitionError):
        ensure_item_transition(BatchItemState.FAILED, BatchItemState.RUNNING)

