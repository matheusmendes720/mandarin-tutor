"""Tests for accent analyzer."""
import unittest
from unittest.mock import MagicMock, patch

from src.lingua.accent.analyzer import AccentResult, detect_accent
from src.lingua.core.config import AccentConfig, DiarizationModel


class TestAccentResult(unittest.TestCase):
    """Test AccentResult dataclass."""

    def test_accent_result_fields(self):
        """AccentResult should have language, dialect, confidence, speaker_segments fields."""
        result = AccentResult(
            language="en",
            dialect=None,
            confidence=0.85,
            speaker_segments=[{"start": 0.0, "end": 1.0, "speaker": "S1"}],
        )
        self.assertEqual(result.language, "en")
        self.assertIsNone(result.dialect)
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(
            result.speaker_segments, [{"start": 0.0, "end": 1.0, "speaker": "S1"}]
        )


class TestDetectAccent(unittest.TestCase):
    """Test detect_accent function."""

    def test_detect_accent_returns_en_with_default_confidence(self):
        """detect_accent should return language='en', dialect=None, confidence=0.85."""
        mock_model = MagicMock(spec=DiarizationModel)
        mock_model.segment.return_value = [{"start": 0.0, "end": 1.0, "speaker": "S1"}]

        result = detect_accent(b"fake_audio_bytes", mock_model)

        self.assertIsInstance(result, AccentResult)
        self.assertEqual(result.language, "en")
        self.assertIsNone(result.dialect)
        self.assertEqual(result.confidence, 0.85)

    def test_detect_accent_calls_model_segment(self):
        """detect_accent should call model.segment with the provided audio_bytes."""
        mock_model = MagicMock(spec=DiarizationModel)
        mock_model.segment.return_value = []

        audio_bytes = b"test_audio_data"
        detect_accent(audio_bytes, mock_model)

        mock_model.segment.assert_called_once_with(audio_bytes)


if __name__ == "__main__":
    unittest.main()
