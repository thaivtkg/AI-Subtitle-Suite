"""Export timed subtitle audio segments to WAV or MP3 preserving source audio quality."""

from __future__ import annotations

import array
import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from typing import Callable, Sequence

from PySide6.QtCore import QThread, Signal

from core.runtime.runtime_paths import RuntimePaths

SUPPORTED_AUDIO_FORMATS = ("wav", "mp3")
DEFAULT_MERGE_GAP_MS = 300
DEFAULT_EDGE_FADE_MS = 15


@dataclass(frozen=True)
class AudioExportItem:
    stt: int
    start_ms: int
    end_ms: int
    output_path: str
    audio_format: str = "wav"


def normalize_audio_format(audio_format: str, output_path: str = "") -> str:
    ext = os.path.splitext(output_path or "")[1].lstrip(".").lower()
    if ext in SUPPORTED_AUDIO_FORMATS:
        return ext
    fmt = (audio_format or "").strip().lower().lstrip(".")
    if fmt in SUPPORTED_AUDIO_FORMATS:
        return fmt
    raise ValueError(f"Định dạng âm thanh không được hỗ trợ: {audio_format!r} (chỉ hỗ trợ WAV/MP3).")


def format_ms_for_filename(ms: int) -> str:
    clamped = max(0, int(ms))
    seconds, millis = divmod(clamped, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}-{minutes:02d}-{seconds:02d}-{millis:03d}"


def format_segment_audio_filename(stt: int, start_ms: int, end_ms: int, audio_format: str = "wav") -> str:
    fmt = normalize_audio_format(audio_format)
    idx = max(1, int(stt))
    return f"{idx:04d}_{format_ms_for_filename(start_ms)}_{format_ms_for_filename(end_ms)}.{fmt}"


def format_merged_audio_filename(stts: Sequence[int], audio_format: str = "wav") -> str:
    fmt = normalize_audio_format(audio_format)
    ordered = sorted(max(1, int(s)) for s in stts)
    if not ordered:
        return f"merged_audio.{fmt}"
    if len(ordered) == 1:
        return f"merged_{ordered[0]:04d}.{fmt}"
    return f"merged_{ordered[0]:04d}-{ordered[-1]:04d}_{len(ordered)}segs.{fmt}"


def build_export_ffmpeg_cmd(
    ffmpeg_exe: str,
    video_path: str,
    start_ms: int,
    end_ms: int,
    output_path: str,
    audio_format: str = "wav",
) -> list[str]:
    """Build an accurate FFmpeg slice command preserving source sample rate and channels."""
    start_ms = int(start_ms)
    end_ms = int(end_ms)
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError(f"Mốc thời gian không hợp lệ: {start_ms}ms -> {end_ms}ms")

    fmt = normalize_audio_format(audio_format, output_path)
    start_s = start_ms / 1000.0
    duration_s = (end_ms - start_ms) / 1000.0

    cmd: list[str] = [ffmpeg_exe, "-y", "-hide_banner", "-loglevel", "error"]
    # Hybrid fast+accurate seek: seek near target before -i, then exact decode after -i.
    if start_s > 2.0:
        fast_seek_s = start_s - 2.0
        cmd.extend(["-ss", f"{fast_seek_s:.3f}", "-i", video_path, "-ss", "2.000"])
    else:
        cmd.extend(["-i", video_path, "-ss", f"{start_s:.3f}"])

    cmd.extend(["-t", f"{duration_s:.3f}", "-vn", "-sn", "-dn", "-map", "0:a:0"])
    if fmt == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
    else:
        cmd.extend(["-c:a", "pcm_s16le"])
    cmd.append(output_path)
    return cmd


