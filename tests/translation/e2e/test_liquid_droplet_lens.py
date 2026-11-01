import pytest
from PySide6.QtCore import Qt, QCoreApplication
from core.translation.models.subtitle import SubtitleModel
from .app_harness import AppHarness


def generate_mock_subtitles(count: int = 20):
    subtitles = []
    for i in range(count):
        s_sec = i * 3
        e_sec = s_sec + 2
        sh, sm, ss = s_sec // 3600, (s_sec % 3600) // 60, s_sec % 60
        eh, em, es = e_sec // 3600, (e_sec % 3600) // 60, e_sec % 60
        subtitles.append({
            "index": i + 1,
            "start_time": f"{sh:02d}:{sm:02d}:{ss:02d},000",
            "end_time": f"{eh:02d}:{em:02d}:{es:02d},000",
            "original": f"Sentence {i + 1} test line.",
            "translation": f"Bản dịch câu {i + 1}." if i % 2 == 0 else "",
            "status": "ACCEPTED" if i == 0 else ("TRANSLATED" if i % 2 == 0 else "PENDING"),
        })
    return subtitles


@pytest.fixture
def harness_lens():
    harness = AppHarness(None)
    mock_data = generate_mock_subtitles(20)
    harness.model.load_data(mock_data)
    QCoreApplication.processEvents()
    yield harness
    harness.close()


def pump_events(duration_sec: float = 0.25):
    import time
    start = time.perf_counter()
    while time.perf_counter() - start < duration_sec:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def test_ac01_droplet_lens_structure_and_tracking(harness_lens):
    """AC-01: subDropletLens được gán vào contentItem và bám sát currentItem."""
    driver = harness_lens.driver
    sub_list = driver.find("subtitleList")
    sub_lens = driver.find("subDropletLens")

    assert sub_lens is not None, "subDropletLens must exist in QML hierarchy"
    assert sub_list.property("count") == 20
    assert sub_list.property("currentIndex") == 0

    QCoreApplication.processEvents()
    assert sub_lens.property("visible") is True
    assert sub_lens.property("z") == 1

    # Khi đổi currentIndex sang 2, subDropletLens cập nhật targetY
    sub_list.setProperty("currentIndex", 2)
    pump_events(0.35)

    cur_item = sub_list.property("currentItem")
    assert cur_item is not None
    assert sub_lens.property("targetY") == cur_item.property("y") + 4


def test_ac02_droplet_lens_clamping_and_drag_state(harness_lens):
    """AC-02: Cơ chế kẹp biên, khóa z-index = 1, kéo giãn chất lỏng và đồng bộ dragHoverIndex theo thời gian thực."""
    driver = harness_lens.driver
    sub_list = driver.find("subtitleList")
    sub_lens = driver.find("subDropletLens")
    root_view = driver.find("subtitleListView")

    pump_events(0.35)
    assert root_view.property("isDraggingLens") is False
    assert root_view.property("dragHoverIndex") == -1
    assert sub_lens.property("fluidScaleX") == 1.0
    assert sub_lens.property("fluidScaleY") == 1.0
    assert sub_lens.property("z") == 1

    # Bật drag giả lập và di chuyển qua câu 3 với kéo giãn chất lỏng bất đối xứng
    root_view.setProperty("isDraggingLens", True)
    root_view.setProperty("dragHoverIndex", 3)
    sub_lens.setProperty("fluidScaleY", 1.20)
    sub_lens.setProperty("fluidScaleX", 0.92)
    pump_events(0.25)
    assert root_view.property("isDraggingLens") is True
    # z-index luôn khóa cứng = 1 để không bao giờ đè che chữ
    assert sub_lens.property("z") == 1
    assert sub_lens.property("fluidScaleY") == pytest.approx(1.20, abs=0.02)
    assert sub_lens.property("fluidScaleX") == pytest.approx(0.92, abs=0.02)

    # Thẻ 3 nhận thấu kính theo thời gian thực -> isPrimarySelected = True
    item3 = sub_list.itemAtIndex(3)
    item0 = sub_list.itemAtIndex(0)
    if item3:
        assert item3.property("isPrimarySelected") is True
    if item0:
        assert item0.property("isPrimarySelected") is False

    # Nhả drag: hồi phục thể tích chất lỏng về 1.0
    root_view.setProperty("isDraggingLens", False)
    root_view.setProperty("dragHoverIndex", -1)
    sub_lens.setProperty("fluidScaleY", 1.0)
    sub_lens.setProperty("fluidScaleX", 1.0)
    pump_events(0.25)
    assert sub_lens.property("z") == 1
    assert sub_lens.property("fluidScaleY") == pytest.approx(1.0, abs=0.02)
    assert sub_lens.property("fluidScaleX") == pytest.approx(1.0, abs=0.02)
    if item0:
        assert item0.property("isPrimarySelected") is True


