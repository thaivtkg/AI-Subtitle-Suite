import os
import io
import logging
from typing import Any, Dict, List, Optional
import numpy as np

try:
    import av
except ImportError:
    av = None

try:
    from faster_whisper.vad import get_speech_timestamps, VadOptions
except ImportError:
    get_speech_timestamps = None
    VadOptions = None

from ui.SubEditor import ms_to_time_str

logger = logging.getLogger(__name__)

DEFAULT_CFG9_PRESET = {
    "vad_threshold": 0.35,
    "min_silence_duration_ms": 300,
    "speech_pad_ms": 300,
    "max_speech_duration_s": 6.0,
}


def extract_audio_window(
    video_path: Optional[str],
    start_offset_s: float = 0.0,
    max_duration_s: float = 120.0,
    sampling_rate: int = 16000,
) -> Optional[np.ndarray]:
    """
    Gate 1 & TC-VAD-10: Windowed Audio Extraction.
    Decodes only the leading audio window (default 60s - 120s) instead of the entire video.
    Ensures execution time < 0.3s and RAM usage < 50MB.
    """
    if not video_path or not os.path.exists(video_path) or av is None:
        return None

    try:
        resampler = av.audio.resampler.AudioResampler(
            format="s16",
            layout="mono",
            rate=sampling_rate,
        )
        raw_buffer = io.BytesIO()
        max_samples = int(max_duration_s * sampling_rate)
        accumulated_samples = 0
        dtype = None

        with av.open(video_path, mode="r", metadata_errors="ignore") as container:
            if not container.streams.audio:
                return None
            audio_stream = container.streams.audio[0]

            if start_offset_s > 0:
                time_base = audio_stream.time_base
                target_pts = int(start_offset_s / time_base) if time_base else 0
                container.seek(target_pts, stream=audio_stream, any_frame=False, backward=True)

            for frame in container.decode(audio_stream):
                resampled_frames = resampler.resample(frame)
                for r_frame in resampled_frames:
                    arr = r_frame.to_ndarray()
                    dtype = arr.dtype
                    raw_buffer.write(arr)
                    accumulated_samples += arr.shape[-1]
                    if accumulated_samples >= max_samples:
                        break
                if accumulated_samples >= max_samples:
                    break

        del resampler
        if accumulated_samples == 0 or dtype is None:
            return None

        audio = np.frombuffer(raw_buffer.getbuffer(), dtype=dtype)
        audio = audio.astype(np.float32) / 32768.0
        return audio
    except Exception as exc:
        logger.warning(f"extract_audio_window failed on {video_path}: {exc}")
        return None


def detect_speech_intervals_vad(
    audio: np.ndarray,
    start_offset_s: float = 0.0,
    sampling_rate: int = 16000,
    vad_threshold: Optional[float] = None,
    min_silence_ms: Optional[int] = None,
    speech_pad_ms: Optional[int] = None,
    max_speech_duration_s: Optional[float] = None,
) -> List[Dict[str, int]]:
    """
    Detect speech chunks using Silero VAD with Preset CFG-9 Anime JA parameters.
    Returns list of dicts with start_ms and end_ms.
    """
    if audio is None or len(audio) == 0 or get_speech_timestamps is None or VadOptions is None:
        return []

    th = vad_threshold if vad_threshold is not None else DEFAULT_CFG9_PRESET["vad_threshold"]
    msil = min_silence_ms if min_silence_ms is not None else DEFAULT_CFG9_PRESET["min_silence_duration_ms"]
    spad = speech_pad_ms if speech_pad_ms is not None else DEFAULT_CFG9_PRESET["speech_pad_ms"]
    mmax = max_speech_duration_s if max_speech_duration_s is not None else DEFAULT_CFG9_PRESET["max_speech_duration_s"]

    try:
        options = VadOptions(
            threshold=th,
            min_silence_duration_ms=msil,
            speech_pad_ms=spad,
            max_speech_duration_s=mmax,
        )
        chunks = get_speech_timestamps(audio, options, sampling_rate=sampling_rate)
        intervals = []
        base_offset_ms = int(start_offset_s * 1000)

        for chunk in chunks:
            c_start_ms = base_offset_ms + int((chunk["start"] / sampling_rate) * 1000)
            c_end_ms = base_offset_ms + int((chunk["end"] / sampling_rate) * 1000)
            # Ensure at least 200ms duration
            if c_end_ms - c_start_ms < 200:
                c_end_ms = c_start_ms + 200
            intervals.append({"start_ms": c_start_ms, "end_ms": c_end_ms})

        return intervals
    except Exception as exc:
        logger.warning(f"detect_speech_intervals_vad failed: {exc}")
        return []


def generate_vad_timing_segments(
    count: int = 5,
    video_path: Optional[str] = None,
    start_offset_s: float = 0.0,
    vad_threshold: Optional[float] = None,
    min_silence_ms: Optional[int] = None,
    speech_pad_ms: Optional[int] = None,
    max_speech_duration_s: Optional[float] = None,
    duration_per_block_ms: int = 2500,
    gap_ms: int = 500,
    preserved_segments: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Generates timing segments using VAD if audio is available, with graceful
    fallback to synthetic timing (Gate 3) if no speech is detected or no video is loaded.
    Adopts text from preserved_segments (Gate 4) if present.
    """
    segments: List[Dict[str, Any]] = []

    # 1. Try VAD extraction if video exists
    if video_path and os.path.exists(video_path):
        audio = extract_audio_window(
            video_path,
            start_offset_s=start_offset_s,
            max_duration_s=max(120.0, count * 15.0),
        )
        if audio is not None:
            intervals = detect_speech_intervals_vad(
                audio,
                start_offset_s=start_offset_s,
                vad_threshold=vad_threshold,
                min_silence_ms=min_silence_ms,
                speech_pad_ms=speech_pad_ms,
                max_speech_duration_s=max_speech_duration_s,
            )
            for idx, inter in enumerate(intervals[:count]):
                segments.append({
                    "id": idx + 1,
                    "start": ms_to_time_str(inter["start_ms"]),
                    "end": ms_to_time_str(inter["end_ms"]),
                    "text": f"Dòng phụ đề #{idx+1}",
                    "translation": f"Subtitle line #{idx+1}",
                })

    # 2. Gate 3: Zero-Crash Synthetic Fallback if no VAD chunks found
    if len(segments) < count:
        missing_count = count - len(segments)
        base_ms = int(start_offset_s * 1000) if start_offset_s > 0 else gap_ms
        if segments:
            # Continue after the last VAD segment
            from ui.SubEditor import time_str_to_ms
            base_ms = time_str_to_ms(segments[-1]["end"]) + gap_ms

        current_ms = base_ms
        for i in range(missing_count):
            idx = len(segments) + 1
            st = current_ms
            en = st + duration_per_block_ms
            segments.append({
                "id": idx,
                "start": ms_to_time_str(st),
                "end": ms_to_time_str(en),
                "text": f"Dòng phụ đề #{idx}",
                "translation": f"Subtitle line #{idx}",
            })
            current_ms = en + gap_ms

    # 3. Gate 4: Text Preservation - inherit manual edits from Gate 1 Preview
    if preserved_segments:
        for idx, seg in enumerate(segments):
            if idx < len(preserved_segments):
                p_text = preserved_segments[idx].get("text")
                if p_text:
                    seg["text"] = p_text
                p_trans = preserved_segments[idx].get("translation")
                if p_trans:
                    seg["translation"] = p_trans

    return segments
