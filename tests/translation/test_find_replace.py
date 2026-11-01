import pytest
from PySide6.QtCore import QCoreApplication
from core.translation.controllers.project_controller import ProjectController
from core.translation.models.subtitle import SubtitleModel


@pytest.fixture(autouse=True)
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def make_test_controller():
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "start_time": "00:00:01,000", "end_time": "00:00:03,000", "original": "Hello teacher, good morning.", "translation": "Chào thầy giáo, chúc buổi sáng.", "status": "TRANSLATED"},
        {"index": 2, "start_time": "00:00:04,000", "end_time": "00:00:06,000", "original": "Goodbye teacher.", "translation": "Tạm biệt thầy.", "status": "PENDING"},
        {"index": 3, "start_time": "00:00:07,000", "end_time": "00:00:09,000", "original": "Welcome student 100.", "translation": "Chào học sinh 100.", "status": "ACCEPTED"},
    ])
    ctrl = ProjectController(model)
    return ctrl, model


def test_preview_find_replace():
    ctrl, model = make_test_controller()

    # 1. Preview in translations
    res = ctrl.previewFindReplace("thầy", scope="TRANSLATION", match_case=False, whole_word=False, is_regex=False)
    assert res["total_matches"] == 2
    assert res["affected_rows"] == [0, 1]

    # 2. Preview case sensitive
    res = ctrl.previewFindReplace("Teacher", scope="ORIGINAL", match_case=True, whole_word=False, is_regex=False)
    assert res["total_matches"] == 0

    res = ctrl.previewFindReplace("teacher", scope="ORIGINAL", match_case=True, whole_word=False, is_regex=False)
    assert res["total_matches"] == 2
    assert res["affected_rows"] == [0, 1]

    # 3. Preview empty text
    res = ctrl.previewFindReplace("", scope="ALL")
    assert res["total_matches"] == 0
    assert res["affected_rows"] == []

    # 4. Preview regex
    res = ctrl.previewFindReplace(r"\d+", scope="ALL", is_regex=True)
    assert res["total_matches"] == 2
    assert res["affected_rows"] == [2]


def test_execute_find_replace_with_auto_glossary():
    ctrl, model = make_test_controller()

    # Replace "thầy" -> "sư phụ" in TRANSLATION scope and add to glossary
    replaced = ctrl.executeFindReplace(
        find_text="thầy",
        replace_text="sư phụ",
        scope="TRANSLATION",
        match_case=False,
        whole_word=False,
        is_regex=False,
        add_to_glossary=True
    )
    assert replaced == 2
    data = model.get_all_data()
    assert data[0]["translation"] == "Chào sư phụ giáo, chúc buổi sáng."
    assert data[0]["status"] == "EDITED"
    assert data[1]["translation"] == "Tạm biệt sư phụ."
    assert data[1]["status"] == "EDITED"

    # Verify auto-glossary addition
    entry = ctrl.glossary.get("thầy")
    assert entry is not None
    assert entry.preferred_translation == "sư phụ"
    assert entry.is_auto is False


def test_execute_find_replace_scope_all_and_regex():
    ctrl, model = make_test_controller()

    # Replace numbers via regex across all scopes
    replaced = ctrl.executeFindReplace(
        find_text=r"\d+",
        replace_text="999",
        scope="ALL",
        match_case=False,
        whole_word=False,
        is_regex=True,
        add_to_glossary=False
    )
    assert replaced == 2
    data = model.get_all_data()
    assert "999" in data[2]["original"]
    assert "999" in data[2]["translation"]

