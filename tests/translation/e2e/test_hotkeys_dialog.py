"""
E2E integration test for Hotkeys Cheatsheet Modal (Bảng tra cứu phím tắt F1).
Verifies:
- btnHotkeys on header opens dialog
- Geometry and padding: 560x560 with topPadding: 16 and bottomPadding: 20
- F1 key toggles dialog open and closed
- Double clicking shortcut hint container in workspace opens dialog
- Escape key closes dialog
"""
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from .app_harness import AppHarness

FIXTURE = Path(__file__).parent / "fixtures" / "regression.srt"


def test_hotkeys_cheatsheet_interactions():
    harness = AppHarness(FIXTURE)
    driver = harness.driver
    try:
        # 1. Nút btnHotkeys trên AppHeader
        btn_hotkeys = driver.find("btnHotkeys")
        assert btn_hotkeys is not None
        dialog = driver.find("hotkeysDialog")
        assert dialog is not None
        assert not dialog.property("visible")

        driver.click("btnHotkeys")
        QTest.qWait(80)
        assert dialog.property("visible") is True
        assert dialog.property("width") == 560.0
        assert dialog.property("height") == 560.0

        scroll = driver.find("cheatsheetScroll")
        assert scroll is not None
        assert scroll.property("topPadding") == 16.0
        assert scroll.property("bottomPadding") == 20.0
        assert scroll.property("leftPadding") == 20.0
        assert scroll.property("rightPadding") == 20.0

        # 2. Đóng bằng phím Escape
        QTest.keyClick(harness.window, Qt.Key_Escape)
        QTest.qWait(80)
        assert not dialog.property("visible")

        # 3. Phím tắt toàn cục F1 (Bật / Tắt)
        QTest.keyClick(harness.window, Qt.Key_F1)
        QTest.qWait(80)
        assert dialog.property("visible") is True

        QTest.keyClick(harness.window, Qt.Key_F1)
        QTest.qWait(80)
        assert not dialog.property("visible")

        # 4. Click đúp vào dòng gợi ý phím tắt ở workspace
        hint_container = driver.find("shortcutHintContainer")
        assert hint_container is not None
        p = hint_container.mapToScene(QPoint(10, 10)).toPoint()
        QTest.mouseDClick(harness.window, Qt.LeftButton, Qt.NoModifier, p)
        QTest.qWait(80)
        assert dialog.property("visible") is True

        dialog.close()
        QTest.qWait(50)
        assert not dialog.property("visible")
    finally:
        harness.close()
