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
    "min_speech_duration_ms": 750,  # Lọc bỏ tạp âm/SFX/nhịp trống intro ngắn < 0.75s
}


def get_video_duration_ms(video_path: Optional[str]) -> Optional[int]:
    """Lấy thời lượng video (ms) từ container hoặc stream âm thanh."""
    if not video_path or not os.path.exists(video_path) or av is None:
        return None
    try:
        with av.open(video_path, mode="r", metadata_errors="ignore") as container:
            if container.duration:
                return int((container.duration / av.time_base) * 1000)
            if container.streams.audio and container.streams.audio[0].duration:
                s = container.streams.audio[0]
                if s.time_base:
                    return int(float(s.duration * s.time_base) * 1000)
    except Exception:
        pass
    return None


def extract_audio_window(
    video_path: Optional[str],
    start_offset_s: float = 0.0,
    max_duration_s: float = 180.0,
    sampling_rate: int = 16000,
) -> Optional[np.ndarray]:
    """
    Gate 1 & TC-VAD-10: Windowed Audio Extraction with Seek-Offset Frame Trimming.
    Decodes audio window starting from start_offset_s.
    Accurately drops excess audio samples from keyframe seek undershoot so sample 0
    corresponds exactly to start_offset_s.
    """
    if not video_path or not os.path.exists(video_path) or av is None:
        return None

    # Tận dụng cache Fast-Seek MP4 nếu có sẵn
    try:
        from core.video.transcode_service import get_cached_transcode
        cached_mp4 = get_cached_transcode(video_path)
        if cached_mp4 and os.path.exists(cached_mp4):
            video_path = cached_mp4
    except Exception:
        pass

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
        trimmed_lead = False
        lead_samples_to_drop = 0

        with av.open(video_path, mode="r", metadata_errors="ignore") as container:
            if not container.streams.audio:
                return None
            audio_stream = container.streams.audio[0]

            if start_offset_s > 0:
                time_base = audio_stream.time_base
                target_pts = int(start_offset_s / time_base) if time_base else 0
                container.seek(target_pts, stream=audio_stream, any_frame=False, backward=True)

            for frame in container.decode(audio_stream):
                # Kiểm tra timestamp để loại bỏ phần âm thanh dôi dư trước start_offset_s
                if start_offset_s > 0 and not trimmed_lead:
                    f_time = float(frame.pts * audio_stream.time_base) if (frame.pts is not None and audio_stream.time_base) else frame.time
                    if f_time is not None:
                        frame_duration = float(frame.samples) / float(frame.sample_rate) if frame.sample_rate else 0.0
                        if f_time + frame_duration <= start_offset_s:
                            # Khung này nằm hoàn toàn trước mốc yêu cầu -> bỏ qua
                            continue
                        elif f_time < start_offset_s:
                            lead_sec = start_offset_s - f_time
                            lead_samples_to_drop = int(lead_sec * sampling_rate)

                resampled_frames = resampler.resample(frame)
                for r_frame in resampled_frames:
                    arr = r_frame.to_ndarray()
                    dtype = arr.dtype
                    if lead_samples_to_drop > 0:
                        samples_in_frame = arr.shape[-1]
                        if samples_in_frame <= lead_samples_to_drop:
                            lead_samples_to_drop -= samples_in_frame
                            continue
                        else:
                            arr = arr[..., lead_samples_to_drop:]
                            lead_samples_to_drop = 0
                            trimmed_lead = True
                    else:
                        trimmed_lead = True

                    raw_buffer.write(arr.tobytes())
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
    min_speech_duration_ms: Optional[int] = None,
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
    minspeech = min_speech_duration_ms if min_speech_duration_ms is not None else DEFAULT_CFG9_PRESET.get("min_speech_duration_ms", 750)

    try:
        options = VadOptions(
            threshold=th,
            min_silence_duration_ms=msil,
            speech_pad_ms=spad,
            max_speech_duration_s=mmax,
            min_speech_duration_ms=minspeech,
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
    min_speech_duration_ms: Optional[int] = None,
    duration_per_block_ms: int = 2500,
    gap_ms: int = 500,
    preserved_segments: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Generates timing segments using VAD if audio is available.
    When a real video is loaded, scans speech chunks starting from start_offset_s
    up to count chunks or video end. Clamps timestamps within video duration.
    DOES NOT inject fake synthetic segments if fewer than count chunks are found in real video.
    Only falls back to synthetic timing when NO video is provided (offline demo mode).
    """
    segments: List[Dict[str, Any]] = []
    has_real_video = bool(video_path and os.path.exists(video_path))
    video_dur_ms = get_video_duration_ms(video_path) if has_real_video else None

    # 1. Try VAD extraction if video exists
    if has_real_video:
        # Window scan: scan sufficiently wide window (up to 300s or count * 60s) to catch count speech intervals
        scan_win_s = max(300.0, count * 60.0)
        audio = extract_audio_window(
            video_path,
            start_offset_s=start_offset_s,
            max_duration_s=scan_win_s,
        )
        if audio is not None:
            intervals = detect_speech_intervals_vad(
                audio,
                start_offset_s=start_offset_s,
                vad_threshold=vad_threshold,
                min_silence_ms=min_silence_ms,
                speech_pad_ms=speech_pad_ms,
                max_speech_duration_s=max_speech_duration_s,
                min_speech_duration_ms=min_speech_duration_ms,
            )
            for idx, inter in enumerate(intervals[:count]):
                st_ms = inter["start_ms"]
                en_ms = inter["end_ms"]
                if video_dur_ms:
                    if st_ms >= video_dur_ms:
                        continue
                    en_ms = min(video_dur_ms, en_ms)
                if en_ms <= st_ms:
                    continue
                segments.append({
                    "id": idx + 1,
                    "start": ms_to_time_str(st_ms),
                    "end": ms_to_time_str(en_ms),
                    "text": "",
                    "translation": "",
                })

    # 2. Gate 3: Fallback only when NO VIDEO is loaded (demo/offline mode without video)
    if not has_real_video and len(segments) < count:
        missing_count = count - len(segments)
        base_ms = int(start_offset_s * 1000) if start_offset_s > 0 else gap_ms
        if segments:
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
