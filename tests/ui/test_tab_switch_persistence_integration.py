# -*- coding: utf-8 -*-
import json
import os
import pytest
from PySide6.QtWidgets import QApplication
from ui.Gui import MainWindow
from tests.uat.conftest import MockProjectService


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_switch_page_persists_active_tab_immediately(app, tmp_path):
    """
    PLAN-TAB-PERSISTENCE-RESTORE-001 (Task 2):
    Khi co project dang mo, switch_page() phai ngay lap tuc:
    1. Cap nhat current_project.state.workspace.active_page.
    2. Ghi de tep workspace.json tren dia cung ngay lap tuc.
    """
    proj_service = MockProjectService(str(tmp_path))
    win = MainWindow(project_service=proj_service)

    # 1. Chuyen sang Tab Dich thuat AI (8)
    win.switch_page(8)
    assert proj_service.current_project.state.workspace.active_page == "translation"

    ws_file = os.path.join(str(tmp_path), "workspace.json")
    assert os.path.exists(ws_file), "workspace.json phai duoc ghi ngay khi chuyen tab"
    with open(ws_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("active_page") == "translation"

    # 2. Chuyen sang Export Center (5)
    win.switch_page(5)
    assert proj_service.current_project.state.workspace.active_page == "export"
    with open(ws_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("active_page") == "export"

    # 3. Chuyen sang Queue & Output (3)
    win.switch_page(3)
    assert proj_service.current_project.state.workspace.active_page == "queue"
    with open(ws_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("active_page") == "queue"
