from core.subtitle_editing.commands.base_command import SubtitleCommand


class MergeCommand(SubtitleCommand):
    def __init__(self, segment_index: int, data_provider: list, on_applied=None, on_undone=None):
        super().__init__("Gộp Subtitle", data_provider)
        self.segment_index = segment_index
        self.on_applied = on_applied
        self.on_undone = on_undone
        self.original_seg1 = None
        self.original_seg2 = None

    def redo(self):
        if self.original_seg1 is None:
            self.original_seg1 = self.data_provider[self.segment_index].copy()
            self.original_seg2 = self.data_provider.pop(self.segment_index + 1)
        else:
            self.data_provider.pop(self.segment_index + 1)

        self.data_provider[self.segment_index]["end"] = self.original_seg2["end"]
        if "end_ms" in self.original_seg2:
            self.data_provider[self.segment_index]["end_ms"] = self.original_seg2["end_ms"]

        merged_text = f"{self.original_seg1.get('text', '').strip()} {self.original_seg2.get('text', '').strip()}".strip()
        self.data_provider[self.segment_index]["text"] = merged_text

        if "original_text" in self.original_seg1 or "original_text" in self.original_seg2:
            merged_original = f"{self.original_seg1.get('original_text', '').strip()} {self.original_seg2.get('original_text', '').strip()}".strip()
            self.data_provider[self.segment_index]["original_text"] = merged_original

        if "translation" in self.original_seg1 or "translation" in self.original_seg2:
            trans1 = self.original_seg1.get("translation", "").strip()
            trans2 = self.original_seg2.get("translation", "").strip()
            merged_trans = f"{trans1} {trans2}".strip()
            self.data_provider[self.segment_index]["translation"] = merged_trans

            st1 = str(self.original_seg1.get("translation_status", "")).upper()
            st2 = str(self.original_seg2.get("translation_status", "")).upper()
            if (st1 in ("TRANSLATED", "EDITED", "ACCEPTED")) and (st2 in ("TRANSLATED", "EDITED", "ACCEPTED")):
                self.data_provider[self.segment_index]["translation_status"] = "EDITED"
            else:
                self.data_provider[self.segment_index]["translation_status"] = "PENDING"

        self._renumber_stt()

        if callable(self.on_applied):
            id1 = str(self.original_seg1.get("id") or self.original_seg1.get("stt") or (self.segment_index + 1))
            id2 = str(self.original_seg2.get("id") or self.original_seg2.get("stt") or (self.segment_index + 2))
            self.on_applied(id1, id2, self.data_provider[self.segment_index])

    def undo(self):
        self.data_provider[self.segment_index] = self.original_seg1.copy()
        self.data_provider.insert(self.segment_index + 1, self.original_seg2.copy())
        self._renumber_stt()
        if callable(self.on_undone):
            id1 = str(self.original_seg1.get("id") or self.original_seg1.get("stt") or (self.segment_index + 1))
            self.on_undone(id1, self.original_seg1, self.original_seg2)
