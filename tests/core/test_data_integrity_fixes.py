# -*- coding: utf-8 -*-
"""
Kiểm thử tự động xác minh khôi phục dữ liệu cho Phase 1:
- BUG-DATA-001 (Critical): Khôi phục phụ đề từ subtitle_artifact_id khi mở lại dự án.
- BUG-DATA-002 (High): Bảo toàn danh sách câu khi chuyển đổi giữa Auto-detected SRT và External SRT.
"""
import os
import json
import uuid
import pytest
from unittest.mock import MagicMock, patch

from core.project.project import Project, SourceInfo
from core.project.project_state import ProjectState
from core.artifacts.artifact import Artifact
from core.artifacts.artifact_types import ArtifactType, ArtifactStatus
from core.services.project_service import ProjectService
from core.services.workspace_service import WorkspaceService
from core.subtitle_generation.subtitle_artifact_service import SubtitleArtifactService


def test_bug_data_001_restore_workspace_with_subtitle_artifact_fallback(tmp_path):
    # Tạo môi trường dự án mẫu
    proj_dir = str(tmp_path / "test_proj.ai-subtitle")
    os.makedirs(os.path.join(proj_dir, "artifacts", "subtitle"), exist_ok=True)
    
    art_id = str(uuid.uuid4())
    sub_path = os.path.join(proj_dir, "artifacts", "subtitle", f"{art_id}.sub.json")
    test_data = {
        "version": 1,
        "segments": [
            {"stt": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu 1"},
            {"stt": 2, "start": "00:00:03,500", "end": "00:00:05,000", "text": "Câu 2"},
        ]
    }
    with open(sub_path, "w", encoding="utf-8") as f:
        json.dump(test_data, f)

    fake_video = str(tmp_path / "video.mp4")
    with open(fake_video, "w") as f:
        f.write("fake video")

    # Giả lập project state: active_artifact_id = None, nhưng subtitle_artifact_id có giá trị (tình huống sau Whisper ASR)
    state = ProjectState()
    state.active_artifact_id = None
    state.subtitle_artifact_id = art_id

    project = Project(
        project_id=str(uuid.uuid4()),
        name="Test Proj",
        created_at="2026-11-07T00:00:00",
        updated_at="2026-11-07T00:00:00",
        source=SourceInfo(path=fake_video, filename="video.mp4", size_bytes=100, modified_at=0.0, fingerprint="fp"),
        state=state
    )

    proj_service = MagicMock()
    proj_service.current_project = project
    proj_service.project_dir = proj_dir
    
    artifact = Artifact(
        artifact_id=art_id,
        artifact_type=ArtifactType.SUBTITLE,
        path=sub_path,
        created_at="2026-11-07T00:00:00",
        updated_at="2026-11-07T00:00:00",
        source_project_id=project.project_id,
        status=ArtifactStatus.READY,
        revision=1
    )
    proj_service.artifact_store.get.return_value = artifact

    ui = MagicMock()
    ui.queue_mgr.get_items.return_value = {}
    ui.queue_mgr.ensure_project_binding.return_value = fake_video
    ws_service = WorkspaceService(ui, proj_service)

    # Thực hiện restore workspace
    ws_service.restore_workspace()

    # Xác minh UI đã được gọi để nạp phụ đề từ subtitle_artifact_id thay vì bị bỏ qua
    ui.queue_mgr.set_srt_for_video.assert_called_once_with(fake_video, os.path.normpath(sub_path))
    ui._load_context_subtitles.assert_called_once_with(os.path.normpath(sub_path))


def test_bug_data_001_subtitle_artifact_service_sets_active_artifact_id(tmp_path):
    proj_dir = str(tmp_path / "test_proj.ai-subtitle")
    os.makedirs(os.path.join(proj_dir, "artifacts", "subtitle"), exist_ok=True)
    
    state = ProjectState()
    project = Project(
        project_id=str(uuid.uuid4()),
        name="Test Proj",
        created_at="2026-11-07T00:00:00",
        updated_at="2026-11-07T00:00:00",
        source=SourceInfo(path="test.mp4", filename="test.mp4", size_bytes=100, modified_at=0.0, fingerprint="fp"),
        state=state
    )

    proj_service = MagicMock()
    proj_service.current_project = project
    proj_service.project_dir = proj_dir
    proj_service.artifact_store.get.return_value = None

    service = SubtitleArtifactService(proj_service)
    art = service.get_or_create_artifact()

    assert art is not None
    assert project.state.subtitle_artifact_id == art.artifact_id
    # Xác minh active_artifact_id được gán đồng bộ
    assert project.state.active_artifact_id == art.artifact_id


def test_project_state_serialization_persists_subtitle_source_segments(tmp_path):
    proj_dir = str(tmp_path / "serialize_proj.ai-subtitle")
    os.makedirs(proj_dir, exist_ok=True)
    
    state = ProjectState()
    state.active_subtitle_source_id = "ext_123"
    state.subtitle_sources = [{"id": "ext_123", "name": "custom.srt"}]
    state.subtitle_source_segments = {
        "default": [{"stt": 1, "text": "Câu gốc ASR"}],
        "ext_123": [{"stt": 1, "text": "Câu dịch SRT"}]
    }

    # 1. Kiểm tra serialize
    serialized = ProjectService.serialize_project_state(state)
    assert serialized["active_subtitle_source_id"] == "ext_123"
    assert serialized["subtitle_sources"] == [{"id": "ext_123", "name": "custom.srt"}]
    assert serialized["subtitle_source_segments"]["default"][0]["text"] == "Câu gốc ASR"
    assert serialized["subtitle_source_segments"]["ext_123"][0]["text"] == "Câu dịch SRT"


def test_bug_data_002_multi_source_srt_switching_preserves_segments(qapp, tmp_path):
    from ui.subtitle_generation_panel import SubtitleGenerationPanel
    
    gen_service = MagicMock()
    panel = SubtitleGenerationPanel(gen_service)

    proj_dir = str(tmp_path / "source_test_proj.ai-subtitle")
    os.makedirs(os.path.join(proj_dir, "artifacts", "subtitle"), exist_ok=True)
    
    state = ProjectState()
    project = Project(
        project_id=str(uuid.uuid4()),
        name="Test Multi Source",
        created_at="2026-11-07T00:00:00",
        updated_at="2026-11-07T00:00:00",
        source=SourceInfo(path="test.mp4", filename="test.mp4", size_bytes=100, modified_at=0.0, fingerprint="fp"),
        state=state
    )
    gen_service.project_service.current_project = project

    # Giả lập MainWindow có sub_editor chứa 5 câu gốc ASR
    mock_win = MagicMock()
    mock_editor = MagicMock()
    default_segments = [
        {"stt": i, "start": f"00:00:0{i},000", "end": f"00:00:0{i+1},000", "text": f"ASR Câu {i}"}
        for i in range(1, 6)
    ]
    mock_editor.all_segments = list(default_segments)
    mock_win.sub_editor = mock_editor
    panel.window = lambda: mock_win

    # Tạo file SRT ngoài với 2 câu
    ext_srt_path = str(tmp_path / "external.srt")
    with open(ext_srt_path, "w", encoding="utf-8") as f:
        f.write("1\n00:00:01,000 --> 00:00:02,000\nExternal Line 1\n\n2\n00:00:02,500 --> 00:00:04,000\nExternal Line 2\n")

    # Giả lập người dùng bấm thêm file External SRT
    with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(ext_srt_path, "srt")):
        panel._on_add_external_srt()

    # Xác minh:
    # 1. Nguồn default đã được lưu snapshot gồm 5 câu
    assert "default" in project.state.subtitle_source_segments
    assert len(project.state.subtitle_source_segments["default"]) == 5
    # 2. Nguồn mới đã active và editor nhận 2 câu
    ext_id = project.state.active_subtitle_source_id
    assert ext_id != "default"
    assert len(project.state.subtitle_source_segments[ext_id]) == 2

    # Bây giờ người dùng chuyển combobox về lại "Auto-detected SRT" (default)
    panel.cmb_subtitle_source.addItem("Auto-detected SRT", "default")
    panel.cmb_subtitle_source.addItem("External SRT", ext_id)
    panel._on_subtitle_source_changed(0) # chọn index 0: default

    # Xác minh sau khi chuyển về default:
    # Không bị xóa trắng (0 câu), mà được phục hồi đúng 5 câu ASR gốc!
    replaced_segments = mock_editor.all_segments
    # _replace_editor_segments clears and extends all_segments
    assert len(mock_editor.all_segments) == 5
    assert mock_editor.all_segments[0]["text"] == "ASR Câu 1"
    assert mock_editor.all_segments[4]["text"] == "ASR Câu 5"
