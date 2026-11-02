# -*- coding: utf-8 -*-
"""
Tests for WorkspaceService tab persistence and 2-way navigation mapping.
PLAN-TAB-PERSISTENCE-RESTORE-001:
Ensures all 8 navigation tabs are captured and restored accurately,
with a safeguard preventing kickback to Dashboard when opening projects.
"""
from unittest.mock import MagicMock
import pytest
from core.project.project import Project, SourceInfo
from core.project.project_state import ProjectState, WorkspaceState
from core.services.workspace_service import WorkspaceService


class DummyMainWindow:
    def __init__(self, nav_index=0):
        self._active_nav_index = nav_index
        self.switched_pages = []

    def switch_page(self, target_index):
        self.switched_pages.append(target_index)
        self._active_nav_index = target_index


class DummyProjectService:
    def __init__(self, active_page="workspace"):
        self.current_project = Project(
            project_id="test_proj_tab",
            name="Test Tab Project",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            source=SourceInfo(
                path="video.mp4",
                filename="video.mp4",
                size_bytes=1000,
                modified_at=0.0,
                fingerprint="hash_tab_1",
            ),
            state=ProjectState(workspace=WorkspaceState(active_page=active_page)),
        )


@pytest.mark.parametrize(
    "nav_index,expected_page",
    [
        (0, "dashboard"),
        (1, "workspace"),
        (2, "queue"),
        (3, "queue"),
        (4, "draft"),
        (5, "export"),
        (6, "settings"),
        (7, "help"),
        (8, "translation"),
    ],
)
def test_capture_workspace_maps_all_nav_pages(nav_index, expected_page):
    """capture_workspace phai anh xa chinh xac moi nav index sang active_page."""
    ui = DummyMainWindow(nav_index=nav_index)
    proj_service = DummyProjectService()
    service = WorkspaceService(ui, proj_service)

    service.capture_workspace()

    actual_page = proj_service.current_project.state.workspace.active_page
    assert actual_page == expected_page, f"Nav {nav_index} expected {expected_page}, got {actual_page}"


@pytest.mark.parametrize(
    "saved_page,expected_nav_index",
    [
        ("translation", 8),
        ("help", 7),
        ("settings", 6),
        ("export", 5),
        ("draft", 4),
        ("queue", 3),
        ("workspace", 1),
        ("editor", 1),  # Backward compatibility
    ],
)
def test_restore_workspace_maps_all_pages(saved_page, expected_nav_index):
    """restore_workspace phai chuyen dung nav index ung voi moi saved active_page."""
    ui = DummyMainWindow()
    proj_service = DummyProjectService(active_page=saved_page)
    service = WorkspaceService(ui, proj_service)

    service.restore_workspace()

    assert ui.switched_pages[-1] == expected_nav_index, (
        f"Page '{saved_page}' expected nav {expected_nav_index}, got {ui.switched_pages[-1]}"
    )


def test_restore_workspace_safeguard_against_dashboard():
    """Khi mo du an, neu active_page la 'dashboard' hoac khong xac dinh, khong duoc vang ve 0 ma phai vao Workspace (1)."""
    ui = DummyMainWindow()
    # 1. active_page la 'dashboard'
    proj_service = DummyProjectService(active_page="dashboard")
    service = WorkspaceService(ui, proj_service)
    service.restore_workspace()
    assert ui.switched_pages[-1] == 1, "Dashboard phai duoc safeguard dua ve Studio Workspace (1)"

    # 2. active_page khong xac dinh
    proj_service.current_project.state.workspace.active_page = "unknown_random_tab"
    service.restore_workspace()
    assert ui.switched_pages[-1] == 1, "Trang khong xac dinh phai fallback ve Studio Workspace (1)"
