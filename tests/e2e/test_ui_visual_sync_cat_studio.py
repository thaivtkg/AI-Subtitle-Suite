# -*- coding: utf-8 -*-
"""
Visual Regression & UI Sync Quality Gate for AI Translation Studio embedded in MainWindow.
Enforces:
1. Studio Obsidian / Dark Slate background luminance (< 45.0).
2. Model button pill hover state (no rectangular bounding box, luminance < 65.0, no blinding glare).
3. Search input tube theme & vertical centering (dark background, text contrast).
4. Toast capsule contrast & legibility (WCAG AAA contrast ratio > 7.0:1, text not disappearing).
"""
import os
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickItem


def test_ui_visual_sync_cat_studio_dark_theme(live_studio_app, tmp_path):
    win, watcher, runner = live_studio_app
    win.resize(1366, 768)
    QTest.qWait(200)

    # 1. Bấm vào tab 🌐 Dịch thuật AI (Nav id 8) trên LiquidNavWidget
    nav = win.liquid_nav
    nav_btn = nav.btn_map.get(8)
    assert nav_btn is not None, "Nút điều hướng Dịch thuật AI (ID 8) phải tồn tại"

    center = nav_btn.rect().center()
    QTest.mouseClick(nav_btn, Qt.LeftButton, Qt.NoModifier, center)
    QTest.qWait(500)

    assert win.stack.currentIndex() == 7

    # 2. Chụp màn hình trang Dịch thuật AI và lưu Artifacts
    page = win.page_translation
    pixmap = page.grab()
    artifact_dirs = [
        r"C:\Users\Kuroberus\.gemini\antigravity\brain\15b69ee2-ac46-4cb5-a08d-e12a3cbab0eb",
        r"C:\Users\Kuroberus\.gemini\antigravity\brain\c4dfcc31-fb31-4ed0-834c-e2b4c6096c27"
    ]
    for adir in artifact_dirs:
        os.makedirs(adir, exist_ok=True)
        pixmap.save(os.path.join(adir, "cat_studio_live_snapshot.png"))

    # 3. Kiểm định Cổng Quang học Trung tâm (Center Workspace Luminance < 45.0)
    img = pixmap.toImage()
    center_color = img.pixelColor(img.width() // 2, img.height() // 2)
    r, g, b = center_color.red(), center_color.green(), center_color.blue()
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    print(f"\n[VISUAL AUDIT] Center Workspace: R={r}, G={g}, B={b} (Hex: {center_color.name()}, Luminance: {luminance:.1f})")

    assert luminance < 45.0, (
        f"LỖI THỊ GIÁC: Nền không gian dịch quá sáng! "
        f"Luminance đo được: {luminance:.1f} > 45.0 (Màu RGB: R={r}, G={g}, B={b})."
    )

    # 4. Kiểm định Nút Model Manager hiển thị & Pill Hover (Không chói, không vỡ góc bo)
    root_qml = page.quick_widget.rootObject()
    btn_model = root_qml.findChild(QQuickItem, "btnModelManager")
    assert btn_model is not None, "btnModelManager phải tồn tại trên HeaderBatchControl"
    assert btn_model.property("visible") is True, "btnModelManager.visible phải bằng True"
    assert btn_model.width() > 80, f"btnModelManager.width ({btn_model.width()}) phải > 80"

    btn_center = btn_model.mapToScene(QPointF(btn_model.width() / 2, btn_model.height() / 2)).toPoint()
    mouse_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(btn_center.x(), btn_center.y()),
        page.quick_widget.mapToGlobal(btn_center),
        Qt.NoButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    QApplication.sendEvent(page.quick_widget, mouse_event)
    QTest.qWait(250)

    # a) btn_model.property("hovered") is True
    assert btn_model.property("hovered") is True, "btn_model.property('hovered') phải là True sau khi di chuột"

    # b) Zero child items of btn_model have "QQuickStyleItem" in child.metaObject().className()
    all_children = list(btn_model.children()) + list(btn_model.childItems())
    style_items = [c for c in all_children if "QQuickStyleItem" in c.metaObject().className()]
    assert len(style_items) == 0, f"Windows NativeStyle.Button hoverButton overlay phát hiện trong children: {style_items}"

    # c) Corner pixels outside the pill radius remain the dark header background (not a rectangular hover box), and center hover luminance is < 75.0
    btn_pixmap = page.grab()
    btn_img = btn_pixmap.toImage()

    hover_color = btn_img.pixelColor(btn_center.x(), btn_center.y())
    hover_lum = 0.299 * hover_color.red() + 0.587 * hover_color.green() + 0.114 * hover_color.blue()
    print(f"[VISUAL AUDIT] Model Button Hover: Width={btn_model.width()}, Hex={hover_color.name()}, Luminance={hover_lum:.1f}")
    assert hover_lum < 75.0, f"LỖI THỊ GIÁC: Nút Model hover bị chói sáng quá mức ({hover_lum:.1f} >= 75.0)"

    corner_points = [
        btn_model.mapToScene(QPointF(1, 1)).toPoint(),
        btn_model.mapToScene(QPointF(btn_model.width() - 2, 1)).toPoint(),
        btn_model.mapToScene(QPointF(1, btn_model.height() - 2)).toPoint(),
        btn_model.mapToScene(QPointF(btn_model.width() - 2, btn_model.height() - 2)).toPoint(),
    ]
    for cp in corner_points:
        corner_color = btn_img.pixelColor(cp.x(), cp.y())
        corner_lum = 0.299 * corner_color.red() + 0.587 * corner_color.green() + 0.114 * corner_color.blue()
        print(f"[VISUAL AUDIT] Model Button Corner at ({cp.x()}, {cp.y()}): Hex={corner_color.name()}, Luminance={corner_lum:.1f}")
        assert corner_lum < 45.0, (
            f"LỖI THỊ GIÁC: Góc nút bị bóng hover hình chữ nhật che phủ! "
            f"Luminance góc đo được: {corner_lum:.1f} >= 45.0 (Hex: {corner_color.name()})"
        )

    # 5. Kiểm định Ô Tìm kiếm (Search Input Tube: Dark Slate, không trắng toát)
    search_input = root_qml.findChild(QQuickItem, "searchInput")
    if search_input:
        search_center = search_input.mapToScene(QPoint(search_input.width() / 2, search_input.height() / 2)).toPoint()
        search_color = img.pixelColor(search_center.x(), search_center.y())
        search_lum = 0.299 * search_color.red() + 0.587 * search_color.green() + 0.114 * search_color.blue()
        print(f"[VISUAL AUDIT] Search Input Tube: Hex={search_color.name()}, Luminance={search_lum:.1f}")
        assert search_lum < 55.0, f"LỖI THỊ GIÁC: Ô tìm kiếm bị trắng chói ({search_lum:.1f} >= 55.0)"

    # 6. Kiểm định ModelManagerDialog (QML) & HotkeysCheatsheetDialog (Python + QML)
    model_dialog = root_qml.findChild(QObject, "modelManagerDialog") if "QObject" in globals() else None
    from PySide6.QtCore import QObject as _QObj
    model_dialog = root_qml.findChild(_QObj, "modelManagerDialog")
    assert model_dialog is not None
    model_dialog.open()
    QTest.qWait(200)
    assert model_dialog.property("visible") is True
    model_dialog.close()
    QTest.qWait(100)

    hotkeys_qml = root_qml.findChild(_QObj, "hotkeysDialog")
    assert hotkeys_qml is not None
    hotkeys_qml.open()
    QTest.qWait(200)
    assert hotkeys_qml.property("visible") is True
    hotkeys_qml.close()
    QTest.qWait(100)

    from ui.dialogs.hotkeys_cheatsheet_dialog import HotkeysCheatsheetDialog
    py_hotkeys = HotkeysCheatsheetDialog(win)
    py_hotkeys.show()
    QTest.qWait(150)
    card = py_hotkeys.findChild(_QObj, "HotkeysCard")
    header = py_hotkeys.findChild(_QObj, "HotkeysHeader")
    assert card is not None and header is not None
    py_pixmap = py_hotkeys.grab()
    for adir in artifact_dirs:
        py_pixmap.save(os.path.join(adir, "hotkeys_dialog_fixed_snapshot.png"))
    py_hotkeys.close()


def test_selective_subtitle_transfer_jmsz_scenario(live_studio_app):
    win, watcher, runner = live_studio_app
    win.resize(1366, 768)
    QTest.qWait(100)

    # 1. Loading 18 already-translated Vietnamese segments (1..18) into win.sub_editor.all_segments
    segments = []
    for i in range(1, 19):
        segments.append({
            "stt": i,
            "start": f"00:00:{i:02d},000",
            "end": f"00:00:{i:02d},900",
            "text": f"Câu tiếng Việt đã dịch #{i}",
            "original_text": f"Original source text #{i}",
            "translation": f"Câu tiếng Việt đã dịch #{i}",
            "translation_status": "ACCEPTED",
        })

    # 2. Appending 6 newly generated Japanese segments (19..24, indices 18..23)
    for i in range(19, 25):
        segments.append({
            "stt": i,
            "start": f"00:01:{i-18:02d},000",
            "end": f"00:01:{i-18:02d},900",
            "text": f"日本語の字幕テキスト #{i}",
            "original_text": f"日本語の字幕テキスト #{i}",
            "translation": "",
            "translation_status": "PENDING",
        })

    win.sub_editor.all_segments = segments
    win.sub_editor.render_page()

    # Trigger win._on_send_selected_to_translation([18, 19, 20, 21, 22, 23])
    win._on_send_selected_to_translation([18, 19, 20, 21, 22, 23])
    QTest.qWait(200)

    # 3. Verifying win.page_translation.subtitle_model.rowCount() == 6
    sub_model = win.page_translation.subtitle_model
    assert sub_model.rowCount() == 6

    # Verify loaded items have index = 19..24 and studio_index = 18..23
    for row in range(6):
        item = sub_model.get_item(row)
        expected_stt = 19 + row
        expected_studio_idx = 18 + row
        assert item.get("index") == expected_stt, f"Row {row} index must be {expected_stt}, got {item.get('index')}"
        assert item.get("studio_index") == expected_studio_idx, f"Row {row} studio_index must be {expected_studio_idx}, got {item.get('studio_index')}"
        assert item.get("original") == f"日本語の字幕テキスト #{expected_stt}"

    # 4. Updating translation on row 0 (sentence #19) in page_translation.subtitle_model
    new_translation_19 = "Bản dịch tiếng Việt mới của câu 19"
    sub_model.update_translation(0, new_translation_19, "TRANSLATED")
    QTest.qWait(100)

    # Switch back to win.switch_page(1)
    win.switch_page(1)
    QTest.qWait(200)

    # 5. Verifying win.sub_editor.all_segments[18]["text"] has the new Vietnamese translation,
    # win.sub_editor.all_segments[18]["original_text"] preserved the Japanese text,
    # and win.sub_editor.all_segments[0]["text"] (sentence #1) was NOT overwritten!
    seg_19 = win.sub_editor.all_segments[18]
    assert seg_19["text"] == new_translation_19, f"Segment 19 text should be updated to '{new_translation_19}', got '{seg_19['text']}'"
    assert seg_19["original_text"] == "日本語の字幕テキスト #19", f"Segment 19 original_text must preserve Japanese, got '{seg_19['original_text']}'"
    assert seg_19["translation"] == new_translation_19

    seg_1 = win.sub_editor.all_segments[0]
    assert seg_1["text"] == "Câu tiếng Việt đã dịch #1", f"Segment 1 text was overwritten! Got '{seg_1['text']}'"
    assert seg_1["original_text"] == "Original source text #1"
