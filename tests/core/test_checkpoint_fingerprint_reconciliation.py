# -*- coding: utf-8 -*-
"""
tests/core/test_checkpoint_fingerprint_reconciliation.py
Kiểm thử tự động cho cơ chế Tự Phục Hồi & Đồng Bộ Vân Tay Checkpoint (Checkpoint Fingerprint Reconciliation)
Khắc phục triệt để lỗi "Generation Error: Vân tay video trong Checkpoint không khớp với video gốc."
"""

import json
import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock

from core.project.project import Project, SourceInfo as ProjectSourceInfo
from core.project.source_fingerprint import generate_source_info
from core.artifacts.artifact_store import ArtifactStore
from core.services.project_service import ProjectService
from core.timing.timing_batch_service import TimingBatchService
from core.timing.timing_checkpoint import TimingCheckpoint
from core.subtitle_generation.generation_service import SubtitleGenerationService
from core.subtitle_generation.subtitle_generation_checkpoint import SubtitleGenerationCheckpoint
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest


@pytest.fixture
def temp_project_env():
    root = tempfile.mkdtemp(prefix="test_reconcile_")
    video_dir = os.path.join(root, "videos")
    os.makedirs(video_dir, exist_ok=True)
    video_path = os.path.join(video_dir, "video1.mp4")
    with open(video_path, "wb") as f:
        f.write(b"SAMPLE_VIDEO_DATA_FOR_FINGERPRINT_1" * 100)

    proj_dir = os.path.join(root, "test_proj.ai-subtitle")
    service = ProjectService(ArtifactStore())
    service.create_project(proj_dir, "test_proj", video_path)

    # Tạo timing checkpoint giả lập
    timing_dir = os.path.join(proj_dir, "artifacts", "timing")
    os.makedirs(timing_dir, exist_ok=True)
    tcp_path = os.path.join(timing_dir, "checkpoint.json")
    tcp_data = {
        "project_id": service.current_project.project_id,
        "source_fingerprint": "old_stale_fingerprint_1111",
        "timing_artifact_id": "art_timing_123",
        "timing_revision": 1,
        "batch_size": 5,
        "active_batch": None,
        "model_size": "large-v3",
        "compute_type": "int8",
        "use_vad": True,
        "min_silence_ms": 500,
        "fix_overlap": True,
        "overlap_gap_ms": 50,
        "overlap_ms": 800,
        "max_window_ms": 120000,
        "music_mode": None,
        "language": None,
        "next_segment_index": 6,
        "last_completed_end_ms": 25000,
        "completed_batches": ["b1"],
        "updated_at": "2026-11-01T00:00:00"
    }
    with open(tcp_path, "w", encoding="utf-8") as f:
        json.dump(tcp_data, f)

    # Tạo subtitle generation checkpoint giả lập
    sub_dir = os.path.join(proj_dir, "artifacts", "subtitle_generation")
    os.makedirs(sub_dir, exist_ok=True)
    scp_path = os.path.join(sub_dir, "checkpoint.json")
    scp_data = {
        "project_id": service.current_project.project_id,
        "source_fingerprint": "old_stale_fingerprint_1111",
        "request_id": "req_123",
        "subtitle_artifact_id": "art_sub_123",
        "artifact_revision": 1,
        "completed_batches": ["b1"],
        "request_data": {
            "request_id": "req_123",
            "project_id": service.current_project.project_id,
            "source_fingerprint": "old_stale_fingerprint_1111",
            "video_path": video_path,
            "model_size": "large-v3",
            "compute_type": "int8",
            "language": None,
            "use_vad": False,
            "min_silence_ms": 500,
            "word_timestamps": False,
            "batch_mode": "segments",
            "batch_size_value": 5,
            "overlap_ms": 2000,
            "batch_duration_ms": None,
            "prompt_context": "",
            "range_start_ms": None,
            "range_end_ms": None
        },
        "batches_data": [],
        "active_batch": None,
        "next_start_ms": 25000,
        "detected_language": None,
        "updated_at": "2026-11-01T00:00:00",
        "status": "COMPLETED",
        "artifact_content_hash": "hash_123",
        "timing_segment_cursor": 5,
        "timing_segment_count": 5
    }
    with open(scp_path, "w", encoding="utf-8") as f:
        json.dump(scp_data, f)

    yield {
        "root": root,
        "service": service,
        "proj_dir": proj_dir,
        "video_path": video_path,
        "tcp_path": tcp_path,
        "scp_path": scp_path,
    }

    shutil.rmtree(root, ignore_errors=True)


