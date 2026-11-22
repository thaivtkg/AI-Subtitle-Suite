import atexit
import os
import shutil
import sys
from pathlib import Path
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


def pytest_configure(config):
    basetemp = getattr(config.option, "basetemp", None)
    if basetemp:
        Path(basetemp).parent.mkdir(parents=True, exist_ok=True)


def _cleanup_stray_test_dirs(include_basetemp: bool = False):
    repo_root = Path(__file__).resolve().parent.parent
    magic_dir = repo_root / "MagicMock"
    if magic_dir.exists():
        shutil.rmtree(magic_dir, ignore_errors=True)
    if include_basetemp:
        temp_dir = repo_root / ".pytest_temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
    stray_subgen = repo_root / "artifacts" / "subtitle_generation"
    if stray_subgen.exists() and not any(stray_subgen.iterdir()):
        shutil.rmtree(stray_subgen, ignore_errors=True)
        artifacts_root = repo_root / "artifacts"
        if artifacts_root.exists() and not any(artifacts_root.iterdir()):
            artifacts_root.rmdir()


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_artifacts_after_session():
    """Luôn dọn các thư mục tạm/dữ liệu test (MagicMock, .pytest_temp, thư mục rỗng) sau khi chạy test."""
    atexit.register(_cleanup_stray_test_dirs, True)
    yield
    _cleanup_stray_test_dirs(include_basetemp=False)
