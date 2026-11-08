from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
import pytest


def test_nav_switching_to_ai_agent_tab(qtbot):
    from ui.Gui import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    # 1. Verify page_ai_agent exists on win
    assert hasattr(win, "page_ai_agent"), "MainWindow missing page_ai_agent"

    # 2. Switch to AI Agent Mission Control tab (id: 9)
    win.switch_page(9)
    assert win.stack.currentWidget() == win.page_ai_agent
    assert win.liquid_nav.active_index == win.liquid_nav._get_tab_index_by_id(9)
    assert win.lbl_page_title.text() == "Phòng Điều Hành AI Agent"

    # 3. Check peripheral panels are hidden outside Studio Workspace
    assert win.timeline_dock.isHidden()
    assert win.bottom_frame.isHidden()

    # 4. Check alias _on_nav_tab_changed works
    win.switch_page(0)
    assert win.stack.currentWidget() != win.page_ai_agent
    win._on_nav_tab_changed(9)
    assert win.stack.currentWidget() == win.page_ai_agent