def _apply_pcm_wav_edge_fade(wav_path: str, edge_fade_ms: int) -> None:
    """Apply a short linear fade-in/out directly to 16-bit PCM WAV edges to prevent cut clicks."""
    fade_ms = max(0, int(edge_fade_ms or 0))
    if fade_ms <= 0:
        return
    with wave.open(wav_path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    if sampwidth != 2 or nframes < 4 or nchannels <= 0:
        return
    fade_frames = min(int(round(framerate * fade_ms / 1000.0)), nframes // 4)
    if fade_frames <= 1:
        return

    samples = array.array("h")
    samples.frombytes(raw)
    denom = float(fade_frames)
    for f in range(fade_frames):
        gain = f / denom
        head_base = f * nchannels
        tail_base = (nframes - 1 - f) * nchannels
        for ch in range(nchannels):
            samples[head_base + ch] = int(round(samples[head_base + ch] * gain))
            samples[tail_base + ch] = int(round(samples[tail_base + ch] * gain))

    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(samples.tobytes())


def export_segment_audio(
    video_path: str,
    start_ms: int,
    end_ms: int,
    output_path: str,
    audio_format: str = "wav",
    ffmpeg_exe: str | None = None,
) -> str:
    """Slice one timed segment from video_path to output_path (WAV/MP3, original sample rate & channels)."""
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(f"Không tìm thấy tệp video nguồn: {video_path}")
    if not output_path:
        raise ValueError("Đường dẫn lưu tệp âm thanh không hợp lệ.")

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    exe = ffmpeg_exe or RuntimePaths.get_ffmpeg_exe()
    cmd = build_export_ffmpeg_cmd(exe, video_path, start_ms, end_ms, output_path, audio_format)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        timeout=120,
    )
    if proc.returncode != 0:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        detail = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        raise RuntimeError(f"FFmpeg xuất âm thanh thất bại: {detail}")

    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 44:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        raise RuntimeError("Tệp âm thanh xuất ra rỗng (video có thể không có track audio tại mốc này).")
    return output_path


def _write_matching_silence_wav(reference_wav_path: str, silence_wav_path: str, duration_ms: int) -> str:
    """Create a silent PCM WAV matching the exact channels, sample width, and sample rate of reference_wav_path."""
    with wave.open(reference_wav_path, "rb") as ref:
        nchannels = ref.getnchannels()
        sampwidth = ref.getsampwidth()
        framerate = ref.getframerate()
    num_frames = max(1, int(round(framerate * duration_ms / 1000.0)))
    with wave.open(silence_wav_path, "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        out.writeframes(b"\x00" * (num_frames * nchannels * sampwidth))
    return silence_wav_path


def export_merged_segments_audio(
    video_path: str,
    segments: Sequence[tuple[int, int, int]],
    output_path: str,
    audio_format: str = "wav",
    ffmpeg_exe: str | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    gap_ms: int = DEFAULT_MERGE_GAP_MS,
    edge_fade_ms: int = DEFAULT_EDGE_FADE_MS,
) -> str:
    """Slice segments ordered by ascending STT and concatenate into one WAV/MP3 preserving source audio."""
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(f"Không tìm thấy tệp video nguồn: {video_path}")
    if not output_path:
        raise ValueError("Đường dẫn lưu tệp âm thanh không hợp lệ.")
    ordered = sorted(
        [(int(stt), int(s), int(e)) for stt, s, e in segments],
        key=lambda item: (item[0], item[1], item[2]),
    )
    if not ordered:
        raise ValueError("Không có đoạn âm thanh hợp lệ để gộp.")

    fmt = normalize_audio_format(audio_format, output_path)
    safe_gap_ms = max(0, int(gap_ms or 0))
    safe_fade_ms = max(0, int(edge_fade_ms or 0))
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    exe = ffmpeg_exe or RuntimePaths.get_ffmpeg_exe()
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    total_steps = len(ordered) + 1

    with tempfile.TemporaryDirectory(prefix="seg_audio_merge_") as tmp_dir:
        part_paths: list[str] = []
        for idx, (stt, start_ms, end_ms) in enumerate(ordered, start=1):
            if is_cancelled and is_cancelled():
                return ""
            if progress_cb:
                progress_cb(idx - 1, total_steps, f"STT #{stt}")
            part_path = os.path.join(tmp_dir, f"part_{idx:04d}.wav")
            export_segment_audio(
                video_path,
                start_ms,
                end_ms,
                part_path,
                audio_format="wav",
                ffmpeg_exe=exe,
            )
            if safe_fade_ms > 0:
                _apply_pcm_wav_edge_fade(part_path, safe_fade_ms)
            part_paths.append(part_path)
            if progress_cb:
                progress_cb(idx, total_steps, f"STT #{stt}")

        if is_cancelled and is_cancelled():
            return ""
        if progress_cb:
            progress_cb(len(ordered), total_steps, os.path.basename(output_path))

        silence_path = None
        if safe_gap_ms > 0 and len(part_paths) > 1:
            silence_path = _write_matching_silence_wav(
                part_paths[0], os.path.join(tmp_dir, "silence.wav"), safe_gap_ms
            )

        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as fh:
            for i, p in enumerate(part_paths):
                escaped = p.replace("\\", "/").replace("'", "'\\''")
                fh.write(f"file '{escaped}'\n")
                if silence_path is not None and i < len(part_paths) - 1:
                    sil_escaped = silence_path.replace("\\", "/").replace("'", "'\\''")
                    fh.write(f"file '{sil_escaped}'\n")

        cmd = [
            exe,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list,
            "-vn",
            "-sn",
            "-dn",
        ]
        if fmt == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
        else:
            cmd.extend(["-c:a", "pcm_s16le"])
        cmd.append(output_path)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            timeout=180,
        )
        if proc.returncode != 0:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            detail = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
            raise RuntimeError(f"FFmpeg gộp âm thanh thất bại: {detail}")

    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 44:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        raise RuntimeError("Tệp âm thanh sau khi gộp bị rỗng.")
    if progress_cb:
        progress_cb(total_steps, total_steps, os.path.basename(output_path))
    return output_path


class SegmentAudioExportWorker(QThread):
    """Background worker exporting 1 or multiple timed audio segments (separate or merged by STT)."""

    progress_signal = Signal(int, int, str)
    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(
        self,
        video_path: str,
        items: Sequence[AudioExportItem],
        parent=None,
        *,
        merge_output_path: str | None = None,
        merge_format: str = "wav",
        merge_gap_ms: int = DEFAULT_MERGE_GAP_MS,
        merge_edge_fade_ms: int = DEFAULT_EDGE_FADE_MS,
    ):
        super().__init__(parent)
        self.video_path = video_path
        self.items = list(items)
        self.merge_output_path = merge_output_path
        self.merge_format = merge_format
        self.merge_gap_ms = merge_gap_ms
        self.merge_edge_fade_ms = merge_edge_fade_ms
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        exported: list[str] = []
        try:
            if self.merge_output_path:
                segs = [(item.stt, item.start_ms, item.end_ms) for item in self.items]
                out_path = export_merged_segments_audio(
                    self.video_path,
                    segs,
                    self.merge_output_path,
                    audio_format=self.merge_format,
                    progress_cb=lambda done, total, label: self.progress_signal.emit(done, total, label),
                    is_cancelled=lambda: self._is_cancelled,
                    gap_ms=self.merge_gap_ms,
                    edge_fade_ms=self.merge_edge_fade_ms,
                )
                if out_path and not self._is_cancelled:
                    exported.append(out_path)
                self.finished_signal.emit(exported)
                return

            ordered_items = sorted(self.items, key=lambda it: (it.stt, it.start_ms, it.end_ms))
            total = len(ordered_items)
            for idx, item in enumerate(ordered_items, start=1):
                if self._is_cancelled:
                    break
                filename = os.path.basename(item.output_path)
                self.progress_signal.emit(idx - 1, total, filename)
                out_path = export_segment_audio(
                    self.video_path,
                    item.start_ms,
                    item.end_ms,
                    item.output_path,
                    audio_format=item.audio_format,
                )
                exported.append(out_path)
                self.progress_signal.emit(idx, total, filename)
            self.finished_signal.emit(exported)
        except Exception as exc:
            self.error_signal.emit(str(exc))
