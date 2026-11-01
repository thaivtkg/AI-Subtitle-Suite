import pytest
from PySide6.QtCore import QCoreApplication
from core.translation.models.subtitle import SubtitleModel, FilteredSubtitleModel

@pytest.fixture(autouse=True)
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])

def test_filtered_subtitle_model_initial():
    source = SubtitleModel()
    data = [
        {"index": 1, "start_time": "00:01:00,000", "end_time": "00:01:02,000", "original": "First", "translation": "", "status": "PENDING"},
        {"index": 2, "start_time": "00:02:00,000", "end_time": "00:02:02,000", "original": "Second", "translation": "", "status": "PENDING"},
        {"index": 3, "start_time": "00:06:00,000", "end_time": "00:06:02,000", "original": "Third", "translation": "Đã dịch", "status": "TRANSLATED"},
    ]
    source.load_data(data)

    proxy = FilteredSubtitleModel(source)
    assert proxy.rowCount() == 3
    assert proxy.filteredCount == 3
    assert proxy.totalCount == 3
    assert proxy.currentPage == 1
    assert proxy.totalPages == 1
    assert proxy.pageSize == 0

    # Test time filter
    proxy.setTimeFilter(True, 1, 5)
    assert proxy.filteredCount == 2
    assert proxy.rowCount() == 2
    assert proxy.getRawIndex(0) == 0
    assert proxy.getRawIndex(1) == 1

    # Test pagination on top of time filter
    proxy.setPageSize(1)
    assert proxy.filteredCount == 2
    assert proxy.rowCount() == 1  # 1 item per page
    assert proxy.totalPages == 2
    assert proxy.currentPage == 1
    assert proxy.getRawIndex(0) == 0

    proxy.nextPage()
    assert proxy.currentPage == 2
    assert proxy.rowCount() == 1
    assert proxy.getRawIndex(0) == 1

    # Reset page size to all
    proxy.setPageSize(0)
    assert proxy.rowCount() == 2

    # Test status filter
    proxy.setTimeFilter(False, 0, 9999)
    proxy.setStatusFilter("TRANSLATED")
    assert proxy.filteredCount == 1
    assert proxy.rowCount() == 1
    assert proxy.getRawIndex(0) == 2

    # Test search
    proxy.setStatusFilter("ALL")
    proxy.setSearchQuery("sec")
    assert proxy.filteredCount == 1
    assert proxy.getRawIndex(0) == 1

def test_filtered_subtitle_model_reactivity():
    source = SubtitleModel()
    data = [
        {"index": 1, "start_time": "00:01:00,000", "end_time": "00:01:02,000", "original": "First", "translation": "", "status": "PENDING"},
        {"index": 2, "start_time": "00:02:00,000", "end_time": "00:02:02,000", "original": "Second", "translation": "", "status": "PENDING"},
    ]
    source.load_data(data)
    proxy = FilteredSubtitleModel(source)

    # Listen to dataChanged on proxy
    changed_rows = []
    proxy.dataChanged.connect(lambda top, bottom, roles: changed_rows.append(top.row()))

    # Update translation in source
    source.update_translation(1, "Bản dịch câu 2", "TRANSLATED")
    assert 1 in changed_rows
    idx = proxy.index(1, 0)
    assert proxy.data(idx, SubtitleModel.TranslationRole) == "Bản dịch câu 2"
    assert proxy.data(idx, SubtitleModel.StatusRole) == "TRANSLATED"
    assert proxy.data(idx, FilteredSubtitleModel.RawIndexRole) == 1


def test_logic_08_empty_filter_and_reset_workspace():
    """Kiểm tra LOGIC-08: Khi bộ lọc trả về 0 kết quả, gọi loadSubtitle(-1) dọn sạch workspace."""
    from core.translation.controllers.translation_controller import TranslationController
    source = SubtitleModel()
    source.load_data([
        {"index": 1, "start_time": "00:01:00,000", "end_time": "00:01:02,000", "original": "First", "translation": "Câu 1", "status": "TRANSLATED"},
    ])
    tc = TranslationController(source)
    tc.loadSubtitle(0)
    assert tc.currentSubtitleIndex == 0
    assert tc.currentOriginal == "First"
    assert tc.currentTranslation == "Câu 1"

    # Giả lập khi lọc rỗng -> gọi loadSubtitle(-1)
    tc.loadSubtitle(-1)
    assert tc.currentSubtitleIndex == -1
    assert tc.currentOriginal == ""
    assert tc.currentTranslation == ""



