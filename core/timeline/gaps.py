"""Derived uncovered intervals on a media timeline; no project mutation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TimelineGap:
    start_ms: int
    end_ms: int
    previous_id: str | None
    next_id: str | None

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def find_timeline_gaps(duration_ms: int, segments) -> list[TimelineGap]:
    if duration_ms <= 0:
        return []

    intervals = []
    for segment in segments:
        try:
            if isinstance(segment, dict):
                s_val = segment.get("start_ms", segment.get("start", 0))
                e_val = segment.get("end_ms", segment.get("end", 0))
                seg_id = segment.get("segment_id", segment.get("id"))
            else:
                s_val = getattr(segment, "start_ms", getattr(segment, "start", 0))
                e_val = getattr(segment, "end_ms", getattr(segment, "end", 0))
                seg_id = getattr(segment, "segment_id", getattr(segment, "id", None))

            if isinstance(s_val, str) and ":" in s_val:
                p = s_val.replace(",", ".").split(":")
                s_val = int((float(p[0]) * 3600 + float(p[1]) * 60 + float(p[2])) * 1000)
            if isinstance(e_val, str) and ":" in e_val:
                p = e_val.replace(",", ".").split(":")
                e_val = int((float(p[0]) * 3600 + float(p[1]) * 60 + float(p[2])) * 1000)

            start = max(0, min(duration_ms, int(s_val)))
            end = max(0, min(duration_ms, int(e_val)))
        except (TypeError, ValueError, OverflowError, AttributeError):
            continue
        if end > start:
            intervals.append((start, end, seg_id))
    intervals.sort(key=lambda item: (item[0], -item[1]))

    gaps = []
    covered_until = 0
    previous_id = None
    for start, end, segment_id in intervals:
        if start > covered_until:
            gaps.append(TimelineGap(covered_until, start, previous_id, segment_id))
        if end > covered_until:
            covered_until = end
            previous_id = segment_id
    if covered_until < duration_ms:
        gaps.append(TimelineGap(covered_until, duration_ms, previous_id, None))
    return gaps
