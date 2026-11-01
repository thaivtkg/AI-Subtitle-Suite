"""
E2E integration tests for ContextInspector, AppHeader, and ProjectController:
- 2000ms summary debounce timer triggering analyzeSummary
- Archetype selection, active pronoun update, and manual locking/unlocking
- Auto-glossary extraction and term dismissal
- AppHeader archetype capsule display and navigation
"""
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from core.translation.core.context_analyzer import (
    ARCHETYPE_ANCIENT_FANTASY,
    ARCHETYPE_ANIME_SCHOOL,
    ARCHETYPE_MODERN_ACTION,
)
from .app_harness import AppHarness


FIXTURE = Path(__file__).parent / "fixtures" / "regression.srt"


@pytest.fixture
def harness():
    app_harness = AppHarness(FIXTURE)
    yield app_harness
    app_harness.close()


def test_story_summary_debounce_timer_and_analysis(harness):
    """Kiểm tra storySummaryInput có debounce timer 2000ms và kích hoạt analyzeSummary."""
    driver = harness.driver
    tabs = driver.find("contextTabs")
    assert tabs is not None
    tabs.setCurrentIndex(2)  # Tab 3: SUMMARY
    QTest.qWait(50)

    summary_input = driver.find("storySummaryInput")
    assert summary_input is not None

    debounce_timer = driver.find("summaryDebounceTimer")
    assert debounce_timer is not None
    assert debounce_timer.property("interval") == 2000
    assert debounce_timer.property("repeat") is False

    # Nhập tóm tắt chứa thực thể và thể loại kiếm hiệp
    summary_text = 'Phim cổ trang kiếm hiệp, nhân vật "Lăng Ba": Khinh công'
    summary_input.setProperty("text", summary_text)
    QTest.qWait(50)

    # Đảm bảo timer đã khởi động
    assert debounce_timer.property("running") is True

    # Kích hoạt timer hoàn tất và trích xuất thuật ngữ tự động
    driver.wait_until(
        lambda: any(t["source_term"] == "Lăng Ba" for t in harness.project_controller.glossaryTerms),
        timeout_ms=3000,
    )
    assert harness.project_controller.activeArchetype == "pure_model"
    assert harness.project_controller.activePronounPair == ""

    # Kiểm tra capsule thông tin dưới thẻ summary
    capsule = driver.find("summaryArchetypeCapsule")
    assert capsule is not None
    assert capsule.property("visible") is True


def test_intelligence_tab_focuses_on_glossary_only(harness):
    """Kiểm tra Tab INTELLIGENCE đã loại bỏ hoàn toàn archetypeCard và tập trung vào glossaryCard."""
    driver = harness.driver
    tabs = driver.find("contextTabs")
    tabs.setCurrentIndex(1)  # Tab 2: INTELLIGENCE
    QTest.qWait(50)

    from PySide6.QtCore import QObject
    assert harness.window.findChild(QObject, "archetypeCard") is None
    assert driver.find("glossaryCard") is not None


def test_project_controller_dismiss_auto_term(harness):
    """Kiểm tra gọi dismissAutoTerm xóa chip khỏi glossaryTerms."""
    driver = harness.driver

    # Kích hoạt trích xuất thuật ngữ tự động
    harness.project_controller.analyzeSummary('Phim thần thoại, nhân vật "Hạo Thiên": Thần kiếm')
    assert any(
        term["source_term"] == "Hạo Thiên" and term["is_auto"] for term in harness.project_controller.glossaryTerms
    )

    # Chuyển sang Tab 2: INTELLIGENCE
    tabs = driver.find("contextTabs")
    tabs.setCurrentIndex(1)
    QTest.qWait(50)

    # Xóa thuật ngữ tự động qua nút bấm X trên chip UI
    driver.click("btnDismissTerm_Hạo Thiên")
    driver.wait_until(
        lambda: not any(term["source_term"] == "Hạo Thiên" for term in harness.project_controller.glossaryTerms)
    )

    # Không còn thuật ngữ "Hạo Thiên" trong glossary
    assert harness.project_controller.glossary.get("Hạo Thiên") is None
    assert "Hạo Thiên" in harness.project_controller.dismissed_auto_terms

    # Thẻ empty state xuất hiện lại
    assert driver.is_visible("glossaryEmptyState")


