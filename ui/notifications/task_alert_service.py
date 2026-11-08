import os
import math
import wave
import struct
import logging
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWidgets import QApplication, QWidget

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:
    QSoundEffect = None

logger = logging.getLogger(__name__)

def _ensure_chime_wav_exists(wav_path: str) -> str:
    """Generate a gentle harmonic audio chime if it does not already exist."""
    if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
        return wav_path

    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    sample_rate = 44100
    duration_s = 0.4
    num_samples = int(sample_rate * duration_s)

    try:
        with wave.open(wav_path, "w") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)

            # Soft two-tone chord: 523.25 Hz (C5) + 659.25 Hz (E5) with exponential decay
            freq1 = 523.25
            freq2 = 659.25
            frames = bytearray()

            for i in range(num_samples):
                t = i / sample_rate
                decay = math.exp(-6.0 * t)
                wave1 = 0.5 * math.sin(2.0 * math.pi * freq1 * t)
                wave2 = 0.35 * math.sin(2.0 * math.pi * freq2 * t)
                sample = int(32767.0 * (wave1 + wave2) * decay)
                sample = max(-32768, min(32767, sample))
                frames.extend(struct.pack("<h", sample))

            wav_file.writeframes(frames)
    except Exception as exc:
        logger.warning(f"Could not generate default chime wav at {wav_path}: {exc}")

    return wav_path


class TaskAlertService(QObject):
    """Notification service for task waiting approval alerts via taskbar flash and chime sound."""

    def __init__(self, parent: Optional[QObject] = None, sound_path: Optional[str] = None):
        super().__init__(parent)
        self._sound_effect = None
        self._sound_path = sound_path or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "resources", "audio", "chime.wav")
        )
        self._init_sound()

    def _init_sound(self):
        """Safely initialize QSoundEffect with gentle chime."""
        if QSoundEffect is None:
            logger.info("QSoundEffect not available in current Qt environment.")
            return

        try:
            chime_file = _ensure_chime_wav_exists(self._sound_path)
            if os.path.exists(chime_file):
                self._sound_effect = QSoundEffect(self)
                self._sound_effect.setSource(QUrl.fromLocalFile(chime_file))
                self._sound_effect.setVolume(0.7)
        except Exception as exc:
            logger.warning(f"TaskAlertService failed to initialize audio device: {exc}")

    def alert_window(self, window: Optional[QWidget] = None):
        """Flash the window icon on the Windows taskbar."""
        target_win = window or QApplication.activeWindow()
        if target_win is not None:
            try:
                QApplication.alert(target_win, 0)
            except Exception as exc:
                logger.warning(f"Failed to alert window {target_win}: {exc}")

    def play_chime(self):
        """Play soft audio chime without raising any exception."""
        if self._sound_effect is not None:
            try:
                self._sound_effect.play()
            except Exception as exc:
                logger.warning(f"Failed to play audio chime: {exc}")

    @Slot(str)
    def on_notification_requested(self, message: str = ""):
        """Slot to handle notification_requested signal from AgentCopilotController."""
        self.notify_task_waiting_approval(None, message)

    def notify_task_waiting_approval(self, window: Optional[QWidget] = None, message: str = "") -> bool:
        """Trigger taskbar flash and chime sound simultaneously."""
        self.alert_window(window)
        self.play_chime()
        return True
