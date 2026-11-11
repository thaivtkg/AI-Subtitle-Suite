import re
import uuid


def _to_ms(value):
    match = re.fullmatch(r"^(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})$", value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    h_str, m_str, s_str, ms_str = match.groups()
    h = int(h_str) if h_str is not None else 0
    m, s, ms = int(m_str), int(s_str), int(ms_str.ljust(3, '0'))
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def parse_srt_content(content: str) -> list[dict]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    pattern = re.compile(
        r"(?:^|\n+)(?:[ \t]*(\d+)[ \t]*\n)?"
        r"[ \t]*((?:(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})[ \t]*-->[ \t]*(?:(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3}))[ \t]*(?:\n|\Z)"
        r"([\s\S]*?)(?=(?:\n+[ \t]*(?:\d+[ \t]*\n)?[ \t]*(?:(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})[ \t]*-->)|\Z)"
    )
    matches = list(pattern.finditer(normalized))
    if matches:
        segments = []
        for match in matches:
            _, ts, txt = match.groups()
            start, end = (part.strip() for part in ts.split("-->", 1))
            segments.append({
                "id": uuid.uuid4().hex,
                "stt": str(len(segments) + 1),
                "start": _to_ms(start),
                "end": _to_ms(end),
                "text": txt.strip(),
                "status": "draft",
                "metadata": {"type": "normal"},
            })
        return segments

    segments = []
    for block in re.split(r"\n{2,}", normalized):
        lines = block.splitlines()
        if not lines:
            continue
        if "-->" in lines[0]:
            ts_line = lines[0]
            text_lines = lines[1:]
        elif len(lines) >= 2 and "-->" in lines[1]:
            ts_line = lines[1]
            text_lines = lines[2:]
        else:
            continue
        start, end = (part.strip() for part in ts_line.split("-->", 1))
        segments.append({
            "id": uuid.uuid4().hex,
            "stt": str(len(segments) + 1),
            "start": _to_ms(start),
            "end": _to_ms(end),
            "text": "\n".join(text_lines).strip(),
            "status": "draft",
            "metadata": {"type": "normal"},
        })
    return segments
