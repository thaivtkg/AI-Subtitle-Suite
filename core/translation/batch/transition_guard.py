from collections.abc import Mapping
from enum import Enum
from typing import TypeVar

from .batch_state import BatchItemState, BatchJobState
from .errors import InvalidStateTransitionError


StateT = TypeVar("StateT", bound=Enum)


_ITEM_TRANSITIONS: Mapping[BatchItemState, frozenset[BatchItemState]] = {
    BatchItemState.PENDING: frozenset({BatchItemState.RUNNING}),
    BatchItemState.RUNNING: frozenset({
        BatchItemState.COMPLETED,
        BatchItemState.FAILED,
    }),
    BatchItemState.COMPLETED: frozenset(),
    BatchItemState.FAILED: frozenset(),
    BatchItemState.SKIPPED: frozenset(),
    BatchItemState.CANCELLED: frozenset(),
}


_JOB_TRANSITIONS: Mapping[BatchJobState, frozenset[BatchJobState]] = {
    BatchJobState.IDLE: frozenset({BatchJobState.RUNNING}),
    BatchJobState.RUNNING: frozenset({
        BatchJobState.COMPLETED,
        BatchJobState.FAILED,
    }),
    BatchJobState.PAUSING: frozenset(),
    BatchJobState.PAUSED: frozenset(),
    BatchJobState.COMPLETED: frozenset(),
    BatchJobState.FAILED: frozenset(),
    BatchJobState.CANCELLED: frozenset(),
}


def _ensure_transition(
    current: StateT,
    target: StateT,
    transitions: Mapping[StateT, frozenset[StateT]],
) -> None:
    allowed = transitions.get(current, frozenset())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid transition: {current.name} -> {target.name}"
        )


def ensure_item_transition(
    current: BatchItemState,
    target: BatchItemState,
) -> None:
    _ensure_transition(current, target, _ITEM_TRANSITIONS)


def ensure_job_transition(
    current: BatchJobState,
    target: BatchJobState,
) -> None:
    _ensure_transition(current, target, _JOB_TRANSITIONS)
