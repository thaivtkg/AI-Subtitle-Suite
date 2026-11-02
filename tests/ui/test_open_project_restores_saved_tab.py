# -*- coding: utf-8 -*-
from dataclasses import asdict
import json
import os
import pytest
from PySide6.QtWidgets import QApplication
from core.project.source_fingerprint import generate_source_info
from ui.Gui import MainWindow


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def _create_sample_project(project_dir: str, active_page: str, tmp_path):
    os.makedirs(project_dir, exist_ok=True)
    video_path = os.path.join(str(tmp_path), "sample_video.mp4")
    if not os.path.exists(video_path):
        with open(video_path, "wb") as f:
            f.write(b"SAMPLE VIDEO CONTENT 1234567890")
    source_info = generate_source_info(video_path)
    proj_data = {
        "project_id": f"proj_{active_page}",
        "name": f"Sample {active_page} Project",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "source": asdict(source_info),
    }
    with open(os.path.join(project_dir, "project.json"), "w", encoding="utf-8") as f:
        json.dump(proj_data, f)
    with open(os.path.join(project_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({}, f)
    with open(os.path.join(project_dir, "workspace.json"), "w", encoding="utf-8") as f:
        json.dump({"active_page": active_page}, f)


def test_open_project_restores_translation_tab(app, tmp_path):
    """
    PLAN-TAB-PERSISTENCE-RESTORE-001 (Task 3):
    Khi mở dự án có workspace.json lưu active_page='translation',
    MainWindow phải mở đúng Tab Dịch thuật AI (_active_nav_index == 8, stack == 7).
    """
    proj_dir = str(tmp_path / "test_trans_project.ai-subtitle")
    _create_sample_project(proj_dir, "translation", tmp_path)

    win = MainWindow()
    success = win._open_project_by_path(proj_dir)
    assert success is True, "Mở dự án phải thành công"

    assert win._active_nav_index == 8, f"Expected nav index 8 (translation), got {win._active_nav_index}"
    assert win.stack.currentIndex() == 7, f"Expected stack index 7 (translation), got {win.stack.currentIndex()}"


def test_open_project_restores_export_tab(app, tmp_path):
    """
    PLAN-TAB-PERSISTENCE-RESTORE-001 (Task 3):
    Khi mở dự án có workspace.json lưu active_page='export',
    MainWindow phải mở đúng Tab Export Center (_active_nav_index == 5, stack == 4).
    """
    proj_dir = str(tmp_path / "test_export_project.ai-subtitle")
    _create_sample_project(proj_dir, "export", tmp_path)

    win = MainWindow()
    success = win._open_project_by_path(proj_dir)
    assert success is True, "Mở dự án phải thành công"

    assert win._active_nav_index == 5, f"Expected nav index 5 (export), got {win._active_nav_index}"
    assert win.stack.currentIndex() == 4, f"Expected stack index 4 (export), got {win.stack.currentIndex()}"


def test_open_project_safeguard_dashboard_to_workspace(app, tmp_path):
    """
    PLAN-TAB-PERSISTENCE-RESTORE-001 (Task 3):
    Khi mở dự án có workspace.json lưu active_page='dashboard' (tàn dư cũ),
    hệ thống không được văng về dashboard mà phải vào Studio Workspace (nav 1, stack 1).
    """
    proj_dir = str(tmp_path / "test_dash_project.ai-subtitle")
    _create_sample_project(proj_dir, "dashboard", tmp_path)

    win = MainWindow()
    success = win._open_project_by_path(proj_dir)
    assert success is True

    assert win._active_nav_index == 1, f"Expected nav index 1 (workspace), got {win._active_nav_index}"
    assert win.stack.currentIndex() == 1, f"Expected stack index 1 (workspace), got {win.stack.currentIndex()}"
