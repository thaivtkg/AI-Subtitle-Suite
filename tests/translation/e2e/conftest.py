from pathlib import Path
import re
import tempfile

import pytest


_final_reports = {}


def pytest_configure(config):
    pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or "test_final_regression.py" not in item.nodeid:
        return

    _final_reports[item.nodeid] = report.outcome
    if report.failed:
        harness = item.funcargs.get("harness")
        if harness is not None:
            harness.driver.artifact_dir = Path("artifacts/t15/failures")
            harness.driver.snapshot(item.name)


def pytest_sessionfinish(session, exitstatus):
    if not _final_reports:
        return

    report_path = Path("artifacts/t15/T15_REPORT.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["P2.5-T15 FINAL REGRESSION", ""]
    for nodeid, outcome in _final_reports.items():
        case_name = nodeid.rsplit("::", 1)[-1]
        match = re.match(r"test_tc15_(\d+)_(.*)", case_name)
        if match:
            case_id = f"TC15-{int(match.group(1)):02d}"
            label = match.group(2).replace("_", " ").title()
            lines.append(f"{case_id} {label} ........ {outcome.upper()}")
        else:
            lines.append(f"{case_name}: {outcome.upper()}")
    passed = sum(outcome == "passed" for outcome in _final_reports.values())
    failed = sum(outcome == "failed" for outcome in _final_reports.values())
    errors = sum(outcome == "error" for outcome in _final_reports.values())
    lines.extend([
        "",
        f"{passed} PASS",
        f"{failed} FAIL",
        f"{errors} ERROR",
        "",
        f"OVERALL: {'GREEN' if failed == 0 and errors == 0 else 'RED'}",
    ])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