def test_open_project_auto_reconciles_stale_checkpoints(temp_project_env):
    """Khi mở dự án, các checkpoint có vân tay cũ tự động đồng bộ theo vân tay video hiện tại."""
    proj_dir = temp_project_env["proj_dir"]
    service = ProjectService(ArtifactStore())
    proj = service.open_project(proj_dir)

    expected_fp = proj.source.fingerprint

    # Kiểm tra timing checkpoint đã được tự động đồng bộ
    tcp = service.load_timing_checkpoint()
    assert tcp is not None
    assert tcp.source_fingerprint == expected_fp

    # Kiểm tra subtitle checkpoint đã được tự động đồng bộ
    with open(temp_project_env["scp_path"], "r", encoding="utf-8") as f:
        scp_data = json.load(f)
    assert scp_data["source_fingerprint"] == expected_fp
    assert scp_data["request_data"]["source_fingerprint"] == expected_fp


def test_relink_project_video_reconciles_checkpoints(temp_project_env):
    """Khi người dùng định vị lại video (relink), tất cả checkpoint được cập nhật vân tay mới."""
    root = temp_project_env["root"]
    proj_dir = temp_project_env["proj_dir"]
    service = temp_project_env["service"]

    new_video = os.path.join(root, "videos", "video2_different.mp4")
    with open(new_video, "wb") as f:
        f.write(b"NEW_DIFFERENT_VIDEO_CONTENT_BYTES_99999" * 100)

    updated_source = service.relink_project_video(proj_dir, new_video, force=True)
    new_fp = updated_source.fingerprint

    # Timing checkpoint
    with open(temp_project_env["tcp_path"], "r", encoding="utf-8") as f:
        tcp_data = json.load(f)
    assert tcp_data["source_fingerprint"] == new_fp

    # Subtitle checkpoint
    with open(temp_project_env["scp_path"], "r", encoding="utf-8") as f:
        scp_data = json.load(f)
    assert scp_data["source_fingerprint"] == new_fp
    assert scp_data["request_data"]["source_fingerprint"] == new_fp
    assert scp_data["request_data"]["video_path"] == new_video


def test_timing_service_validate_checkpoint_identity_self_heals(temp_project_env):
    """TimingBatchService tự động khắc phục sai lệch vân tay nếu cùng thuộc project ID."""
    proj_dir = temp_project_env["proj_dir"]
    service = ProjectService(ArtifactStore())
    proj = service.open_project(proj_dir)

    mismatched_cp = TimingCheckpoint(
        project_id=proj.project_id,
        source_fingerprint="some_other_stale_hash",
        timing_artifact_id=proj.state.timing.timing_artifact_id,
        timing_revision=1,
        batch_size=5,
        active_batch=None,
        model_size="large-v3",
        compute_type="int8",
        use_vad=True,
        min_silence_ms=500,
        fix_overlap=True,
        overlap_gap_ms=50,
        overlap_ms=800,
        max_window_ms=120000,
        music_mode=None,
        language=None,
        next_segment_index=1,
        last_completed_end_ms=0,
        completed_batches=[],
        updated_at="2026-11-01T00:00:00",
    )

    tbs = TimingBatchService(service)
    # Không được ném ngoại lệ ValueError("Vân tay video trong Checkpoint không khớp với video gốc.")
    tbs._validate_checkpoint_identity(mismatched_cp)
    assert mismatched_cp.source_fingerprint == proj.source.fingerprint


def test_timing_service_rejects_alien_project_id(temp_project_env):
    """TimingBatchService vẫn ngăn chặn tuyệt đối checkpoint từ dự án khác (project_id không khớp)."""
    proj_dir = temp_project_env["proj_dir"]
    service = ProjectService(ArtifactStore())
    service.open_project(proj_dir)

    alien_cp = TimingCheckpoint(
        project_id="alien-project-uuid-9999",
        source_fingerprint="some_hash",
        timing_artifact_id="art_1",
        timing_revision=1,
        batch_size=5,
        active_batch=None,
        model_size="large-v3",
        compute_type="int8",
        use_vad=True,
        min_silence_ms=500,
        fix_overlap=True,
        overlap_gap_ms=50,
        overlap_ms=800,
        max_window_ms=120000,
        music_mode=None,
        language=None,
        next_segment_index=1,
        last_completed_end_ms=0,
        completed_batches=[],
        updated_at="2026-11-01T00:00:00",
    )

    tbs = TimingBatchService(service)
    with pytest.raises(ValueError, match="Checkpoint không thuộc về Dự án hiện tại"):
        tbs._validate_checkpoint_identity(alien_cp)


def test_jmsz_real_project_no_generation_error():
    """Kiểm tra trực tiếp trên dự án thật D:\\Projects\\JMSZ.ai-subtitle không còn bị lỗi Generation Error."""
    jmsz_dir = r"D:\Projects\JMSZ.ai-subtitle"
    if not os.path.exists(jmsz_dir):
        pytest.skip("Thư mục JMSZ không tồn tại trên máy")

    service = ProjectService(ArtifactStore())
    proj = service.open_project(jmsz_dir)
    assert proj is not None

    tcp = service.load_timing_checkpoint()
    assert tcp is not None
    assert tcp.source_fingerprint == proj.source.fingerprint

    tbs = TimingBatchService(service)
    # Kiểm tra validate identity hoàn toàn mượt mà
    tbs._validate_checkpoint_identity(tcp)