def test_app_header_archetype_capsule_purged_for_space(harness):
    """Kiểm tra capsule thể loại đã được dọn sạch khỏi Header để giải phóng không gian mặt bằng."""
    from PySide6.QtCore import QObject
    header_capsule = harness.window.findChild(QObject, "archetypeHeaderCapsule")
    assert header_capsule is None

def test_context_inspector_geometry_and_padding(harness):
    """Kiểm tra khoảng thở an toàn của Nút Thêm, Khung Empty State và Capsule nguồn gốc."""
    driver = harness.driver
    tabs = driver.find("contextTabs")
    assert tabs is not None

    # 1. Đo đạc Tab 1: GLOSSARY
    tabs.setCurrentIndex(1)
    QTest.qWait(50)
    card = driver.find("glossaryCard")
    empty = driver.find("glossaryEmptyState")
    btn = driver.find("btnToggleAddTerm")
    card_w = card.property("width")
    empty_w = empty.property("width")
    btn_x = btn.property("x")
    btn_w = btn.property("width")

    assert (card_w - (btn_x + btn_w)) >= 18.0, f"Nút Thêm quá sát mép phải: {card_w - (btn_x + btn_w)}"
    assert (card_w - empty_w) >= 32.0, f"Khung trắng quá sát viền card: {card_w - empty_w}"

    # 2. Đo đạc Tab 2: SUMMARY (Origin Capsule)
    tabs.setCurrentIndex(2)
    QTest.qWait(50)
    capsule = driver.find("btnOriginCapsule")
    assert capsule is not None
    assert capsule.property("width") > 0
    init_is_ja = harness.project_controller.isJaOrigin
    driver.click("btnOriginCapsule")
    QTest.qWait(50)
    assert harness.project_controller.isJaOrigin != init_is_ja
    driver.click("btnOriginCapsule")
    QTest.qWait(50)
    assert harness.project_controller.isJaOrigin == init_is_ja


def test_term_alignment_flow_and_extract_button(harness):
    """Kiểm tra hiển thị nút Tra từ gốc và thẻ chip ánh xạ từ vựng trên TranslationWorkspace."""
    driver = harness.driver
    tc = harness.translation_controller

    # Cài đặt dữ liệu cho câu đang chọn: có original và translation nhưng chưa có auto_terms
    subtitles = harness.model.get_all_data()
    subtitles[0]["original"] = "妖魔王やっと見つけたわ"
    subtitles[0]["translation"] = "Cuối cùng ta cũng tìm thấy ngươi rồi Ma Vương"
    subtitles[0]["status"] = "TRANSLATED"
    tc.loadSubtitle(0)
    QTest.qWait(50)

    # 1. Nút btnExtractTerms xuất hiện vì câu đã dịch sẵn nhưng chưa có auto_terms
    btn_extract = driver.find("btnExtractTerms")
    assert btn_extract is not None
    assert btn_extract.property("visible") is True

    # 2. Gán auto_terms cho câu 0 và nạp lại
    subtitles[0]["auto_terms"] = [{"source": "妖魔王", "target": "ác quỷ"}]
    tc.loadSubtitle(0)
    QTest.qWait(50)

    # Nút btnExtractTerms ẩn đi, termAlignmentFlow hiển thị chip
    assert btn_extract.property("visible") is False
    flow = driver.find("termAlignmentFlow")
    assert flow is not None
    assert flow.property("visible") is True

    # 3. Ghim thuật ngữ qua 1-click
    assert tc.currentAppliedTerms[0]["is_glossary"] is False
    ok = tc.pinTermToGlossary("妖魔王", "ác quỷ")
    assert ok is True
    assert tc.currentAppliedTerms[0]["is_glossary"] is True

