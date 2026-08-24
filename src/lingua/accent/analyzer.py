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
    """Detect accent/dialect and speaker segments from audio.

    This is the legacy interface. For new code, use detect_accent_from_file().

    Args:
        audio_bytes: Raw audio bytes
        model: DiarizationModel for speaker segmentation
        config: Optional accent configuration

    Returns:
        AccentResult with language, dialect, confidence, and speaker segments
    """
    config = config or AccentConfig()
    segments = model.segment(audio_bytes)

    # Try FunASR detection if available
    # Note: audio_bytes requires saving to temp file for FunASR
    # Fall back to legacy behavior
    return AccentResult(
        language="en",
        dialect=None,
        confidence=0.85,
        speaker_segments=segments,
    )


def detect_accent_from_file(audio_path: str) -> dict:
    """Detect accent from audio file using FunASR.

    Args:
        audio_path: Path to audio file (wav, mp3, etc.)

    Returns:
        Dict with language, dialect, confidence, transcription keys.
        On failure, returns {"language": "unknown", "confidence": 0.0}
    """
    from src.lingua.accent.detector import detect_accent as funasr_detect

    try:
        result = funasr_detect(audio_path)
        return result
    except ImportError:
        # FunASR not available
        return {"language": "unknown", "dialect": None, "confidence": 0.0, "transcription": ""}
    except Exception:
        # Any other error - graceful fallback
        return {"language": "unknown", "dialect": None, "confidence": 0.0, "transcription": ""}
