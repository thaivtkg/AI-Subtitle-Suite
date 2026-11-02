import os
import json
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from core.translation.models.subtitle import SubtitleModel
from core.translation.controllers.project_controller import ProjectController
from core.translation.controllers.translation_controller import TranslationController
from ui.pages.translation_studio_page import TranslationStudioPage


@pytest.fixture
def app():
    instance = QCoreApplication.instance()
    if not instance:
        instance = QCoreApplication([])
    return instance


def test_ac_filter_01_load_project_filters_accepted_subtitles(app, tmp_path):
    """
    AC-FILTER-01 (Load Sanitization):
    Khi gọi loadProject() với file .aisrt chứa các câu hỗn hợp (ACCEPTED, TRANSLATED, PENDING),
    SubtitleModel chỉ chứa các câu chưa duyệt. Tuyệt đối không có câu ACCEPTED nào xuất hiện trong danh sách.
    """
    model = SubtitleModel()
    controller = ProjectController(model)

    project_data = {
        "metadata": {
            "source_file": "sample.srt",
            "source_language": "Japanese",
            "target_language": "Vietnamese",
            "version": "1.0",
        },
        "story_summary": "Test Summary",
        "subtitles": [
            {"index": 1, "original": "Câu 1", "translation": "Bản dịch 1", "status": "ACCEPTED"},
            {"index": 2, "original": "Câu 2", "translation": "Bản dịch 2", "status": "TRANSLATED"},
            {"index": 3, "original": "Câu 3", "translation": "", "status": "PENDING"},
            {"index": 4, "original": "Câu 4", "translation": "Bản dịch 4", "status": "ACCEPTED"},
        ],
        "intelligence": {},
    }

    file_path = tmp_path / "mixed_project.aisrt"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(project_data, f, ensure_ascii=False)

    controller.loadProject(str(file_path))

    # Chỉ có 2 câu chưa duyệt (Câu 2 và Câu 3) được nạp vào SubtitleModel
    loaded = model.get_all_data()
    assert len(loaded) == 2
    assert loaded[0]["index"] == 2
    assert loaded[0]["status"] == "TRANSLATED"
    assert loaded[1]["index"] == 3
    assert loaded[1]["status"] == "PENDING"
    assert all(item["status"] != "ACCEPTED" for item in loaded)


def test_ac_filter_02_empty_workspace_when_all_accepted(app, tmp_path):
    """
    AC-FILTER-02 (Empty Workspace on All Accepted):
    Khi mở file .aisrt mà toàn bộ câu đều đã ACCEPTED (như project JMSZ),
    SubtitleModel rỗng (0 câu) và TranslationStudioPage gọi loadSubtitle(-1).
    """
    page = TranslationStudioPage()
    project_data = {
        "metadata": {"source_language": "Japanese", "target_language": "Vietnamese"},
        "story_summary": "",
        "subtitles": [
            {"index": 19, "original": "俺に忠誠を誓うというか", "translation": "Phải trung thành với tôi", "status": "ACCEPTED"}
        ],
        "intelligence": {},
    }

    file_path = tmp_path / "all_accepted.aisrt"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(project_data, f, ensure_ascii=False)

    page.load_translation_project(str(file_path))

    assert page.subtitle_model.rowCount() == 0
    # Khi 0 câu, currentIndex phải là -1 (hiển thị EmptyWorkspace.qml)
    assert page.translation_controller.currentSubtitleIndex == -1


def test_ac_filter_03_save_project_sanitizes_accepted(app, tmp_path):
    """
    AC-FILTER-03 (Save Sanitization):
    Khi lưu file dự án, các câu mang trạng thái ACCEPTED (nếu có lọt vào)
    sẽ bị lọc bỏ hoàn toàn khỏi trường 'subtitles' của file .aisrt.
    """
    model = SubtitleModel()
    controller = ProjectController(model)

    model.load_data([
        {"index": 1, "original": "Hello", "translation": "Xin chào", "status": "ACCEPTED"},
        {"index": 2, "original": "World", "translation": "", "status": "PENDING"},
    ])

    save_path = tmp_path / "saved_project.aisrt"
    controller.saveProject(str(save_path), "Summary", "English", "Vietnamese", notify=False)

    with open(save_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    saved_subs = data.get("subtitles", [])
    assert len(saved_subs) == 1
    assert saved_subs[0]["index"] == 2
    assert saved_subs[0]["status"] == "PENDING"


def test_ac_filter_04_selective_timeline_import_skips_accepted(app):
    """
    AC-FILTER-04 (Selective Timeline Import):
    Khi bấm 'Nạp phụ đề từ Timeline' (selected_indices=None),
    chỉ các câu chưa duyệt được nạp vào CAT Studio.
    """
    page = TranslationStudioPage()

    studio_segments = [
        {"id": "seg_1", "stt": 1, "start": 0, "end": 1000, "text": "Đã duyệt 1", "translation": "Đã duyệt 1", "translation_status": "ACCEPTED"},
        {"id": "seg_2", "stt": 2, "start": 1000, "end": 2000, "text": "Chờ dịch 2", "translation": "", "translation_status": "PENDING"},
        {"id": "seg_3", "stt": 3, "start": 2000, "end": 3000, "text": "Đã duyệt 3", "translation": "Đã duyệt 3", "translation_status": "ACCEPTED"},
        {"id": "seg_4", "stt": 4, "start": 3000, "end": 4000, "text": "Nháp 4", "translation": "Nháp", "translation_status": "TRANSLATED"},
    ]

    # Nạp toàn bộ từ timeline (selected_indices = None)
    page.load_subtitles_from_studio(studio_segments, selected_indices=None)

    loaded = page.subtitle_model.get_all_data()
    assert len(loaded) == 2
    assert loaded[0]["segment_id"] == "seg_2"
    assert loaded[0]["status"] == "PENDING"
    assert loaded[1]["segment_id"] == "seg_4"
    assert loaded[1]["status"] == "TRANSLATED"


def test_jmsz_project_on_disk_loads_clean_and_empty(app):
    """
    Kiểm tra thực tế với file project JMSZ trên ổ đĩa:
    Khi nạp project.aisrt của JMSZ, CAT Studio phải rỗng và không còn subtitle #019.
    """
    jmsz_aisrt = r"D:\Projects\JMSZ.ai-subtitle\artifacts\translation\project.aisrt"
    if not os.path.exists(jmsz_aisrt):
        pytest.skip("Project JMSZ not found on disk")

    page = TranslationStudioPage()
    page.load_translation_project(jmsz_aisrt)

    assert page.subtitle_model.rowCount() == 0
    assert page.translation_controller.currentSubtitleIndex == -1
    # TM vẫn được bảo toàn
    assert "俺に忠誠を誓うというか" in page.project_controller.translation_memory._entries
