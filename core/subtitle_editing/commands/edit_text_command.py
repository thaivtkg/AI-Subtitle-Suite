from core.subtitle_editing.commands.base_command import SubtitleCommand


class EditTextCommand(SubtitleCommand):
    on_executed_callback = None

    def __init__(self, segment_index: int, old_text: str, new_text: str, data_provider: list, on_executed=None, sync_translation=False):
        super().__init__("Sửa nội dung", data_provider)
        self.segment_index = segment_index
        self.old_text = old_text
        self.new_text = new_text
        self.on_executed = on_executed
        self.sync_translation = sync_translation
        segment = data_provider[segment_index]
        self.old_translation = segment.get("translation")
        self.old_translation_status = segment.get("translation_status")

    def id(self):
        return 1

    def mergeWith(self, other: SubtitleCommand) -> bool:
        if (not isinstance(other, EditTextCommand) or self.segment_index != other.segment_index
                or self.sync_translation != other.sync_translation):
            return False
        self.new_text = other.new_text
        if getattr(other, "on_executed", None):
            self.on_executed = other.on_executed
        return True

    def undo(self):
        segment = self.data_provider[self.segment_index]
        segment["text"] = self.old_text
        if self.sync_translation:
            if self.old_translation is None:
                segment.pop("translation", None)
            else:
                segment["translation"] = self.old_translation
            if self.old_translation_status is None:
                segment.pop("translation_status", None)
            else:
                segment["translation_status"] = self.old_translation_status
        self._notify_change()

    def redo(self):
        segment = self.data_provider[self.segment_index]
        segment["text"] = self.new_text
        if self.sync_translation:
            translated = self.new_text.strip() and self.new_text.strip() != str(segment.get("original_text") or "").strip()
            segment["translation"] = self.new_text if translated else ""
            segment["translation_status"] = "ACCEPTED" if translated else "PENDING"
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
