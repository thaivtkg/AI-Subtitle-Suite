# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from core.utils.recent_projects import (
    add_recent_project,
    get_recent_projects,
    clear_recent_projects,
)


def test_e2e_recent_projects_ui_workflow(live_studio_app, tmp_path, monkeypatch, qapp):
    """
    Selenium-equivalent E2E UI Test for Recent Projects:
    - Step 1: Open Dashboard and verify Empty State placeholder.
    - Step 2: Seed recent projects and verify dynamic card rendering on Dashboard.
    - Step 3: Simulate QTest mouseClick on 'Mở' button -> verify project dispatch.
    - Step 4: Open Topbar 'Dự Án' menu via QTest -> inspect '🕒 Mở Dự Án Gần Đây' submenu.
    - Step 5: Trigger '🗑 Xóa Lịch Sử' action -> verify real-time UI synchronization.
    - Step 6: Test opening non-existent project -> verify error handling and auto-pruning.
    """
    win, log_watcher, runner = live_studio_app

    # Ensure isolated settings file for E2E run
    custom_settings = str(tmp_path / "settings_e2e.json")
    monkeypatch.setattr(
        "core.runtime.runtime_paths.RuntimePaths.get_settings_file",
        lambda: custom_settings,
    )
    clear_recent_projects()

    screenshot_dir = r"C:\Users\Kuroberus\.gemini\antigravity\brain\15b69ee2-ac46-4cb5-a08d-e12a3cbab0eb"

    # =========================================================================
    # Step 1: Verify Initial Dashboard Empty State
    # =========================================================================
    with runner.step("Bước 1: Kiểm tra trạng thái rỗng trên trang Dashboard", timeout_ms=5000):
        win.switch_page(0)  # Dashboard page
        qapp.processEvents()

        assert hasattr(win.page_dashboard, "recent_container")
        win.page_dashboard.refresh_recent_projects()
        qapp.processEvents()

        labels = [lbl.text() for lbl in win.page_dashboard.recent_container.findChildren(QLabel)]
        assert "Chưa có dự án nào gần đây." in labels

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "e2e_step1_dashboard_empty.png"))

    # =========================================================================
    # Step 2: Seed Recent Projects & Verify Dashboard Card Rendering
    # =========================================================================
    with runner.step("Bước 2: Nạp 3 dự án gần đây và kiểm tra hiển thị trên Dashboard", timeout_ms=5000):
        proj_dir_1 = str(tmp_path / "Project_Alpha.ai-subtitle")
        proj_dir_2 = str(tmp_path / "Project_Beta.ai-subtitle")
        proj_dir_3 = str(tmp_path / "Project_Gamma.ai-subtitle")
        os.makedirs(proj_dir_1, exist_ok=True)
        os.makedirs(proj_dir_2, exist_ok=True)
        os.makedirs(proj_dir_3, exist_ok=True)

        add_recent_project(proj_dir_1, "Project Alpha", "alpha.mp4")
        add_recent_project(proj_dir_2, "Project Beta", "beta.mp4")
        add_recent_project(proj_dir_3, "Project Gamma", "gamma.mp4")

        win.page_dashboard.refresh_recent_projects()
        qapp.processEvents()

        labels = [lbl.text() for lbl in win.page_dashboard.recent_container.findChildren(QLabel)]
        assert "Project Gamma" in labels
        assert "Project Beta" in labels
        assert "Project Alpha" in labels

        buttons = win.page_dashboard.recent_container.findChildren(QPushButton)
        open_buttons = [btn for btn in buttons if btn.text() == "Mở"]
        assert len(open_buttons) == 3

        # Capture visual proof of populated card
        win.grab().save(os.path.join(screenshot_dir, "e2e_step2_dashboard_populated.png"))

    # =========================================================================
    # Step 3: Simulate QTest MouseClick on 'Mở' button on Dashboard
    # =========================================================================
    with runner.step("Bước 3: Nhấp nút 'Mở' trên thẻ Dashboard qua QTest mouseClick", timeout_ms=5000):
        dispatched_paths = []
        original_open = win._open_project_by_path
        win._open_project_by_path = lambda path: dispatched_paths.append(path)

        # Click "Mở" button of the first item (Project Gamma)
        QTest.mouseClick(open_buttons[0], Qt.LeftButton)
        qapp.processEvents()

        assert len(dispatched_paths) == 1
        assert os.path.normpath(dispatched_paths[0]) == os.path.normpath(proj_dir_3)

        # Restore original open method
        win._open_project_by_path = original_open

    # =========================================================================
    # Step 4: Open Topbar 'Dự Án' Menu & Verify Submenu via QTest
    # =========================================================================
    with runner.step("Bước 4: Mở menu Topbar 'Dự Án' và kiểm tra Submenu 'Mở Dự Án Gần Đây'", timeout_ms=5000):
        # Click Topbar Project Menu Button
        QTest.mouseClick(win.btn_project_menu, Qt.LeftButton)
        qapp.processEvents()

        # Verify Submenu actions
        win._refresh_recent_projects_menu()
        actions = [a.text() for a in win.menu_recent.actions()]
        assert "1.  Project Gamma" in actions
        assert "2.  Project Beta" in actions
        assert "3.  Project Alpha" in actions
        assert "🗑  Xóa Lịch Sử" in actions

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "e2e_step4_topbar_menu.png"))

    # =========================================================================
    # Step 5: Trigger 'Xóa Lịch Sử' and Verify Synchronized UI Cleared State
    # =========================================================================
    with runner.step("Bước 5: Kích hoạt 'Xóa Lịch Sử' và kiểm tra đồng bộ giao diện", timeout_ms=5000):
        clear_action = next(a for a in win.menu_recent.actions() if "Xóa Lịch Sử" in a.text())
        clear_action.trigger()
        qapp.processEvents()

        # Recent list must be empty
        assert get_recent_projects() == []

        # Submenu must show "(Trống)"
        win._refresh_recent_projects_menu()
        sub_actions = [a.text() for a in win.menu_recent.actions()]
        assert sub_actions == ["(Trống)"]

        # Dashboard must immediately refresh to empty state
        labels_after_clear = [lbl.text() for lbl in win.page_dashboard.recent_container.findChildren(QLabel)]
        assert "Chưa có dự án nào gần đây." in labels_after_clear

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "e2e_step5_cleared_state.png"))

    # =========================================================================
    # Step 6: Test Opening Non-Existent Project (Error & Pruning)
    # =========================================================================
    with runner.step("Bước 6: Mở đường dẫn dự án không tồn tại và kiểm tra tự động loại bỏ", timeout_ms=5000):
        ghost_path = str(tmp_path / "Ghost_Project.ai-subtitle")
        add_recent_project(ghost_path, "Ghost Project")
        assert len(get_recent_projects()) == 1

        # Attempt to open missing directory
        result = win._open_project_by_path(ghost_path)
        assert result is False

        # Must be pruned from recent projects list
        assert len(get_recent_projects()) == 0

        # Dashboard must update
        win.page_dashboard.refresh_recent_projects()
        qapp.processEvents()
        labels_final = [lbl.text() for lbl in win.page_dashboard.recent_container.findChildren(QLabel)]
        assert "Chưa có dự án nào gần đây." in labels_final
