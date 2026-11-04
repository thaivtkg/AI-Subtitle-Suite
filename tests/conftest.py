import os
import sys
import pytest
from PySide6.QtWidgets import QApplication

# Ensure a global QApplication is instantiated once before any test runs,
# preventing non-GUI QCoreApplication from conflicting with GUI widget tests.
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

@pytest.fixture(scope="session", autouse=True)
def qapp():
    return _app


@pytest.fixture(autouse=True)
def clean_recent_projects_after_test():
    """Tự động dọn dẹp các dự án thử nghiệm (test/temp) khỏi settings.json sau mỗi bài test."""
    from core.utils.recent_projects import get_recent_projects, remove_recent_project
    initial_paths = {p["path"] for p in get_recent_projects()}
    yield
    for p in get_recent_projects():
        path = p.get("path", "")
        if path not in initial_paths or "Temp" in path or "pytest" in path or not os.path.exists(path):
            remove_recent_project(path)
