import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange
from ui.theme import Theme

from core.subtitle_editing.selection_controller import (
    SelectionSource,
    SubtitleSelectionController,
)
from core.timeline.timeline_controller import TimelineController
from core.timeline.timeline_data_provider import TimelineDataProvider
from player.video_player import VideoPlayerWidget
from ui.SubEditor import SubtitleEditorWidget
from ui.timeline.timeline_widget import TimelineWidget


_app = QApplication.instance() or QApplication([])


class TestPlaybackSyncFixes(unittest.TestCase):
    def setUp(self):
        self.sub_editor = SubtitleEditorWidget()
        self.sub_editor.all_segments = [
            {"stt": 1, "id": "seg_1", "start": "00:00:00,000", "end": "00:00:05,000", "start_ms": 0, "end_ms": 5000, "text": "First"},
            {"stt": 2, "id": "seg_2", "start": "00:00:10,000", "end": "00:00:16,000", "start_ms": 10000, "end_ms": 16000, "text": "Second"},
            {"stt": 3, "id": "seg_3", "start": "00:00:20,000", "end": "00:00:25,000", "start_ms": 20000, "end_ms": 25000, "text": "Third"},
        ]
        self.sub_editor._visible_source_indices = [0, 1, 2]
        self.sub_editor.render_page()

    def tearDown(self):
        self.sub_editor.close()
        self.sub_editor.deleteLater()

    def test_tc_sync_01_highlight_row_by_stt_updates_current_editor_and_selection(self):
        """TC-SYNC-01: highlight_row_by_stt updates current subtitle editor and notifies selection_controller."""
        selection_ctrl = MagicMock(spec=SubtitleSelectionController)
        self.sub_editor.selection_controller = selection_ctrl

        self.sub_editor.highlight_row_by_stt(2)

        self.assertEqual(self.sub_editor.current_index, 1)
        self.assertIn("#2", self.sub_editor.current_editor.lbl_title.text())
        selection_ctrl.select.assert_called_once_with(1, "seg_2", SelectionSource.PLAYBACK)

        # Highlight next sentence #3
        selection_ctrl.reset_mock()
        self.sub_editor.highlight_row_by_stt(3)
        self.assertEqual(self.sub_editor.current_index, 2)
        self.assertIn("#3", self.sub_editor.current_editor.lbl_title.text())
        selection_ctrl.select.assert_called_once_with(2, "seg_3", SelectionSource.PLAYBACK)

    def test_tc_sync_02_video_player_segment_bounds_release_and_global_time(self):
        """TC-SYNC-02: toggle_playback and position_changed release _segment_bounds when leaving segment."""
        player = VideoPlayerWidget()
        try:
            player._segment_bounds = (10000, 16000)
            player._segment_playback_active = False

            # toggle_playback releases segment focus
            player.toggle_playback()
            self.assertIsNone(player._segment_bounds)

            # position_changed outside bounds releases _segment_bounds
            player._segment_bounds = (10000, 16000)
            player._segment_playback_active = False
            player.position_changed(20000)
            self.assertIsNone(player._segment_bounds)
        finally:
            player.close()
            player.deleteLater()

    def test_tc_play_01_global_selection_ignores_playback_source(self):
        """TC-PLAY-01: _on_global_selection_changed ignores PLAYBACK source to prevent pausing video."""
        from ui.Gui import MainWindow
        win = MainWindow.__new__(MainWindow)
        win.sub_editor = SimpleNamespace(
            all_segments=[
                {"start": "00:00:10,000", "end": "00:00:16,000", "start_ms": 10000, "end_ms": 16000, "text": "Sub"}
            ]
        )
        focused_calls = []
        win._on_segment_focused = lambda s, e, auto_play=False: focused_calls.append((s, e, auto_play))

        # PLAYBACK source must be ignored
        MainWindow._on_global_selection_changed(win, 0, "seg_id", SelectionSource.PLAYBACK)
        self.assertEqual(len(focused_calls), 0)

        # EDITOR source must trigger segment preview
        MainWindow._on_global_selection_changed(win, 0, "seg_id", SelectionSource.EDITOR)
        self.assertEqual(len(focused_calls), 1)
        self.assertEqual(focused_calls[0], (10000, 16000, False))

    def test_tc_wmv_format_detection(self):
        """TC-WMV-01: Detects WMV / ASF extension and binary header."""
        player = VideoPlayerWidget()
        try:
            self.assertTrue(player._is_legacy_wmv_format("test.wmv"))
            self.assertTrue(player._is_legacy_wmv_format("video.asf"))
            self.assertFalse(player._is_legacy_wmv_format("video.mp4"))

            # Test ASF binary header even if named .mp4
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(b"\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa\x00\x62\xce\x6c" + b"extra_bytes")
                temp_path = f.name
            try:
                self.assertTrue(player._is_legacy_wmv_format(temp_path))
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        finally:
            player.close()
            player.deleteLater()

    def test_tc_player_a_01_dual_time_display(self):
        """TC-PLAYER-A-01: Video player displays dual time with active subtitle duration and Cyan style."""
        player = VideoPlayerWidget()
        try:
            player.player.duration = MagicMock(return_value=60000)
            
            # Position at 12s -> in seg_2 (10s - 16s, duration 6.0s)
            player._current_playback_sub = {"stt": 2, "start_ms": 10000, "end_ms": 16000, "text": "Second"}
            player.update_time_label(12000)
            self.assertIn("00:12 / 01:00", player.lbl_time.text())
            self.assertIn("[Sub #2: 6.0s]", player.lbl_time.text())
            self.assertIn(Theme.CYAN, player.lbl_time.styleSheet())

            # Position in gap at 7s -> no subtitle
            player._current_playback_sub = None
            player.update_time_label(7000)
            self.assertEqual(player.lbl_time.text(), "00:07 / 01:00")
            self.assertEqual(player.lbl_time.styleSheet(), "")
        finally:
            player.close()
            player.deleteLater()

    def test_tc_ctrl_select_02_multi_selection_retention(self):
        """TC-CTRL-SELECT-02: Holding Ctrl/Shift keeps multi-row selection and updates title and scan button text."""
        # Select row 0 normally first
        self.sub_editor._on_row_selected(0, 0)
        self.assertEqual(self.sub_editor.current_index, 0)
        self.assertEqual(self.sub_editor.current_editor.btn_scan.text(), "Quét lại")

        # Select row 0 and 1 in table
        self.sub_editor.table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 4), True)

        with patch.object(QApplication, "keyboardModifiers", return_value=Qt.ControlModifier):
            self.sub_editor._on_row_selected(1, 0)

        # Multi-selection is preserved (rows 0 and 1)
        selected = self.sub_editor.get_selected_or_current_indices()
        self.assertEqual(selected, [0, 1])
        self.assertEqual(self.sub_editor.current_index, 1)
        self.assertIn("#2 (2 câu)", self.sub_editor.current_editor.lbl_title.text())
        self.assertEqual(self.sub_editor.current_editor.btn_scan.text(), "Quét lại (2)")

        # Normal selection without Ctrl restores single row selection and button text
        with patch.object(QApplication, "keyboardModifiers", return_value=Qt.NoModifier):
            self.sub_editor._on_row_selected(2, 0)

        self.assertEqual(self.sub_editor.current_index, 2)
        self.assertEqual(self.sub_editor.current_editor.btn_scan.text(), "Quét lại")

    def test_tc_batch_scan_requested_from_button_and_context_menu(self):
        """TC-BATCH-SCAN-03: Scan button emits batch_scan_requested when multi-selected."""
        batch_emitted = []
        self.sub_editor.batch_scan_requested.connect(lambda lst: batch_emitted.append(lst))

        # Mock multi-selection [0, 2]
        self.sub_editor._get_selected_source_indices = MagicMock(return_value=[0, 2])
        self.sub_editor.current_index = 0

        self.sub_editor._on_current_editor_scan_requested()
        self.assertEqual(len(batch_emitted), 1)
        self.assertEqual(batch_emitted[0], [0, 2])

    def test_tc_batch_segment_scan_worker_run(self):
        """TC-BATCH-SCAN-04: BatchSegmentScanWorker processes segments sequentially and emits signals."""
        from workers.SegmentScanWorker import BatchSegmentScanWorker
        from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
        from core.subtitle_generation.subtitle_generation_result import SubtitleGenerationResult, WhisperSegmentResult

        mock_whisper = MagicMock()
        mock_result = SubtitleGenerationResult(
            batch_id="scan_seg_1",
            error=None,
            segments=[WhisperSegmentResult(start_ms=0, end_ms=2000, text="Hello world")],
        )
        mock_whisper.transcribe_batch.return_value = mock_result

        req = SubtitleGenerationRequest(
            request_id="req1",
            project_id="p1",
            source_fingerprint="fp",
            video_path="test.mp4",
            model_size="base",
            compute_type="int8",
            language="ja",
            use_vad=True,
            min_silence_ms=500,
            word_timestamps=False,
        )

        segments_data = [
            {"id": "seg_1", "start_ms": 0, "end_ms": 2000},
            {"id": "seg_2", "start_ms": 3000, "end_ms": 5000},
        ]

        worker = BatchSegmentScanWorker(segments_data, req, mock_whisper)
        progress_calls = []
        completed_calls = []
        finished_calls = []

        worker.progress_signal.connect(lambda c, t, m: progress_calls.append((c, t, m)))
        worker.segment_completed_signal.connect(lambda sid, txt: completed_calls.append((sid, txt)))
        worker.finished_signal.connect(lambda: finished_calls.append(True))

        worker.run()

        self.assertEqual(len(progress_calls), 2)
        self.assertEqual(len(completed_calls), 2)
        self.assertEqual(completed_calls[0], ("seg_1", "Hello world"))
        self.assertEqual(completed_calls[1], ("seg_2", "Hello world"))
        self.assertEqual(len(finished_calls), 1)

    def test_tc_segment_scan_worker_transcribes_with_configured_language(self):
        """Xác thực SegmentScanWorker truyền đúng language="ja" từ request vào FasterWhisperService.transcribe_batch."""
        from workers.SegmentScanWorker import SegmentScanWorker
        from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
        from core.subtitle_generation.subtitle_generation_result import SubtitleGenerationResult, WhisperSegmentResult

        mock_whisper = MagicMock()
        mock_result = SubtitleGenerationResult(
            batch_id="scan_seg_1",
            error=None,
            segments=[WhisperSegmentResult(start_ms=1000, end_ms=2000, text="こんにちは")],
        )
        mock_whisper.transcribe_batch.return_value = mock_result

        req = SubtitleGenerationRequest(
            request_id="scan_1",
            project_id="p1",
            source_fingerprint="fp",
            video_path="test.mp4",
            model_size="large-v3-turbo",
            compute_type="int8",
            language="ja",
            use_vad=True,
            min_silence_ms=500,
            word_timestamps=False,
        )

        worker = SegmentScanWorker("seg_1", 1000, 2000, req, mock_whisper)
        finished_results = []
        worker.finished_signal.connect(lambda sid, txt: finished_results.append((sid, txt)))

        worker.run()

        mock_whisper.load_model.assert_called_once_with("large-v3-turbo", "int8")
        self.assertTrue(mock_whisper.transcribe_batch.called)
        called_req = mock_whisper.transcribe_batch.call_args[0][0]
        self.assertEqual(called_req.language, "ja")
        self.assertEqual(finished_results, [("seg_1", "こんにちは")])

    def test_tc_segment_scan_worker_timing_mode(self):
        """Xác thực SegmentScanWorker ở chế độ timing xuất timing_finished_signal hoặc NO_SPEECH_DETECTED."""
        from workers.SegmentScanWorker import SegmentScanWorker
        from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
        from core.subtitle_generation.subtitle_generation_result import SubtitleGenerationResult, WhisperSegmentResult

        mock_whisper = MagicMock()
        mock_result = SubtitleGenerationResult(
            batch_id="scan_seg_1",
            error=None,
            segments=[
                WhisperSegmentResult(start_ms=1200, end_ms=1500, text="hello"),
                WhisperSegmentResult(start_ms=1600, end_ms=1950, text="world"),
            ],
        )
        mock_whisper.transcribe_batch.return_value = mock_result

        req = SubtitleGenerationRequest(
            request_id="scan_1",
            project_id="p1",
            source_fingerprint="fp",
            video_path="test.mp4",
            model_size="large-v3-turbo",
            compute_type="int8",
            language="ja",
            use_vad=True,
            min_silence_ms=500,
            word_timestamps=False,
        )

        worker = SegmentScanWorker("seg_1", 1000, 2000, req, mock_whisper, scan_mode="timing")
        timing_results = []
        finished_results = []
        errors = []
        worker.timing_finished_signal.connect(lambda sid, s, e: timing_results.append((sid, s, e)))
        worker.finished_signal.connect(lambda sid, txt: finished_results.append((sid, txt)))
        worker.error_signal.connect(lambda sid, err: errors.append((sid, err)))

        worker.run()
        self.assertEqual(timing_results, [("seg_1", 1200, 1950)])
        self.assertEqual(finished_results, [])
        self.assertEqual(errors, [])

        # Trường hợp không phát hiện giọng nói
        mock_whisper.transcribe_batch.return_value = SubtitleGenerationResult(
            batch_id="scan_seg_2", error=None, segments=[]
        )
        worker_empty = SegmentScanWorker("seg_2", 1000, 2000, req, mock_whisper, scan_mode="timing")
        empty_timing = []
        empty_errors = []
        worker_empty.timing_finished_signal.connect(lambda sid, s, e: empty_timing.append((sid, s, e)))
        worker_empty.error_signal.connect(lambda sid, err: empty_errors.append((sid, err)))
        worker_empty.run()
        self.assertEqual(empty_timing, [])
        self.assertEqual(empty_errors, [("seg_2", "NO_SPEECH_DETECTED")])

    def test_tc_context_aware_rescan_tooltip_and_routing(self):
        """Xác thực tooltip nút Quét lại thay đổi theo nội dung và MainWindow phân nhánh đúng scan_mode."""
        from ui.SubEditor import SubtitleEditorWidget
        from ui.Gui import MainWindow

        editor = SubtitleEditorWidget()
        editor.all_segments = [
            {"id": "s1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "[ Chưa có nội dung ]"},
            {"id": "s2", "start": "00:00:04,000", "end": "00:00:06,000", "text": "Câu thoại đã có"},
        ]
        editor.select_segment(0)
        self.assertEqual(editor.current_editor.btn_scan.toolTip(), "Quét lại mốc thời gian (Timing) đoạn này")

        editor.select_segment(1)
        self.assertEqual(editor.current_editor.btn_scan.toolTip(), "Nhận diện lại chữ (ASR) đoạn này")

        # Kiểm tra MainWindow phân nhánh scan_mode
        win = MainWindow.__new__(MainWindow)
        win.sub_editor = editor
        win.project_service = MagicMock()
        win.project_service.current_project = MagicMock(project_id="p1", video_path="v.mp4")
        win.current_vid = "v.mp4"
        win.generation_panel = MagicMock()
        win.generation_panel._timing_settings.return_value = {"model_size": "large-v3-turbo"}
        win.subtitle_whisper_service = MagicMock()
        win.undo_manager = MagicMock()

        with patch("workers.SegmentScanWorker.SegmentScanWorker.start"):
            # Quét câu s1 (chưa có sub) -> scan_mode='timing'
            win._on_segment_scan_requested("s1", 1000, 3000)
            self.assertEqual(win.scan_worker.scan_mode, "timing")

            # Quét câu s2 (đã có sub) -> scan_mode='asr'
            win._on_segment_scan_requested("s2", 4000, 6000)
            self.assertEqual(win.scan_worker.scan_mode, "asr")

            # Thử nghiệm timing hoàn tất -> tạo EditTimingCommand và live_edit_applied
            win.sub_editor.live_edit_applied = MagicMock()
            win._on_segment_timing_scan_finished("s1", 1200, 2800)
            self.assertTrue(win.undo_manager.push.called)
            self.assertTrue(win.sub_editor.live_edit_applied.emit.called)

    def test_tc_clean_01_no_ai_translate_in_editor(self):
        """TC-CLEAN-01 & TC-CLEAN-02: SubtitleEditorWidget and MainWindow have no AI translation signals or handlers."""
        from ui.Gui import MainWindow
        self.assertFalse(hasattr(self.sub_editor, "request_ai_translate"))
        self.assertFalse(hasattr(self.sub_editor, "ai_translate_btn"))
        self.assertFalse(hasattr(self.sub_editor, "_on_ai_translate_clicked"))
        self.assertFalse(hasattr(MainWindow, "_on_ai_translate_requested"))

    def test_tc_tl_gen_01_and_02_timeline_batch_scan_button(self):
        """TC-TL-GEN-01 & TC-TL-GEN-02: Timeline Gen Sub button state and text dynamically updates with selection."""
        from ui.Gui import MainWindow
        from PySide6.QtWidgets import QPushButton

        win = MainWindow.__new__(MainWindow)
        win.btn_timeline_batch_scan = QPushButton("🎙️ Gen Sub đã chọn")
        win.btn_timeline_batch_scan.setEnabled(False)
        win.sub_editor = self.sub_editor

        # TC-TL-GEN-01: Default state (no selection)
        win.sub_editor.current_index = -1
        win.sub_editor._get_selected_source_indices = MagicMock(return_value=[])
        win.sub_editor.get_selected_or_current_indices = MagicMock(return_value=[])
        win._update_timeline_batch_scan_button()

        self.assertFalse(win.btn_timeline_batch_scan.isEnabled())
        self.assertEqual(win.btn_timeline_batch_scan.text(), "🎙️ Gen Sub đã chọn")

        # TC-TL-GEN-02: 1 sentence selected
        win.sub_editor.get_selected_or_current_indices = MagicMock(return_value=[0])
        win._update_timeline_batch_scan_button()
        self.assertTrue(win.btn_timeline_batch_scan.isEnabled())
        self.assertEqual(win.btn_timeline_batch_scan.text(), "🎙️ Gen Sub (1 câu)")

        # TC-TL-GEN-02: 3 sentences selected
        win.sub_editor._get_selected_source_indices = MagicMock(return_value=[0, 1, 2])
        win._update_timeline_batch_scan_button()
        self.assertTrue(win.btn_timeline_batch_scan.isEnabled())
        self.assertEqual(win.btn_timeline_batch_scan.text(), "🎙️ Gen Sub (3 câu)")

        # Clicking calls _on_batch_segment_scan_requested
        batch_scan_called = []
        win._on_batch_segment_scan_requested = lambda idxs: batch_scan_called.append(idxs)
        win._on_timeline_batch_scan_clicked()
        self.assertEqual(batch_scan_called, [[0, 1, 2]])

    def test_tc_progress_reset_01_subtitle_generation_panel_finish_resets(self):
        """TC-PROGRESS-RESET-01: SubtitleGenerationPanel._on_finish resets progress_bar to 0."""
        from ui.subtitle_generation_panel import SubtitleGenerationPanel
        from PySide6.QtCore import QTimer

        panel = SubtitleGenerationPanel(MagicMock())
        try:
            panel.generation_service.is_running = False
            panel.generation_service.checkpoint_manager.load_checkpoint.return_value = None
            panel._is_range_generation = False
            panel.progress_bar.setValue(50)
            
            with patch.object(QTimer, "singleShot") as mock_timer:
                panel._on_finish()
                self.assertEqual(panel.progress_bar.value(), 100)
                # Verify singleShot was called with 800ms to reset to 0
                self.assertTrue(mock_timer.called)
                args = mock_timer.call_args[0]
                self.assertEqual(args[0], 800)
                # Execute callback
                args[1]()
                self.assertEqual(panel.progress_bar.value(), 0)
        finally:
            panel.close()
            panel.deleteLater()

    def test_tc_progress_reset_02_interactive_generation_finished_resets(self):
        """TC-PROGRESS-RESET-02: MainWindow._on_interactive_generation_finished resets all progress bars."""
        from ui.Gui import MainWindow
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QProgressBar

        win = MainWindow.__new__(MainWindow)
        win.timeline_widget = MagicMock()
        win.subtitle_generation_service = MagicMock()
        win.subtitle_generation_service.current_request = None
        win.subtitle_generation_service.current_checkpoint = None
        win._on_generation_batch_sync = MagicMock(return_value=None)
        win.generation_panel = MagicMock()
        win.progress_bar = QProgressBar()
        win.progress_bar.setValue(100)
        win.page_dashboard = MagicMock()
        win.page_dashboard.quick_progress = QProgressBar()
        win.page_dashboard.quick_progress.setValue(100)

        with patch.object(QTimer, "singleShot") as mock_timer:
            win._on_interactive_generation_finished()
            self.assertTrue(mock_timer.called)
            args = mock_timer.call_args[0]
            self.assertEqual(args[0], 800)
            self.assertEqual(args[1], win._reset_generation_progress_bars)

        # Test helper directly
        win._reset_generation_progress_bars()
        self.assertEqual(win.progress_bar.value(), 0)
        self.assertEqual(win.page_dashboard.quick_progress.value(), 0)

    def test_tc_progress_reset_03_timing_state_changed_resets(self):
        """TC-PROGRESS-RESET-03: MainWindow._on_timing_state_changed handles READY, COMPLETED, FAILED."""
        from ui.Gui import MainWindow
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QProgressBar

        win = MainWindow.__new__(MainWindow)
        win.generation_panel = MagicMock()
        win.generation_panel.progress_bar = QProgressBar()
        win.progress_bar = QProgressBar()
        win.page_dashboard = MagicMock()
        win.page_dashboard.quick_progress = QProgressBar()

        # COMPLETED state sets to 100 and schedules 800ms reset
        with patch.object(QTimer, "singleShot") as mock_timer:
            win._on_timing_state_changed("COMPLETED", "Done")
            self.assertEqual(win.generation_panel.progress_bar.value(), 100)
            self.assertEqual(win.progress_bar.value(), 100)
            self.assertEqual(win.page_dashboard.quick_progress.value(), 100)
            self.assertTrue(mock_timer.called)
            self.assertEqual(mock_timer.call_args[0][0], 800)

        # FAILED state resets immediately
        win.progress_bar.setValue(50)
        win._on_timing_state_changed("FAILED", "Error")
        self.assertEqual(win.progress_bar.value(), 0)

    def test_tc_focus_segment_positions_without_playing(self):
        """focus_segment sets position and bounds with playback_active=False without calling play."""
        player = VideoPlayerWidget()
        try:
            player.player = MagicMock()
            player.cancel_segment_playback = MagicMock()
            player.set_position = MagicMock()
            player.update_time_label = MagicMock()

            player.focus_segment(1000, 5000)

            player.cancel_segment_playback.assert_called_once_with(pause=True)
            player.set_position.assert_called_once_with(1000)
            self.assertEqual(player._segment_bounds, (1000, 5000))
            self.assertFalse(player._segment_playback_active)
            player.player.play.assert_not_called()
        finally:
            player.close()
            player.deleteLater()

    def test_tc_on_segment_focused_routes_auto_play_flag(self):
        """_on_segment_focused routes to focus_segment when auto_play=False, play_segment when True."""
        from ui.Gui import MainWindow
        win = MainWindow.__new__(MainWindow)
        win.video_player = MagicMock()
        win.timeline_widget = None

        MainWindow._on_segment_focused(win, 2000, 6000, auto_play=False)
        win.video_player.focus_segment.assert_called_once_with(2000, 6000)
        win.video_player.play_segment.assert_not_called()

        win.video_player.reset_mock()
        MainWindow._on_segment_focused(win, 2000, 6000, auto_play=True)
        win.video_player.play_segment.assert_called_once_with(2000, 6000)
        win.video_player.focus_segment.assert_not_called()

    def test_tc_sub_editor_select_segment_ui_focuses_text_edit(self):
        """_select_segment_ui gives keyboard focus to current_editor.text_edit."""
        with patch.object(self.sub_editor.current_editor.text_edit, "setFocus") as mock_focus:
            self.sub_editor._select_segment_ui(0)
            mock_focus.assert_called_once()

    def test_tc_rescan_passes_audio_boost_flag_when_checked(self):
        """Xác thực checkbox Tăng âm truyền đúng cờ audio_boost=True vào SubtitleGenerationRequest khi quét lại."""
        from ui.Gui import MainWindow

        editor = self.sub_editor
        editor.all_segments = [
            {"id": "s1", "start": "00:00:01,000", "end": "00:00:03,000", "text": "Câu thoại test"},
        ]
        editor.select_segment(0)
        self.assertTrue(hasattr(editor.current_editor, "chk_boost_audio"))
        self.assertFalse(editor.current_editor.chk_boost_audio.isChecked())

        win = MainWindow.__new__(MainWindow)
        win.sub_editor = editor
        win.project_service = MagicMock()
        win.project_service.current_project = MagicMock(project_id="p1", video_path="v.mp4")
        win.current_vid = "v.mp4"
        win.generation_panel = MagicMock()
        win.generation_panel._timing_settings.return_value = {"model_size": "large-v3-turbo"}
        win.subtitle_whisper_service = MagicMock()

        # Khi checkbox chưa tick -> audio_boost=False
        with patch("workers.SegmentScanWorker.SegmentScanWorker.start"):
            win._on_segment_scan_requested("s1", 1000, 3000)
            self.assertFalse(win.scan_worker.request.audio_boost)

        # Khi checkbox được tick -> audio_boost=True
        editor.current_editor.chk_boost_audio.setChecked(True)
        with patch("workers.SegmentScanWorker.SegmentScanWorker.start"):
            win._on_segment_scan_requested("s1", 1000, 3000)
            self.assertTrue(win.scan_worker.request.audio_boost)

    def test_tc_extract_batch_audio_applies_volume_filter(self):
        """Xác thực FasterWhisperService._extract_batch_audio bổ sung '-af volume=2.0' khi audio_boost=True."""
        from core.subtitle_generation.faster_whisper_service import FasterWhisperService
        from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
        from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
        import shutil

        req_normal = SubtitleGenerationRequest(
            request_id="r1", project_id="p1", source_fingerprint="fp", video_path="v.mp4",
            model_size="small", compute_type="int8", language="vi", use_vad=True, min_silence_ms=500,
            word_timestamps=False, audio_boost=False
        )
        req_boost = SubtitleGenerationRequest(
            request_id="r2", project_id="p1", source_fingerprint="fp", video_path="v.mp4",
            model_size="small", compute_type="int8", language="vi", use_vad=True, min_silence_ms=500,
            word_timestamps=False, audio_boost=True
        )
        batch = SubtitleGenerationBatch("b1", 1000, 3000, "RUNNING", 1, "", "")

        with patch("subprocess.run") as mock_run:
            _, tmp_normal = FasterWhisperService._extract_batch_audio(req_normal, batch)
            shutil.rmtree(tmp_normal, ignore_errors=True)
            cmd_normal = mock_run.call_args[0][0]
            self.assertNotIn("-af", cmd_normal)

        with patch("subprocess.run") as mock_run:
            _, tmp_boost = FasterWhisperService._extract_batch_audio(req_boost, batch)
            shutil.rmtree(tmp_boost, ignore_errors=True)
            cmd_boost = mock_run.call_args[0][0]
            self.assertIn("-af", cmd_boost)
            self.assertIn("volume=2.0", cmd_boost)

    def test_tc_current_editor_prev_next_buttons_emit_signals(self):
        """Xác thực 2 nút < và > trên CurrentSubtitleEditor phát đúng signal và gọi select_previous/select_next."""
        editor = self.sub_editor
        editor.all_segments = [
            {"id": "1", "start": "00:00:00,000", "end": "00:00:02,000", "text": "Câu 1"},
            {"id": "2", "start": "00:00:02,000", "end": "00:00:04,000", "text": "Câu 2"},
        ]
        editor.select_segment(0)

        # Bấm nút > phải chuyển sang câu 2
        editor.current_editor.btn_next.click()
        self.assertEqual(editor.current_index, 1)

        # Bấm nút < phải quay lại câu 1
        editor.current_editor.btn_prev.click()
        self.assertEqual(editor.current_index, 0)

    def test_tc_inspector_preset_syncs_with_selected_segment(self):
        """Xác thực tab Style hiển thị và thay đổi preset cho câu được chọn."""
        from ui.subtitle_inspector_panel import SubtitleInspectorPanel
        from ui.Gui import MainWindow

        win = MainWindow.__new__(MainWindow)
        win.sub_editor = self.sub_editor
        win.sub_editor.all_segments = [
            {"id": "1", "start": "00:00:00,000", "end": "00:00:02,000", "text": "Câu 1", "style_preset": "normal"},
            {"id": "2", "start": "00:00:02,000", "end": "00:00:04,000", "text": "Câu 2", "style_preset": "loud"},
        ]
        win.inspector_panel = SubtitleInspectorPanel()
        try:
            win.inspector_panel.preset_changed.connect(win._on_inspector_preset_changed)

            # Chọn câu 2 -> Inspector phải hiển thị 'loud'
            win.sub_editor.current_index = 1
            win._on_segment_focused(2000, 4000)
            self.assertEqual(win.inspector_panel.cmb_preset.currentData(), "loud")

            # Đổi preset trên inspector sang 'whisper' -> all_segments câu 2 đổi thành 'whisper'
            win.inspector_panel.cmb_preset.setCurrentIndex(win.inspector_panel.cmb_preset.findData("whisper"))
            self.assertEqual(win.sub_editor.all_segments[1].get("style_preset"), "whisper")
        finally:
            win.inspector_panel.close()
            win.inspector_panel.deleteLater()

    def test_tc_project_style_and_preset_persistence_roundtrip(self):
        """Xác thực lưu và khôi phục subtitle_style + segment_styles qua ProjectService và SubtitleInspectorPanel."""
        from core.services.project_service import ProjectService
        from ui.subtitle_inspector_panel import SubtitleInspectorPanel

        with tempfile.TemporaryDirectory() as tmp_dir:
            vid_path = os.path.join(tmp_dir, "sample.mp4")
            with open(vid_path, "wb") as f:
                f.write(b"fake_video_bytes")
            proj_dir = os.path.join(tmp_dir, "TestProj.ai-subtitle")

            svc = ProjectService()
            proj = svc.create_project(proj_dir, "TestProj", vid_path)
            proj.state.subtitle_style = {
                "font_name": "Arial",
                "font_size": 32,
                "font_color": "#00ff88",
                "outline_color": "#112233",
                "outline_width": 4,
                "position": "top",
                "x": 0.4,
                "y": 0.2,
                "position_edit_mode": True,
            }
            proj.state.segment_styles = {"seg_1": "loud", "seg_2": "whisper"}
            svc.save_project()

            svc2 = ProjectService()
            reopened = svc2.open_project(proj_dir)
            self.assertEqual(reopened.state.subtitle_style["font_size"], 32)
            self.assertEqual(reopened.state.subtitle_style["font_color"], "#00ff88")
            self.assertEqual(reopened.state.segment_styles, {"seg_1": "loud", "seg_2": "whisper"})

            panel = SubtitleInspectorPanel()
            try:
                panel.set_style(reopened.state.subtitle_style)
                restored = panel.get_current_style()
                self.assertEqual(restored["font_size"], 32)
                self.assertEqual(restored["font_color"], "#00ff88")
                self.assertEqual(restored["outline_color"], "#112233")
                self.assertEqual(restored["outline_width"], 4)
                self.assertEqual(restored["position"], "top")
                self.assertTrue(restored["position_edit_mode"])
            finally:
                panel.close()
                panel.deleteLater()

    def test_tc_set_style_preset_immediately_refreshes_player_and_inspector(self):
        """Xác thực đổi preset câu sẽ ép VideoPlayer.refresh_current_subtitle() và đồng bộ Inspector ngay lập tức."""
        from ui.subtitle_inspector_panel import SubtitleInspectorPanel
        from PySide6.QtWidgets import QWidget, QVBoxLayout

        host = QWidget()
        layout = QVBoxLayout(host)
        layout.addWidget(self.sub_editor)
        host.video_player = MagicMock()
        host.inspector_panel = SubtitleInspectorPanel(host)
        try:
            self.sub_editor._set_style_preset_for_indices([0], "whisper")
            host.video_player.refresh_current_subtitle.assert_called_once()
            self.assertEqual(host.inspector_panel.cmb_preset.currentData(), "whisper")
            self.assertTrue(hasattr(host.inspector_panel, "lbl_preset_hint"))
            self.assertIn("Loud", host.inspector_panel.lbl_preset_hint.text())
        finally:
            layout.removeWidget(self.sub_editor)
            self.sub_editor.setParent(None)
            host.close()
            host.deleteLater()

    def test_tc_video_player_refresh_current_subtitle_clears_cache_and_updates(self):
        """Xác thực refresh_current_subtitle xóa _last_style_preset và gọi position_changed tại vị trí hiện tại."""
        player = VideoPlayerWidget()
        try:
            player._last_style_preset = "normal"
            player.get_current_time_ms = MagicMock(return_value=2500)
            player.position_changed = MagicMock()

            player.refresh_current_subtitle()

            self.assertIsNone(player._last_style_preset)
            player.position_changed.assert_called_once_with(2500)
        finally:
            player.close()
            player.deleteLater()


    def test_tc_preset_01_to_06_custom_presets_dialog_reset_persist_and_ass_export(self):
        """Xác thực toàn diện TC-PRESET-01..06: Hộp thoại cấu hình, Reset từng tab, Lưu dự án, Backward compatibility và ASS Export."""
        import json
        from ui.preset_config_dialog import PresetConfigDialog
        from ui.subtitle_inspector_panel import SubtitleInspectorPanel
        from player.subtitle_overlay import SubtitleOverlay
        from core.services.project_service import ProjectService
        from core.Backend import _build_multistyle_ass

        # TC-PRESET-01: Mở hộp thoại cấu hình Preset mặc định
        dlg = PresetConfigDialog()
        try:
            from PySide6.QtGui import QColor
            self.assertEqual(dlg.tabs.count(), 2)
            self.assertEqual(dlg._controls["loud"]["spin_scale"].value(), 120)
            self.assertEqual(dlg._controls["loud"]["color"].name().upper(), "#FFE600")
            self.assertAlmostEqual(dlg._controls["loud"]["spin_outline"].value(), 3.5)
            self.assertTrue(dlg._controls["loud"]["chk_bold"].isChecked())
            self.assertFalse(dlg._controls["loud"]["chk_italic"].isChecked())

            self.assertEqual(dlg._controls["whisper"]["spin_scale"].value(), 85)
            self.assertEqual(dlg._controls["whisper"]["color"].name().upper(), "#D0D0D0")
            self.assertAlmostEqual(dlg._controls["whisper"]["spin_outline"].value(), 1.5)
            self.assertFalse(dlg._controls["whisper"]["chk_bold"].isChecked())
            self.assertTrue(dlg._controls["whisper"]["chk_italic"].isChecked())

            # TC-PRESET-03: Khôi phục mặc định độc lập từng Tab
            dlg._controls["loud"]["spin_scale"].setValue(135)
            dlg._update_color_btn("loud", QColor("#FF0000"))
            dlg._controls["whisper"]["spin_scale"].setValue(70)
            dlg._update_color_btn("whisper", QColor("#00FF00"))

            dlg.reset_preset("loud")
            self.assertEqual(dlg._controls["loud"]["spin_scale"].value(), 120)
            self.assertEqual(dlg._controls["loud"]["color"].name().upper(), "#FFE600")
            # Tab Whisper vẫn giữ nguyên cấu hình đang sửa
            self.assertEqual(dlg._controls["whisper"]["spin_scale"].value(), 70)
            self.assertEqual(dlg._controls["whisper"]["color"].name().upper(), "#00FF00")

            # TC-PRESET-02: Thay đổi thông số Loud và áp dụng trực tiếp
            dlg._controls["loud"]["spin_scale"].setValue(130)
            dlg._update_color_btn("loud", QColor("#FF0000"))
            dlg._controls["loud"]["spin_outline"].setValue(4.0)
            emitted = []
            dlg.presets_configured.connect(lambda p: emitted.append(p))
            dlg._on_save_clicked()
            self.assertEqual(len(emitted), 1)
            custom_presets = emitted[0]
            self.assertAlmostEqual(custom_presets["loud"]["scale"], 1.30)
            self.assertEqual(custom_presets["loud"]["font_color"], "#FF0000")
        finally:
            dlg.close()
            dlg.deleteLater()

        panel = SubtitleInspectorPanel()
        overlay = SubtitleOverlay()
        try:
            panel.update_preset_hints(custom_presets)
            self.assertIn("Phóng to +30%", panel.lbl_preset_hint.text())
            self.assertIn("#FF0000", panel.lbl_preset_hint.text())

            from ui.animations.animation_types import SubtitleRenderInput
            overlay.update_style(size=20, color="#FFFFFF", out_width=2)
            overlay.render_input = SubtitleRenderInput(segment_id="seg_1", text="Hello", start_ms=0, end_ms=2000, style_preset="loud")
            overlay.set_custom_presets(custom_presets)
            resolved = overlay.get_active_resolved_style()
            self.assertEqual(resolved["font_size"], 26)
            self.assertEqual(resolved["font_color"], "#FF0000")
            self.assertAlmostEqual(resolved["outline_width"], 4.0)
        finally:
            panel.close()
            panel.deleteLater()
            overlay.close()
            overlay.deleteLater()

        # TC-PRESET-04 & TC-PRESET-05: Lưu dự án (.ass_proj) và tương thích ngược dự án cũ
        with tempfile.TemporaryDirectory() as tmp_dir:
            vid_path = os.path.join(tmp_dir, "sample.mp4")
            with open(vid_path, "wb") as f:
                f.write(b"fake_video_bytes")
            proj_dir = os.path.join(tmp_dir, "PresetProj.ai-subtitle")

            svc = ProjectService()
            proj = svc.create_project(proj_dir, "PresetProj", vid_path)
            proj.state.style_presets = custom_presets
            svc.save_project()

            svc2 = ProjectService()
            reopened = svc2.open_project(proj_dir)
            self.assertEqual(reopened.state.style_presets["loud"]["font_color"], "#FF0000")
            self.assertAlmostEqual(reopened.state.style_presets["loud"]["scale"], 1.30)

            # TC-PRESET-05: Xóa trường style_presets giả lập dự án cũ
            state_file = os.path.join(proj_dir, "state.json")
            with open(state_file, "r", encoding="utf-8") as f:
                raw_state = json.load(f)
            raw_state.pop("style_presets", None)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(raw_state, f)

            svc3 = ProjectService()
            legacy_proj = svc3.open_project(proj_dir)
            self.assertEqual(legacy_proj.state.style_presets, {})

            # TC-PRESET-06: Đồng bộ khi xuất video Hardsub (.ass)
            ass_content = _build_multistyle_ass(
                segments=[{"start": 0.0, "end": 2.0, "text": "Câu nhấn mạnh", "style_preset": "loud"}],
                width=1920,
                height=1080,
                placement_state=None,
                global_style={"font_name": "Arial", "font_size": 20, "font_color": "#FFFFFF", "outline_width": 2.0},
                custom_presets=custom_presets,
            )
            self.assertIn("Style: Style_Loud,Arial,26,&H000000FF", ass_content)
            self.assertIn(",4.0,0,5,", ass_content)


    def test_tc_preset_outline_01_to_03_custom_outline_color_preview_reset_and_ass(self):
        """Xác thực TC-PRESET-OUTLINE-01..03: Nút Màu viền mặc định #000000, áp dụng preview + ASS export, và reset từng tab."""
        from PySide6.QtGui import QColor
        from ui.preset_config_dialog import PresetConfigDialog
        from player.subtitle_overlay import SubtitleOverlay
        from ui.animations.animation_types import SubtitleRenderInput
        from core.Backend import _build_multistyle_ass

        # TC-PRESET-OUTLINE-01: Mở Dialog Preset lần đầu -> cả 2 tab Loud và Whisper có màu viền #000000
        dlg = PresetConfigDialog()
        try:
            self.assertEqual(dlg._controls["loud"]["outline_color"].name().upper(), "#000000")
            self.assertEqual(dlg._controls["loud"]["btn_outline_color"].text(), "#000000")
            self.assertEqual(dlg._controls["whisper"]["outline_color"].name().upper(), "#000000")
            self.assertEqual(dlg._controls["whisper"]["btn_outline_color"].text(), "#000000")

            # TC-PRESET-OUTLINE-03: Đổi màu viền cả 2 tab rồi bấm Khôi phục mặc định Loud
            dlg._update_outline_color_btn("loud", QColor("#FF0000"))
            dlg._update_outline_color_btn("whisper", QColor("#FFFFFF"))
            dlg.reset_preset("loud")
            self.assertEqual(dlg._controls["loud"]["outline_color"].name().upper(), "#000000")
            self.assertEqual(dlg._controls["whisper"]["outline_color"].name().upper(), "#FFFFFF")

            # TC-PRESET-OUTLINE-02: Đổi màu viền Loud sang #FF0000 và Whisper sang #FFFFFF -> Lưu áp dụng
            dlg._update_outline_color_btn("loud", QColor("#FF0000"))
            emitted = []
            dlg.presets_configured.connect(lambda p: emitted.append(p))
            dlg._on_save_clicked()
            self.assertEqual(len(emitted), 1)
            custom_presets = emitted[0]
            self.assertEqual(custom_presets["loud"]["outline_color"], "#FF0000")
            self.assertEqual(custom_presets["whisper"]["outline_color"], "#FFFFFF")
        finally:
            dlg.close()
            dlg.deleteLater()

        # Preview trên SubtitleOverlay: Loud viền #FF0000, Whisper viền #FFFFFF
        overlay = SubtitleOverlay()
        try:
            overlay.set_custom_presets(custom_presets)
            overlay.render_input = SubtitleRenderInput(segment_id="seg_1", text="Loud line", start_ms=0, end_ms=2000, style_preset="loud")
            _, _, _, loud_out_color = overlay.get_active_font()
            self.assertEqual(loud_out_color.name().upper(), "#FF0000")

            overlay.render_input = SubtitleRenderInput(segment_id="seg_2", text="Whisper line", start_ms=2000, end_ms=4000, style_preset="whisper")
            _, _, _, whisper_out_color = overlay.get_active_font()
            self.assertEqual(whisper_out_color.name().upper(), "#FFFFFF")
        finally:
            overlay.close()
            overlay.deleteLater()

        # Xuất ASS Hardsub: Style_Loud có OutlineColour &H000000FF (Đỏ), Style_Whisper có OutlineColour &H00FFFFFF (Trắng)
        ass_content = _build_multistyle_ass(
            segments=[
                {"start": 0.0, "end": 2.0, "text": "Loud", "style_preset": "loud"},
                {"start": 2.0, "end": 4.0, "text": "Whisper", "style_preset": "whisper"},
            ],
            width=1920,
            height=1080,
            placement_state=None,
            global_style={"font_name": "Arial", "font_size": 20, "font_color": "#FFFFFF", "outline_width": 2.0},
            custom_presets=custom_presets,
        )
        self.assertIn("Style: Style_Loud,Arial,24,&H0000E6FF,&H0000E6FF,&H000000FF,&H00000000", ass_content)
        self.assertIn("Style: Style_Whisper,Arial,17,&H00D0D0D0,&H00D0D0D0,&H00FFFFFF,&H00000000", ass_content)


    def test_tc_preset_roundtrip_persistence_with_srt_reparse(self):
        """Xác thực lưu và khôi phục style_preset theo STT ngay cả khi SRT re-parse cấp UUID ngẫu nhiên mới, đồng thời đồng bộ Inspector & Video Player."""
        from types import SimpleNamespace
        from core.export.subtitle_parser import parse_srt_content
        from ui.Gui import MainWindow
        from ui.subtitle_inspector_panel import SubtitleInspectorPanel

        srt_content = "1\n00:00:01,000 --> 00:00:03,000\nCâu 1 Nhấn mạnh\n\n2\n00:00:04,000 --> 00:00:06,000\nCâu 2 Thì thầm\n"

        # 1. Phiên làm việc đầu tiên
        segs_session1 = parse_srt_content(srt_content)
        segs_session1[0]["style_preset"] = "loud"
        segs_session1[1]["style_preset"] = "whisper"

        saved_segment_styles = {
            str(s.get("stt", i + 1)): s.get("style_preset", "normal")
            for i, s in enumerate(segs_session1)
            if s.get("style_preset") and s.get("style_preset") != "normal"
        }
        self.assertEqual(saved_segment_styles, {"1": "loud", "2": "whisper"})

        # 2. Phiên làm việc thứ 2 (Mở lại dự án, SRT re-parse ra UUID hoàn toàn mới)
        segs_session2 = parse_srt_content(srt_content)
        self.assertNotEqual(segs_session1[0]["id"], segs_session2[0]["id"])

        win = MainWindow.__new__(MainWindow)
        win.project_service = SimpleNamespace(
            current_project=SimpleNamespace(
                state=SimpleNamespace(
                    subtitle_style=None,
                    segment_styles=saved_segment_styles,
                    style_presets={"loud": {"scale": 1.3}},
                    subtitle_placement=None,
                    dirty=False,
                )
            ),
            mark_dirty=MagicMock(),
        )
        win.sub_editor = SimpleNamespace(
            all_segments=segs_session2,
            current_index=0,
            render_page=MagicMock(),
        )
        win.video_player = SimpleNamespace(
            subtitle_overlay=SimpleNamespace(set_custom_presets=MagicMock()),
            refresh_current_subtitle=MagicMock(),
        )
        win.inspector_panel = SubtitleInspectorPanel()
        try:
            win._sync_subtitle_placement_from_project()

            self.assertEqual(segs_session2[0]["style_preset"], "loud")
            self.assertEqual(segs_session2[1]["style_preset"], "whisper")
            self.assertEqual(win.inspector_panel.cmb_preset.currentData(), "loud")
            win.video_player.subtitle_overlay.set_custom_presets.assert_called_once_with({"loud": {"scale": 1.3}})
            win.video_player.refresh_current_subtitle.assert_called_once()
        finally:
            win.inspector_panel.close()
            win.inspector_panel.deleteLater()
