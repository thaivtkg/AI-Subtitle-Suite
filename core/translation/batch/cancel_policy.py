from .batch_state import BatchItemState, BatchJobState
from .errors import InvalidStateTransitionError


def ensure_item_cancel_transition(
    current: BatchItemState,
    target: BatchItemState,
) -> None:
    if current is not BatchItemState.PENDING or target is not BatchItemState.CANCELLED:
        raise InvalidStateTransitionError(
            f"Invalid cancel item transition: {current.name} -> {target.name}"
        )


def ensure_job_cancel_transition(
    current: BatchJobState,
    target: BatchJobState,
) -> None:
    if current is not BatchJobState.RUNNING or target is not BatchJobState.CANCELLED:
        raise InvalidStateTransitionError(
            f"Invalid cancel job transition: {current.name} -> {target.name}"
        )
