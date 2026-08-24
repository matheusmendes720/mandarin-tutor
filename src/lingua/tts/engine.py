"""TTS engine wrapper for language learning prompts."""
from dataclasses import dataclass
from typing import overload

from src.lingua.core.config import TTSModel


@dataclass
class SynthesisResult:
    audio_bytes: bytes
    sample_rate: int
    duration_seconds: float


def estimate_duration(audio_bytes: bytes, sample_rate: int) -> float:
    """Estimate duration from 16-bit PCM audio bytes."""
    frames = len(audio_bytes) // 2
    return frames / sample_rate


@overload
def synthesize_text(
    text: str,
    model: TTSModel | None = None,
    speaker_id: int = 0,
) -> SynthesisResult: ...


@overload
def synthesize_text(
    model: TTSModel,
    text: str,
    speaker_id: int = 0,
) -> SynthesisResult: ...


def synthesize_text(
    text_or_model: str | TTSModel,
    text_or_model2: str | TTSModel | None = None,
    speaker_id: int = 0,
) -> SynthesisResult:
    """Synthesize text to audio with duration metadata.

    Supports both new and legacy calling conventions:
    - New: synthesize_text("Hello") or synthesize_text("Hello", model=my_model)
    - Legacy: synthesize_text(model, "Hello")

    Args:
        text_or_model: Either text (new API) or model (legacy API).
        text_or_model2: Either model (new API) or text (legacy API).
        speaker_id: Speaker ID for models that support multiple speakers.

    Returns:
        SynthesisResult with audio bytes, sample rate, and duration.
    """
    # Detect legacy API: first arg has synthesize method
    if hasattr(text_or_model, "synthesize"):
        model: TTSModel = text_or_model  # type: ignore[assignment]
        text: str = text_or_model2  # type: ignore[assignment]
    else:
        text = text_or_model  # type: ignore[assignment]
        model = text_or_model2  # type: ignore[assignment]

    if model is None:
        from src.lingua.tts.coqui import CoquiTTSModel

        model = CoquiTTSModel()

    audio_bytes, sample_rate = model.synthesize(text, speaker_id)
    duration = estimate_duration(audio_bytes, sample_rate)
    return SynthesisResult(audio_bytes=audio_bytes, sample_rate=sample_rate, duration_seconds=duration)
