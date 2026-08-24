"""Tests for TTS synthesis engine."""
import pytest
from unittest.mock import Mock


def test_estimate_duration_zero_bytes():
    """Test estimate_duration with 0 bytes returns 0.0 seconds."""
    from lingua.tts.engine import estimate_duration

    result = estimate_duration(b"", 22050)
    assert result == 0.0


def test_estimate_duration_44100_bytes_at_22050_hz():
    """Test estimate_duration with 44100 bytes at 22050 Hz returns 1.0 seconds."""
    from lingua.tts.engine import estimate_duration

    # 44100 bytes / 2 = 22050 frames / 22050 Hz = 1.0 second
    audio_bytes = b"\x00" * 44100
    result = estimate_duration(audio_bytes, 22050)
    assert result == 1.0


def test_estimate_duration_88200_bytes_at_22050_hz():
    """Test estimate_duration with 88200 bytes at 22050 Hz returns 2.0 seconds."""
    from lingua.tts.engine import estimate_duration

    # 88200 bytes / 2 = 44100 frames / 22050 Hz = 2.0 seconds
    audio_bytes = b"\x00" * 88200
    result = estimate_duration(audio_bytes, 22050)
    assert result == 2.0


def test_estimate_duration_mismatched_byte_count():
    """Test estimate_duration with odd byte count uses floor division."""
    from lingua.tts.engine import estimate_duration

    # With odd byte count, floor division should handle it
    # 3 bytes / 2 = 1 frame / 22050 Hz = ~0.000045 seconds
    audio_bytes = b"\x00\x01\x02"  # 3 bytes
    result = estimate_duration(audio_bytes, 22050)
    assert result == 1 / 22050  # floor(3/2) = 1 frame


def test_synthesize_text_returns_synthesis_result():
    """Test synthesize_text returns SynthesisResult with correct duration."""
    from lingua.tts.engine import SynthesisResult, synthesize_text, estimate_duration
    from lingua.core.config import TTSModel

    # Create mock TTS model
    mock_model = Mock(spec=TTSModel)
    # Return 44100 bytes at 22050 Hz = 1 second
    mock_model.synthesize.return_value = (b"\x00" * 44100, 22050)

    result = synthesize_text(mock_model, "Hello world", speaker_id=0)

    assert isinstance(result, SynthesisResult)
    assert result.sample_rate == 22050
    assert result.audio_bytes == b"\x00" * 44100
    # Duration should be estimated: 44100 // 2 = 22050 frames / 22050 = 1.0
    assert result.duration_seconds == 1.0
    mock_model.synthesize.assert_called_once_with("Hello world", 0)


def test_synthesis_result_dataclass():
    """Test SynthesisResult dataclass has correct fields."""
    from lingua.tts.engine import SynthesisResult

    result = SynthesisResult(
        audio_bytes=b"test",
        sample_rate=22050,
        duration_seconds=1.5
    )

    assert result.audio_bytes == b"test"
    assert result.sample_rate == 22050
    assert result.duration_seconds == 1.5
