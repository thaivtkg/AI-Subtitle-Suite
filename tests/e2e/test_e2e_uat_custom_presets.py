# -*- coding: utf-8 -*-
"""
E2E UAT Automated Driver for Customizable Style Presets & Visual Balance Verification:
Validates commit 31ba2a7 using pytest-qt + QTest + live_studio_app.

Verification Targets:
- UAT-PRESET-01: Visual balance and non-clipped layout of SubtitleInspectorPanel.
- UAT-PRESET-02: PresetConfigDialog proportions, form alignment, and Tab 1 (Loud) defaults.
- UAT-PRESET-03: Tab 2 (Whisper) layout and visual styling.
- UAT-PRESET-04: Independent per-tab Reset to Default functionality.
- UAT-PRESET-05: Real-time UI hint updates and live Video Player preview synchronization upon Save.
"""
import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox

from core.subtitle_quality.style_preset_resolver import DEFAULT_STYLE_PRESETS, StylePresetResolver
from ui.preset_config_dialog import PresetConfigDialog


def test_e2e_uat_custom_presets_visual_balance_and_behavior(live_studio_app, tmp_path, monkeypatch, qapp):
    win, log_watcher, runner = live_studio_app
    screenshot_dir = r"C:\Users\Kuroberus\.gemini\antigravity\brain\15b69ee2-ac46-4cb5-a08d-e12a3cbab0eb"

    # =========================================================================
    # Step 1: UAT-PRESET-01: Inspector Panel Layout & Alignment
    # =========================================================================
    with runner.step("UAT-PRESET-01: Kiem tra can doi bo cuc SubtitleInspectorPanel", timeout_ms=5000):
        win.switch_page(1)  # Workspace
        if hasattr(win, "overlay_host"):
            win.overlay_host.show()
        if hasattr(win, "generation_drawer"):
            win.generation_drawer.show()
        win.dock_tabs.setCurrentWidget(win.inspector_panel)
        qapp.processEvents()

        inspector = win.inspector_panel
        assert hasattr(inspector, "btn_config_presets")
        assert hasattr(inspector, "cmb_preset")
        assert hasattr(inspector, "lbl_preset_hint")

        # Visual balance checks
        btn = inspector.btn_config_presets
        cmb = inspector.cmb_preset
        assert btn.isVisible()
        assert cmb.isVisible()
        assert btn.text() == "⚙️ Cấu hình..."
        # Both controls should be properly sized and vertically aligned
        assert btn.height() >= 24
        assert cmb.height() >= 24
        assert abs(btn.geometry().center().y() - cmb.geometry().center().y()) <= 6

        # Check hint label formatting and wrap
        assert inspector.lbl_preset_hint.wordWrap() is True
        assert "Loud" in inspector.lbl_preset_hint.text()
        assert "Whisper" in inspector.lbl_preset_hint.text()

        # Visual evidence
        win.grab().save(os.path.join(screenshot_dir, "uat_preset_01_inspector_layout.png"))

    # =========================================================================
    # Step 2: UAT-PRESET-02: PresetConfigDialog Dimensions & Tab Loud Layout
    # =========================================================================
    dialog = PresetConfigDialog(parent=win)
    dialog.show()
    qapp.processEvents()

    with runner.step("UAT-PRESET-02: Kiem tra ty le va thong so mac dinh Tab 1 (Loud)", timeout_ms=5000):
        # Dialog visual metrics
        assert dialog.width() >= 420, f"Dialog width {dialog.width()} below minimum 420px"
        assert dialog.tabs.count() == 2
        assert "Loud" in dialog.tabs.tabText(0)
        assert "Whisper" in dialog.tabs.tabText(1)

        # Tab Loud controls layout
        dialog.tabs.setCurrentIndex(0)
        qapp.processEvents()

        loud_ctrl = dialog._controls["loud"]
        spin_scale = loud_ctrl["spin_scale"]
        btn_color = loud_ctrl["btn_color"]
        spin_outline = loud_ctrl["spin_outline"]
        btn_outline_color = loud_ctrl["btn_outline_color"]
        chk_bold = loud_ctrl["chk_bold"]
        chk_italic = loud_ctrl["chk_italic"]
        btn_reset = loud_ctrl["btn_reset"]

        # Default assertions for Loud
        assert spin_scale.value() == 120
        assert spin_scale.suffix() == " %"
        assert btn_color.text() == "#FFE600"
        assert spin_outline.value() == 3.5
        assert spin_outline.suffix() == " px"
        assert btn_outline_color.text() == "#000000"
        assert chk_bold.isChecked() is True
        assert chk_italic.isChecked() is False
        assert "Khôi phục mặc định Loud" in btn_reset.text()

        # Vertical non-overlapping order check
        assert spin_scale.geometry().top() < btn_color.geometry().top()
        assert btn_color.geometry().top() < spin_outline.geometry().top()
        assert spin_outline.geometry().top() < btn_outline_color.geometry().top()
        assert btn_outline_color.geometry().top() < chk_bold.geometry().top()
        assert chk_bold.geometry().top() < btn_reset.geometry().top()

        dialog.grab().save(os.path.join(screenshot_dir, "uat_preset_02_dialog_tab_loud.png"))

    # =========================================================================
    # Step 3: UAT-PRESET-03: Tab Whisper Layout & Alignment
    # =========================================================================
    with runner.step("UAT-PRESET-03: Kiem tra can doi bo cuc va thong so Tab 2 (Whisper)", timeout_ms=5000):
        dialog.tabs.setCurrentIndex(1)
        qapp.processEvents()

        whisper_ctrl = dialog._controls["whisper"]
        spin_scale_w = whisper_ctrl["spin_scale"]
        btn_color_w = whisper_ctrl["btn_color"]
        spin_outline_w = whisper_ctrl["spin_outline"]
        btn_outline_color_w = whisper_ctrl["btn_outline_color"]
        chk_bold_w = whisper_ctrl["chk_bold"]
        chk_italic_w = whisper_ctrl["chk_italic"]
        btn_reset_w = whisper_ctrl["btn_reset"]

        # Default assertions for Whisper
        assert spin_scale_w.value() == 85
        assert btn_color_w.text() == "#D0D0D0"
        assert spin_outline_w.value() == 1.5
        assert btn_outline_color_w.text() == "#000000"
        assert chk_bold_w.isChecked() is False
        assert chk_italic_w.isChecked() is True
        assert "Khôi phục mặc định Whisper" in btn_reset_w.text()

        dialog.grab().save(os.path.join(screenshot_dir, "uat_preset_03_dialog_tab_whisper.png"))

    # =========================================================================
    # Step 4: UAT-PRESET-04: Independent Tab Reset Behavior
    # =========================================================================
    with runner.step("UAT-PRESET-04: Kiem tra tinh doc lap cua nut Khoi phuc mac dinh", timeout_ms=5000):
        # 1. Modify Whisper to custom values
        dialog.tabs.setCurrentIndex(1)
        whisper_ctrl["spin_scale"].setValue(60)
        dialog._update_color_btn("whisper", QColor("#00E5FF"))
        whisper_ctrl["spin_outline"].setValue(2.0)
        dialog._update_outline_color_btn("whisper", QColor("#112233"))
        qapp.processEvents()

        assert whisper_ctrl["spin_scale"].value() == 60
        assert whisper_ctrl["btn_color"].text() == "#00E5FF"
        assert whisper_ctrl["btn_outline_color"].text() == "#112233"

        # 2. Modify Loud to custom values
        dialog.tabs.setCurrentIndex(0)
        loud_ctrl["spin_scale"].setValue(160)
        dialog._update_color_btn("loud", QColor("#FF0055"))
        loud_ctrl["spin_outline"].setValue(5.0)
        dialog._update_outline_color_btn("loud", QColor("#AA0000"))
        qapp.processEvents()

        assert loud_ctrl["spin_scale"].value() == 160
        assert loud_ctrl["btn_color"].text() == "#FF0055"
        assert loud_ctrl["btn_outline_color"].text() == "#AA0000"

        # 3. Click Reset ON TAB LOUD ONLY
        QTest.mouseClick(loud_ctrl["btn_reset"], Qt.LeftButton)
        qapp.processEvents()

        # Verify Tab Loud is restored to defaults
        assert loud_ctrl["spin_scale"].value() == 120
        assert loud_ctrl["btn_color"].text() == "#FFE600"
        assert loud_ctrl["spin_outline"].value() == 3.5
        assert loud_ctrl["btn_outline_color"].text() == "#000000"
        assert loud_ctrl["chk_bold"].isChecked() is True

        # 4. Switch to Tab Whisper -> Verify it is STILL CUSTOMIZED (not reset)
        dialog.tabs.setCurrentIndex(1)
        qapp.processEvents()
        assert whisper_ctrl["spin_scale"].value() == 60, "Whisper scale should NOT be affected by Loud reset"
        assert whisper_ctrl["btn_color"].text() == "#00E5FF", "Whisper color should NOT be affected by Loud reset"
        assert whisper_ctrl["btn_outline_color"].text() == "#112233", "Whisper outline color should NOT be affected by Loud reset"
        assert whisper_ctrl["spin_outline"].value() == 2.0

        dialog.grab().save(os.path.join(screenshot_dir, "uat_preset_04_dialog_independent_reset.png"))

    # =========================================================================
    # Step 5: UAT-PRESET-05: Save, Inspector Hint Sync & Video Preview Refresh
    # =========================================================================
    with runner.step("UAT-PRESET-05: Luu cau hinh, dong bo hint va lam moi video preview", timeout_ms=5000):
        # Set distinct custom values on Loud (+35% / #FF6600 / Outline #330000)
        dialog.tabs.setCurrentIndex(0)
        loud_ctrl["spin_scale"].setValue(135)
        dialog._update_color_btn("loud", QColor("#FF6600"))
        loud_ctrl["spin_outline"].setValue(4.0)
        dialog._update_outline_color_btn("loud", QColor("#330000"))
        qapp.processEvents()

        # Connect dialog signal to MainWindow handler
        dialog.presets_configured.connect(win._on_style_presets_configured)

        # Click "Lưu áp dụng"
        QTest.mouseClick(dialog.btn_save, Qt.LeftButton)
        qapp.processEvents()

        # Verify Project State received custom presets if project loaded
        proj = getattr(win.project_service, "current_project", None)
        if proj and hasattr(proj, "state"):
            assert "loud" in proj.state.style_presets
            assert proj.state.style_presets["loud"]["scale"] == 1.35
            assert proj.state.style_presets["loud"]["font_color"] == "#FF6600"
            assert proj.state.style_presets["loud"]["outline_width"] == 4.0
            assert proj.state.style_presets["loud"]["outline_color"] == "#330000"

        # Verify Inspector Hint was updated dynamically
        hint_text = win.inspector_panel.lbl_preset_hint.text()
        assert "+35%" in hint_text
        assert "#FF6600" in hint_text

        # Verify SubtitleOverlay has updated custom presets
        overlay = win.video_player.subtitle_overlay
        assert hasattr(overlay, "custom_presets")
        assert overlay.custom_presets["loud"]["font_color"] == "#FF6600"
        assert overlay.custom_presets["loud"]["outline_color"] == "#330000"

        from ui.animations.animation_types import SubtitleRenderInput
        overlay.render_input = SubtitleRenderInput(
            segment_id="seg_1", text="Loud Subtitle", start_ms=0, end_ms=2000, style_preset="loud"
        )
        overlay.update()
        qapp.processEvents()

        active_style = overlay.get_active_resolved_style()
        assert active_style["font_color"] == "#FF6600"
        assert active_style["outline_color"] == "#330000"
        assert active_style["outline_width"] == 4.0
        assert active_style["font_size"] == int(round(overlay.font_size * 1.35))

        win.grab().save(os.path.join(screenshot_dir, "uat_preset_05_saved_workspace_preview.png"))

    dialog.close()
    dialog.deleteLater()
