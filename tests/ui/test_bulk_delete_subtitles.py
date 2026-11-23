# -*- coding: utf-8 -*-
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, QItemSelectionModel, QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QStackedWidget, QWidget

from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from core.subtitle_editing.selection_controller import (
    SelectionSource,
    SubtitleSelectionController,
)
from core.timeline.timeline_controller import TimelineController
from core.timeline.timeline_data_provider import TimelineDataProvider
from ui.Gui import MainWindow
from ui.SubEditor import SubtitleEditorWidget
from ui.timeline.timeline_widget import TimelineWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _make_segments(count: int, step_ms: int = 2000) -> list[dict]:
    def _fmt(ms: int) -> str:
        s, rem = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{rem:03d}"

    return [
        {
            "id": f"seg-{i + 1}",
            "stt": str(i + 1),
            "start": _fmt(i * step_ms),
            "end": _fmt(i * step_ms + 1500),
            "start_ms": i * step_ms,
            "end_ms": i * step_ms + 1500,
            "text": f"Dialogue {i + 1}",
            "style_preset": "normal",
        }
        for i in range(count)
    ]


class _HarnessWindow(QWidget):
    """Lightweight MainWindow harness reusing real MainWindow methods without full heavy app init."""

    _get_selected_sub_indices = MainWindow._get_selected_sub_indices
    _update_timeline_batch_scan_button = MainWindow._update_timeline_batch_scan_button
    _on_timeline_delete_selected_requested = MainWindow._on_timeline_delete_selected_requested
    _on_delete_selected_subtitles = MainWindow._on_delete_selected_subtitles
    _sync_live_subtitle_on_undo_redo = MainWindow._sync_live_subtitle_on_undo_redo
    eventFilter = MainWindow.eventFilter

    def __init__(self, segments: list[dict], duration_ms: int = 30000):
        super().__init__()
        self.undo_manager = GlobalUndoManager(self)
        self.selection_controller = SubtitleSelectionController(self)
        self.project_service = SimpleNamespace(
            current_project=SimpleNamespace(project_id="p1"),
            mark_dirty=MagicMock(),
        )
        self._ai_running = False

        self.stack = QStackedWidget(self)
        self.stack.addWidget(QWidget())
        self.stack.addWidget(QWidget())
        self.stack.setCurrentIndex(1)

        self.sub_editor = SubtitleEditorWidget(self)
        self.sub_editor.undo_manager = self.undo_manager
        self.sub_editor.selection_controller = self.selection_controller
        self.sub_editor.project_service = self.project_service

        self.timeline_widget = TimelineWidget(self)
        self.timeline_data_provider = TimelineDataProvider()
        self.timeline_controller = TimelineController(
            self.project_service,
            self.timeline_widget,
            self.timeline_data_provider,
            undo_manager=self.undo_manager,
            selection_controller=self.selection_controller,
        )

        self.video_player = SimpleNamespace(
            sub_controller=SimpleNamespace(update_live_data=MagicMock()),
            refresh_current_subtitle=MagicMock(),
            toggle_playback=MagicMock(),
        )

        self.btn_timeline_batch_scan = QPushButton("Gen Sub đã chọn", self)
        self.btn_timeline_batch_scan.setEnabled(False)
        self.btn_timeline_batch_delete = QPushButton("Xóa đã chọn", self)
        self.btn_timeline_batch_delete.setObjectName("btn_timeline_batch_delete")
        self.btn_timeline_batch_delete.setEnabled(False)
        self.btn_timeline_batch_delete.clicked.connect(lambda: self._on_delete_selected_subtitles())

        # Wire signals identically to MainWindow
        self.selection_controller.selection_changed.connect(self.sub_editor.sync_selection)
        self.selection_controller.multi_selection_changed.connect(self.sub_editor.sync_multi_selection)
        self.selection_controller.selection_changed.connect(lambda *_: self._update_timeline_batch_scan_button())
        self.selection_controller.multi_selection_changed.connect(lambda *_: self._update_timeline_batch_scan_button())
        self.sub_editor.delete_requested.connect(self._on_delete_selected_subtitles)
        self.timeline_controller.delete_selected_requested.connect(self._on_timeline_delete_selected_requested)
        self.undo_manager.state_changed.connect(self.sub_editor.render_page)
        self.undo_manager.state_changed.connect(self._sync_live_subtitle_on_undo_redo)
        self.undo_manager.state_changed.connect(self.timeline_controller._refresh_ui)
        self.sub_editor.live_edit_applied.connect(
            lambda *_: self.timeline_controller.sync_from_editor_segments(self.sub_editor.all_segments)
        )

        # Load data
        self.sub_editor.all_segments = list(segments)
        self.sub_editor.render_page()
        self.timeline_data_provider.load_runtime_data(self.sub_editor.all_segments, duration_ms)
        self.timeline_widget.load_project_data(duration_ms, self.timeline_data_provider.get_all_segments())

    def _is_any_ai_process_running(self) -> bool:
        return self._ai_running

    def isActiveWindow(self) -> bool:
        return True


