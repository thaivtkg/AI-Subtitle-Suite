import pytest
from PySide6.QtCore import QCoreApplication
from core.translation.models.subtitle import SubtitleModel, FilteredSubtitleModel


@pytest.fixture(autouse=True)
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def test_progress_stats_and_qa_filter():
    source = SubtitleModel()
    data = [
        {"index": 1, "start_time": "00:00:01,000", "end_time": "00:00:03,000", "original": "First", "translation": "Một", "status": "ACCEPTED"},
        {"index": 2, "start_time": "00:00:04,000", "end_time": "00:00:06,000", "original": "Second", "translation": "Hai", "status": "TRANSLATED"},
        {"index": 3, "start_time": "00:00:07,000", "end_time": "00:00:09,000", "original": "Third", "translation": "", "status": "PENDING"},
        {"index": 4, "start_time": "00:00:10,000", "end_time": "00:00:10,200", "original": "Too fast", "translation": "Quá nhanh vượt mức CPS tối đa rất nhiều ký tự ở đây", "status": "TRANSLATED"},
    ]
    source.load_data(data)

    stats = source.progressStats
    assert stats["total"] == 4
    assert stats["accepted"] == 1
    assert stats["translated"] >= 1
    assert stats["pending"] == 1
    # Check QA issue presence on item 4 (fast CPS)
    assert stats["qa_issues"] >= 1

    proxy = FilteredSubtitleModel(source)
    assert proxy.rowCount() == 4
    assert proxy.qaOnly is False

    # Filter QA only
    proxy.setQaOnlyFilter(True)
    assert proxy.qaOnly is True
    assert proxy.rowCount() == 1
    assert proxy.getRawIndex(0) == 3

    # Toggle off QA only
    proxy.setQaOnlyFilter(False)
    assert proxy.rowCount() == 4

