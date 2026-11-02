from core.subtitle_editing.commands.base_command import SubtitleCommand


class EditTextCommand(SubtitleCommand):
    on_executed_callback = None

    def __init__(self, segment_index: int, old_text: str, new_text: str, data_provider: list, on_executed=None):
        super().__init__("Sửa nội dung", data_provider)
        self.segment_index = segment_index
        self.old_text = old_text
        self.new_text = new_text
        self.on_executed = on_executed

    def id(self):
        return 1

    def mergeWith(self, other: SubtitleCommand) -> bool:
        if not isinstance(other, EditTextCommand) or self.segment_index != other.segment_index:
            return False
        self.new_text = other.new_text
        if getattr(other, "on_executed", None):
            self.on_executed = other.on_executed
        return True

    def undo(self):
        self.data_provider[self.segment_index]["text"] = self.old_text
        self._notify_change()

    def redo(self):
        self.data_provider[self.segment_index]["text"] = self.new_text
        self._notify_change()

    def _notify_change(self):
        if callable(self.on_executed):
            try:
                self.on_executed()
            except Exception:
                pass
        if callable(EditTextCommand.on_executed_callback):
            try:
                EditTextCommand.on_executed_callback()
            except Exception:
                pass
