"""Global configuration and Protocol interfaces for all subsystems."""
from dataclasses import dataclass, field
from typing import Protocol


# ── Pronunciation ─────────────────────────────────────────────────────────────

@dataclass
class PronunciationConfig:
    model_name: str = "openai/whisper-large-v3"
    language: str = "en"
    scoring_threshold: float = 0.70


class PhonemeAnalyzer(Protocol):
    """Analyzes text into phoneme sequences."""

    def analyze(self, text: str) -> list[str]:
        """Return phoneme sequence for input text."""
        ...


# ── TTS ────────────────────────────────────────────────────────────────────────

@dataclass
class TTSConfig:
    model_name: str = "mozilla/TTS"
    sample_rate: int = 22050


class TTSModel(Protocol):
    """Text-to-speech synthesis model."""

    def synthesize(self, text: str, speaker_id: int = 0) -> tuple[bytes, int]:
        """Return (wav_bytes, sample_rate)."""
        ...


# ── Accent ────────────────────────────────────────────────────────────────────

@dataclass
class AccentConfig:
    funasr_model: str = "paraformer-zh"
    diarization_model: str = "pyannote/pepper"
    supported_languages: list[str] = field(
        default_factory=lambda: ["en", "zh", "ja", "ko", "es", "fr", "de"]
    )


class DiarizationModel(Protocol):
    """Speaker diarization model."""

    def segment(self, audio_bytes: bytes) -> list[dict]:
        """Return [{start, end, speaker}] for audio."""
        ...


# ── Vocab SRS ─────────────────────────────────────────────────────────────────

@dataclass
class VocabConfig:
    fsrs_optimization: bool = True
    max_reviews_per_day: int = 200


# ── Voice Agent ───────────────────────────────────────────────────────────────

@dataclass
class VoiceAgentConfig:
    language: str = "en"
    system_prompt: str = (
        "You are a friendly language tutor. "
        "Help the user practice pronunciation and vocabulary. "
        "Always respond with encouragement and correction tips."
    )
    voice_model: str = "sensevoice"
    max_turns: int = 20
