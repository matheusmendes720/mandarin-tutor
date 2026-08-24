"""Whisper-based pronunciation scoring using g2p for phoneme comparison."""
from typing import Any

from lingua.pronunciation.scorer import compute_phoneme_score


class WhisperPhonemeScorer:
    """Pronunciation scorer using Whisper for transcription and g2p for phonemes."""

    def __init__(self, model_name: str = "medium") -> None:
        """Initialize Whisper model.

        Args:
            model_name: Whisper model size (tiny, base, small, medium, large).
        """
        self.model_name = model_name
        self._model: Any = None
        self._load_model()

    def _load_model(self) -> None:
        """Load Whisper model lazily."""
        try:
            import whisper
            self._model = whisper.load_model(self.model_name)
        except ImportError:
            self._model = None

    def _g2p(self, text: str) -> list[str]:
        """Convert text to phonemes using g2p.

        Args:
            text: Input text to convert.

        Returns:
            List of phoneme strings.
        """
        try:
            from g2p import G2p
            out = G2p()(text)
            return [phoneme for phoneme in out if phoneme not in (" ", "_", "EOS")]
        except ImportError:
            # Fallback: return character-based representation
            return list(text.lower())

    def _transcribe(self, audio_path: str) -> str | None:
        """Transcribe audio file using Whisper.

        Args:
            audio_path: Path to audio file.

        Returns:
            Transcribed text or None if transcription fails.
        """
        if self._model is None:
            raise RuntimeError("Whisper model not loaded. Install openai-whisper.")

        try:
            import whisper
            result = self._model.transcribe(audio_path, fp16=False)
            return result.get("text", "").strip()
        except Exception:
            return None

    def score(self, audio_path: str, target_text: str) -> dict[str, Any]:
        """Score pronunciation against target text.

        Args:
            audio_path: Path to audio file.
            target_text: Expected text pronunciation.

        Returns:
            Dict with keys: score (0-100), transcription, expected_phonemes,
            transcribed_phonemes.
        """
        # Step 1: Transcribe audio
        transcribed_text = self._transcribe(audio_path)
        if transcribed_text is None:
            return {
                "score": 0,
                "transcription": "",
                "expected_phonemes": [],
                "transcribed_phonemes": [],
                "error": "Transcription failed",
            }

        # Step 2: Get expected phonemes from target text
        expected_phonemes = self._g2p(target_text)

        # Step 3: Get transcribed phonemes
        transcribed_phonemes = self._g2p(transcribed_text)

        # Step 4: Compute score (0-1 to 0-100)
        raw_score = compute_phoneme_score(expected_phonemes, transcribed_phonemes)
        score = int(raw_score * 100)

        return {
            "score": score,
            "transcription": transcribed_text,
            "expected_phonemes": expected_phonemes,
            "transcribed_phonemes": transcribed_phonemes,
        }
