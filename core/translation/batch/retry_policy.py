from .batch_job import BatchJob
from .batch_state import BatchItemState, BatchJobState
from .errors import InvalidStateTransitionError


def ensure_retry_eligible(job: BatchJob) -> None:
    if job.state is not BatchJobState.COMPLETED:
        raise InvalidStateTransitionError(
            f"Retry requires COMPLETED job, got {job.state.name}"
        )
    if not any(item.state is BatchItemState.FAILED for item in job.items.values()):
        raise InvalidStateTransitionError(
            "Retry requires at least one FAILED item"
        )


def ensure_job_retry_transition(
    current: BatchJobState,
    target: BatchJobState,
) -> None:
    if current is not BatchJobState.COMPLETED or target is not BatchJobState.RUNNING:
        raise InvalidStateTransitionError(
            f"Invalid retry job transition: {current.name} -> {target.name}"
        )


def ensure_item_retry_transition(
    current: BatchItemState,
    target: BatchItemState,
) -> None:
    if current is not BatchItemState.FAILED or target is not BatchItemState.RUNNING:
        raise InvalidStateTransitionError(
            f"Invalid retry item transition: {current.name} -> {target.name}"
        )
