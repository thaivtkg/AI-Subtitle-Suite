# -*- coding: utf-8 -*-
"""
End-to-End & Integration Test Suite for AI Subtitle Studio + Translation Studio CAT View
Covers Lead QA Acceptance Criteria:
  AC-SUITE-01: App launch without DLL/import conflict
  AC-SUITE-02: Navigate to Dịch thuật AI tab & verify QML load with subtitle data
  AC-SUITE-03: Translate and accept subtitle segment (state ACCEPTED & TM update)
  AC-SUITE-04: Return to Studio Workspace and verify bidirectional sync to SubEditor & VideoPlayer
  AC-SUITE-05: Unified project save and reload (.aisrt in bundle)
"""
import os
import json
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from ui.Gui import MainWindow
from core.recovery.revision_tracker import RevisionTracker
from core.recovery.recovery_manager import RecoveryManager
from core.recovery.atomic_snapshot_store import AtomicSnapshotStore
from core.recovery.recovery_validator import RecoveryValidator
from core.runtime.runtime_paths import RuntimePaths
from core.subtitle_editing.global_undo_manager import GlobalUndoManager


@pytest.fixture
def studio_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    undo_manager = GlobalUndoManager()
    tracker = RevisionTracker(undo_manager)
    manager = RecoveryManager(
        RuntimePaths.get_recovery_sessions_dir(),
        RuntimePaths.get_recovery_quarantine_dir(),
        tracker,
        AtomicSnapshotStore(),
        RecoveryValidator(),
    )
    win = MainWindow(
        revision_tracker=tracker,
        recovery_manager=manager,
        undo_manager=undo_manager,
    )
    win.show()
    QTest.qWait(100)
    yield win
    win.close()


def test_ac_suite_01_app_launch_and_page_registration(studio_window):
    """AC-SUITE-01: Ứng dụng khởi động mượt mà, đầy đủ TranslationStudioPage trong stack."""
    win = studio_window
    assert hasattr(win, "page_translation")
    assert win.page_translation is not None
    assert win.stack.count() >= 8
    assert win.page_translation.quick_widget is not None
    assert len(win.page_translation.quick_widget.errors()) == 0


def test_ac_suite_02_navigate_to_translation_tab_and_data_feed(studio_window):
    """AC-SUITE-02: Chuyển sang tab Dịch thuật AI, phụ đề từ SubEditor nạp đầy đủ vào QML."""
    win = studio_window
    # Giả lập dữ liệu nhận dạng từ Whisper vào SubEditor
    mock_segments = [
        {"stt": 1, "start": "00:00:01,000", "end": "00:00:04,500", "text": "Good morning everybody.", "translation": ""},
        {"stt": 2, "start": "00:00:05,000", "end": "00:00:08,200", "text": "Welcome to our studio.", "translation": ""},
    ]
    win.sub_editor.all_segments = mock_segments

    # Chuyển sang tab Dịch thuật AI (Nav index 8)
    win.switch_page(8)
    QTest.qWait(250)

    assert win.stack.currentIndex() == 7
    assert win.page_translation.subtitle_model.rowCount() == 2
    item0 = win.page_translation.subtitle_model.get_item(0)
    assert item0["original"] == "Good morning everybody."
    assert item0["status"] == "PENDING"


def test_ac_suite_03_accept_translation_and_tm_update(studio_window):
    """AC-SUITE-03: Thao tác duyệt câu chuyển trạng thái ACCEPTED và cập nhật TM."""
    win = studio_window
    mock_segments = [
        {"stt": 1, "start": "00:00:01,000", "end": "00:00:04,000", "text": "Good morning.", "translation": ""},
    ]
    win.sub_editor.all_segments = mock_segments
    win.switch_page(8)
    QTest.qWait(250)

    # Thực hiện duyệt bản dịch
    success = win.page_translation.translation_controller.acceptTranslation(0, "Chào buổi sáng.")
    assert success is True

    item = win.page_translation.subtitle_model.get_item(0)
    assert item["translation"] == "Chào buổi sáng."
    assert item["status"] == "ACCEPTED"

    # Kiểm tra TM đã ghi nhận
    tm = win.page_translation.project_controller.translation_memory
    assert tm is not None
    entry = tm.get("Good morning.")
    assert entry is not None
    assert entry.target_text == "Chào buổi sáng."


def test_ac_suite_04_bidirectional_sync_to_studio_workspace(studio_window):
    """AC-SUITE-04: Quay lại Workspace, bản dịch lập tức xuất hiện ở SubEditor và Video Player."""
    win = studio_window
    mock_segments = [
        {"stt": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Hello world", "translation": ""},
    ]
    win.sub_editor.all_segments = mock_segments

    # Vào tab dịch thuật và cập nhật bản dịch
    win.switch_page(8)
    QTest.qWait(250)
    win.page_translation.translation_controller.acceptTranslation(0, "Xin chào thế giới")

    # Quay lại Studio Workspace (Nav index 1)
    win.switch_page(1)
    QTest.qWait(250)

    assert win.stack.currentIndex() == 1
    # Kiểm tra SubEditor đã được cập nhật
    assert win.sub_editor.all_segments[0]["translation"] == "Xin chào thế giới"
    assert win.sub_editor.all_segments[0]["translation_status"] == "ACCEPTED"


def test_ac_suite_05_unified_project_save_and_reload(studio_window, tmp_path):
    """AC-SUITE-05: Lưu dự án (.ai-subtitle) và mở lại bảo toàn 100% câu dịch & Glossary."""
    win = studio_window
    project_dir = str(tmp_path / "MyProject.ai-subtitle")
    dummy_vid = str(tmp_path / "dummy.mp4")
    with open(dummy_vid, "wb") as f:
        f.write(b"0" * 1024)

    # Thiết lập dự án hiện tại
    win.project_service.create_project(project_dir, name="MyProject", video_path=dummy_vid)

    # Thêm câu và thuật ngữ
    mock_segments = [
        {"stt": 1, "start": "00:00:01,000", "end": "00:00:03,000", "text": "Neural network", "translation": ""},
    ]
    win.sub_editor.all_segments = mock_segments
    win.switch_page(8)
    QTest.qWait(250)
    win.page_translation.translation_controller.acceptTranslation(0, "Mạng nơ-ron")
    win.page_translation.project_controller.glossary.add("Neural network", "Mạng nơ-ron")

    # Lưu dự án
    saved = win._save_current_project(notify_user=False)
    assert saved is True

    # Kiểm tra tệp project.aisrt được tạo
    aisrt_file = os.path.join(project_dir, "artifacts", "translation", "project.aisrt")
    assert os.path.exists(aisrt_file)
    with open(aisrt_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["subtitles"]) == 1
    assert data["subtitles"][0]["translation"] == "Mạng nơ-ron"
    assert "Neural network" in data["intelligence"]["glossary"]

    # Xóa dữ liệu bộ nhớ để kiểm tra khôi phục
    win.sub_editor.all_segments = []
    win.page_translation.subtitle_model.load_data([])

    # Mở lại dự án
    win._open_project_by_path(project_dir)
    QTest.qWait(250)

    # Xác minh dữ liệu được nạp hoàn chỉnh
    assert len(win.sub_editor.all_segments) == 1
    assert win.sub_editor.all_segments[0]["translation"] == "Mạng nơ-ron"
    assert win.page_translation.subtitle_model.rowCount() == 1
    assert win.page_translation.subtitle_model.get_item(0)["translation"] == "Mạng nơ-ron"
    assert win.page_translation.project_controller.glossary.get("Neural network").preferred_translation == "Mạng nơ-ron"
