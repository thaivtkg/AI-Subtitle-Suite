import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import QCoreApplication, QThreadPool

from core.batch.batch_models import BatchJob, BatchSession, BatchStatus
from core.batch.batch_manager import BatchManager, ExportService
from core.export.subtitle_parser import parse_srt_content
from core.services.project_service import ProjectService
from core.artifacts.artifact_store import ArtifactStore
from core.artifacts.artifact import Artifact
from core.artifacts.artifact_types import ArtifactType, ArtifactStatus

if not QCoreApplication.instance():
    app = QCoreApplication(sys.argv)

class TestEightIntegrityFixes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_eight_fixes_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. [P1] Xóa hết phụ đề rồi lưu không cập nhật file
    def test_tc1_empty_subtitles_save_updates_artifact_on_disk(self):
        from ui.Gui import MainWindow
        
        art_path = os.path.join(self.temp_dir, "test_subs.srt")
        with open(art_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nOld Subtitle\n\n")
            
        window = MainWindow.__new__(MainWindow)
        window.sub_editor = MagicMock()
        window.sub_editor.all_segments = []  # Empty list of segments
        window.sub_editor.time_str_to_ms = lambda s: 0

        proj = MagicMock()
        proj.state.active_artifact_id = "art_1"
        proj.state.subtitle_artifact_id = None
        proj.state.timing = None
        proj.state.saved_revision = None

        art = MagicMock()
        art.artifact_id = "art_1"
        art.path = art_path

        store = MagicMock()
        store.get.return_value = art

        window.project_service = MagicMock()
        window.project_service.current_project = proj
        window.project_service.project_dir = self.temp_dir
        window.project_service.artifact_store = store
        window.project_service.save_project.return_value = True
        window.revision_tracker = MagicMock()
        window.revision_tracker.edit_revision = 1
        window.revision_tracker.is_dirty = False
        window.workspace_service = MagicMock()
        window.queue_mgr = MagicMock()
        window.queue_mgr.active_vid = "vid_1"
        window.recovery_manager = MagicMock()
        window._project_owned_artifact_path = lambda p: p
        window._sync_from_ai_agent_page = MagicMock()
        window._active_nav_index = 0
        window._update_window_title_dirty_marker = MagicMock()
        window._emit_debug_event = MagicMock()
        
        success = window._save_current_project(notify_user=False)
        self.assertTrue(success)
        
        # Verify artifact on disk was updated with empty string
        with open(art_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "")

    # 2. [P1] Tạo dự án nhanh từ thư mục thay ngữ cảnh trước khi lưu dự án cũ
    def test_tc2_quick_folder_project_context_isolation(self):
        svc = ProjectService()
        vid_a = os.path.join(self.temp_dir, "video_a.mp4")
        with open(vid_a, "wb") as f: f.write(b"videoA")
        
        # Project A is current
        proj_a, is_created_a = svc.create_or_get_folder_project(vid_a, set_as_current=True)
        self.assertEqual(svc.current_project.project_id, proj_a.project_id)
        
        # Create Project B with set_as_current=False
        vid_b = os.path.join(self.temp_dir, "video_b.mp4")
        with open(vid_b, "wb") as f: f.write(b"videoB")
        proj_b, is_created_b = svc.create_or_get_folder_project(vid_b, set_as_current=False)
        
        # Service must still point to Project A!
        self.assertEqual(svc.current_project.project_id, proj_a.project_id)
        self.assertNotEqual(proj_a.project_id, proj_b.project_id)

    # 3. [P1] Lưu draft thất bại vẫn báo lưu dự án thành công
    def test_tc3_save_draft_failure_aborts_save_project(self):
        from ui.Gui import MainWindow
        
        art_path = os.path.join(self.temp_dir, "test.ai-subtitle-draft")
        window = MainWindow.__new__(MainWindow)
        window.sub_editor = MagicMock()
        window.sub_editor.all_segments = [{"start": 0, "end": 1000, "text": "Hello"}]
        window.sub_editor.time_str_to_ms = lambda s: 0
        window.sub_editor.save_draft.return_value = None  # Draft save fails!

        proj = MagicMock()
        proj.state.active_artifact_id = "art_1"
        proj.state.subtitle_artifact_id = None
        proj.state.timing = None
        proj.state.saved_revision = None

        art = MagicMock()
        art.artifact_id = "art_1"
        art.path = art_path

        store = MagicMock()
        store.get.return_value = art

        window.project_service = MagicMock()
        window.project_service.current_project = proj
        window.project_service.project_dir = self.temp_dir
        window.project_service.artifact_store = store
        window.project_service.save_project = MagicMock()
        window.revision_tracker = MagicMock()
        window.revision_tracker.edit_revision = 1
        window.revision_tracker.is_dirty = True
        window.workspace_service = MagicMock()
        window.queue_mgr = MagicMock()
        window.queue_mgr.active_vid = "vid_1"
        window.recovery_manager = MagicMock()
        window._project_owned_artifact_path = lambda p: p
        window._sync_from_ai_agent_page = MagicMock()
        window._active_nav_index = 0
        window._update_window_title_dirty_marker = MagicMock()
        window._emit_debug_event = MagicMock()

        res = window._save_current_project(notify_user=False)
        self.assertFalse(res)
        window.project_service.save_project.assert_not_called()

    # 4. [P1] Parser SRT nuốt câu tiếp theo khi gặp câu trống
    def test_tc4_srt_parser_empty_first_subtitle_preserves_both(self):
        srt_content = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "\n"
            "2\n"
            "00:00:03,000 --> 00:00:04,500\n"
            "Subtitle Two text content\n"
        )
        segments = parse_srt_content(srt_content)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["stt"], "1")
        self.assertEqual(segments[0]["text"], "")
        self.assertEqual(segments[1]["stt"], "2")
        self.assertEqual(segments[1]["text"], "Subtitle Two text content")

    # 5. [P1] Batch dùng service giả nhưng báo hoàn tất
    def test_tc5_batch_nonexistent_file_fails_with_proper_status(self):
        manager = BatchManager()
        non_existent = os.path.join(self.temp_dir, "ghost_video.mp4")
        job = BatchJob(id="job_ghost", input_file=non_existent)
        session = BatchSession("s_ghost", "tiny", "en", "srt", [job])
        
        manager.start_session(session)
        QThreadPool.globalInstance().waitForDone()
        QCoreApplication.processEvents()
        
        self.assertEqual(job.status, BatchStatus.FAILED)
        self.assertIn("not found", job.error_message.lower())
        self.assertIsNone(job.output_path)

    def test_tc5b_batch_valid_file_generates_verified_output(self):
        vid_path = os.path.join(self.temp_dir, "clip.mp4")
        with open(vid_path, "wb") as f: f.write(b"fake media")
        
        manager = BatchManager()
        job = BatchJob(id="job_real", input_file=vid_path)
        session = BatchSession("s_real", "tiny", "en", "srt", [job])
        
        def fake_whisper_run(input_file, *args, **kwargs):
            art_file = os.path.join(self.temp_dir, "clip_art.srt")
            with open(art_file, "w", encoding="utf-8") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nGenerated line\n\n")
            art = Artifact(
                artifact_id="art_real_1",
                artifact_type=ArtifactType.SUBTITLE,
                path=art_file,
                created_at="2026-01-01T00:00:00",
                updated_at="2026-01-01T00:00:00",
                source_project_id="s_real",
                status=ArtifactStatus.READY
            )
            manager.artifact_store.register(art)
            return "art_real_1"

        with patch("core.batch.batch_manager.FasterWhisperService.run", side_effect=fake_whisper_run):
            manager.start_session(session)
            QThreadPool.globalInstance().waitForDone()
            QCoreApplication.processEvents()
            
        self.assertEqual(job.status, BatchStatus.COMPLETED)
        self.assertIsNotNone(job.output_path)
        self.assertTrue(os.path.exists(job.output_path))
        with open(job.output_path, "r", encoding="utf-8") as f:
            self.assertIn("Generated line", f.read())

    # 6. [P1] Bật dịch batch luôn lỗi khởi tạo dịch vụ
    def test_tc6_batch_translation_init_with_valid_provider_and_prompt_builder(self):
        vid_path = os.path.join(self.temp_dir, "trans_clip.mp4")
        with open(vid_path, "wb") as f: f.write(b"fake media")
        
        manager = BatchManager()
        mock_provider = MagicMock()
        mock_provider.translate.return_value = "1\n00:00:00,000 --> 00:00:01,000\nCâu dịch tiếng Việt\n\n"
        
        job = BatchJob(id="job_trans", input_file=vid_path)
        session = BatchSession(
            session_id="s_trans",
            model_size="tiny",
            target_lang="vi",
            output_format="srt",
            jobs=[job],
            translation_config={
                "enabled": True,
                "provider_instance": mock_provider,
                "target_lang": "Vietnamese"
            }
        )
        
        def fake_whisper_run(input_file, *args, **kwargs):
            art_file = os.path.join(self.temp_dir, "trans_whisper.srt")
            with open(art_file, "w", encoding="utf-8") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nOriginal text\n\n")
            art = Artifact(
                artifact_id="art_w_1",
                artifact_type=ArtifactType.SUBTITLE,
                path=art_file,
                created_at="2026-01-01T00:00:00",
                updated_at="2026-01-01T00:00:00",
                source_project_id="s_trans",
                status=ArtifactStatus.READY
            )
            manager.artifact_store.register(art)
            return "art_w_1"

        with patch("core.batch.batch_manager.FasterWhisperService.run", side_effect=fake_whisper_run):
            manager.start_session(session)
            QThreadPool.globalInstance().waitForDone()
            QCoreApplication.processEvents()
            
        self.assertEqual(job.status, BatchStatus.COMPLETED)
        self.assertTrue(os.path.exists(job.output_path))
        with open(job.output_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Câu dịch tiếng Việt", content)

    # 7. [P2] Hai video khác nhau có thể dùng chung bundle dự án
    def test_tc7_bundle_collision_isolation_different_extensions(self):
        svc = ProjectService()
        vid_mp4 = os.path.join(self.temp_dir, "movie.mp4")
        vid_mkv = os.path.join(self.temp_dir, "movie.mkv")
        with open(vid_mp4, "wb") as f: f.write(b"mp4")
        with open(vid_mkv, "wb") as f: f.write(b"mkv")
        
        # Create project for mp4 so bundle exists on disk
        proj_mp4, _ = svc.create_or_get_folder_project(vid_mp4)
        
        bundle_mp4 = ProjectService.get_canonical_bundle_dir(vid_mp4)
        bundle_mkv = ProjectService.get_canonical_bundle_dir(vid_mkv)
        
        self.assertNotEqual(str(bundle_mp4), str(bundle_mkv))
        self.assertTrue(str(bundle_mp4).endswith("movie.ai-subtitle"))
        self.assertTrue(str(bundle_mkv).endswith("movie_mkv.ai-subtitle"))

    # 8. [P2] CI bỏ qua phần lớn bộ kiểm thử
    def test_tc8_ci_workflow_uses_pytest_and_includes_main_branch(self):
        ci_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".github", "workflows", "ci.yml")
        self.assertTrue(os.path.exists(ci_path))
        with open(ci_path, "r", encoding="utf-8") as f:
            ci_content = f.read()
            
        self.assertIn("pytest tests -v", ci_content)
        self.assertNotIn("unittest discover", ci_content)
        self.assertIn("main", ci_content)

if __name__ == "__main__":
    unittest.main()
