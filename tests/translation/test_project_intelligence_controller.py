"""
Test ProjectController state management, auto-glossary extraction, anti-resurrection,
manual archetype locking, and .aisrt persistence.
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock
from core.translation.controllers.project_controller import ProjectController
from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.context_analyzer import (
    ARCHETYPE_PURE,
    ARCHETYPE_ANCIENT_FANTASY,
    ARCHETYPE_ANIME_SCHOOL,
    ARCHETYPE_MODERN_ACTION,
    ARCHETYPE_CUSTOM,
)


def test_project_controller_summary_analysis_and_dismissal():
    ctrl = ProjectController(subtitle_model=MagicMock())
    # 1. Phân tích tóm tắt tự động
    ctrl.analyzeSummary('Phim cổ trang kiếm hiệp, nhân vật "Lăng Ba": Khinh công')
    assert ctrl.activeArchetype == ARCHETYPE_PURE
    assert ctrl.activePronounPair == ""

    # 2. Kiểm tra thuật ngữ tự động được thêm vào glossary
    glossary = ctrl.glossary
    assert glossary is not None
    assert glossary.get("Lăng Ba") is not None
    assert glossary.get("Lăng Ba").is_auto is True
    assert any(term["source_term"] == "Lăng Ba" and term["is_auto"] is True for term in ctrl.glossaryTerms)

    # 3. Người dùng bấm xóa chip (✕)
    ctrl.dismissAutoTerm("Lăng Ba")
    assert glossary.get("Lăng Ba") is None
    assert "Lăng Ba" in ctrl.dismissed_auto_terms

    # 4. Debounce kích hoạt lại với cùng tóm tắt -> BẮT BUỘC KHÔNG HỒI SINH TỪ ĐÃ XÓA
    ctrl.analyzeSummary('Phim cổ trang kiếm hiệp, nhân vật "Lăng Ba": Khinh công')
    assert glossary.get("Lăng Ba") is None

    # 5. Khóa thủ công thể loại
    ctrl.selectArchetype(ARCHETYPE_ANIME_SCHOOL, manual_lock=True)
    assert ctrl.isArchetypeLocked is True
    assert ctrl.activeArchetype == ARCHETYPE_PURE
    assert ctrl.activePronounPair == ""

    # Tóm tắt mới không được ghi đè thể loại đã khóa
    ctrl.analyzeSummary("Phim cổ trang kiếm hiệp khác")
    assert ctrl.activeArchetype == ARCHETYPE_PURE
    assert ctrl.activePronounPair == ""


def test_project_controller_save_and_load_persistence():
    mock_model = MagicMock()
    mock_model.get_all_data.return_value = [
        {"id": 1, "start_time": "00:00:01,000", "end_time": "00:00:02,000", "original": "Test", "translation": "Thử", "status": "TRANSLATED"}
    ]
    mock_model.rowCount.return_value = 1
    ctrl = ProjectController(subtitle_model=mock_model)
    ctrl.analyzeSummary('Phim về lập trình viên đối đầu "Bug Master": Trùm Bug')
    ctrl.dismissAutoTerm("Bug Master")
    ctrl.selectArchetype(ARCHETYPE_MODERN_ACTION, manual_lock=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, "test_proj.aisrt")
        ctrl.saveProject(save_path, "Summary test", "English", "Vietnamese")

        # Nạp lại vào một Controller mới tinh
        new_mock_model = MagicMock()
        load_ctrl = ProjectController(subtitle_model=new_mock_model)
        load_ctrl.loadProject(save_path)

        assert load_ctrl.activeArchetype == ARCHETYPE_PURE
        assert load_ctrl.activePronounPair == ""
        assert load_ctrl.isArchetypeLocked is True
        assert "Bug Master" in load_ctrl.dismissed_auto_terms


def test_manual_terms_preserved_against_auto_dismissal():
    ctrl = ProjectController(subtitle_model=MagicMock())
    # Thêm thuật ngữ thủ công (is_auto=False)
    ctrl.glossary.add("Tiên Đan", "Elixir", (), is_auto=False)
    assert ctrl.glossary.get("Tiên Đan").is_auto is False

    # Phân tích tóm tắt có nhắc đến Tiên Đan
    ctrl.analyzeSummary('Truyện tu tiên luyện "Tiên Đan" thành thần')
    # Thuật ngữ thủ công giữ nguyên is_auto=False, không bị đè
    assert ctrl.glossary.get("Tiên Đan").is_auto is False


def test_translation_controller_binds_project_controller_and_cleans_hallucinated_prefix():
    mock_model = MagicMock()
    mock_model.get_all_data.return_value = []
    tc = TranslationController(subtitle_model=mock_model)
    pc = ProjectController(subtitle_model=mock_model)
    pc.selectArchetype(ARCHETYPE_ANCIENT_FANTASY, manual_lock=True)

    tc.bind_intelligence(
        glossary=pc.glossary,
        entities=pc.entity_dictionary,
        translation_memory=pc.translation_memory,
        project_controller=pc,
    )
    assert tc._project_controller == pc

    # Kiểm tra gọt sạch tiền tố dòng do mô hình ảo giác
    mock_worker = MagicMock()
    tc.worker = mock_worker
    tc._active_translation_index = 0
    tc._current_index = 0
    tc.on_finished(0, "[Line 1]: Ngươi muốn gì ở ta?")
    assert tc.currentTranslation == "Ngươi muốn gì ở ta?"

    # Kiểm tra cắt sạch phần rò rỉ suy nghĩ tiếng Anh (CoT leakage)
    tc._active_translation_index = 0
    tc._current_index = 0
    tc.on_finished(0, "Em không đầu hàngEither this subtitle continues with 'Em không' or switches to...")
    assert tc.currentTranslation == "Em không đầu hàng"

    tc._active_translation_index = 0
    tc._current_index = 0
    tc.on_finished(0, "Tôi sẽ không đầu hàng. Note: Here I used 'Tôi' because...")
    assert tc.currentTranslation == "Tôi sẽ không đầu hàng."


def test_project_controller_set_is_ja_origin():
    mock_model = MagicMock()
    pc = ProjectController(subtitle_model=mock_model)
    pc._has_project = True
    assert pc.isJaOrigin is False

    signals_received = []
    pc.archetypeChanged.connect(lambda: signals_received.append("archetypeChanged"))
    pc.projectStateChanged.connect(lambda: signals_received.append("projectStateChanged"))

    pc.setIsJaOrigin(True)
    assert pc.isJaOrigin is True
    assert pc.isDirty is True
    assert "archetypeChanged" in signals_received

    # Setting same value does not re-emit
    signals_received.clear()
    pc.setIsJaOrigin(True)
    assert len(signals_received) == 0

    # Setting False updates state and emits
    pc.setIsJaOrigin(False)
    assert pc.isJaOrigin is False
    assert "archetypeChanged" in signals_received


def test_close_project_returns_to_launchpad_and_cleans_state():
    """Kiểm tra tính năng đóng dự án srt, xóa dữ liệu và trở về trạng thái khởi động."""
    from core.translation.controllers.project_controller import ProjectController
    from core.translation.models.subtitle import SubtitleModel
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "start_time": "00:00:01,000", "end_time": "00:00:02,000", "original": "Hello", "translation": ""}
    ])
    controller = ProjectController(model)
    assert controller.hasProject is True
    assert model.rowCount() == 1
    # Thực thi đóng dự án
    controller.closeProject()
    # Xác nhận toàn bộ dữ liệu phụ đề và trạng thái dự án đã được dọn sạch
    assert model.rowCount() == 0
    assert controller.hasProject is False
    assert controller.isDirty is False
    assert controller.storySummary == ""


def test_dynamic_intelligence_sync_after_project_load_and_safe_close():
    """Kiểm chứng sau khi load .aisrt, TranslationController đồng bộ động glossary/entities/TM từ ProjectController (BUG-01) và closeProject an toàn (BUG-02)."""
    mock_model = MagicMock()
    mock_model.get_all_data.return_value = [
        {"id": 1, "start_time": "00:00:01,000", "end_time": "00:00:02,000", "original": "Senpai", "translation": "Tiền bối", "status": "TRANSLATED"}
    ]
    mock_model.rowCount.return_value = 1

    pc = ProjectController(subtitle_model=mock_model)
    tc = TranslationController(subtitle_model=mock_model)
    tc.bind_intelligence(
        glossary=pc.glossary,
        entities=pc.entity_dictionary,
        translation_memory=pc.translation_memory,
        project_controller=pc,
    )
    pc.bind_translation_controller(tc)

    # Thêm thuật ngữ và lưu project
    pc.glossary.add("Senpai", "Tiền bối", ("Đàn anh",), is_auto=False)
    pc.entity_dictionary.add("Tokyo", "LOCATION", "Tokyo")
    pc.translation_memory.add("Hello", "Xin chào")

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, "sync_test.aisrt")
        pc.saveProject(save_path, "Sync Test", "Japanese", "Vietnamese")

        # Nạp lại file vào pc (thay thế hoàn toàn đối tượng glossary/entities/TM)
        pc.loadProject(save_path)

        # Kiểm chứng BUG-01: tc.glossary, tc.entities, tc.translation_memory trỏ tới đối tượng mới nạp
        assert tc.glossary.get("Senpai") is not None
        assert tc.glossary.get("Senpai").preferred_translation == "Tiền bối"
        assert len(tc.entities.match("Đi tới Tokyo")) == 1
        assert tc.translation_memory.lookup("Hello") is not None

        # Kiểm chứng BUG-02: closeProject an toàn và gọi shutdown translation worker nếu có
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        tc.worker = mock_worker
        pc.closeProject()
        assert mock_worker.cancel.called or mock_worker.wait.called


def test_dirty_project_close_confirmation_contract():
    """Kiểm tra BUG-08: Main.qml và SubtitleListView khai báo dirtyCloseConfirmDialog và handleCloseProject."""
    with open("ui/qml_translation/Main.qml", "r", encoding="utf-8") as f:
        main_qml = f.read()
    assert "dirtyCloseConfirmDialog" in main_qml
    assert "handleCloseProject" in main_qml
    assert "Đóng không lưu" in main_qml
    assert "Lưu dự án" in main_qml

    with open("ui/qml_translation/components/SubtitleListView.qml", "r", encoding="utf-8") as f:
        sub_view_qml = f.read()
    assert "handleCloseProject" in sub_view_qml
    assert "pendingCloseAction" in main_qml
    assert "EXIT_APP" in main_qml
    assert "CLOSE_PROJECT" in main_qml
    assert "forceClose" in main_qml






