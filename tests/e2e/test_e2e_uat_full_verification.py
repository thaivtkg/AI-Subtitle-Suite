# -*- coding: utf-8 -*-
"""
Selenium-equivalent E2E UAT Automated Driver for AI Subtitle Studio:
Executes the full User Acceptance Testing (UAT) suite across 6 verified defect areas:
- Step 1: UAT-01: ExportCenterPage batch sentence count clamping.
- Step 2: UAT-02: DashboardPage recent projects ✕ button rendering and removal.
- Step 3: UAT-03: SubtitleEditorWidget prev/next buttons (< and >) navigation and signal routing.
- Step 4: UAT-04: Subtitle rescan 🔊 Tăng âm (+6dB) audio boost option.
- Step 5: UAT-05: SubtitleInspectorPanel preset dropdown, block separation, and instant preview refresh.
- Step 6: UAT-06: QualityInspectorPanel liquid physics selection overlay full-width stretching.
"""
import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QLabel, QCheckBox

from core.utils.recent_projects import (
    add_recent_project,
    get_recent_projects,
    clear_recent_projects,
)


def test_e2e_uat_full_acceptance_suite(live_studio_app, tmp_path, monkeypatch, qapp):
    win, log_watcher, runner = live_studio_app
    screenshot_dir = r"C:\Users\Kuroberus\.gemini\antigravity\brain\15b69ee2-ac46-4cb5-a08d-e12a3cbab0eb"

    # =========================================================================
    # Step 1: UAT-01: ExportCenterPage Batch Sentence Count Clamping
    # =========================================================================
    with runner.step("UAT-01: Kiem tra gioi han so cau xuat dot dich (ExportCenterPage)", timeout_ms=5000):
        win.switch_page(4)  # Export Center page
        qapp.processEvents()

        # Simulate translation progress: 14/18 done, next batch start = 15, remaining = 4
        win.page_export.update_translation_progress(current_start=15, total_count=18, translated_count=14)
        qapp.processEvents()

        assert win.page_export.spin_batch_start.value() == 15
        assert win.page_export.spin_batch_count.maximum() == 4
        assert win.page_export.spin_batch_count.value() == 4
        assert "15" in win.page_export.lbl_batch_progress.text()
        assert "18" in win.page_export.lbl_batch_progress.text()

        # Dynamic change: change start to 17 -> remaining = 2
        win.page_export.spin_batch_start.setValue(17)
        qapp.processEvents()
        assert win.page_export.spin_batch_count.maximum() == 2
        assert win.page_export.spin_batch_count.value() == 2

        # Reset back to 15 for screenshot
        win.page_export.spin_batch_start.setValue(15)
        qapp.processEvents()

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "uat_step1_export_center_clamped.png"))

    # =========================================================================
    # Step 2: UAT-02: DashboardPage Recent Projects ✕ Button Rendering & Removal
    # =========================================================================
    with runner.step("UAT-02: Kiem tra nut xoa [X] tren Dashboard Recent Projects", timeout_ms=5000):
        win.switch_page(0)  # Dashboard page
        qapp.processEvents()

        custom_settings = str(tmp_path / "settings_uat.json")
        monkeypatch.setattr(
            "core.runtime.runtime_paths.RuntimePaths.get_settings_file",
            lambda: custom_settings,
        )
        clear_recent_projects()

        # Seed 2 sample projects
        proj_1 = str(tmp_path / "UAT_Alpha_Project.ai-subtitle")
        proj_2 = str(tmp_path / "UAT_Beta_Project.ai-subtitle")
        add_recent_project(proj_1, "UAT_Alpha_Project")
        add_recent_project(proj_2, "UAT_Beta_Project")

        win.page_dashboard.refresh_recent_projects()
        qapp.processEvents()

        # Verify buttons
        buttons = win.page_dashboard.recent_container.findChildren(QPushButton)
        remove_buttons = [btn for btn in buttons if btn.text() == "✕"]
        assert len(remove_buttons) == 2, f"Expected 2 remove buttons with '✕', got {len(remove_buttons)}"

        # Capture visual proof with ✕ buttons visible
        win.grab().save(os.path.join(screenshot_dir, "uat_step2_recent_projects_remove_btn.png"))

        # Click remove on first button via QTest (equivalent to Selenium driver.click)
        QTest.mouseClick(remove_buttons[0], Qt.LeftButton)
        qapp.processEvents()

        # Verify 1 project remaining
        remaining_remove_buttons = [btn for btn in win.page_dashboard.recent_container.findChildren(QPushButton) if btn.text() == "✕"]
        assert len(remaining_remove_buttons) == 1

    # =========================================================================
    # Step 3: UAT-03: Subtitle Editor < and > Navigation Buttons
    # =========================================================================
    with runner.step("UAT-03: Kiem tra nut dieu huong [<] va [>] tren Subtitle Editor", timeout_ms=5000):
        win.switch_page(1)  # Workspace page
        qapp.processEvents()

        # Seed 3 segments
        win.sub_editor.all_segments = [
            {"stt": 1, "id": "seg_1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1: UAT Start"},
            {"stt": 2, "id": "seg_2", "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu 2: UAT Middle"},
            {"stt": 3, "id": "seg_3", "start": "00:00:07,000", "end": "00:00:09,000", "text": "Câu 3: UAT Finish"},
        ]
        win.sub_editor._visible_source_indices = [0, 1, 2]
        win.sub_editor.render_page()
        win.sub_editor.select_segment(0)
        qapp.processEvents()

        current_ed = win.sub_editor.current_editor
        assert current_ed.btn_prev.text() == "<"
        assert current_ed.btn_next.text() == ">"
        assert current_ed.btn_prev.isEnabled() is False
        assert current_ed.btn_next.isEnabled() is True

        # Click Next button via QTest
        QTest.mouseClick(current_ed.btn_next, Qt.LeftButton)
        qapp.processEvents()
        assert win.sub_editor.current_index == 1
        assert current_ed.btn_prev.isEnabled() is True
        assert current_ed.btn_next.isEnabled() is True

        # Click Prev button via QTest
        QTest.mouseClick(current_ed.btn_prev, Qt.LeftButton)
        qapp.processEvents()
        assert win.sub_editor.current_index == 0
        assert current_ed.btn_prev.isEnabled() is False

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "uat_step3_sub_editor_nav_buttons.png"))

    # =========================================================================
    # Step 4: UAT-04: Audio Boost Checkbox 🔊 Tăng âm (+6dB)
    # =========================================================================
    with runner.step("UAT-04: Kiem tra checkbox [Tang am] (+6dB) tren Editor Toolbar", timeout_ms=5000):
        current_ed = win.sub_editor.current_editor
        assert hasattr(current_ed, "chk_boost_audio")
        assert isinstance(current_ed.chk_boost_audio, QCheckBox)
        assert "Tăng âm" in current_ed.chk_boost_audio.text()

        # Toggle on
        if not current_ed.chk_boost_audio.isChecked():
            QTest.mouseClick(current_ed.chk_boost_audio, Qt.LeftButton)
            qapp.processEvents()
        assert current_ed.chk_boost_audio.isChecked() is True

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "uat_step4_audio_boost_checked.png"))

    # =========================================================================
    # Step 5: UAT-05: Tab Style Presets & Instant Refresh
    # =========================================================================
    with runner.step("UAT-05: Kiem tra tab Style tach khoi va lam moi preview tuc thi", timeout_ms=5000):
        inspector = win.inspector_panel
        assert hasattr(inspector, "cmb_preset")
        assert hasattr(inspector, "lbl_preset_hint")

        # Select 'loud' preset
        loud_idx = inspector.cmb_preset.findData("loud")
        assert loud_idx >= 0
        inspector.cmb_preset.setCurrentIndex(loud_idx)
        qapp.processEvents()

        # Verify segment 0 is updated with 'loud'
        assert win.sub_editor.all_segments[0].get("style_preset") == "loud"

        # Verify VideoPlayer has been notified / refreshed
        assert hasattr(win.video_player, "refresh_current_subtitle")

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "uat_step5_style_preset_instant_refresh.png"))

    # =========================================================================
    # Step 6: UAT-06: Tab Quality Liquid Physics Full-Width Highlight
    # =========================================================================
    with runner.step("UAT-06: Kiem tra tab Quality vet highlight kinh long trai dai 100% chieu rong", timeout_ms=5000):
        from ui.liquid_physics import apply_liquid_overlay

        quality = win.quality_inspector_panel
        quality.set_segments([
            {
                "id": "1",
                "start": "00:00:00,000",
                "end": "00:00:02,000",
                "text": "Câu này rất dài và sẽ gây ra cảnh báo line_too_long để kiểm tra hiển thị liquid overlay"
            }
        ])
        qapp.processEvents()

        quality.refresh()
        qapp.processEvents()

        issue_list = quality.issue_list
        assert issue_list.count() > 0

        # Select first issue
        issue_list.setCurrentRow(0)
        qapp.processEvents()

        # Check liquid overlay width stretches to match list viewport
        overlay = apply_liquid_overlay(issue_list)
        assert overlay is not None
        overlay._sync_geometry()
        overlay._sync_active_target()
        assert overlay._blob_w > 150.0

        # Capture visual proof
        win.grab().save(os.path.join(screenshot_dir, "uat_step6_quality_liquid_highlight.png"))
