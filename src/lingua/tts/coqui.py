"""Coqui XTTS TTS engine implementation."""
from __future__ import annotations

import io

import numpy as np
from scipy.io import wavfile

DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_SAMPLE_RATE = 24000


class CoquiTTSModel:
    """Coqui XTTS text-to-speech model.

    Uses the Coqui TTS library for offline, local synthesis.
    Requires the TTS package to be installed.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        """Initialize the Coqui TTS model.

        Args:
            model_name: The model to use for synthesis.
                        Defaults to xtts_v2 multilingual model.
        """
        self.model_name = model_name
        self._model = None

    @property
    def model(self):  # type: ignore[return]
        """Lazy-load the TTS model on first access."""
        if self._model is None:
            try:
                from TTS.tts.configs.xtts_config import XttsConfig
                from TTS.tts.models.xtts import Xtts
            except ImportError as e:
                msg = (
                    "Coqui TTS is not installed. Install it with:\n"
                    "  pip install TTS\n"
                    "Note: This requires a significant amount of disk space for model downloads."
                )
                raise ImportError(msg) from e

            self._model = Xtts.init_from_config(XttsConfig())
            self._model.load_model()
        return self._model

    def synthesize(self, text: str, speaker_id: int = 0) -> tuple[bytes, int]:
        """Synthesize text to audio.

        Args:
            text: The text to synthesize.
            speaker_id: Speaker ID (ignored for XTTS, included for protocol compatibility).

        Returns:
            Tuple of (audio_bytes, sample_rate) where audio_bytes is WAV format.
        """
        # Run synthesis
        wav = self.model.synthesize(text, language="en")

        # Ensure numpy array
        if isinstance(wav, list):
            wav = np.array(wav)

        # Normalize to 16-bit PCM range if needed
        wav = np.clip(wav, -1.0, 1.0)
        if wav.max() > 1.0 or wav.min() < -1.0:
            wav = wav / max(abs(wav.max()), abs(wav.min()))

        # Convert float32 to int16
        wav_int16 = (wav * 32767).astype(np.int16)

        # Write to WAV format in memory
        buffer = io.BytesIO()
        wavfile.write(buffer, XTTS_SAMPLE_RATE, wav_int16)
        buffer.seek(0)

        return buffer.read(), XTTS_SAMPLE_RATE
