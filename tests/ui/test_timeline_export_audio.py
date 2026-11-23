import os
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QWidget

from core.runtime.runtime_paths import RuntimePaths
from core.timeline.timeline_data_provider import TimelineDataProvider
from ui.timeline.timeline_widget import TimelineWidget


def _make_sample_mp4(tmp_path) -> str:
    video_path = str(tmp_path / "ui_export_sample.mp4")
    ffmpeg_exe = RuntimePaths.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100:duration=5",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=64x64:d=5",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:v",
        "libx264",
        "-t",
        "5",
        "-c:a",
        "aac",
        video_path,
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=creationflags, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return video_path


def _load_segments(timeline: TimelineWidget, duration_ms: int, rows: list[dict]):
    dp = TimelineDataProvider()
    dp.load_runtime_data(rows, duration_ms)
    timeline.load_project_data(duration_ms, dp.get_all_segments(), [])


def test_timeline_export_audio_button_placement_and_states(qtbot):
    timeline = TimelineWidget()
    qtbot.addWidget(timeline)
    timeline.show()

    _load_segments(
        timeline,
        10000,
        [
            {"id": "s1", "start_ms": 1000, "end_ms": 2500, "text": "Line 1"},
            {"id": "s2", "start_ms": 3000, "end_ms": 4500, "text": "Line 2"},
        ],
    )

    # Verify exact layout order: Play Segment -> Xuất Audio -> range_validation text
    gap_layout = timeline.gap_row.layout()
    widgets = [gap_layout.itemAt(i).widget() for i in range(gap_layout.count())]
    idx_play = widgets.index(timeline.container.play_segment_button)
    idx_export = widgets.index(timeline.container.export_audio_button)
    idx_hint = widgets.index(timeline.container.range_validation)
    assert idx_export == idx_play + 1
    assert idx_hint == idx_export + 1
    assert timeline.container.export_audio_button.objectName() == "btn_export_segment_audio"

    # 0 selected -> hidden & disabled
    assert not timeline.container.export_audio_button.isEnabled()
    assert not timeline.container.export_audio_button.isVisible()

    # 1 segment focused -> both Play Segment and Xuất Audio visible & enabled, hint shifted right
    timeline.container.track.set_selection({"s1"})
    timeline.refresh_segment_focus()
    assert timeline.container.play_segment_button.isVisible()
    assert timeline.container.export_audio_button.isVisible()
    assert timeline.container.export_audio_button.isEnabled()
    assert timeline.container.export_audio_button.text() == "Xuất Audio"
    assert timeline.container.range_validation.text() == "Kéo mép trái/phải để chỉnh thời gian."

    # Clicking Xuất Audio emits export_audio_requested
    emitted = []
    timeline.export_audio_requested.connect(lambda: emitted.append(True))
    timeline.container.export_audio_button.click()
    assert emitted == [True]

    # Multi-selection -> Play Segment hidden/disabled, Xuất Audio stays enabled with count
    timeline.container.track.set_selection({"s1", "s2"})
    timeline.refresh_segment_focus()
    assert not timeline.container.play_segment_button.isEnabled()
    assert timeline.container.export_audio_button.isVisible()
    assert timeline.container.export_audio_button.isEnabled()
    assert "2" in timeline.container.export_audio_button.text()

    # Gap selected -> Xuất Audio hidden & disabled
    timeline.set_generation_range(2600, 2900)
    assert not timeline.container.export_audio_button.isEnabled()
    assert not timeline.container.export_audio_button.isVisible()


