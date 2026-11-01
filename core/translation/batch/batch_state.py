from enum import Enum, auto


class BatchItemState(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()
    CANCELLED = auto()


class BatchJobState(Enum):
    IDLE = auto()
    RUNNING = auto()
    PAUSING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
