from core.subtitle_editing.commands.base_command import SubtitleCommand


class MergeCommand(SubtitleCommand):
    def __init__(self, segment_index: int, data_provider: list, on_applied=None, on_undone=None, count: int = 2):
        super().__init__("Gộp Subtitle", data_provider)
        self.segment_index = segment_index
        self.count = max(2, int(count))
        self.on_applied = on_applied
        self.on_undone = on_undone
        self.original_segs = None
        self.original_seg1 = None
        self.original_seg2 = None

    def redo(self):
        if self.original_segs is None:
            end_idx = min(len(self.data_provider), self.segment_index + self.count)
            self.original_segs = [
                self.data_provider[i].copy() for i in range(self.segment_index, end_idx)
            ]
            self.count = len(self.original_segs)
            if self.count < 2:
                return
            self.original_seg1 = self.original_segs[0]
            self.original_seg2 = self.original_segs[-1]

        del self.data_provider[self.segment_index + 1 : self.segment_index + self.count]

        target = self.data_provider[self.segment_index]
        target["end"] = self.original_seg2["end"]
        if "end_ms" in self.original_seg2:
            target["end_ms"] = self.original_seg2["end_ms"]

        target["text"] = " ".join(
            str(seg.get("text", "")).strip()
            for seg in self.original_segs
            if str(seg.get("text", "")).strip()
        ).strip()

        if any("original_text" in seg for seg in self.original_segs):
            target["original_text"] = " ".join(
                str(seg.get("original_text", "")).strip()
                for seg in self.original_segs
                if str(seg.get("original_text", "")).strip()
            ).strip()

        if any("translation" in seg for seg in self.original_segs):
            target["translation"] = " ".join(
                str(seg.get("translation", "")).strip()
                for seg in self.original_segs
                if str(seg.get("translation", "")).strip()
            ).strip()
            statuses = [str(seg.get("translation_status", "")).upper() for seg in self.original_segs]
            if all(st in ("TRANSLATED", "EDITED", "ACCEPTED") for st in statuses):
                target["translation_status"] = "EDITED"
            else:
                target["translation_status"] = "PENDING"

        self._renumber_stt()

        if callable(self.on_applied):
            id1 = str(self.original_seg1.get("id") or self.original_seg1.get("stt") or (self.segment_index + 1))
            id2 = str(self.original_seg2.get("id") or self.original_seg2.get("stt") or (self.segment_index + self.count))
            self.on_applied(id1, id2, target)

    def undo(self):
        if not self.original_segs:
            return
        self.data_provider[self.segment_index] = self.original_segs[0].copy()
        for offset, orig_seg in enumerate(self.original_segs[1:], start=1):
            self.data_provider.insert(self.segment_index + offset, orig_seg.copy())
        self._renumber_stt()
        if callable(self.on_undone):
            id1 = str(self.original_seg1.get("id") or self.original_seg1.get("stt") or (self.segment_index + 1))
            self.on_undone(id1, self.original_seg1, self.original_seg2)
