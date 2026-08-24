"""Accent detection and speaker diarization."""
from dataclasses import dataclass
from src.lingua.core.config import AccentConfig, DiarizationModel


@dataclass
class AccentResult:
    language: str
    dialect: str | None
    confidence: float
    speaker_segments: list[dict]


def detect_accent(
    audio_bytes: bytes,
    model: DiarizationModel,
    config: AccentConfig | None = None,
) -> AccentResult:
    """Detect accent/dialect and speaker segments from audio."""
    config = config or AccentConfig()
    segments = model.segment(audio_bytes)
    # FunASR integration point — returns (language, dialect, confidence)
    # Stub returns "en" with 0.85 confidence
    return AccentResult(
        language="en",
        dialect=None,
        confidence=0.85,
        speaker_segments=segments,
    )
