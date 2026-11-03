import os
import tempfile
import unittest
from pathlib import Path

from core.services.project_service import ProjectService


class TestFolderProjectScanner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.service = ProjectService()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_dummy_file(self, filename: str, size_bytes: int = 1024) -> Path:
        p = self.root / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"0" * size_bytes)
        return p

    def test_scan_video_folder_filters_and_metadata(self):
        """Quét thư mục chứa hỗn hợp file video, text và thư mục con; chỉ nhận diện đúng các file video hợp lệ."""
        self._create_dummy_file("alpha.mp4", 1024 * 1024)  # 1MB
        self._create_dummy_file("beta.mkv", 2 * 1024 * 1024)  # 2MB
        self._create_dummy_file("gamma.avi", 512 * 1024)
        self._create_dummy_file("notes.txt", 100)  # text file -> skip
        self._create_dummy_file(".hidden.mp4", 1024)  # hidden -> skip
        (self.root / "subfolder").mkdir()  # directory -> skip

        results = self.service.scan_video_folder(str(self.root))

        self.assertEqual(len(results), 3)
        filenames = [r["filename"] for r in results]
        self.assertEqual(filenames, ["alpha.mp4", "beta.mkv", "gamma.avi"])

        first = results[0]
        self.assertEqual(first["filename"], "alpha.mp4")
        self.assertAlmostEqual(first["size_mb"], 1.0, places=1)
        self.assertFalse(first["has_project"])
        self.assertTrue(first["expected_project_dir"].endswith("alpha.ai-subtitle"))
        self.assertTrue(os.path.isabs(first["video_path"]))

    def test_scan_video_folder_detects_existing_project(self):
        """Nhận diện chính xác has_project=True khi bundle {tên}.ai-subtitle đã tồn tại kề bên video."""
        vid = self._create_dummy_file("movie.mp4", 1024)
        # Ban đầu chưa có project
        results = self.service.scan_video_folder(str(self.root))
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["has_project"])

        # Tạo project bằng service
        self.service.create_project(results[0]["expected_project_dir"], "movie", str(vid))

        # Quét lại -> has_project phải là True
        results_after = self.service.scan_video_folder(str(self.root))
        self.assertEqual(len(results_after), 1)
        self.assertTrue(results_after[0]["has_project"])

    def test_create_or_get_folder_project_creates_new(self):
        """Tạo mới bundle dự án khi chưa tồn tại (created=True)."""
        vid = self._create_dummy_file("clip.mp4", 1024)
        project, created = self.service.create_or_get_folder_project(str(vid))

        self.assertTrue(created)
        self.assertIsNotNone(project)
        self.assertEqual(project.name, "clip")
        expected_dir = os.path.join(str(self.root), "clip.ai-subtitle")
        self.assertTrue(os.path.exists(os.path.join(expected_dir, "project.json")))

    def test_create_or_get_folder_project_opens_existing_without_overwrite(self):
        """Mở lại dự án cũ nếu đã tồn tại, đảm bảo không ghi đè mất dữ liệu (created=False)."""
        vid = self._create_dummy_file("series_ep1.mp4", 1024)
        expected_dir = os.path.join(str(self.root), "series_ep1.ai-subtitle")

        # 1. Tạo và sửa đổi trạng thái
        proj1 = self.service.create_project(expected_dir, "series_ep1", str(vid))
        proj1.state.text_status = "COMPLETED_TRANSLATION"
        self.service.save_project()

        # 2. Khởi tạo service mới và gọi create_or_get_folder_project
        fresh_service = ProjectService()
        proj2, created = fresh_service.create_or_get_folder_project(str(vid))

        self.assertFalse(created)
        self.assertEqual(proj2.project_id, proj1.project_id)
        self.assertEqual(proj2.state.text_status, "COMPLETED_TRANSLATION")

    def test_scan_nonexistent_or_empty_folder(self):
        """Quét thư mục trống hoặc đường dẫn không tồn tại trả về danh sách rỗng an toàn."""
        self.assertEqual(self.service.scan_video_folder(str(self.root)), [])
        self.assertEqual(self.service.scan_video_folder(str(self.root / "nonexistent")), [])
        self.assertEqual(self.service.scan_video_folder(""), [])


if __name__ == "__main__":
    unittest.main()
