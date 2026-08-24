"""TTS engine wrapper for language learning prompts."""
from dataclasses import dataclass
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


def synthesize_text(model: TTSModel, text: str, speaker_id: int = 0) -> SynthesisResult:
    """Synthesize text to audio with duration metadata."""
    audio_bytes, sample_rate = model.synthesize(text, speaker_id)
    duration = estimate_duration(audio_bytes, sample_rate)
    return SynthesisResult(audio_bytes=audio_bytes, sample_rate=sample_rate, duration_seconds=duration)
