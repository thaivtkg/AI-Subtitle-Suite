from core.subtitle_editing.commands.base_command import SubtitleCommand


class SplitCommand(SubtitleCommand):
    def __init__(self, segment_index: int, split_time_ms: int, data_provider: list, on_applied=None, on_undone=None):
        super().__init__("Tách Subtitle", data_provider)
        self.segment_index = segment_index
        self.split_time_ms = split_time_ms
        self.on_applied = on_applied
        self.on_undone = on_undone
        self.original_seg = None
        self.new_segment = None

    def _split_text_at_midpoint(self, text: str) -> tuple[str, str]:
        if not text:
            return "", ""
        text = text.strip()
        if len(text) <= 1:
            return text, ""
        midpoint = len(text) // 2
        r_start = max(0, midpoint - 100)
        r_end = min(len(text), midpoint + 100)

        # 1. Ưu tiên dấu ngắt câu chính (. ! ? … 。 ！ ？ \n)
        primary_puncts = ".!?…\n。！？"
        primary_cands = [i + 1 for i in range(r_start, min(r_end, len(text) - 1)) if text[i] in primary_puncts]
        if primary_cands:
            best = min(primary_cands, key=lambda i: abs(i - midpoint))
            return text[:best].strip(), text[best:].strip()

        # 2. Ưu tiên dấu ngắt câu phụ (, ; : 、 ， ；)
        secondary_puncts = ",;:、，；"
        sec_cands = [i + 1 for i in range(r_start, min(r_end, len(text) - 1)) if text[i] in secondary_puncts]
        if sec_cands:
            best = min(sec_cands, key=lambda i: abs(i - midpoint))
            return text[:best].strip(), text[best:].strip()

        # 3. Ưu tiên dấu cách (space/tab)
        spaces = [i for i in range(r_start, r_end) if text[i].isspace()]
        if spaces:
            best = min(spaces, key=lambda i: abs(i - midpoint))
            return text[:best].strip(), text[best:].strip()

        # 4. Fallback cho chuỗi không dấu cách (tiếng Nhật/Trung): cắt đôi chuỗi
        return text[:midpoint].strip(), text[midpoint:].strip()

    def redo(self):
        if self.original_seg is None:
            self.original_seg = self.data_provider[self.segment_index].copy()
            if "id" in self.original_seg and not self.original_seg["id"]:
                import uuid
                self.original_seg["id"] = uuid.uuid4().hex
                self.data_provider[self.segment_index]["id"] = self.original_seg["id"]

        text1, text2 = self._split_text_at_midpoint(self.original_seg.get("text", ""))

        start_val = self.original_seg.get("start")
        if isinstance(start_val, str):
            from ui.SubEditor import ms_to_time_str
            split_end = ms_to_time_str(self.split_time_ms)
        else:
            split_end = self.split_time_ms

        self.data_provider[self.segment_index]["end"] = split_end
        self.data_provider[self.segment_index]["text"] = text1
        if "start_ms" in self.original_seg:
            self.data_provider[self.segment_index]["end_ms"] = self.split_time_ms

        # Split original_text if present
        if "original_text" in self.original_seg:
            orig1, orig2 = self._split_text_at_midpoint(self.original_seg.get("original_text", ""))
            self.data_provider[self.segment_index]["original_text"] = orig1
        else:
            orig1, orig2 = None, None

        # Reset translation and status on split halves
        if "translation" in self.original_seg or "translation_status" in self.original_seg:
            self.data_provider[self.segment_index]["translation"] = ""
            self.data_provider[self.segment_index]["translation_status"] = "PENDING"

        if self.new_segment is None:
            self.new_segment = self.original_seg.copy()
            self.new_segment["start"] = split_end
            self.new_segment["end"] = self.original_seg["end"]
            self.new_segment["text"] = text2
            if orig2 is not None:
                self.new_segment["original_text"] = orig2
            if "start_ms" in self.original_seg:
                self.new_segment["start_ms"] = self.split_time_ms
                self.new_segment["end_ms"] = self.original_seg.get("end_ms", self.split_time_ms)
            if "id" in self.new_segment:
                import uuid
                self.new_segment["id"] = uuid.uuid4().hex
            if "translation" in self.original_seg or "translation_status" in self.original_seg:
                self.new_segment["translation"] = ""
                self.new_segment["translation_status"] = "PENDING"

        self.data_provider.insert(self.segment_index + 1, self.new_segment)
        self._renumber_stt()

        if callable(self.on_applied):
            orig_id = str(self.original_seg.get("id") or self.original_seg.get("stt") or (self.segment_index + 1))
            self.on_applied(
                orig_id,
                self.data_provider[self.segment_index],
                self.data_provider[self.segment_index + 1]
            )

    def undo(self):
        self.data_provider.pop(self.segment_index + 1)
        self.data_provider[self.segment_index] = self.original_seg.copy()
        self._renumber_stt()
        if callable(self.on_undone):
            orig_id = str(self.original_seg.get("id") or self.original_seg.get("stt") or (self.segment_index + 1))
            new_id = str(self.new_segment.get("id") if self.new_segment else "")
            self.on_undone(orig_id, new_id, self.original_seg)
