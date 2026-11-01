from dataclasses import dataclass
from typing import Optional

from .batch_state import BatchItemState


@dataclass
class BatchItem:
    target_index: int
    source_hash: str
    state: BatchItemState = BatchItemState.PENDING
    error_msg: Optional[str] = None

    def __post_init__(self) -> None:
        if self.target_index < 0:
            raise ValueError("target_index must be >= 0")
        if not self.source_hash.strip():
            raise ValueError("source_hash must not be empty")