def test_sub_editor_bulk_delete_non_contiguous_debounce_and_atomic_undo_redo(qapp):
    win = _HarnessWindow(_make_segments(7))
    try:
        # Focus row 0 and simulate pending debounce text edit timer
        win.sub_editor.select_segment(0)
        win.sub_editor.current_editor._debounce.start()
        assert win.sub_editor.current_editor._debounce.isActive()

        # Select non-contiguous rows #1, #4, #7 -> indices [0, 3, 6]
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            deleted = win._on_delete_selected_subtitles(explicit_indices=[0, 3, 6])
        assert deleted is True
        assert not win.sub_editor.current_editor._debounce.isActive()
        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-2", "seg-3", "seg-5", "seg-6"]
        assert [s["stt"] for s in win.sub_editor.all_segments] == ["1", "2", "3", "4"]
        assert win.project_service.mark_dirty.called

        # Atomic Ctrl+Z restores all 7 segments to exact positions
        win.undo_manager.undo()
        assert [s["id"] for s in win.sub_editor.all_segments] == [f"seg-{i}" for i in range(1, 8)]
        assert [s["stt"] for s in win.sub_editor.all_segments] == [str(i) for i in range(1, 8)]

        # Atomic Ctrl+Y deletes all 3 again
        win.undo_manager.redo()
        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-2", "seg-3", "seg-5", "seg-6"]
    finally:
        win.deleteLater()


