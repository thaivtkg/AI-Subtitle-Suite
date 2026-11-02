import os
import json
import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from core.translation.controllers.project_controller import ProjectController
from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel
from ui.Gui import MainWindow
from ui.pages.translation_studio_page import TranslationStudioPage


def test_ac_filter_01_load_sanitization(tmp_path):
    """
    AC-FILTER-01: Load Sanitization
    Gọi loadProject() với file .aisrt chứa 3 câu (#1: ACCEPTED, #2: TRANSLATED, #3: PENDING).
    Kiểm tra subtitle_model.rowCount() == 2, chỉ có câu #2 và #3.
    Câu #1 hoàn toàn không tồn tại trong model.
    """
    aisrt_file = tmp_path / "test_load.aisrt"
    payload = {
        "metadata": {"source_language": "English", "target_language": "Vietnamese"},
        "story_summary": "Test story",
        "subtitles": [
            {
                "index": 1,
                "start_time": "00:00:01,000",
                "end_time": "00:00:03,000",
                "original": "Sentence 1",
                "translation": "Câu 1",
                "status": "ACCEPTED",
            },
            {
                "index": 2,
                "start_time": "00:00:04,000",
                "end_time": "00:00:06,000",
                "original": "Sentence 2",
                "translation": "Câu 2",
                "status": "TRANSLATED",
            },
            {
                "index": 3,
                "start_time": "00:00:07,000",
                "end_time": "00:00:09,000",
                "original": "Sentence 3",
                "translation": "",
                "status": "PENDING",
            },
        ],
        "intelligence": {"glossary": {}, "entities": {}, "translation_memory": {}},
    }
    with open(aisrt_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    model = SubtitleModel()
    project_controller = ProjectController(subtitle_model=model)
    trans_controller = TranslationController(subtitle_model=model)
    project_controller.bind_translation_controller(trans_controller)

    project_controller.loadProject(str(aisrt_file))

    assert model.rowCount() == 2
    data = model.get_all_data()
    assert len(data) == 2
    assert data[0]["original"] == "Sentence 2"
    assert data[0]["status"] == "TRANSLATED"
    assert data[1]["original"] == "Sentence 3"
    assert data[1]["status"] == "PENDING"
    assert not any(str(sub.get("status", "")).upper() == "ACCEPTED" for sub in data)


def test_ac_filter_02_empty_workspace_on_project_open(qtbot):
    """
    AC-FILTER-02: Empty Workspace on Project Open
    Mở dự án D:\\Projects\\JMSZ.ai-subtitle bằng _open_project_by_path() rồi chuyển sang Tab DỊCH (switch_page(8)).
    Xác nhận subtitle_model.rowCount() == 0 và workspace hiển thị màn hình EmptyWorkspace.qml với nút Nạp phụ đề từ Timeline.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1280, 720)
    qtbot.addWidget(win)

    jmsz_path = "D:/Projects/JMSZ.ai-subtitle"
    assert os.path.exists(jmsz_path)

    from unittest.mock import patch
    real_json_load = json.load
    def mocked_json_load(f, *args, **kwargs):
        data = real_json_load(f, *args, **kwargs)
        if isinstance(data, dict) and "subtitles" in data:
            return {
                **data,
                "subtitles": [
                    {**s, "status": "ACCEPTED"} for s in data["subtitles"]
                ]
            }
        return data

    with patch("json.load", side_effect=mocked_json_load):
        win._open_project_by_path(jmsz_path)

    # Chuyển sang Tab DỊCH (Trang 8)
    win.switch_page(8)

    # Xác nhận subtitle_model có 0 phần tử
    sub_model = win.page_translation.subtitle_model
    assert sub_model.rowCount() == 0

    # Xác nhận nút [ 📥 Nạp phụ đề từ Timeline ] trên EmptyWorkspace hiển thị
    from tests.gui.drivers.qt_driver import QtDriver

    driver = QtDriver(win, qtbot)
    btn_import = driver.find_qml_item("btnImportFromTimeline", quick_widget=win.page_translation.quick_widget)
    assert btn_import is not None
    assert btn_import.property("visible") is True


def test_ac_filter_03_save_sanitization(tmp_path):
    """
    AC-FILTER-03: Save Sanitization
    Khi gọi saveProject(), kiểm tra tệp json .aisrt được ghi xuống đĩa có trường "subtitles"
    không chứa bất kỳ item nào có status == "ACCEPTED".
    """
    aisrt_file = tmp_path / "test_save.aisrt"
    model = SubtitleModel()
    model.load_data([
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:03,000",
            "original": "Sentence 1",
            "translation": "Câu 1",
            "status": "ACCEPTED",
        },
        {
            "index": 2,
            "start_time": "00:00:04,000",
            "end_time": "00:00:06,000",
            "original": "Sentence 2",
            "translation": "Câu 2",
            "status": "TRANSLATED",
        },
        {
            "index": 3,
            "start_time": "00:00:07,000",
            "end_time": "00:00:09,000",
            "original": "Sentence 3",
            "translation": "",
            "status": "PENDING",
        },
    ])
    project_controller = ProjectController(subtitle_model=model)
    trans_controller = TranslationController(subtitle_model=model)
    project_controller.bind_translation_controller(trans_controller)

    project_controller.saveProject(str(aisrt_file), story_summary="Test Save", notify=False)

    with open(aisrt_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)

    saved_subs = saved_data.get("subtitles", [])
    assert len(saved_subs) == 2
    assert not any(str(sub.get("status", "")).upper() == "ACCEPTED" for sub in saved_subs)
    statuses = [sub.get("status") for sub in saved_subs]
    assert "TRANSLATED" in statuses
    assert "PENDING" in statuses


def test_ac_filter_04_selective_timeline_import(qtbot):
    """
    AC-FILTER-04: Selective Timeline Import
    Có 5 câu trên Timeline (câu 1, 2 đã ACCEPTED, câu 3, 4, 5 là PENDING).
    Khi bấm import_all_from_timeline() (selected_indices is None), CAT Studio chỉ nạp 3 câu (câu 3, 4, 5).
    Khi chọn cụ thể các dòng (selected_indices list), nạp chính xác các dòng được chọn.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    page = TranslationStudioPage()
    qtbot.addWidget(page)

    studio_segments = [
        {
            "id": "s1",
            "stt": "1",
            "start": "00:00:01,000",
            "end": "00:00:02,000",
            "text": "Seg 1",
            "translation": "Dịch 1",
            "translation_status": "ACCEPTED",
        },
        {
            "id": "s2",
            "stt": "2",
            "start": "00:00:03,000",
            "end": "00:00:04,000",
            "text": "Seg 2",
            "translation": "Dịch 2",
            "translation_status": "ACCEPTED",
        },
        {
            "id": "s3",
            "stt": "3",
            "start": "00:00:05,000",
            "end": "00:00:06,000",
            "text": "Seg 3",
            "translation": "",
            "translation_status": "PENDING",
        },
        {
            "id": "s4",
            "stt": "4",
            "start": "00:00:07,000",
            "end": "00:00:08,000",
            "text": "Seg 4",
            "translation": "",
            "translation_status": "PENDING",
        },
        {
            "id": "s5",
            "stt": "5",
            "start": "00:00:09,000",
            "end": "00:00:10,000",
            "text": "Seg 5",
            "translation": "",
            "translation_status": "PENDING",
        },
    ]

    # Nạp chủ động từ Timeline (selected_indices is None): bỏ qua câu ACCEPTED
    page.load_subtitles_from_studio(studio_segments, selected_indices=None)

    assert page.subtitle_model.rowCount() == 3
    loaded_data = page.subtitle_model.get_all_data()
    assert len(loaded_data) == 3
    loaded_ids = [sub.get("segment_id") for sub in loaded_data]
    assert loaded_ids == ["s3", "s4", "s5"]
    assert not any(str(sub.get("status", "")).upper() == "ACCEPTED" for sub in loaded_data)

    # Khi bôi đen chỉ định các dòng (selected_indices cụ thể): giữ nguyên các dòng được chọn
    page.load_subtitles_from_studio(studio_segments, selected_indices=[0, 2])
    assert page.subtitle_model.rowCount() == 2
    explicit_data = page.subtitle_model.get_all_data()
    assert explicit_data[0]["segment_id"] == "s1"
    assert explicit_data[1]["segment_id"] == "s3"
