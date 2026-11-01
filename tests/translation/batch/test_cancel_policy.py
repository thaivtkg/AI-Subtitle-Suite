import pytest

from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.cancel_policy import (
    ensure_item_cancel_transition,
    ensure_job_cancel_transition,
)
from core.translation.batch.errors import InvalidStateTransitionError
from core.translation.batch.transition_guard import ensure_item_transition, ensure_job_transition


def test_tc_p3a4_02_cancel_policy_allows_specialized_transitions():
    ensure_item_cancel_transition(BatchItemState.PENDING, BatchItemState.CANCELLED)
    ensure_job_cancel_transition(BatchJobState.RUNNING, BatchJobState.CANCELLED)


def test_tc_p3a4_02_generic_guard_still_rejects_cancel_transitions():
    with pytest.raises(InvalidStateTransitionError):
        ensure_item_transition(BatchItemState.PENDING, BatchItemState.CANCELLED)

    with pytest.raises(InvalidStateTransitionError):
        ensure_job_transition(BatchJobState.RUNNING, BatchJobState.CANCELLED)