def test_sub_editor_context_menu_shows_delete_action_and_emits_signal(qapp):
    win = _HarnessWindow(_make_segments(5))
    try:
        emitted = []
        win.sub_editor.delete_requested.disconnect()
        win.sub_editor.delete_requested.connect(emitted.append)

        # Multi-select 3 rows (indices 0, 2, 4)
        sel_model = win.sub_editor.table.selectionModel()
        for r in (0, 2, 4):
            sel_model.select(
                win.sub_editor.table.model().index(r, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows,
            )

        captured_labels = []
        from PySide6.QtWidgets import QMenu as _RealQMenu

        class _FakeMenu(_RealQMenu):
            def exec(self, *_args, **_kwargs):
                captured_labels.extend(a.text() for a in self.actions() if a.text())
                return next(a for a in self.actions() if "Xóa 3 câu đã chọn (Delete)" in a.text())

        with patch("PySide6.QtWidgets.QMenu", _FakeMenu):
            win.sub_editor._show_table_context_menu(QPoint(5, 5))

        assert "Xóa 3 câu đã chọn (Delete)" in captured_labels
        assert emitted == [[0, 2, 4]]
    finally:
        win.deleteLater()


def test_pagination_cross_page_timeline_selection_and_last_page_clamp(qapp):
    win = _HarnessWindow(_make_segments(12), duration_ms=40000)
    try:
        win.sub_editor.group_size = 5
        win.sub_editor.current_page = 0
        win.sub_editor.render_page()
        assert win.sub_editor.lbl_page.text() == "1 / 3"

        # Cross-page multi-selection from Timeline (indices 3, 4 on Page 1 + 5, 6 on Page 2)
        win.selection_controller.select_multiple(
            [3, 4, 5, 6],
            {"seg-4", "seg-5", "seg-6", "seg-7"},
            SelectionSource.TIMELINE,
        )
        assert win._get_selected_sub_indices() == [3, 4, 5, 6]
        assert win.btn_timeline_batch_delete.text() == "Xóa (4 câu)"
        assert win.btn_timeline_batch_delete.isEnabled()

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            win.btn_timeline_batch_delete.click()

        assert len(win.sub_editor.all_segments) == 8
        assert {"seg-4", "seg-5", "seg-6", "seg-7"}.isdisjoint(
            {s["id"] for s in win.sub_editor.all_segments}
        )

        # Navigate to last page (Page 2/2 with 3 segments: indices 5, 6, 7) and delete all of it
        win.sub_editor.current_page = 1
        win.sub_editor.render_page()
        assert win.sub_editor.lbl_page.text() == "2 / 2"
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            win._on_delete_selected_subtitles(explicit_indices=[5, 6, 7])

        # Page must clamp back to 1 / 1 (never showing blank page 2)
        assert len(win.sub_editor.all_segments) == 5
        assert win.sub_editor.current_page == 0
        assert win.sub_editor.lbl_page.text() == "1 / 1"
        assert win.sub_editor.table.rowCount() == 5
    finally:
        win.deleteLater()


def test_delete_all_subtitles_updates_all_views_and_undo_restores_100_percent(qapp):
    win = _HarnessWindow(_make_segments(3))
    try:
        win.selection_controller.select_multiple(
            [0, 1, 2], {"seg-1", "seg-2", "seg-3"}, SelectionSource.TIMELINE
        )
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            assert win._on_delete_selected_subtitles() is True

        assert win.sub_editor.all_segments == []
        assert win.sub_editor.current_index == -1
        assert not win.sub_editor.editor_group.isEnabled()
        assert len(win.timeline_widget.container.track.segments) == 0
        assert not win.btn_timeline_batch_delete.isEnabled()
        assert not win.btn_timeline_batch_scan.isEnabled()
        win.video_player.sub_controller.update_live_data.assert_called_with([])
        assert win.video_player.refresh_current_subtitle.called

        # Undo restores all 3 subtitles cleanly
        win.undo_manager.undo()
        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-1", "seg-2", "seg-3"]
        assert len(win.timeline_widget.container.track.segments) == 3
    finally:
        win.deleteLater()


def test_range_filter_deletes_only_selected_visible_rows(qapp):
    # 6 segments at 0s, 30s, 60s, 90s, 120s, 150s
    win = _HarnessWindow(_make_segments(6, step_ms=30000), duration_ms=200000)
    try:
        # Filter [60000, 120000) -> visible source indices [2, 3]
        win.sub_editor._active_time_range_ms = (60000, 120000)
        win.sub_editor.render_page()
        assert win.sub_editor._visible_source_indices == [2, 3]
        assert win.sub_editor.table.rowCount() == 2

        win.sub_editor.table.selectAll()
        assert win._get_selected_sub_indices() == [2, 3]

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            assert win._on_delete_selected_subtitles() is True

        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-1", "seg-2", "seg-5", "seg-6"]
    finally:
        win.deleteLater()


def test_confirmation_dialog_no_cancels_and_single_delete_is_instant(qapp):
    win = _HarnessWindow(_make_segments(4))
    try:
        # Single delete: NO confirmation dialog
        win.selection_controller.select(1, "seg-2", SelectionSource.EDITOR)
        with patch.object(QMessageBox, "question") as mock_q:
            assert win._on_delete_selected_subtitles() is True
            mock_q.assert_not_called()
        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-1", "seg-3", "seg-4"]

        # Multi delete with No -> cancelled, nothing deleted
        win.selection_controller.select_multiple([0, 2], {"seg-1", "seg-4"}, SelectionSource.EDITOR)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as mock_q:
            assert win._on_delete_selected_subtitles() is False
            mock_q.assert_called_once()
        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-1", "seg-3", "seg-4"]
    finally:
        win.deleteLater()


def test_focus_guard_and_ai_worker_guard_protect_against_unwanted_delete(qapp):
    win = _HarnessWindow(_make_segments(3))
    try:
        win.selection_controller.select(0, "seg-1", SelectionSource.EDITOR)

        # 1. Focus guard: typing inside CurrentSubtitleEditor text_edit -> Delete must NOT trigger row delete
        key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
        with patch.object(QApplication, "focusWidget", return_value=win.sub_editor.current_editor.text_edit):
            handled = win.eventFilter(win.sub_editor.current_editor.text_edit, key_ev)
        assert handled is False
        assert len(win.sub_editor.all_segments) == 3

        # 2. AI worker running guard blocks delete even when triggered directly
        win._ai_running = True
        with patch("ui.Gui.Toast.show_warning") as mock_warn:
            assert win._on_delete_selected_subtitles(explicit_indices=[0, 1]) is False
            mock_warn.assert_called_once()
        assert len(win.sub_editor.all_segments) == 3
    finally:
        win.deleteLater()


def test_timeline_controller_unifies_delete_into_single_undo_manager(qapp):
    win = _HarnessWindow(_make_segments(4))
    try:
        track = win.timeline_widget.container.track
        track.set_selection({"seg-2", "seg-4"})
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            track.action_delete_requested.emit({"seg-2", "seg-4"})

        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-1", "seg-3"]
        assert len(win.timeline_widget.container.track.segments) == 2

        win.undo_manager.undo()
        assert [s["id"] for s in win.sub_editor.all_segments] == ["seg-1", "seg-2", "seg-3", "seg-4"]
    finally:
        win.deleteLater()
