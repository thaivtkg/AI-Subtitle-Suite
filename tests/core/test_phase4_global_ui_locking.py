import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import QObject, Signal

from core.timing.timing_batch_service import TimingBatchService


class MockWorker(QObject):
    finished = Signal()

    def __init__(self, running=True):
        super().__init__()
        self._running = running
        self.is_cancelled = False

    def isRunning(self):
        return self._running

    def cancel(self):
        self.is_cancelled = True


class TestTimingBatchServiceLifecycle:
    def test_is_running_property(self):
        service = TimingBatchService(MagicMock())
        assert service.is_running is False

        service.worker = MockWorker(running=True)
        assert service.is_running is True

        service.worker._running = False
        assert service.is_running is False

    def test_cancel_timing_emits_ready_immediately_when_no_worker(self):
        service = TimingBatchService(MagicMock())
        service.worker = None

        emitted_states = []
        service.state_changed_signal.connect(lambda state, msg: emitted_states.append((state, msg)))

        service.cancel_timing()
        assert len(emitted_states) == 1
        assert emitted_states[0][0] == "READY"
        assert emitted_states[0][1] == "Đã hủy tiến trình."

    def test_cancel_timing_waits_for_worker_finished_before_ready(self):
        service = TimingBatchService(MagicMock())
        worker = MockWorker(running=True)
        service.worker = worker

        emitted_states = []
        service.state_changed_signal.connect(lambda state, msg: emitted_states.append((state, msg)))

        service.cancel_timing()
        assert worker.is_cancelled is True
        # Must not emit READY while worker is still running
        assert len(emitted_states) == 0

        # Simulate worker finishing
        worker._running = False
        worker.finished.emit()

        assert len(emitted_states) == 1
        assert emitted_states[0][0] == "READY"
        assert emitted_states[0][1] == "Đã hủy tiến trình."

    def test_worker_finished_waits_for_qthread_exit_and_unlocks_panel(self, qapp):
        """Regression test: Segment-based TimingBatchWorker emits finished_signal before QThread.run() returns.

        Ensure READY/COMPLETED/FAILED is deferred until QThread.finished so SubtitleGenerationPanel._reset_ui_state()
        does not re-lock the controls permanently.
        """
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        gen_service = MagicMock()
        gen_service.is_running = False
        gen_service.project_service.current_project = None
        panel = SubtitleGenerationPanel(gen_service)

        service = TimingBatchService(MagicMock())
        panel.timing_service = service
        worker = MockWorker(running=True)
        service.worker = worker

        emitted_states = []

        def on_state(state, msg):
            emitted_states.append((state, msg))
            panel.lbl_status.setText(msg)
            if state in {"READY", "COMPLETED", "FAILED"}:
                panel._reset_ui_state()

        service.state_changed_signal.connect(on_state)
        panel._set_ui_state_running()
        assert panel.btn_generate.isEnabled() is False
        assert panel.btn_cancel.isEnabled() is True

        # Simulate finished_signal handler executing while QThread is still winding down
        service._emit_terminal_state("READY", "Đã lưu Checkpoint (Đến câu 8).")
        assert emitted_states == []
        assert panel.btn_generate.isEnabled() is False

        # Now QThread finishes completely
        worker._running = False
        worker.finished.emit()

        assert emitted_states == [("READY", "Đã lưu Checkpoint (Đến câu 8).")]
        assert service.is_running is False
        assert panel.btn_generate.isEnabled() is True
        assert panel.btn_cancel.isEnabled() is False