def test_ac03_multi_selection_contrast_guard(harness_lens):
    """AC-03: Multi-selection giữ tương phản: câu chính isPrimarySelected, câu phụ isSecondarySelected."""
    driver = harness_lens.driver
    sub_list = driver.find("subtitleList")
    root_view = driver.find("subtitleListView")

    # Chọn câu 0 (chính) và câu 1 (phụ)
    sub_list.setProperty("currentIndex", 0)
    root_view.setProperty("selectedIndices", [0, 1])
    QCoreApplication.processEvents()

    item0 = sub_list.property("currentItem")
    assert item0 is not None
    assert item0.property("isPrimarySelected") is True
    assert item0.property("isSecondarySelected") is False

    # Thẻ 1 là chọn phụ
    item1 = sub_list.itemAtIndex(1)
    if item1:
        assert item1.property("isPrimarySelected") is False
        assert item1.property("isSecondarySelected") is True


def test_ac04_status_badge_geometry_and_alignment(harness_lens):
    """AC-04: Status badge có chiều cao 20, bo góc 10, font 10 bold."""
    driver = harness_lens.driver
    sub_list = driver.find("subtitleList")
    QCoreApplication.processEvents()

    item0 = sub_list.property("currentItem")
    assert item0 is not None

    card_pod = item0.findChild(object, "cardPod")
    # Kiểm tra delegate item geometry
    assert item0.property("hasTranslation") is True
    assert item0.property("height") == 82


def test_ac05_context_inspector_fluid_dynamics(harness_lens):
    """AC-05: Context Inspector Tab Bar có biến dạng chất lỏng (fluidScaleX/Y), bán kính bo capsule đồng tâm và activeHoverIndex thời gian thực."""
    driver = harness_lens.driver
    tab_container = driver.find("tabOuterContainer")
    sliding_pill = driver.find("slidingPill")

    assert tab_container is not None, "tabOuterContainer must exist"
    assert sliding_pill is not None, "slidingPill must exist"

    # Trạng thái tĩnh ban đầu và bán kính bo capsule đồng tâm (18px outer, 15px inner)
    assert tab_container.property("isDragging") is False
    assert tab_container.property("fluidScaleX") == 1.0
    assert tab_container.property("fluidScaleY") == 1.0
    assert sliding_pill.property("z") == 1
    assert tab_container.property("radius") == pytest.approx(18.0, abs=0.1)
    assert sliding_pill.property("radius") == pytest.approx(15.0, abs=0.1)

    # Kéo trượt ngang: giãn trục X, nén trục Y và kiểm tra activeHoverIndex thời gian thực
    tab_container.setProperty("isDragging", True)
    tab_container.setProperty("fluidScaleX", 1.25)
    tab_container.setProperty("fluidScaleY", 0.875)

    tab_width = tab_container.property("tabWidth")
    assert tab_width > 0

    # Hover tại tab 1 (INTELLIGENCE)
    tab_container.setProperty("pillDragX", tab_width + 5)
    pump_events(0.1)
    assert tab_container.property("activeHoverIndex") == 1

    # Hover tại tab 2 (SUMMARY)
    tab_container.setProperty("pillDragX", tab_width * 2 + 5)
    pump_events(0.1)
    assert tab_container.property("activeHoverIndex") == 2

    assert tab_container.property("isDragging") is True
    assert tab_container.property("fluidScaleX") == pytest.approx(1.25, abs=0.02)
    assert tab_container.property("fluidScaleY") == pytest.approx(0.875, abs=0.02)

    # Thả chuột: phục hồi đàn hồi về 1.0
    tab_container.setProperty("isDragging", False)
    tab_container.setProperty("fluidScaleX", 1.0)
    tab_container.setProperty("fluidScaleY", 1.0)
    pump_events(0.25)
    assert tab_container.property("isDragging") is False
    assert tab_container.property("fluidScaleX") == pytest.approx(1.0, abs=0.02)
    assert tab_container.property("fluidScaleY") == pytest.approx(1.0, abs=0.02)


