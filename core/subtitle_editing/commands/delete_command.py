from typing import Sequence, Union

from core.subtitle_editing.commands.base_command import SubtitleCommand


class DeleteCommand(SubtitleCommand):
    def __init__(self, segment_indices: Union[int, Sequence[int]], data_provider: list):
        if isinstance(segment_indices, int) and not isinstance(segment_indices, bool):
            raw_indices = [segment_indices]
            legacy_single = segment_indices
        else:
            raw_indices = list(segment_indices or ())
            legacy_single = None

        valid_indices = sorted(
            {
                int(idx)
                for idx in raw_indices
                if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(data_provider)
            }
        )
        title = "Xóa Subtitle" if len(valid_indices) <= 1 else f"Xóa {len(valid_indices)} Subtitle"
        super().__init__(title, data_provider)
        self.indices: list[int] = valid_indices
        self.segment_index: int = (
            legacy_single if legacy_single is not None else (valid_indices[0] if valid_indices else -1)
        )
        self.deleted_items: list[tuple[int, dict]] = []
        self.deleted_segment = None

    def redo(self):
        self.deleted_items = []
        for idx in reversed(self.indices):
            if 0 <= idx < len(self.data_provider):
                self.deleted_items.append((idx, self.data_provider.pop(idx)))
        self.deleted_items.reverse()
        self.deleted_segment = self.deleted_items[0][1] if len(self.deleted_items) == 1 else None
        self._renumber_stt()

    def undo(self):
        for idx, seg in self.deleted_items:
            insert_pos = max(0, min(idx, len(self.data_provider)))
            self.data_provider.insert(insert_pos, seg)
        self._renumber_stt()
