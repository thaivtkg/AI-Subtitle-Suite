import sys
from unittest.mock import patch
import pytest

from core.translation.core.runtime_check import check_vc_redist, verify_environment


def test_check_vc_redist_on_current_machine():
    """Kiểm tra máy phát triển hiện tại có VC++ runtime."""
    if sys.platform == "win32":
        assert check_vc_redist() is True
    else:
        assert check_vc_redist() is True


def test_verify_environment_non_interactive_success():
    """verify_environment(interactive=False) trả về True trên máy có đủ DLL."""
    assert verify_environment(interactive=False) is True


def test_verify_environment_simulated_missing_dll():
    """Giả lập thiếu DLL và kiểm tra hàm trả về False khi non-interactive."""
    with patch("core.translation.core.runtime_check.check_vc_redist", return_value=False):
        assert verify_environment(interactive=False) is False


def test_main_cli_smoke_test():
    """Kiểm tra cờ CLI --smoke-test khởi động QML thành công và thoát mã 0."""
    import subprocess
    import os

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main_py = os.path.join(project_root, "main.py")

    result = subprocess.run(
        [sys.executable, main_py, "--smoke-test"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "[SMOKE TEST] Application initialized successfully" in result.stdout

