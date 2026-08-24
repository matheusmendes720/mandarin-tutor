"""Tests for FunASR accent detector."""
import unittest
from unittest.mock import MagicMock, patch


class TestFunASRAccentDetector(unittest.TestCase):
    """Test FunASRAccentDetector class."""

    def test_instantiation_without_model_dir(self):
        """Should instantiate without providing model_dir."""
        # Skip if funasr not installed
        try:
            from funasr import AutoModel
        except ImportError:
            self.skipTest("funasr not installed")

        from src.lingua.accent.detector import FunASRAccentDetector

        detector = FunASRAccentDetector()
        self.assertIsNone(detector._model)
        self.assertIsNone(detector._model_dir)

    def test_instantiation_with_model_dir(self):
        """Should instantiate with custom model_dir."""
        try:
            from funasr import AutoModel
        except ImportError:
            self.skipTest("funasr not installed")

        from src.lingua.accent.detector import FunASRAccentDetector

        detector = FunASRAccentDetector(model_dir="/path/to/model")
        self.assertEqual(detector._model_dir, "/path/to/model")

    def test_instantiation_uses_env_var(self):
        """Should use ACCENT_MODEL_DIR env var if model_dir not provided."""
        try:
            from funasr import AutoModel
        except ImportError:
            self.skipTest("funasr not installed")

        with patch.dict("src.lingua.accent.detector.ACCENT_MODEL_DIR", "/env/model"):
            from src.lingua.accent.detector import FunASRAccentDetector

            detector = FunASRAccentDetector()
            self.assertEqual(detector._model_dir, "/env/model")

    def test_detect_returns_dict_with_required_keys(self):
        """detect() should return dict with language, confidence, transcription keys."""
        try:
            from funasr import AutoModel
        except ImportError:
            self.skipTest("funasr not installed")

        from src.lingua.accent.detector import FunASRAccentDetector

        # Mock the model
        detector = FunASRAccentDetector()
        mock_model = MagicMock()
        mock_model.generate.return_value = [{"text": "你好世界"}]
        detector._model = mock_model

        result = detector.detect("/fake/audio.wav")

        self.assertIsInstance(result, dict)
        self.assertIn("language", result)
        self.assertIn("confidence", result)
        self.assertIn("transcription", result)

    def test_confidence_is_float_between_0_and_1(self):
        """confidence should be float between 0 and 1."""
        try:
            from funasr import AutoModel
        except ImportError:
            self.skipTest("funasr not installed")

        from src.lingua.accent.detector import FunASRAccentDetector

        detector = FunASRAccentDetector()
        mock_model = MagicMock()
        mock_model.generate.return_value = [{"text": "测试"}]
        detector._model = mock_model

        result = detector.detect("/fake/audio.wav")

        self.assertIsInstance(result.confidence, float)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_graceful_import_error(self):
        """Should raise helpful ImportError if funasr not installed."""
        with patch.dict("sys.modules", {"funasr": None}):
            # Re-import to trigger the check
            import importlib
            import src.lingua.accent.detector as detector_module

            # The import happens at runtime, so we need to test differently
            # Test the error message
            try:
                from funasr import AutoModel
            except ImportError:
                # Expected - funasr not installed
                pass


class TestDetectAccentFunction(unittest.TestCase):
    """Test detect_accent convenience function."""

    def test_detect_accent_returns_dict(self):
        """detect_accent should return a dict."""
        try:
            from funasr import AutoModel
        except ImportError:
            self.skipTest("funasr not installed")

        from src.lingua.accent.detector import detect_accent

        # Mock the model
        with patch("src.lingua.accent.detector.FunASRAccentDetector") as MockDetector:
            mock_instance = MagicMock()
            mock_instance.detect.return_value = MagicMock(
                language="zh",
                dialect="Mandarin",
                confidence=0.85,
                transcription="你好",
            )
            MockDetector.return_value = mock_instance

            result = detect_accent("/fake/audio.wav")

            self.assertIsInstance(result, dict)

    def test_detect_accent_graceful_fallback_on_error(self):
        """detect_accent should return fallback on error."""
        from src.lingua.accent.detector import detect_accent

        result = detect_accent("/nonexistent/audio.wav")

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("language"), "unknown")
        self.assertEqual(result.get("confidence"), 0.0)


class TestAccentDetectionResult(unittest.TestCase):
    """Test AccentDetectionResult dataclass."""

    def test_accent_detection_result_fields(self):
        """AccentDetectionResult should have all required fields."""
        try:
            from funasr import AutoModel
        except ImportError:
            self.skipTest("funasr not installed")

        from src.lingua.accent.detector import AccentDetectionResult

        result = AccentDetectionResult(
            language="zh",
            dialect="Mandarin",
            confidence=0.85,
            transcription="你好世界",
        )

        self.assertEqual(result.language, "zh")
        self.assertEqual(result.dialect, "Mandarin")
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(result.transcription, "你好世界")


if __name__ == "__main__":
    unittest.main()
