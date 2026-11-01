from .batch_state import BatchJobState
from .errors import InvalidStateTransitionError


def ensure_job_pause_transition(
    current: BatchJobState,
    target: BatchJobState,
) -> None:
    allowed = {
        (BatchJobState.RUNNING, BatchJobState.PAUSING),
        (BatchJobState.PAUSING, BatchJobState.PAUSED),
        (BatchJobState.PAUSED, BatchJobState.RUNNING),
    }
    if (current, target) not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid pause transition: {current.name} -> {target.name}"
        )
