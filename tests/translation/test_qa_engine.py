import pytest
from core.translation.core.qa_engine import QAIssue, analyze_subtitle, strip_html_tags, time_to_ms

def test_tc_qa_01_sanitization_and_html_entities():
    # "Tom &amp; Jerry" unescapes to "Tom & Jerry" (11 chars)
    assert strip_html_tags("Tom &amp; Jerry") == "Tom & Jerry"
    assert len(strip_html_tags("Tom &amp; Jerry")) == 11

    # "<i>Xin chào các bạn</i>" raw 22 chars -> clean 16 chars
    # Duration: 1000ms -> clean CPS is 16.0 (Pass <= 17.0). If tags weren't stripped, CPS would be 22.0 (Error).
    issues = analyze_subtitle(0, 1000, "Hello friends", "<i>Xin chào các bạn</i>")
    assert not any(i.code == "CPS_HIGH" for i in issues)

def test_tc_qa_02_timing_resilience_zero_or_negative():
    issues_zero = analyze_subtitle(1000, 1000, "Hi", "Chào")
    assert any(i.code == "TIME_ERROR" and i.severity == "ERROR" for i in issues_zero)

    issues_negative = analyze_subtitle(2000, 1000, "Hi", "Chào")
    assert any(i.code == "TIME_ERROR" and i.severity == "ERROR" for i in issues_negative)

    # Malformed timestamp string
    issues_invalid = analyze_subtitle("invalid", "00:00:02,000", "Hi", "Chào")
    assert any(i.code == "TIME_ERROR" and i.severity == "ERROR" for i in issues_invalid)

def test_tc_qa_03_cps_cpl_boundaries():
    # Exact CPS = 17.0 (17 chars in 1.0 sec) -> Pass
    text_17 = "12345678901234567"
    issues = analyze_subtitle(0, 1000, "Source", text_17)
    assert not any(i.code == "CPS_HIGH" for i in issues)

    # CPS 18.0 (18 chars in 1.0 sec) -> WARNING
    text_18 = "123456789012345678"
    issues = analyze_subtitle(0, 1000, "Source", text_18)
    cps_issues = [i for i in issues if i.code == "CPS_HIGH"]
    assert len(cps_issues) == 1 and cps_issues[0].severity == "WARNING"

    # CPS 21.0 (21 chars in 1.0 sec) -> ERROR
    text_21 = "123456789012345678901"
    issues = analyze_subtitle(0, 1000, "Source", text_21)
    cps_issues = [i for i in issues if i.code == "CPS_HIGH"]
    assert len(cps_issues) == 1 and cps_issues[0].severity == "ERROR"

    # Exact CPL = 40 -> Pass
    line_40 = "A" * 40
    issues = analyze_subtitle(0, 5000, "Source", line_40)
    assert not any(i.code == "CPL_LONG" for i in issues)

    # CPL = 41 -> WARNING
    line_41 = "A" * 41
    issues = analyze_subtitle(0, 5000, "Source", line_41)
    cpl_issues = [i for i in issues if i.code == "CPL_LONG"]
    assert len(cpl_issues) == 1 and cpl_issues[0].severity == "WARNING"

    # CPL = 43 -> ERROR
    line_43 = "A" * 43
    issues = analyze_subtitle(0, 5000, "Source", line_43)
    cpl_issues = [i for i in issues if i.code == "CPL_LONG"]
    assert len(cpl_issues) == 1 and cpl_issues[0].severity == "ERROR"

def test_tc_qa_04_line_overflow_and_empty_middle_lines():
    # 2 lines with accidental empty middle line -> Pass (only 2 real lines)
    text_with_empty_line = "Dòng 1\n\nDòng 2\n"
    issues = analyze_subtitle(0, 3000, "Source", text_with_empty_line)
    assert not any(i.code == "LINE_OVERFLOW" for i in issues)

    # 3 real lines -> ERROR
    text_3_lines = "Dòng 1\nDòng 2\nDòng 3"
    issues = analyze_subtitle(0, 3000, "Source", text_3_lines)
    line_issues = [i for i in issues if i.code == "LINE_OVERFLOW"]
    assert len(line_issues) == 1 and line_issues[0].severity == "ERROR"

def test_tc_qa_05_tag_integrity_attributes_and_self_closing():
    # Unclosed tag in translation
    issues = analyze_subtitle(0, 2000, "<i>Hello</i>", "<i>Xin chào")
    assert any(i.code == "TAG_MISMATCH" and i.severity == "ERROR" for i in issues)

    # Missing tag from source
    issues = analyze_subtitle(0, 2000, "<i>Hello</i>", "Xin chào")
    assert any(i.code == "TAG_MISMATCH" and i.severity == "ERROR" for i in issues)

    # Matching tags with attributes (e.g. font color)
    issues = analyze_subtitle(0, 2000, '<font color="#ff0000">Red</font>', '<font color="red">Đỏ</font>')
    assert not any(i.code == "TAG_MISMATCH" for i in issues)

    # Self-closing tag <br/> or <br /> does not trigger tag mismatch
    issues_br = analyze_subtitle(0, 2000, "Line 1<br/>Line 2", "Dòng 1<br />Dòng 2")
    assert not any(i.code == "TAG_MISMATCH" for i in issues_br)

def test_tc_qa_06_empty_or_whitespace_translation():
    assert analyze_subtitle(0, 2000, "Hello", "") == ()
    assert analyze_subtitle(0, 2000, "Hello", "   \n  ") == ()

def test_tc_qa_07_no_cascading_cps_on_time_error():
    # Long text with time error (2000 -> 1000) must only emit TIME_ERROR, NOT CPS_HIGH
    long_text = "Đây là một câu phụ đề tương đối dài có thể kích hoạt lỗi tốc độ đọc nếu tính nhầm"
    issues = analyze_subtitle(2000, 1000, "Source", long_text)
    assert any(i.code == "TIME_ERROR" for i in issues)
    assert not any(i.code == "CPS_HIGH" for i in issues)

def test_tc_qa_08_ignore_non_subtitle_tags():
    # Placeholders like <player_name> or angle brackets like Vector<int> should not trigger TAG_MISMATCH
    issues = analyze_subtitle(0, 3000, "Winner: <player_name>", "Người thắng: <player_name>")
    assert not any(i.code == "TAG_MISMATCH" for i in issues)

    issues_brackets = analyze_subtitle(0, 3000, "Type Vector<int>", "Kiểu Vector<int>")
    assert not any(i.code == "TAG_MISMATCH" for i in issues_brackets)


