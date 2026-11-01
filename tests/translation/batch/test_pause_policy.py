import pytest

from core.translation.batch.batch_state import BatchJobState
from core.translation.batch.errors import InvalidStateTransitionError
from core.translation.batch.pause_policy import (
    ensure_job_pause_transition,
)
from core.translation.batch.transition_guard import ensure_job_transition


def test_tc_p3a6_01_pause_policy_allows_specialized_transitions():
    ensure_job_pause_transition(BatchJobState.RUNNING, BatchJobState.PAUSING)
    ensure_job_pause_transition(BatchJobState.PAUSING, BatchJobState.PAUSED)
    ensure_job_pause_transition(BatchJobState.PAUSED, BatchJobState.RUNNING)


def test_tc_p3a6_01_generic_guard_still_rejects_pause_transitions():
    with pytest.raises(InvalidStateTransitionError):
        ensure_job_transition(BatchJobState.RUNNING, BatchJobState.PAUSING)

    with pytest.raises(InvalidStateTransitionError):
        ensure_job_transition(BatchJobState.PAUSING, BatchJobState.PAUSED)

    with pytest.raises(InvalidStateTransitionError):
        ensure_job_transition(BatchJobState.PAUSED, BatchJobState.RUNNING)

