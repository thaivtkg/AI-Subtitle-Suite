from core.subtitle_editing.commands.base_command import SubtitleCommand
from core.subtitle_editing.segment_factory import SubtitleSegmentFactory


def _ms_to_time_str(ms: int) -> str:
    s, ms_rem = divmod(max(0, int(ms)), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"


class AddCommand(SubtitleCommand):
    def __init__(self, segment_index: int, start_ms: int, end_ms: int, data_provider: list, text: str = ""):
        super().__init__("Thêm Subtitle", data_provider)
        self.segment_index = segment_index
        self.new_segment = SubtitleSegmentFactory.create_segment(start_ms, end_ms, text=text)
        if data_provider and isinstance(data_provider[0].get("start"), str):
            self.new_segment["start"] = _ms_to_time_str(start_ms)
            self.new_segment["end"] = _ms_to_time_str(end_ms)
            self.new_segment["start_ms"] = int(start_ms)
            self.new_segment["end_ms"] = int(end_ms)

    def redo(self):
        self.data_provider.insert(self.segment_index, self.new_segment)
        self._renumber_stt()

    def undo(self):
        self.data_provider.pop(self.segment_index)
        self._renumber_stt()