class TestSubtitleGenerationPanelUILocking:
    def test_is_any_service_running_detection(self, qapp):
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        gen_service = MagicMock()
        gen_service.is_running = False
        panel = SubtitleGenerationPanel(gen_service)

        # 1. Idle
        assert panel._is_any_service_running() is False

        # 2. Generation service running
        gen_service.is_running = True
        assert panel._is_any_service_running() is True
        gen_service.is_running = False

        # 3. Timing service running on window
        timing_service = MagicMock()
        timing_service.is_running = True
        panel.timing_service = timing_service
        assert panel._is_any_service_running() is True
        panel.timing_service.is_running = False
        assert panel._is_any_service_running() is False

    def test_set_ui_state_running_disables_all_17_controls(self, qapp):
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        gen_service = MagicMock()
        gen_service.is_running = False
        panel = SubtitleGenerationPanel(gen_service)

        panel._set_ui_state_running()

        controls = [
            "cmb_vad_preset", "spin_min_silence", "spin_vad_threshold",
            "spin_speech_pad", "spin_max_speech", "chk_apply_preset_rescan",
            "chk_music_mode", "btn_download_model", "btn_delete_model",
            "cmb_subtitle_source", "btn_add_external_srt", "cmb_range_unit",
            "txt_start", "txt_end", "btn_range_timeline", "btn_range_preview",
            "btn_context_edit",
        ]
        assert len(controls) == 17
        for ctrl_name in controls:
            ctrl = getattr(panel, ctrl_name, None)
            assert ctrl is not None, f"Control {ctrl_name} not found on panel"
            assert ctrl.isEnabled() is False, f"Control {ctrl_name} was not disabled"

    def test_reset_ui_state_does_not_unlock_if_service_is_running(self, qapp):
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        gen_service = MagicMock()
        gen_service.is_running = True
        panel = SubtitleGenerationPanel(gen_service)

        panel._reset_ui_state()

        # Controls should stay disabled
        assert panel.btn_generate.isEnabled() is False
        assert panel.cmb_mode.isEnabled() is False

    def test_reset_ui_state_restores_all_17_controls_when_idle(self, qapp):
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        gen_service = MagicMock()
        gen_service.is_running = False
        panel = SubtitleGenerationPanel(gen_service)

        panel._set_ui_state_running()
        panel._reset_ui_state()

        controls = [
            "cmb_vad_preset", "spin_min_silence", "spin_vad_threshold",
            "spin_speech_pad", "spin_max_speech", "chk_apply_preset_rescan",
            "chk_music_mode", "btn_download_model", "btn_delete_model",
            "cmb_subtitle_source", "btn_add_external_srt", "cmb_range_unit",
            "txt_start", "txt_end", "btn_range_timeline", "btn_range_preview",
            "btn_context_edit",
        ]
        assert len(controls) == 17
        for ctrl_name in controls:
            ctrl = getattr(panel, ctrl_name, None)
            assert ctrl is not None, f"Control {ctrl_name} not found on panel"
            assert ctrl.isEnabled() is True, f"Control {ctrl_name} was not restored to enabled"

    def test_start_generation_with_strategy_exception_calls_reset_ui_state(self, qapp):
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        gen_service = MagicMock()
        gen_service.is_running = False
        gen_service.start_generation.side_effect = RuntimeError("Failed to start")
        panel = SubtitleGenerationPanel(gen_service)

        with patch("PySide6.QtWidgets.QMessageBox.critical"):
            with patch.object(panel, "_build_asr_request", return_value=MagicMock()):
                with patch.object(panel, "_reset_ui_state") as mock_reset:
                    panel._start_generation_with_strategy(0, 1000, None)
                    assert mock_reset.call_count >= 1

    def test_premature_unlock_guards_when_service_running(self, qapp):
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        gen_service = MagicMock()
        gen_service.is_running = True
        panel = SubtitleGenerationPanel(gen_service)

        with patch.object(panel, "_on_mode_changed") as mock_mode_changed:
            panel.check_resumable_state()
            mock_mode_changed.assert_not_called()

            panel._on_download_model_clicked()
            mock_mode_changed.assert_not_called()

            panel.sync_timing_settings_from_project()
            mock_mode_changed.assert_not_called()


class TestGuiGlobalLockingAndStateSafety:
    def test_rescan_guards_pop_warning_when_ai_running(self, qapp):
        from ui.Gui import MainWindow

        win = MainWindow.__new__(MainWindow)
        win.project_service = MagicMock()
        win.subtitle_whisper_service = MagicMock()
        win.timing_service = MagicMock()
        win.scan_worker = None
        win._batch_scan_worker = None
        win.generation_panel = MagicMock()

        # When no AI is running
        win.subtitle_whisper_service.is_running = False
        win.timing_service.is_running = False
        win.generation_panel.generation_service.is_running = False
        assert win._is_any_ai_process_running() is False

        # When timing service is running
        win.timing_service.is_running = True
        assert win._is_any_ai_process_running() is True

        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn:
            win._on_segment_scan_requested("s1", 1000, 2000)
            mock_warn.assert_called_once()
            assert "Quá trình AI đang chạy" in mock_warn.call_args[0][2]

        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn:
            win._on_batch_segment_scan_requested([0, 1])
            mock_warn.assert_called_once()
            assert "Quá trình AI đang chạy" in mock_warn.call_args[0][2]

    def test_timing_draft_busy_lifecycle(self, qapp):
        from ui.Gui import MainWindow

        win = MainWindow.__new__(MainWindow)
        win.timeline_widget = MagicMock()
        win.subtitle_generation_service = MagicMock()
        win.timing_service = MagicMock()
        win.generation_panel = MagicMock()
        win.page_dashboard = MagicMock()
        win.project_service = MagicMock()
        win._current_range_segments = MagicMock(return_value=[])

        # Start timing draft sets busy True
        win._start_timing_draft(5, {})
        win.timeline_widget.set_generation_busy.assert_called_with(True)

        # On timing state changed to COMPLETED sets busy False
        win._on_timing_state_changed("COMPLETED", "Done")
        win.timeline_widget.set_generation_busy.assert_called_with(False)

        # On timing error sets busy False
        with patch.object(win, "append_log"):
            win._on_timing_error("Some error")
            win.timeline_widget.set_generation_busy.assert_called_with(False)
