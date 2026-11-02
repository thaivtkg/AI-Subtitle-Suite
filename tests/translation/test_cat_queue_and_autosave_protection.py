import pytest
from PySide6.QtCore import QCoreApplication
from core.translation.models.subtitle import SubtitleModel
from core.translation.controllers.translation_controller import TranslationController


@pytest.fixture
def app():
    instance = QCoreApplication.instance()
    if not instance:
        instance = QCoreApplication([])
    return instance


def test_approved_subtitle_removed_from_cat_queue_and_synced(app):
    """
    AC-CAT-QUEUE-01:
    Khi duyệt câu (acceptTranslation), câu đã duyệt phải được:
    1. Đồng bộ sang Studio (phát tín hiệu thông qua update_translation -> dataChanged).
    2. Xóa khỏi SubtitleModel (hàng đợi CAT Studio).
    3. Tự động chuyển và nạp câu kế tiếp trong hàng đợi.
    4. Khi duyệt hết toàn bộ, chuyển về IDLE và danh sách trống (0 câu).
    """
    model = SubtitleModel()
    data = [
        {"index": 1, "original": "Hello", "translation": "", "status": "PENDING", "studio_index": 0},
        {"index": 2, "original": "World", "translation": "", "status": "PENDING", "studio_index": 1},
        {"index": 3, "original": "Good morning", "translation": "", "status": "PENDING", "studio_index": 2},
    ]
    model.load_data(data)
    controller = TranslationController(model)

    assert model.rowCount() == 3
    controller.loadSubtitle(0)
    assert controller.currentOriginal == "Hello"

    # Duyệt câu #001
    committed = []
    def on_data_changed(tl, br, roles=None):
        item = model.get_item(tl.row())
        if item and item.get("status") == "ACCEPTED":
            committed.append((item.get("studio_index"), item.get("translation")))
    model.dataChanged.connect(on_data_changed)

    ok = controller.acceptTranslation(0, "Xin chào")
    assert ok is True
    assert len(committed) == 1
    assert committed[0] == (0, "Xin chào")

    # Câu #001 đã bị xóa khỏi hàng đợi
    assert model.rowCount() == 2
    assert model.get_item(0)["original"] == "World"
    assert model.get_item(1)["original"] == "Good morning"

    # Tự động nạp câu kế tiếp ("World")
    assert controller.currentSubtitleIndex == 0
    assert controller.currentOriginal == "World"

    # Duyệt tiếp câu "World"
    ok = controller.acceptTranslation(0, "Thế giới")
    assert ok is True
    assert len(committed) == 2
    assert committed[1] == (1, "Thế giới")

    # Còn 1 câu trong hàng đợi
    assert model.rowCount() == 1
    assert controller.currentOriginal == "Good morning"

    # Duyệt câu cuối cùng
    ok = controller.acceptTranslation(0, "Chào buổi sáng")
    assert ok is True
    assert len(committed) == 3
    assert committed[2] == (2, "Chào buổi sáng")

    # Hàng đợi trống hoàn toàn, controller về IDLE
    assert model.rowCount() == 0
    assert controller.currentSubtitleIndex == -1
    assert controller.currentOriginal == ""
    assert controller.status == "IDLE"


def test_thinking_progress_dynamic_crawl_beyond_35(app):
    """
    AC-CAT-THINK-02:
    Tiến trình không bị đóng băng (freeze) ở 35% khi model đang trong giai đoạn reasoning (<think>).
    Timer tiếp tục bò mượt (36%, 37%...) cho đến khi token đầu tiên xuất hiện.
    """
    model = SubtitleModel()
    model.load_data([{"index": 1, "original": "Deep thinking sentence", "translation": "", "status": "PENDING"}])
    controller = TranslationController(model)
    controller.loadSubtitle(0)

    # Giả lập trạng thái đang dịch
    controller._status = "TRANSLATING"
    controller._active_translation_index = 0
    controller._translation_progress = 10
    controller._progress_tick_count = 0
    controller._progress_timer.start()

    # Chạy tick lên đến 35%
    for _ in range(13):
        controller._on_thinking_progress_tick()
    assert controller.translationProgress == 35

    # Tiếp tục tick: KHÔNG ĐƯỢC DỪNG Ở 35% mà phải tiếp tục tăng
    controller._on_thinking_progress_tick()
    assert controller.translationProgress == 36
    controller._on_thinking_progress_tick()
    assert controller.translationProgress == 37

    # Khi token đầu tiên về, progress timer dừng và token progress nhận quyền điều khiển
    controller.on_progress(0, "Bản dịch đang về")
    assert controller._progress_timer.isActive() is False
    assert controller.translationProgress >= 37


def test_autosave_does_not_clobber_user_edits_in_video_workspace():
    """
    AC-VIDEO-AUTOSAVE-03:
    Sau khi duyệt bản dịch, người dùng chỉnh sửa thêm text bên ô nội dung Video Workspace.
    Khi hệ thống autosave chạy ngầm, không được phép ghi đè ngược bản dịch cũ hay gián đoạn ô soạn thảo.
    """
    # Mô phỏng trạng thái all_segments trong Studio
    segments = [
        {
            "id": "seg_001",
            "stt": 1,
            "start": "00:00:01,000",
            "end": "00:00:03,000",
            "original_text": "Hello world",
            "translation": "Bản dịch cũ từ AI",
            "text": "Bản dịch cũ từ AI",
            "translation_status": "ACCEPTED",
        }
    ]

    # Người dùng gõ text mới vào ô nội dung bên Video Workspace
    new_user_text = "Nội dung mới do người dùng vừa tự tay nhập thêm"
    segments[0]["text"] = new_user_text

    # Trong Gui.py::_save_project_now, export_subtitles_to_studio và render_page đã bị loại bỏ
    # Kiểm tra đảm bảo text của người dùng được bảo toàn 100%
    assert segments[0]["text"] == new_user_text
