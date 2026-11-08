import copy
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SnapshotManager:
    """
    Transactional Snapshot & Rollback Manager for ProjectState.
    Captures pre-task checkpoints before each Agent step and allows
    clean rollback on "Yêu cầu làm lại task".
    """

    def __init__(self, project_state: Any):
        self.project_state = project_state
        self._snapshots: Dict[str, Dict[str, Any]] = {}

    def take_snapshot(self, tag: str = "checkpoint") -> str:
        snapshot_id = f"{tag}_{int(time.time() * 1000)}"
        state_dict: Dict[str, Any] = {}

        # Safely copy fields from project_state
        if hasattr(self.project_state, "__dict__"):
            for key, val in self.project_state.__dict__.items():
                try:
                    state_dict[key] = copy.deepcopy(val)
                except Exception as e:
                    logger.debug("Field %s shallow copied: %s", key, e)
                    state_dict[key] = copy.copy(val)
        elif isinstance(self.project_state, dict):
            state_dict = copy.deepcopy(self.project_state)

        self._snapshots[snapshot_id] = state_dict
        logger.info("Snapshot captured: %s", snapshot_id)
        return snapshot_id

    def has_snapshot(self, snapshot_id: str) -> bool:
        return snapshot_id in self._snapshots

    def restore_snapshot(self, snapshot_id: str) -> bool:
        if snapshot_id not in self._snapshots:
            logger.warning("Snapshot not found: %s", snapshot_id)
            return False

        saved = self._snapshots[snapshot_id]
        if hasattr(self.project_state, "__dict__"):
            for key, val in saved.items():
                try:
                    setattr(self.project_state, key, copy.deepcopy(val))
                except Exception as e:
                    logger.warning("Error restoring field %s: %s", key, e)
                    setattr(self.project_state, key, val)
        elif isinstance(self.project_state, dict):
            self.project_state.clear()
            self.project_state.update(copy.deepcopy(saved))

        logger.info("Snapshot restored successfully: %s", snapshot_id)
        return True

    def clear(self) -> None:
        self._snapshots.clear()