def test_mainwindow_export_single_and_batch_audio_flow(qtbot, tmp_path):
    from ui.Gui import MainWindow

    video_path = _make_sample_mp4(tmp_path)
    out_wav = str(tmp_path / "single_export.wav")
    batch_dir = str(tmp_path / "batch_mp3")
    os.makedirs(batch_dir, exist_ok=True)

    # Lightweight QWidget harness binding MainWindow's export methods directly
    timeline = TimelineWidget()
    qtbot.addWidget(timeline)
    host = QWidget()
    qtbot.addWidget(host)
    host._audio_export_worker = None
    host._last_audio_export_dir = ""
    host.project_service = SimpleNamespace(current_project=SimpleNamespace(source=SimpleNamespace(video_path=video_path)))
    host.queue_mgr = None
    host.video_player = None
    host.timeline_widget = timeline
    host.sub_editor = SimpleNamespace(
        all_segments=[
            {"id": "s1", "stt": 1, "start_ms": 500, "end_ms": 1800, "text": "[ Chưa có nội dung ]"},
            {"id": "s2", "stt": 2, "start_ms": 2000, "end_ms": 3400, "text": "Second line"},
        ]
    )
    host._selected = [0]
    host._get_selected_sub_indices = lambda: list(host._selected)
    host._resolve_active_export_video_path = lambda: MainWindow._resolve_active_export_video_path(host)
    host._collect_exportable_segments = lambda: MainWindow._collect_exportable_segments(host)

    # 1. Single segment -> WAV
    with patch.object(QFileDialog, "getSaveFileName", return_value=(out_wav, "WAV Audio (*.wav)")), \
         patch("ui.toast.Toast.show_success") as mock_ok, \
         patch("ui.toast.Toast.show_warning") as mock_warn:
        MainWindow._on_export_segment_audio_requested(host)
        t0 = time.time()
        while host._audio_export_worker is not None and time.time() - t0 < 20:
            QApplication.processEvents()
            time.sleep(0.05)
        assert mock_warn.call_count == 0
        assert mock_ok.call_count == 1
        assert os.path.isfile(out_wav) and os.path.getsize(out_wav) > 1000

    # 2. Multiple segments -> separate MP3 into folder
    host._selected = [1, 0]  # reversed selection order must sort by STT
    assert [x[0] for x in host._collect_exportable_segments()] == [1, 2]
    with patch.object(QInputDialog, "getItem", return_value=("Xuất từng đoạn riêng (.mp3)", True)), \
         patch.object(QFileDialog, "getExistingDirectory", return_value=batch_dir), \
         patch("ui.toast.Toast.show_success") as mock_ok, \
         patch("ui.toast.Toast.show_warning") as mock_warn:
        MainWindow._on_export_segment_audio_requested(host)
        t0 = time.time()
        while host._audio_export_worker is not None and time.time() - t0 < 20:
            QApplication.processEvents()
            time.sleep(0.05)
        assert mock_warn.call_count == 0
        assert mock_ok.call_count == 1
        exported = sorted(os.listdir(batch_dir))
        assert len(exported) == 2
        assert all(f.endswith(".mp3") for f in exported)

    # 3. Multiple segments -> merge all into 1 WAV ordered by STT with 300ms silence gap + fade
    merged_wav = str(tmp_path / "merged_by_stt.wav")
    with patch.object(QInputDialog, "getItem", return_value=("Gộp thành 1 file theo STT (.wav)", True)), \
         patch.object(QInputDialog, "getInt", return_value=(300, True)), \
         patch.object(QFileDialog, "getSaveFileName", return_value=(merged_wav, "WAV Audio (*.wav)")), \
         patch("ui.toast.Toast.show_success") as mock_ok, \
         patch("ui.toast.Toast.show_warning") as mock_warn:
        MainWindow._on_export_segment_audio_requested(host)
        t0 = time.time()
        while host._audio_export_worker is not None and time.time() - t0 < 20:
            QApplication.processEvents()
            time.sleep(0.05)
        assert mock_warn.call_count == 0
        assert mock_ok.call_count == 1
        assert os.path.isfile(merged_wav) and os.path.getsize(merged_wav) > 2000
        import wave
        with wave.open(merged_wav, "rb") as wf:
            # 1.3s + 0.3s gap + 1.4s = 3.0s
            dur_s = wf.getnframes() / float(wf.getframerate())
            assert 2.85 <= dur_s <= 3.15

    # 4. Multiple segments -> merge all into 1 MP3 ordered by STT with 300ms gap + fade
    merged_mp3 = str(tmp_path / "merged_by_stt.mp3")
    with patch.object(QInputDialog, "getItem", return_value=("Gộp thành 1 file theo STT (.mp3)", True)), \
         patch.object(QInputDialog, "getInt", return_value=(300, True)), \
         patch.object(QFileDialog, "getSaveFileName", return_value=(merged_mp3, "MP3 Audio (*.mp3)")), \
         patch("ui.toast.Toast.show_success") as mock_ok, \
         patch("ui.toast.Toast.show_warning") as mock_warn:
        MainWindow._on_export_segment_audio_requested(host)
        t0 = time.time()
        while host._audio_export_worker is not None and time.time() - t0 < 20:
            QApplication.processEvents()
            time.sleep(0.05)
        assert mock_warn.call_count == 0
        assert mock_ok.call_count == 1
        assert os.path.isfile(merged_mp3) and os.path.getsize(merged_mp3) > 1500
