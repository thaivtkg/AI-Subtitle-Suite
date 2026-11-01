import os
import tempfile
import unittest
from unittest.mock import patch

from core.utils.recent_projects import (
    get_recent_projects,
    add_recent_project,
    remove_recent_project,
    clear_recent_projects,
    MAX_RECENT_PROJECTS,
)


class TestRecentProjects(unittest.TestCase):
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

    def test_tc_recent_01_mru_ordering_and_deduplication(self):
        """TC-RECENT-01: Mở A, B, C -> C, B, A. Mở lại A -> A, C, B. Không trùng lặp."""
        self.assertEqual(get_recent_projects(), [])

        add_recent_project("D:/Projects/ProjectA", "Project A")
        add_recent_project("D:/Projects/ProjectB", "Project B")
        add_recent_project("D:/Projects/ProjectC", "Project C")

        recent = get_recent_projects()
        self.assertEqual(len(recent), 3)
        self.assertEqual([p["name"] for p in recent], ["Project C", "Project B", "Project A"])

        # Mở lại A: nhảy lên đầu
        add_recent_project("D:/Projects/ProjectA", "Project A")
        recent = get_recent_projects()
        self.assertEqual(len(recent), 3)
        self.assertEqual([p["name"] for p in recent], ["Project A", "Project C", "Project B"])

    def test_tc_recent_02_max_limit_capping(self):
        """Danh sách giới hạn tối đa 10 dự án (cắt bỏ cũ nhất)."""
        for i in range(15):
            add_recent_project(f"D:/Projects/Proj_{i}", f"Proj {i}")

        recent = get_recent_projects()
        self.assertEqual(len(recent), MAX_RECENT_PROJECTS)
        self.assertEqual(recent[0]["name"], "Proj 14")
        self.assertEqual(recent[-1]["name"], "Proj 5")

    def test_tc_recent_03_remove_and_clear(self):
        """Xóa một phần tử theo path và xóa sạch lịch sử."""
        add_recent_project("D:/Projects/ProjectA", "Project A")
        add_recent_project("D:/Projects/ProjectB", "Project B")

        # Xóa ProjectA
        remove_recent_project("D:/Projects/ProjectA")
        recent = get_recent_projects()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["name"], "Project B")

        # Xóa sạch
        clear_recent_projects()
        self.assertEqual(get_recent_projects(), [])

    def test_tc_recent_04_filters_invalid_entries(self):
        """Lọc bỏ các bản ghi hỏng/thiếu trường."""
        from core.utils.settings_utils import save_settings
        save_settings({
            "recent_projects": [
                {"name": "Valid", "path": "D:/Projects/Valid"},
                {"name": "NoPath"},
                "invalid_string",
                {"path": "D:/Projects/NoName"},  # Thiếu name
            ]
        })
        recent = get_recent_projects()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["name"], "Valid")


if __name__ == "__main__":
    unittest.main()