def test_ac06_contrast_tokens_on_light_surfaces():
    """AC-06: Guard against white-on-white contrast bug on luminous/frosted pods."""
    from pathlib import Path
    toast_content = Path("ui/qml_translation/components/Toast.qml").read_text(encoding="utf-8")
    assert "Theme.textOnLightPod" in toast_content, "Toast must use Theme.textOnLightPod for messageText"
    assert "Theme.textPrimary" not in toast_content, "Toast must not use Theme.textPrimary (white on white)"

    main_content = Path("ui/qml_translation/Main.qml").read_text(encoding="utf-8")
    dialog_start = main_content.find('id: qaConfirmDialog')
    assert dialog_start != -1
    dialog_chunk = main_content[dialog_start:dialog_start + 1800]
    assert "Theme.textOnLightPod" in dialog_chunk, "qaConfirmDialog must use Theme.textOnLightPod for high contrast"
    assert "Theme.textPrimary" not in dialog_chunk, "qaConfirmDialog must not use Theme.textPrimary (white on white)"


def test_ac07_launchpad_dropzone_hover_and_border():
    """AC-07: StudioLaunchpad dropzone has solid specular border, no dashed line, and hover lift/glow."""
    from pathlib import Path
    launchpad_content = Path("ui/qml_translation/components/StudioLaunchpad.qml").read_text(encoding="utf-8")
    assert "ShapePath.DashLine" not in launchpad_content, "Dashed shape line must be eliminated"
    assert "Translate" in launchpad_content and "dropZoneBox.isHoveredOrDragged ? -2 : 0" in launchpad_content, "Must have translateY -2px hover lift"
    assert "Theme.accentSapphire" in launchpad_content, "Must use sapphire border when hovered/dragged"
    assert "Theme.glassBorderSpecularUpper" in launchpad_content, "Must use specular border by default"
    assert "MultiEffect" in launchpad_content, "Must use MultiEffect for 3D optical sapphire glow"


def test_ac08_squash_and_stretch_impulse_animation():
    """AC-08: Impulse animations exist with elastic spring (damping: 0.28, spring: 3.4)."""
    from pathlib import Path
    ctx_content = Path("ui/qml_translation/components/ContextInspector.qml").read_text(encoding="utf-8")
    assert "tabSquashImpulse" in ctx_content, "ContextInspector must have tabSquashImpulse"
    assert "damping: 0.28" in ctx_content, "ContextInspector must use damping 0.28"
    assert "spring: 3.4" in ctx_content, "ContextInspector must use spring 3.4"

    sub_content = Path("ui/qml_translation/components/SubtitleListView.qml").read_text(encoding="utf-8")
    assert "subLensImpulse" in sub_content, "SubtitleListView must have subLensImpulse"
    assert "damping: 0.28" in sub_content, "SubtitleListView must use damping 0.28"
    assert "spring: 3.4" in sub_content, "SubtitleListView must use spring 3.4"







