# -*- coding: utf-8 -*-
import json
import os
import shutil
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication, QMessageBox
from core.project.source_fingerprint import generate_source_info
from core.artifacts.artifact_store import ArtifactStore
from core.services.project_service import ProjectService
from ui.Gui import MainWindow
from ui.dialogs.missing_media_dialog import MissingMediaDialog


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture
def sample_project_env():
    root = tempfile.mkdtemp(prefix="test_gui_relink_")
    video_dir = os.path.join(root, "orig_dir")
    os.makedirs(video_dir, exist_ok=True)
    video_path = os.path.join(video_dir, "ep01.mp4")
    with open(video_path, "wb") as f:
        f.write(b"SAMPLE_VIDEO_FOR_GUI_TEST_1234567890_PADDING" * 100)

    proj_dir = os.path.join(root, "my_show.ai-subtitle")
    service = ProjectService(ArtifactStore())
    service.create_project(proj_dir, "ep01.mp4", video_path)

    # Thêm 1 artifact subtitle mẫu (canonical .sub.json và _shadow.srt)
    art_dir = os.path.join(proj_dir, "artifacts", "subtitles")
    os.makedirs(art_dir, exist_ok=True)
    sub_json_file = os.path.join(art_dir, "canonical.sub.json")
    shadow_srt_file = os.path.join(art_dir, "canonical_shadow.srt")

    sub_data = {
        "schema_version": 2,
        "segments": [
            {
                "id": "seg_001",
                "start_ms": 1000,
                "end_ms": 4000,
                "text": "Xin chao",
                "original_text": "Xin chao",
                "stt": 1,
            }
        ]
    }
    with open(sub_json_file, "w", encoding="utf-8") as f:
        json.dump(sub_data, f)
    with open(shadow_srt_file, "w", encoding="utf-8") as f:
        f.write("1\n00:00:01,000 --> 00:00:04,000\nXin chao\n\n")

    from core.artifacts.artifact import Artifact
    from core.artifacts.artifact_types import ArtifactType, ArtifactStatus
    from datetime import datetime

    art_id = "art_test_subtitles"
    now_str = datetime.now().isoformat()
    artifact = Artifact(
        artifact_id=art_id,
        artifact_type=ArtifactType.SUBTITLE,
        path=sub_json_file,
        created_at=now_str,
        updated_at=now_str,
        source_project_id=service.current_project.project_id,
        status=ArtifactStatus.READY,
        revision=1,
        metadata={"generated_count": 1}
    )
    service.artifact_store.register(artifact)
    service.current_project.state.active_artifact_id = art_id
    service.current_project.state.subtitle_artifact_id = art_id
    service.save_project()

    yield {
        "root": root,
        "video_path": video_path,
        "proj_dir": proj_dir,
    }

    shutil.rmtree(root, ignore_errors=True)


def test_open_project_auto_relocate_adjacent(app, sample_project_env):
    root = sample_project_env["root"]
    proj_dir = sample_project_env["proj_dir"]
    orig_vid = sample_project_env["video_path"]

    # Di chuyển video sang thư mục cha cùng cấp với project bundle (root/ep01.mp4)
    adjacent_vid = os.path.join(root, "ep01.mp4")
    shutil.move(orig_vid, adjacent_vid)

    win = MainWindow()
    success = win._open_project_by_path(proj_dir)
    assert success is True

    # Dự án phải tự động nhận đường dẫn mới
    cur = win.project_service.current_project
    assert cur is not None
    assert os.path.normpath(cur.source.path) == os.path.normpath(adjacent_vid)
    assert cur.state.is_video_missing is False


def test_open_project_without_video_mode(app, sample_project_env):
    proj_dir = sample_project_env["proj_dir"]
    orig_vid = sample_project_env["video_path"]

    # Xóa file video gốc
    os.remove(orig_vid)

    win = MainWindow()

    # Giả lập người dùng bấm "Mở Không Cần Video" trên dialog
    def mock_exec(self):
        self.result_action = "OPEN_WITHOUT_VIDEO"
        self.selected_video_path = None
        return 1

    with patch.object(MissingMediaDialog, "exec", mock_exec):
        success = win._open_project_by_path(proj_dir)

    assert success is True
    cur = win.project_service.current_project
    assert cur is not None
    assert cur.state.is_video_missing is True
    # Phụ đề vẫn phải nạp vào editor
    assert len(win.sub_editor.all_segments) > 0


def test_open_project_missing_media_cancel(app, sample_project_env):
    proj_dir = sample_project_env["proj_dir"]
    orig_vid = sample_project_env["video_path"]

    # Xóa file video gốc
    os.remove(orig_vid)

    win = MainWindow()

    def mock_exec(self):
        self.result_action = "CANCEL"
        self.selected_video_path = None
        return 0

    with patch.object(MissingMediaDialog, "exec", mock_exec):
        success = win._open_project_by_path(proj_dir)

    assert success is False


def test_action_relink_video_menu(app, sample_project_env):
    root = sample_project_env["root"]
    proj_dir = sample_project_env["proj_dir"]
    orig_vid = sample_project_env["video_path"]

    # Xóa file video gốc
    os.remove(orig_vid)

    win = MainWindow()

    def mock_exec(self):
        self.result_action = "OPEN_WITHOUT_VIDEO"
        self.selected_video_path = None
        return 1

    with patch.object(MissingMediaDialog, "exec", mock_exec):
        success = win._open_project_by_path(proj_dir)

    assert success is True
    cur = win.project_service.current_project
    assert cur.state.is_video_missing is True

    # Tạo file video mới ở vị trí khác
    new_video = os.path.join(root, "relinked_media.mp4")
    with open(new_video, "wb") as f:
        f.write(b"NEW_VIDEO_CONTENT_1234567890")

    with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(new_video, "Video Files")), \
         patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes):
        win._action_relink_video()

    assert os.path.normpath(cur.source.path) == os.path.normpath(new_video)
    assert cur.state.is_video_missing is False

