"""Voice Activity Detection for turn switching."""
from __future__ import annotations

import numpy as np


class VoiceActivityDetector:
    """Energy-based voice activity detection for turn switching.

    Uses RMS energy thresholding to detect speech and manages state
    for turn-end and interruption detection.
    """

    def __init__(self, energy_threshold: float = 0.01) -> None:
        """Initialize VAD with energy threshold.

        Parameters
        ----------
        energy_threshold : float
            RMS energy threshold for speech detection (default 0.01).
        """
        self.energy_threshold = energy_threshold
        self.speech_history: list[bool] = []
        self.max_history = 10

    def is_speech(self, chunk: np.ndarray) -> bool:
        """Detect if chunk contains speech based on RMS energy.

        Parameters
        ----------
        chunk : np.ndarray
            Audio chunk as numpy array.

        Returns
        -------
        bool
            True if RMS energy exceeds threshold (speech detected).
        """
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        is_speech = rms > self.energy_threshold

        # Maintain history for turn-end detection
        self.speech_history.append(is_speech)
        if len(self.speech_history) > self.max_history:
            self.speech_history.pop(0)

        return is_speech

    def is_turn_end(self) -> bool:
        """Check if current position marks end of user turn.

        Returns
        -------
        bool
            True if last 3 consecutive chunks are silence.
        """
        return len(self.speech_history) >= 3 and not any(self.speech_history[-3:])

    def is_interrupt(self, chunk: np.ndarray) -> bool:
        """Detect interruption during speaking state.

        Parameters
        ----------
        chunk : np.ndarray
            Audio chunk to check for speech.

        Returns
        -------
        bool
            True if speech detected while in speaking state.
        """
        return self.is_speech(chunk)
