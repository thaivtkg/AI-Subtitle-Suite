import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QMenu
from core.utils.recent_projects import add_recent_project, get_recent_projects, clear_recent_projects
from ui.pages.dashboard_page import DashboardPage


class TestRecentProjectsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.settings_file = os.path.join(self.test_dir, "settings.json")
        self.patcher = patch("core.runtime.runtime_paths.RuntimePaths.get_settings_file", return_value=self.settings_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        if os.path.exists(self.test_dir):
            os.rmdir(self.test_dir)

    def test_dashboard_recent_projects_empty_state(self):
        """DashboardPage hiển thị nhãn rỗng khi chưa có dự án nào."""
        clear_recent_projects()
        page = DashboardPage()
        page.refresh_recent_projects()

        labels = [lbl.text() for lbl in page.recent_container.findChildren(QLabel)]
        self.assertIn("Chưa có dự án nào gần đây.", labels)

    def test_dashboard_recent_projects_renders_and_emits(self):
        """DashboardPage hiển thị danh sách dự án và phát tín hiệu open_project_requested khi bấm Mở."""
        add_recent_project("D:/Projects/Alpha.ai-subtitle", "Alpha")
        add_recent_project("D:/Projects/Beta.ai-subtitle", "Beta")

        page = DashboardPage()
        page.refresh_recent_projects()

        labels = [lbl.text() for lbl in page.recent_container.findChildren(QLabel)]
        self.assertIn("Beta", labels)
        self.assertIn("Alpha", labels)

        emitted = []
        page.open_project_requested.connect(emitted.append)

        # Tìm nút Mở của hàng đầu tiên (Beta)
        buttons = page.recent_container.findChildren(QPushButton)
        open_buttons = [btn for btn in buttons if btn.text() == "Mở"]
        self.assertEqual(len(open_buttons), 2)
        open_buttons[0].click()

        self.assertEqual(len(emitted), 1)
        self.assertTrue(emitted[0].endswith("Beta.ai-subtitle"))

    def test_topbar_menu_refresh_and_clear(self):
        """Topbar Submenu hiển thị danh sách gần đây và nút Xóa Lịch Sử."""
        from ui.Gui import MainWindow

        win = MainWindow.__new__(MainWindow)
        win.btn_project_menu = QPushButton()
        project_menu = QMenu(win.btn_project_menu)
        win.menu_recent = project_menu.addMenu("🕒  Mở Dự Án Gần Đây")
        win._open_project_by_path = MagicMock()

        clear_recent_projects()
        win._refresh_recent_projects_menu()
        actions = [a.text() for a in win.menu_recent.actions()]
        self.assertEqual(actions, ["(Trống)"])

        # Thêm 2 dự án
        add_recent_project("D:/Projects/One.ai-subtitle", "One")
        add_recent_project("D:/Projects/Two.ai-subtitle", "Two")
        win._refresh_recent_projects_menu()

        actions = [a.text() for a in win.menu_recent.actions()]
        self.assertIn("1.  Two", actions)
        self.assertIn("2.  One", actions)
        self.assertIn("🗑  Xóa Lịch Sử", actions)

        # Kích hoạt action 1. Two
        action_two = next(a for a in win.menu_recent.actions() if "Two" in a.text())
        action_two.trigger()
        win._open_project_by_path.assert_called_once()
        self.assertTrue(win._open_project_by_path.call_args[0][0].endswith("Two.ai-subtitle"))

        # Kích hoạt Xóa Lịch Sử
        action_clear = next(a for a in win.menu_recent.actions() if "Xóa Lịch Sử" in a.text())
        action_clear.trigger()
        self.assertEqual(get_recent_projects(), [])

    def test_open_project_by_path_prunes_missing_directory(self):
        """Mở dự án không tồn tại trên ổ đĩa sẽ tự động xóa khỏi danh sách và báo lỗi."""
        from ui.Gui import MainWindow
        win = MainWindow.__new__(MainWindow)
        win._refresh_recent_projects_menu = MagicMock()
        win.page_dashboard = MagicMock()

        add_recent_project("D:/NonExistent/Missing.ai-subtitle", "Missing")
        self.assertEqual(len(get_recent_projects()), 1)

        with patch("ui.toast.Toast.show_error") as mock_toast:
            result = win._open_project_by_path("D:/NonExistent/Missing.ai-subtitle")
            self.assertFalse(result)
            mock_toast.assert_called_once()

        self.assertEqual(len(get_recent_projects()), 0)

    def test_dashboard_remove_recent_project_button_emits(self):
        """DashboardPage hiển thị nút ✕ và phát tín hiệu remove_recent_requested khi bấm."""
        add_recent_project("D:/Projects/Alpha.ai-subtitle", "Alpha")
        add_recent_project("D:/Projects/Beta.ai-subtitle", "Beta")
        page = DashboardPage()
        page.refresh_recent_projects()
        emitted = []
        page.remove_recent_requested.connect(emitted.append)
        # Tìm nút ✕ của hàng đầu tiên (Beta)
        buttons = page.recent_container.findChildren(QPushButton)
        remove_buttons = [btn for btn in buttons if btn.text() == "✕"]
        self.assertEqual(len(remove_buttons), 2)
        remove_buttons[0].click()
        self.assertEqual(len(emitted), 1)
        self.assertTrue(emitted[0].endswith("Beta.ai-subtitle"))

    def test_main_window_on_remove_recent_project_removes_and_refreshes(self):
        """MainWindow._on_remove_recent_project gỡ bỏ dự án và làm mới UI."""
        from ui.Gui import MainWindow
        win = MainWindow.__new__(MainWindow)
        win._refresh_recent_projects_menu = MagicMock()
        win.page_dashboard = MagicMock()

        add_recent_project("D:/Projects/Alpha.ai-subtitle", "Alpha")
        add_recent_project("D:/Projects/Beta.ai-subtitle", "Beta")
        self.assertEqual(len(get_recent_projects()), 2)

        win._on_remove_recent_project("D:/Projects/Beta.ai-subtitle")
        self.assertEqual(len(get_recent_projects()), 1)
        self.assertEqual(get_recent_projects()[0]["name"], "Alpha")
        win._refresh_recent_projects_menu.assert_called_once()
        win.page_dashboard.refresh_recent_projects.assert_called_once()


if __name__ == "__main__":
    unittest.main()
