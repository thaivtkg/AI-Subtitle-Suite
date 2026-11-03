from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QObject, Signal


class SelectionSource(Enum):
    EDITOR = auto()
    TIMELINE = auto()
    PLAYBACK = auto()
    PROGRAMMATIC = auto()


class SubtitleSelectionController(QObject):
    """Nguồn chân lý duy nhất (Single Source of Truth) cho trạng thái Selection."""

    # Sử dụng object để cho phép truyền đồng thời str (segment_id) hoặc None
    selection_changed = Signal(int, object, SelectionSource)
    multi_selection_changed = Signal(list, set, SelectionSource)
    editor_activation_requested = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_index: int = -1
        self._selected_segment_id: Optional[str] = None
        self._selected_indices: list[int] = []
        self._selected_ids: set[str] = set()

    @property
    def selected_index(self) -> int:
        return self._selected_index

    @property
    def selected_segment_id(self) -> Optional[str]:
        return self._selected_segment_id

    @property
    def selected_indices(self) -> list[int]:
        return list(self._selected_indices)

    @property
    def selected_ids(self) -> set[str]:
        return set(self._selected_ids)

    def select(
        self,
        index: int,
        segment_id: Optional[str],
        source: SelectionSource = SelectionSource.PROGRAMMATIC,
    ):
        """Cập nhật trạng thái và phát tín hiệu đồng bộ xuống các View."""
        if self._selected_index == index and self._selected_segment_id == segment_id and len(self._selected_ids) <= 1:
            return

        self._selected_index = index
        self._selected_segment_id = segment_id
        self._selected_indices = [index] if index >= 0 else []
        self._selected_ids = {segment_id} if segment_id else set()
        self.selection_changed.emit(index, segment_id, source)
        self.multi_selection_changed.emit(self._selected_indices, self._selected_ids, source)

    def select_multiple(
        self,
        indices: list[int],
        segment_ids: set[str],
        source: SelectionSource = SelectionSource.PROGRAMMATIC,
    ):
        """Cập nhật trạng thái chọn nhiều phân đoạn đồng thời."""
        sorted_indices = sorted(indices)
        set_ids = set(segment_ids)
        if self._selected_indices == sorted_indices and self._selected_ids == set_ids:
            return

        self._selected_indices = sorted_indices
        self._selected_ids = set_ids
        self._selected_index = sorted_indices[0] if len(sorted_indices) == 1 else -1
        self._selected_segment_id = next(iter(set_ids)) if len(set_ids) == 1 else None
        self.multi_selection_changed.emit(self._selected_indices, self._selected_ids, source)

    def clear_selection(
        self, source: SelectionSource = SelectionSource.PROGRAMMATIC
    ):
        """Bỏ chọn toàn bộ, truyền segment_id = None."""
        self._selected_indices = []
        self._selected_ids = set()
        self.select(-1, None, source)

    def request_editor_activation(self, index: int, segment_id: Optional[str]):
        """Notify editor intent without changing duplicate logical selection state."""
        if self._selected_index == index and self._selected_segment_id == segment_id:
            self.editor_activation_requested.emit(index, segment_id)
