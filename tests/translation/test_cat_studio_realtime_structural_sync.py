import unittest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_editing.selection_controller import SubtitleSelectionController
from ui.SubEditor import SubtitleEditorWidget
from ui.pages.translation_studio_page import TranslationStudioPage


class TestCatStudioRealtimeStructuralSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.undo_manager = GlobalUndoManager()
        self.selection_controller = SubtitleSelectionController()

        self.sub_editor = SubtitleEditorWidget()
        self.sub_editor.undo_manager = self.undo_manager
        self.sub_editor.selection_controller = self.selection_controller

        self.page_translation = TranslationStudioPage()

        # Connect realtime structural signals
        self.sub_editor.segment_split_applied.connect(self.page_translation.handle_segment_split)
        self.sub_editor.segment_split_undone.connect(self.page_translation.handle_segment_split_undo)
        self.sub_editor.segments_merge_applied.connect(self.page_translation.handle_segments_merged)
        self.sub_editor.segments_merge_undone.connect(self.page_translation.handle_segments_merge_undo)

        # Seed segments
        self.raw_segments = [
            {
                "id": "seg-1",
                "stt": "1",
                "start": "00:00:00,000",
                "end": "00:00:04,000",
                "start_ms": 0,
                "end_ms": 4000,
                "text": "Hello world first sentence",
                "original_text": "Konichiwa minna san",
                "translation": "Xin chào mọi người",
                "translation_status": "TRANSLATED",
            },
            {
                "id": "seg-2",
                "stt": "2",
                "start": "00:00:04,500",
                "end": "00:00:08,000",
                "start_ms": 4500,
                "end_ms": 8000,
                "text": "Second sentence here",
                "original_text": "Arigatou gozaimasu",
                "translation": "Cảm ơn",
                "translation_status": "ACCEPTED",
            },
            {
                "id": "seg-3",
                "stt": "3",
                "start": "00:00:08,500",
                "end": "00:00:12,000",
                "start_ms": 8500,
                "end_ms": 12000,
                "text": "Third sentence ending",
                "original_text": "Sayonara mata ashita",
                "translation": "",
                "translation_status": "PENDING",
            },
        ]
        self.sub_editor.all_segments = [s.copy() for s in self.raw_segments]
        self.page_translation.load_subtitles_from_studio(self.sub_editor.all_segments, selected_indices=[0, 1, 2])

    def test_tc_split_001_realtime_split_sync(self):
        """TC-SPLIT-001: Cắt câu 1 trên Timeline -> CAT Studio tức thời chia đôi với STT và status chuẩn."""
        self.assertEqual(self.page_translation.subtitle_model.rowCount(), 3)

        self.sub_editor.current_index = 0
        self.sub_editor.trigger_split(2000)

        # Kiểm tra SubEditor
        self.assertEqual(len(self.sub_editor.all_segments), 4)
        self.assertEqual(self.sub_editor.all_segments[0]["end_ms"], 2000)
        self.assertEqual(self.sub_editor.all_segments[1]["start_ms"], 2000)

        # Kiểm tra SubtitleModel của CAT Studio
        model = self.page_translation.subtitle_model
        self.assertEqual(model.rowCount(), 4)

        cat_rows = model.get_all_data()
        # Row 0
        self.assertEqual(cat_rows[0]["index"], 1)
        self.assertEqual(cat_rows[0]["segment_id"], "seg-1")
        self.assertEqual(cat_rows[0]["translation"], "")
        self.assertEqual(cat_rows[0]["status"], "PENDING")
        self.assertEqual(cat_rows[0]["end_time"], "00:00:02,000")

        # Row 1
        self.assertEqual(cat_rows[1]["index"], 2)
        self.assertTrue(bool(cat_rows[1]["segment_id"]))
        self.assertNotEqual(cat_rows[1]["segment_id"], "seg-1")
        self.assertEqual(cat_rows[1]["translation"], "")
        self.assertEqual(cat_rows[1]["status"], "PENDING")
        self.assertEqual(cat_rows[1]["start_time"], "00:00:02,000")

        # Cả 2 câu con ghép lại bằng original ban đầu
        self.assertEqual(
            f"{cat_rows[0]['original']} {cat_rows[1]['original']}".strip(),
            "Konichiwa minna san",
        )

        # Row 2 & 3 giữ nguyên và được đánh lại STT
        self.assertEqual(cat_rows[2]["index"], 3)
        self.assertEqual(cat_rows[2]["segment_id"], "seg-2")
        self.assertEqual(cat_rows[3]["index"], 4)
        self.assertEqual(cat_rows[3]["segment_id"], "seg-3")

    def test_tc_split_undo_001_undo_and_redo_split_sync(self):
        """TC-SPLIT-UNDO-001: Hoàn tác cắt (Ctrl+Z) phục hồi nguyên trạng; Làm lại (Ctrl+Y) tách lại chuẩn xác."""
        self.sub_editor.current_index = 0
        self.sub_editor.trigger_split(2000)
        self.assertEqual(self.page_translation.subtitle_model.rowCount(), 4)

        # Undo
        self.sub_editor.undo_manager.undo()
        self.assertEqual(len(self.sub_editor.all_segments), 3)

        model = self.page_translation.subtitle_model
        self.assertEqual(model.rowCount(), 3)
        cat_rows = model.get_all_data()
        self.assertEqual(cat_rows[0]["index"], 1)
        self.assertEqual(cat_rows[0]["segment_id"], "seg-1")
        self.assertEqual(cat_rows[0]["original"], "Konichiwa minna san")
        self.assertEqual(cat_rows[0]["translation"], "Xin chào mọi người")
        self.assertEqual(cat_rows[0]["status"], "TRANSLATED")
        self.assertEqual(cat_rows[1]["index"], 2)
        self.assertEqual(cat_rows[2]["index"], 3)

        # Redo
        self.sub_editor.undo_manager.redo()
        self.assertEqual(len(self.sub_editor.all_segments), 4)
        self.assertEqual(model.rowCount(), 4)
        cat_rows_redo = model.get_all_data()
        self.assertEqual(cat_rows_redo[0]["index"], 1)
        self.assertEqual(cat_rows_redo[1]["index"], 2)
        self.assertEqual(cat_rows_redo[1]["status"], "PENDING")

    def test_tc_merge_001_realtime_merge_sync(self):
        """TC-MERGE-001: Gộp câu 1 và câu 2 -> CAT Studio hợp nhất thành 1 dòng, ghép translation và status EDITED."""
        self.sub_editor.current_index = 0
        self.sub_editor.trigger_merge()

        # Kiểm tra SubEditor
        self.assertEqual(len(self.sub_editor.all_segments), 2)

        # Kiểm tra SubtitleModel
        model = self.page_translation.subtitle_model
        self.assertEqual(model.rowCount(), 2)

        cat_rows = model.get_all_data()
        self.assertEqual(cat_rows[0]["index"], 1)
        self.assertEqual(cat_rows[0]["segment_id"], "seg-1")
        self.assertEqual(cat_rows[0]["original"], "Konichiwa minna san Arigatou gozaimasu")
        self.assertEqual(cat_rows[0]["translation"], "Xin chào mọi người Cảm ơn")
        self.assertEqual(cat_rows[0]["status"], "EDITED")
        self.assertEqual(cat_rows[0]["end_time"], "00:00:08,000")

        # Row kế tiếp đánh lại STT thành 2
        self.assertEqual(cat_rows[1]["index"], 2)
        self.assertEqual(cat_rows[1]["segment_id"], "seg-3")

    def test_tc_merge_undo_001_undo_and_redo_merge_sync(self):
        """TC-MERGE-UNDO-001: Hoàn tác gộp (Ctrl+Z) tách trả lại 2 dòng với bản dịch độc lập."""
        self.sub_editor.current_index = 0
        self.sub_editor.trigger_merge()
        self.assertEqual(self.page_translation.subtitle_model.rowCount(), 2)

        # Undo
        self.sub_editor.undo_manager.undo()
        self.assertEqual(len(self.sub_editor.all_segments), 3)

        model = self.page_translation.subtitle_model
        self.assertEqual(model.rowCount(), 3)
        cat_rows = model.get_all_data()
        self.assertEqual(cat_rows[0]["segment_id"], "seg-1")
        self.assertEqual(cat_rows[0]["translation"], "Xin chào mọi người")
        self.assertEqual(cat_rows[1]["segment_id"], "seg-2")
        self.assertEqual(cat_rows[1]["translation"], "Cảm ơn")
        self.assertEqual(cat_rows[2]["segment_id"], "seg-3")

        # Redo
        self.sub_editor.undo_manager.redo()
        self.assertEqual(len(self.sub_editor.all_segments), 2)
        self.assertEqual(model.rowCount(), 2)

    def test_tc_overwrite_guard_compat(self):
        """TC-OVERWRITE-GUARD-COMPAT: Xuất phụ đề sang Studio sau khi cắt/gộp không bị chặn bởi Overwrite Guard."""
        # 1. Cắt câu 1
        self.sub_editor.current_index = 0
        self.sub_editor.trigger_split(2000)

        # 2. Giả lập CAT dịch xong câu con thứ 2
        model = self.page_translation.subtitle_model
        model.update_translation(1, "Nửa câu sau đã dịch", "TRANSLATED")

        # 3. Xuất ngược lại Studio
        self.page_translation.export_subtitles_to_studio(self.sub_editor.all_segments)

        # Kiểm tra câu con thứ 2 trên timeline nhận được bản dịch mới
        self.assertEqual(self.sub_editor.all_segments[1]["translation"], "Nửa câu sau đã dịch")
        self.assertEqual(self.sub_editor.all_segments[1]["translation_status"], "TRANSLATED")

    def test_tc_isolation_guard_non_cat_subtitles(self):
        """TC-ISOLATION-GUARD: Cắt câu KHÔNG nằm trong danh sách CAT Studio -> CAT Studio an toàn tuyệt đối."""
        # Thêm câu 4 vào sub_editor nhưng không nạp vào CAT
        isolated_seg = {
            "id": "isolated-999",
            "stt": "4",
            "start": "00:00:15,000",
            "end": "00:00:19,000",
            "start_ms": 15000,
            "end_ms": 19000,
            "text": "Isolated segment not in CAT",
        }
        self.sub_editor.all_segments.append(isolated_seg)
        cat_count_before = self.page_translation.subtitle_model.rowCount()

        # Cắt câu cô lập này
        self.sub_editor.current_index = 3
        self.sub_editor.trigger_split(17000)

        # SubEditor tăng lên 5
        self.assertEqual(len(self.sub_editor.all_segments), 5)
        # CAT Studio vẫn giữ nguyên số lượng và không gặp ngoại lệ
        self.assertEqual(self.page_translation.subtitle_model.rowCount(), cat_count_before)

    def test_tc_llm_guard_cancel_on_split_or_merge(self):
        """TC-LLM-GUARD-CANCEL: Hủy an toàn tiến trình dịch AI ngầm nếu câu bị cắt/gộp đang được dịch."""
        # Mock translation_controller
        tc = self.page_translation.translation_controller
        tc.is_busy = MagicMock(return_value=True)
        tc._active_translation_index = 0
        tc.cancelTranslation = MagicMock()

        # Cắt câu 0 đang dịch
        self.sub_editor.current_index = 0
        self.sub_editor.trigger_split(2000)

        # Xác nhận cancelTranslation đã được gọi
        tc.cancelTranslation.assert_called_once()


if __name__ == "__main__":
    unittest.main()
