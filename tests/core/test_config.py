"""Tests for core config and Protocol interfaces."""
import pytest


def test_pronunciation_config_defaults():
    from lingua.core.config import PronunciationConfig

    cfg = PronunciationConfig()
    assert cfg.model_name == "openai/whisper-large-v3"
    assert cfg.language == "en"
    assert cfg.scoring_threshold == 0.70


def test_phoneme_analyzer_protocol_exists():
    from lingua.core.config import PhonemeAnalyzer

    # Verify it's a Protocol
    assert hasattr(PhonemeAnalyzer, "analyze")


def test_tts_config_defaults():
    from lingua.core.config import TTSConfig

    cfg = TTSConfig()
    assert cfg.model_name == "mozilla/TTS"
    assert cfg.sample_rate == 22050


def test_tts_model_protocol_exists():
    from lingua.core.config import TTSModel

    # Verify it's a Protocol
    assert hasattr(TTSModel, "synthesize")


def test_accent_config_defaults():
    from lingua.core.config import AccentConfig

    cfg = AccentConfig()
    assert cfg.funasr_model == "paraformer-zh"
    assert cfg.diarization_model == "pyannote/pepper"
    assert cfg.supported_languages == ["en", "zh", "ja", "ko", "es", "fr", "de"]


def test_diarization_model_protocol_exists():
    from lingua.core.config import DiarizationModel

    # Verify it's a Protocol
    assert hasattr(DiarizationModel, "segment")


def test_vocab_config_defaults():
    from lingua.core.config import VocabConfig

    cfg = VocabConfig()
    assert cfg.fsrs_optimization is True
    assert cfg.max_reviews_per_day == 200


def test_voice_agent_config_defaults():
    from lingua.core.config import VoiceAgentConfig

    cfg = VoiceAgentConfig()
    assert cfg.language == "en"
    assert cfg.voice_model == "sensevoice"
    assert cfg.max_turns == 20
    assert "language tutor" in cfg.system_prompt
