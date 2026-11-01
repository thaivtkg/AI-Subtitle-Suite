import time
import pytest
from PySide6.QtCore import Qt, QCoreApplication

from core.translation.models.subtitle import SubtitleModel, FilteredSubtitleModel
from .app_harness import AppHarness


def generate_mock_subtitles(count: int = 3000):
    """Sinh động 3.000 dòng phụ đề mà không tạo file .srt vào repo Git."""
    subtitles = []
    for i in range(count):
        s_sec = i * 3
        e_sec = s_sec + 2
        sh, sm, ss = s_sec // 3600, (s_sec % 3600) // 60, s_sec % 60
        eh, em, es = e_sec // 3600, (e_sec % 3600) // 60, e_sec % 60
        start_str = f"{sh:02d}:{sm:02d}:{ss:02d},000"
        end_str = f"{eh:02d}:{em:02d}:{es:02d},000"
        subtitles.append({
            "index": i + 1,
            "start_time": start_str,
            "end_time": end_str,
            "original": f"Sentence number {i + 1} with context data.",
            "translation": f"Bản dịch câu {i + 1}." if i % 2 == 0 else "",
            "status": "TRANSLATED" if i % 2 == 0 else "PENDING",
        })
    return subtitles


def test_ac03_model_load_and_filter_performance():
    """AC-03: Kiểm tra hiệu năng nạp và lọc trên 3.000 câu."""
    model = SubtitleModel()
    mock_data = generate_mock_subtitles(3000)

    start = time.perf_counter()
    model.load_data(mock_data)
    load_time = time.perf_counter() - start

    assert model.rowCount() == 3000
    assert load_time < 0.25, f"Thời gian nạp 3000 câu quá lâu: {load_time:.3f}s (yêu cầu < 250ms)"

    filtered_model = FilteredSubtitleModel(model)
    assert filtered_model.filteredCount == 3000

    # Lọc tìm kiếm 1 câu cụ thể trong 3.000 câu
    start_search = time.perf_counter()
    filtered_model.setSearchQuery("Sentence number 2500")
    search_time = time.perf_counter() - start_search

    assert filtered_model.filteredCount == 1
    assert filtered_model.getRawIndex(0) == 2499
    assert search_time < 0.05, f"Tìm kiếm quá lâu: {search_time:.3f}s"

    # Reset tìm kiếm
    filtered_model.setSearchQuery("")
    assert filtered_model.filteredCount == 3000


@pytest.fixture
def harness_3000():
    """Khởi tạo AppHarness và nạp 3.000 câu động vào model."""
    harness = AppHarness(None)
    mock_data = generate_mock_subtitles(3000)
    harness.model.load_data(mock_data)
    QCoreApplication.processEvents()
    yield harness
    harness.close()


def test_ac01_keyboard_navigation_3000_items(harness_3000):
    """AC-01: Phím tắt Home, End, PageUp, PageDown hoạt động chính xác trên 3.000 câu."""
    driver = harness_3000.driver
    sub_list = driver.find("subtitleList")
    assert sub_list.property("count") == 3000

    # Đảm bảo subListView có active focus
    sub_list.forceActiveFocus()
    QCoreApplication.processEvents()
    assert sub_list.property("activeFocus") is True

    # 1. Bấm End -> nhảy về cuối danh sách (2999)
    driver.key(Qt.Key_End)
    assert sub_list.property("currentIndex") == 2999

    # 2. Bấm PageUp -> nhảy lùi 10 câu (2989)
    driver.key(Qt.Key_PageUp)
    assert sub_list.property("currentIndex") == 2989

    # 3. Bấm PageDown -> nhảy tiến 10 câu (2999)
    driver.key(Qt.Key_PageDown)
    assert sub_list.property("currentIndex") == 2999

    # 4. Bấm Home -> nhảy về đầu danh sách (0)
    driver.key(Qt.Key_Home)
    assert sub_list.property("currentIndex") == 0

    # 5. Bấm PageDown từ 0 -> nhảy tiến 10 câu (10)
    driver.key(Qt.Key_PageDown)
    assert sub_list.property("currentIndex") == 10

    # 6. Bấm PageUp từ 10 -> nhảy lùi về 0
    driver.key(Qt.Key_PageUp)
    assert sub_list.property("currentIndex") == 0


def test_ac01_esc_returns_focus_to_sublistview(harness_3000):
    """AC-01: Bấm Esc từ searchInput trả focus cho subListView."""
    driver = harness_3000.driver
    search_input = driver.find("searchInput")
    sub_list = driver.find("subtitleList")

    # Focus vào searchInput
    search_input.forceActiveFocus()
    QCoreApplication.processEvents()
    assert search_input.property("activeFocus") is True

    # Bấm Esc
    driver.key(Qt.Key_Escape)
    assert sub_list.property("activeFocus") is True


def test_ac02_scroll_to_active_pill_fab(harness_3000):
    """AC-02: Nút pill '👇 Cuộn tới câu đang dịch' hiển thị đúng lúc và cuộn chính xác."""
    driver = harness_3000.driver
    sub_list = driver.find("subtitleList")
    pill = driver.find("btnScrollToActive")

    assert pill is not None
    assert pill.property("z") == 50

    # Ban đầu ở câu 0 (đang nhìn thấy), không có dịch đang chạy -> pill ẩn
    QCoreApplication.processEvents()
    assert pill.property("visible") is False

    # Giả lập đang dịch câu 1500 (ở rất xa ngoài viewport)
    harness_3000.translation_controller._active_translation_index = 1500
    harness_3000.translation_controller.statusChanged.emit("TRANSLATING")
    QCoreApplication.processEvents()

    # Nút pill phải hiện ra
    assert pill.property("visible") is True

    # Click vào pill -> nhảy tới câu 1500
    driver.click("btnScrollToActive")
    assert sub_list.property("currentIndex") == 1500

    # Sau khi tới câu 1500, kết thúc dịch
    harness_3000.translation_controller._active_translation_index = -1
    harness_3000.translation_controller.statusChanged.emit("TRANSLATED")
    QCoreApplication.processEvents()
    assert pill.property("visible") is False

