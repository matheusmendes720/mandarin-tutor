"""Tests for Coqui XTTS TTS model."""
import pytest

# Check if TTS is available
try:
    from TTS.tts.configs.xtts_config import XttsConfig

    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not TTS_AVAILABLE, reason="TTS not installed")


def test_coqui_tts_model_instantiation():
    """Test CoquiTTSModel can be instantiated with default model."""
    from lingua.tts.coqui import CoquiTTSModel, DEFAULT_MODEL

    model = CoquiTTSModel()
    assert model.model_name == DEFAULT_MODEL
    assert model._model is None  # Lazy loaded


def test_coqui_tts_model_custom_model_name():
    """Test CoquiTTSModel can be instantiated with custom model."""
    from lingua.tts.coqui import CoquiTTSModel

    model = CoquiTTSModel(model_name="custom_model")
    assert model.model_name == "custom_model"


def test_coqui_tts_synthesize_returns_tuple():
    """Test synthesize() returns (bytes, int) tuple."""
    from lingua.tts.coqui import CoquiTTSModel, XTTS_SAMPLE_RATE

    model = CoquiTTSModel()
    result = model.synthesize("Hello world")

    assert isinstance(result, tuple)
    assert len(result) == 2
    audio_bytes, sample_rate = result
    assert isinstance(audio_bytes, bytes)
    assert isinstance(sample_rate, int)


def test_coqui_tts_synthesize_returns_non_empty_bytes():
    """Test synthesize() returns non-empty audio bytes."""
    from lingua.tts.coqui import CoquiTTSModel

    model = CoquiTTSModel()
    audio_bytes, _ = model.synthesize("Hello world")

    assert len(audio_bytes) > 0


def test_coqui_tts_sample_rate():
    """Test synthesize() returns correct sample rate (24000 Hz for XTTS)."""
    from lingua.tts.coqui import CoquiTTSModel, XTTS_SAMPLE_RATE

    model = CoquiTTSModel()
    _, sample_rate = model.synthesize("Hello world")

    assert sample_rate == XTTS_SAMPLE_RATE
    assert sample_rate == 24000


def test_coqui_tts_with_different_text():
    """Test synthesize() works with different text inputs."""
    from lingua.tts.coqui import CoquiTTSModel

    model = CoquiTTSModel()

    test_texts = ["Hello", "Testing one two three", "A longer sentence for testing"]

    for text in test_texts:
        audio_bytes, sample_rate = model.synthesize(text)
        assert len(audio_bytes) > 0
        assert sample_rate == 24000


def test_coqui_tts_speaker_id_optional():
    """Test synthesize() accepts optional speaker_id parameter."""
    from lingua.tts.coqui import CoquiTTSModel

    model = CoquiTTSModel()
    # Should work with speaker_id
    result = model.synthesize("Hello", speaker_id=0)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_coqui_tts_wav_format():
    """Test synthesize() returns valid WAV format audio."""
    from lingua.tts.coqui import CoquiTTSModel
    import io
    from scipy.io import wavfile

    model = CoquiTTSModel()
    audio_bytes, sample_rate = model.synthesize("Test")

    # Should be able to read as WAV
    buffer = io.BytesIO(audio_bytes)
    rate, data = wavfile.read(buffer)

    assert rate == sample_rate
    assert len(data) > 0
