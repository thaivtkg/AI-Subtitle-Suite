import pytest

from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.errors import InvalidStateTransitionError
from core.translation.batch.transition_guard import ensure_item_transition, ensure_job_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BatchItemState.PENDING, BatchItemState.RUNNING),
        (BatchItemState.RUNNING, BatchItemState.COMPLETED),
        (BatchItemState.RUNNING, BatchItemState.FAILED),
    ],
)
def test_tc_p3a2_01_valid_item_transitions(current, target):
    ensure_item_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BatchJobState.IDLE, BatchJobState.RUNNING),
        (BatchJobState.RUNNING, BatchJobState.COMPLETED),
        (BatchJobState.RUNNING, BatchJobState.FAILED),
    ],
)
def test_tc_p3a2_01_valid_job_transitions(current, target):
    ensure_job_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BatchItemState.FAILED, BatchItemState.RUNNING),
        (BatchItemState.RUNNING, BatchItemState.PENDING),
        (BatchItemState.COMPLETED, BatchItemState.RUNNING),
        (BatchItemState.PENDING, BatchItemState.CANCELLED),
    ],
)
def test_tc_p3a2_02_invalid_item_transitions(current, target):
    with pytest.raises(InvalidStateTransitionError):
        ensure_item_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BatchJobState.RUNNING, BatchJobState.PAUSING),
        (BatchJobState.PAUSED, BatchJobState.RUNNING),
        (BatchJobState.RUNNING, BatchJobState.CANCELLED),
        (BatchJobState.COMPLETED, BatchJobState.RUNNING),
    ],
)
def test_tc_p3a2_02_invalid_job_transitions(current, target):
    with pytest.raises(InvalidStateTransitionError):
        ensure_job_transition(current, target)

