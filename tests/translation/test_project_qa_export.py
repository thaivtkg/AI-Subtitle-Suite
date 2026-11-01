import pytest
from PySide6.QtCore import QCoreApplication
from core.translation.controllers.project_controller import ProjectController
from core.translation.models.subtitle import SubtitleModel


@pytest.fixture
def qtbot():
    return QCoreApplication.instance() or QCoreApplication([])


def test_export_intercept_when_qa_errors_exist(qtbot, tmp_path):
    model = SubtitleModel()
    controller = ProjectController(subtitle_model=model)
    export_path = str(tmp_path / "output.srt")

    # Load 1 valid item and 1 item with QA ERROR (CPL > 42)
    model.load_data([
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:05,000",
            "original": "Source 1",
            "translation": "Bản dịch 1",
            "status": "ACCEPTED"
        },
        {
            "index": 2,
            "start_time": "00:00:06,000",
            "end_time": "00:00:10,000",
            "original": "Source 2",
            "translation": "Dòng này cố tình vượt quá bốn mươi hai ký tự để kích hoạt lỗi QA Error tràn màn hình",
            "status": "ACCEPTED"
        }
    ])

    warning_emitted = []
    controller.qaExportWarningRequired.connect(lambda path, count: warning_emitted.append((path, count)))

    # 1-argument call without force -> must intercept
    controller.exportSrt(export_path)

    assert len(warning_emitted) == 1
    assert warning_emitted[0][0] == export_path
    assert warning_emitted[0][1] == 1  # 1 error item

    # 2-argument call with force=True -> must export without extra warning
    controller.exportSrt(export_path, True)
    assert len(warning_emitted) == 1  # No extra warning emitted


def test_export_srt_emits_clean_local_path(qtbot, tmp_path):
    model = SubtitleModel()
    controller = ProjectController(subtitle_model=model)
    export_path = tmp_path / "output.srt"
    file_url = f"file:///{export_path.as_posix()}"

    model.load_data([{
        "index": 1,
        "start_time": "00:00:01,000",
        "end_time": "00:00:02,000",
        "original": "Short",
        "translation": "Dòng này cố tình vượt quá bốn mươi hai ký tự để kích hoạt lỗi QA Error",
        "status": "ACCEPTED"
    }])

    warning_emitted = []
    controller.qaExportWarningRequired.connect(lambda path, count: warning_emitted.append((path, count)))

    controller.exportSrt(file_url)

    assert len(warning_emitted) == 1
    # Must be a clean local file path, NOT starting with file:///
    assert not warning_emitted[0][0].startswith("file:///")
    assert str(export_path).replace("\\", "/") in warning_emitted[0][0].replace("\\", "/")


def test_save_project_strips_volatile_qa_keys(qtbot, tmp_path):
    import json
    model = SubtitleModel()
    controller = ProjectController(subtitle_model=model)
    save_path = str(tmp_path / "test_project.aisrt")

    model.load_data([{
        "index": 1,
        "start_time": "00:00:01,000",
        "end_time": "00:00:02,000",
        "original": "Short",
        "translation": "Dòng này cố tình vượt quá bốn mươi hai ký tự để kích hoạt lỗi QA Error",
        "status": "TRANSLATED"
    }])

    controller.saveProject(save_path, "Test Summary")

    with open(save_path, "r", encoding="utf-8") as f:
        saved_data = json.load(f)

    subtitles = saved_data["subtitles"]
    assert len(subtitles) == 1
    # Assert NO keys starting with '_' are saved in the project file
    for sub in subtitles:
        for key in sub.keys():
            assert not key.startswith("_"), f"Found volatile key in saved project: {key}"


