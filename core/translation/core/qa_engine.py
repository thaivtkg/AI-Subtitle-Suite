"""
Core Subtitle Quality Assurance (QA) Engine
Cung cấp các quy tắc kiểm định chất lượng phụ đề (CPS, CPL, Lines, Tags, Timings).
Thuần logic toán học và xử lý chuỗi (Zero LLM token, Zero third-party dependency).
"""

from dataclasses import dataclass
import html
import re
from typing import Tuple, Union


@dataclass(frozen=True)
class QAIssue:
    code: str        # 'TIME_ERROR', 'CPS_HIGH', 'CPL_LONG', 'LINE_OVERFLOW', 'TAG_MISMATCH'
    severity: str    # 'WARNING' hoặc 'ERROR'
    message: str     # Mô tả tiếng Việt chi tiết


TIME_SRT_PATTERN = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")
TAG_TOKEN_PATTERN = re.compile(r"<\s*(/?)\s*([a-zA-Z0-9]+)(?:\s+[^>]*?)?(\s*/?)>")


def time_to_ms(time_val: Union[int, str]) -> int:
    """Chuyển đổi thời gian dạng số nguyên mili-giây hoặc chuỗi SRT (HH:MM:SS,mmm) sang ms."""
    if isinstance(time_val, int):
        return time_val
    if isinstance(time_val, str):
        val = time_val.strip()
        if val.isdigit():
            return int(val)
        match = TIME_SRT_PATTERN.match(val)
        if match:
            h, m, s, ms = map(int, match.groups())
            return h * 3600000 + m * 60000 + s * 1000 + ms
    return -1


def strip_html_tags(text: str) -> str:
    """Loại bỏ thẻ HTML và giải mã thực thể HTML (&amp;, &nbsp;, ...) để lấy văn bản hiển thị thực tế."""
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", "", text)
    return html.unescape(no_tags).strip()


SUPPORTED_SUBTITLE_TAGS = {"i", "b", "u", "s", "font", "strike", "em", "strong"}


def _check_tags(original: str, translated: str) -> list[QAIssue]:
    """Kiểm tra tính cân bằng thẻ trong câu dịch và tính toàn vẹn so với câu gốc."""
    issues = []

    # 1. Kiểm tra tính cân bằng (Tag balance) trong bản dịch
    stack = []
    has_mismatch = False
    tokens = TAG_TOKEN_PATTERN.findall(translated)

    for is_closing, tag_name, is_self_closing in tokens:
        tag_lower = tag_name.lower()
        # Bỏ qua thẻ tự đóng và các thẻ không thuộc định dạng phụ đề (tránh false positive với placeholder)
        if tag_lower in {"br", "hr"} or is_self_closing.strip() == "/":
            continue
        if tag_lower not in SUPPORTED_SUBTITLE_TAGS:
            continue

        if not is_closing:
            stack.append(tag_lower)
        else:
            if not stack or stack[-1] != tag_lower:
                has_mismatch = True
                break
            stack.pop()

    if has_mismatch or len(stack) > 0:
        issues.append(
            QAIssue(
                code="TAG_MISMATCH",
                severity="ERROR",
                message="Thẻ định dạng HTML trong bản dịch không được đóng đúng cách.",
            )
        )

    # 2. Kiểm tra tính toàn vẹn (Tag parity) so với câu gốc
    orig_tags = {
        name.lower()
        for is_closing, name, is_self in TAG_TOKEN_PATTERN.findall(original)
        if name.lower() in SUPPORTED_SUBTITLE_TAGS and is_self.strip() != "/"
    }
    trans_tags = {
        name.lower()
        for is_closing, name, is_self in TAG_TOKEN_PATTERN.findall(translated)
        if name.lower() in SUPPORTED_SUBTITLE_TAGS and is_self.strip() != "/"
    }

    missing_tags = orig_tags - trans_tags
    if missing_tags and not any(i.code == "TAG_MISMATCH" for i in issues):
        tag_str = ", ".join(f"<{t}>" for t in sorted(missing_tags))
        issues.append(
            QAIssue(
                code="TAG_MISMATCH",
                severity="ERROR",
                message=f"Bản dịch bị thiếu thẻ định dạng từ bản gốc: {tag_str}.",
            )
        )

    return issues


def analyze_subtitle(
    start_time: Union[int, str],
    end_time: Union[int, str],
    original: str,
    translated: str,
) -> Tuple[QAIssue, ...]:
    """
    Kiểm định phụ đề toàn diện:
    - Timing & Duration
    - CPS (Characters Per Second)
    - CPL (Characters Per Line)
    - Line Count (Số dòng)
    - Tag Integrity (Toàn vẹn thẻ HTML)
    """
    # Untranslated or whitespace-only translation -> không bắt lỗi
    if not translated or not translated.strip():
        return ()

    issues: list[QAIssue] = []

    # 1. Timing validation
    start_ms = time_to_ms(start_time)
    end_ms = time_to_ms(end_time)
    has_time_error = (start_ms == -1 or end_ms == -1 or end_ms <= start_ms)

    if has_time_error:
        issues.append(
            QAIssue(
                code="TIME_ERROR",
                severity="ERROR",
                message="Lỗi timestamp: Thời lượng kết thúc nhỏ hơn hoặc bằng thời lượng bắt đầu.",
            )
        )

    # 2. Lấy nội dung hiển thị thực tế sau khi gỡ thẻ và giải mã thực thể
    clean_text = strip_html_tags(translated)

    # 3. CPS (Characters Per Second) - Chỉ tính khi thời lượng hợp lệ
    if not has_time_error:
        duration_sec = max(0.1, (end_ms - start_ms) / 1000.0)
        cps = len(clean_text) / duration_sec
        if cps > 20.0:
            issues.append(
                QAIssue(
                    code="CPS_HIGH",
                    severity="ERROR",
                    message=f"Tốc độ đọc quá nhanh ({cps:.1f} ký tự/giây > 20).",
                )
            )
        elif cps > 17.0:
            issues.append(
                QAIssue(
                    code="CPS_HIGH",
                    severity="WARNING",
                    message=f"Tốc độ đọc hơi nhanh ({cps:.1f} ký tự/giây > 17).",
                )
            )

    # 4. CPL (Characters Per Line) & Line Count (Lọc bỏ dòng trống)
    raw_lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
    line_count = len(raw_lines)
    max_cpl = max((len(l) for l in raw_lines), default=0)

    if max_cpl > 42:
        issues.append(
            QAIssue(
                code="CPL_LONG",
                severity="ERROR",
                message=f"Dòng quá dài, nguy cơ tràn màn hình ({max_cpl} ký tự > 42).",
            )
        )
    elif max_cpl > 40:
        issues.append(
            QAIssue(
                code="CPL_LONG",
                severity="WARNING",
                message=f"Dòng hơi dài ({max_cpl} ký tự > 40).",
            )
        )

    if line_count >= 3:
        issues.append(
            QAIssue(
                code="LINE_OVERFLOW",
                severity="ERROR",
                message=f"Số dòng vượt quá quy định ({line_count} dòng > 2 dòng).",
            )
        )

    # 5. Tag Integrity
    tag_issues = _check_tags(original or "", translated or "")
    issues.extend(tag_issues)

    return tuple(issues)
