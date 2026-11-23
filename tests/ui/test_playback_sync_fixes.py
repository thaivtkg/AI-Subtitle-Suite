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
        mock_whisper.transcribe_batch.side_effect = lambda req_arg, batch_arg, cancel_fn: SubtitleGenerationResult(
            batch_id=batch_arg.batch_id,
            error=None,
            segments=[WhisperSegmentResult(start_ms=batch_arg.start_ms, end_ms=batch_arg.end_ms, text="Hello world")],
        )

        req = SubtitleGenerationRequest(
            request_id="req1",
            project_id="p1",
            source_fingerprint="fp",
            video_path="test.mp4",
            model_size="base",
            compute_type="int8",
            language="en",
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

        with patch("subprocess.run") as mock_run, patch("wave.open") as mock_audio:
            mock_audio.return_value.__enter__.return_value.getnframes.return_value = 32000
            mock_audio.return_value.__enter__.return_value.getframerate.return_value = 16000
            _, tmp_normal = FasterWhisperService._extract_batch_audio(req_normal, batch)
            shutil.rmtree(tmp_normal, ignore_errors=True)
            cmd_normal = mock_run.call_args[0][0]
            self.assertNotIn("-af", cmd_normal)

        with patch("subprocess.run") as mock_run, patch("wave.open") as mock_audio:
            mock_audio.return_value.__enter__.return_value.getnframes.return_value = 32000
            mock_audio.return_value.__enter__.return_value.getframerate.return_value = 16000
            _, tmp_boost = FasterWhisperService._extract_batch_audio(req_boost, batch)
            shutil.rmtree(tmp_boost, ignore_errors=True)
            cmd_boost = mock_run.call_args[0][0]
            self.assertIn("-af", cmd_boost)
            af_val = cmd_boost[cmd_boost.index("-af") + 1]
            self.assertIn("volume=2.0", af_val)
            self.assertIn("alimiter=limit=0.95", af_val)

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
