# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import pytest

from core.artifacts.artifact_store import ArtifactStore
from core.project.source_fingerprint import generate_source_info
from core.services.project_service import ProjectService, MissingVideoError


@pytest.fixture
def temp_env():
    root = tempfile.mkdtemp(prefix="test_recovery_")
    video_dir = os.path.join(root, "videos")
    os.makedirs(video_dir, exist_ok=True)
    video_path = os.path.join(video_dir, "ep01.mp4")
    with open(video_path, "wb") as f:
        f.write(b"ORIGINAL_VIDEO_CONTENT_1234567890_PADDING" * 100)

    proj_dir = os.path.join(root, "my_project.ai-subtitle")
    service = ProjectService(ArtifactStore())
    service.create_project(proj_dir, "ep01.mp4", video_path)

    yield {
        "root": root,
        "video_dir": video_dir,
        "video_path": video_path,
        "proj_dir": proj_dir,
        "service": service,
    }

    shutil.rmtree(root, ignore_errors=True)


def test_probe_project_source_valid(temp_env):
    service = temp_env["service"]
    proj_dir = temp_env["proj_dir"]
    video_path = temp_env["video_path"]

    source_info, current_path, is_valid, suggested = service.probe_project_source(proj_dir)
    assert is_valid is True
    assert current_path == video_path
    assert suggested is None
    assert source_info.filename == "ep01.mp4"


def test_probe_project_source_missing_with_adjacent_candidate(temp_env):
    service = temp_env["service"]
    proj_dir = temp_env["proj_dir"]
    video_path = temp_env["video_path"]
    root = temp_env["root"]

    # Di chuyển video sang thư mục cha cùng cấp với project bundle (root/ep01.mp4)
    new_adjacent_path = os.path.join(root, "ep01.mp4")
    shutil.move(video_path, new_adjacent_path)

    source_info, current_path, is_valid, suggested = service.probe_project_source(proj_dir)
    assert is_valid is False
    assert current_path == video_path  # đường dẫn cũ
    assert suggested == new_adjacent_path  # tự động tìm thấy ứng viên liền kề!


def test_open_project_raises_missing_video_error(temp_env):
    service = temp_env["service"]
    proj_dir = temp_env["proj_dir"]
    video_path = temp_env["video_path"]

    # Xóa video
    os.remove(video_path)

    with pytest.raises(MissingVideoError) as exc_info:
        service.open_project(proj_dir, allow_missing_video=False)

    err = exc_info.value
    assert err.video_path == video_path
    assert err.project_dir == proj_dir
    assert isinstance(err, FileNotFoundError)


def test_open_project_allow_missing_video(temp_env):
    service = temp_env["service"]
    proj_dir = temp_env["proj_dir"]
    video_path = temp_env["video_path"]

    # Xóa video
    os.remove(video_path)

    project = service.open_project(proj_dir, allow_missing_video=True)
    assert project is not None
    assert project.state.is_video_missing is True
    assert project.source.path == video_path


def test_relink_project_video_matching_hash(temp_env):
    service = temp_env["service"]
    proj_dir = temp_env["proj_dir"]
    video_path = temp_env["video_path"]
    root = temp_env["root"]

    # Di chuyển video sang thư mục mới
    new_dir = os.path.join(root, "moved_videos")
    os.makedirs(new_dir, exist_ok=True)
    new_path = os.path.join(new_dir, "ep01_renamed.mp4")
    shutil.move(video_path, new_path)

    # Relink với file mới (cùng nội dung -> cùng hash)
    updated_source = service.relink_project_video(proj_dir, new_path)
    assert updated_source.path == new_path

    # Mở lại project bình thường
    project = service.open_project(proj_dir)
    assert project.source.path == new_path
    assert project.state.is_video_missing is False


def test_relink_project_video_mismatching_hash_requires_force(temp_env):
    service = temp_env["service"]
    proj_dir = temp_env["proj_dir"]
    root = temp_env["root"]

    # Tạo một video khác hoàn toàn
    different_video = os.path.join(root, "different.mp4")
    with open(different_video, "wb") as f:
        f.write(b"COMPLETELY_DIFFERENT_CONTENT_456")

    # Không force -> ValueError
    with pytest.raises(ValueError) as exc_info:
        service.relink_project_video(proj_dir, different_video, force=False)
    assert "Sai lệch" in str(exc_info.value) or "khác" in str(exc_info.value)

    # Có force -> Thành công
    updated = service.relink_project_video(proj_dir, different_video, force=True)
    assert updated.path == different_video

    project = service.open_project(proj_dir)
    assert project.source.path == different_video
