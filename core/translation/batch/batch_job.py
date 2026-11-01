from dataclasses import dataclass, field
from typing import Dict
from uuid import uuid4

from .batch_item import BatchItem
from .batch_state import BatchJobState


@dataclass
class BatchJob:
    job_id: str
    project_id: str
    items: Dict[int, BatchItem] = field(default_factory=dict)
    state: BatchJobState = BatchJobState.IDLE

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id must not be empty")
        if not self.project_id.strip():
            raise ValueError("project_id must not be empty")
        for index, item in self.items.items():
            if index != item.target_index:
                raise ValueError(
                    f"Item key {index} does not match "
                    f"target_index {item.target_index}"
                )

    @classmethod
    def create(cls, project_id: str, items: Dict[int, BatchItem]) -> "BatchJob":
        return cls(job_id=str(uuid4()), project_id=project_id, items=items)
