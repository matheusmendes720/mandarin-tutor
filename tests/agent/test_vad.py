"""Tests for VoiceActivityDetector."""
import numpy as np
import pytest

from lingua.agent.vad import VoiceActivityDetector


class TestVoiceActivityDetector:
    """Test suite for VoiceActivityDetector."""

    def test_vad_detects_speech_above_threshold(self):
        """Verify energy-based speech detection above threshold."""
        vad = VoiceActivityDetector(energy_threshold=0.01)
        # Create a chunk with RMS > 0.01 (speech-like audio)
        speech_chunk = np.random.randn(1600).astype(np.float32) * 0.1
        assert vad.is_speech(speech_chunk) is True

    def test_vad_detects_silence_below_threshold(self):
        """Verify silence returns False for low energy."""
        vad = VoiceActivityDetector(energy_threshold=0.01)
        # Create a chunk with RMS < 0.01 (silence-like audio)
        silence_chunk = np.zeros(1600, dtype=np.float32) * 0.001
        assert vad.is_speech(silence_chunk) is False

    def test_vad_turn_end_after_silence(self):
        """Verify turn end detection after 3+ silent chunks."""
        vad = VoiceActivityDetector(energy_threshold=0.01)
        silence_chunk = np.zeros(1600, dtype=np.float32) * 0.001

        # First 2 silent chunks - should not be turn end yet
        vad.is_speech(silence_chunk)
        vad.is_speech(silence_chunk)
        assert vad.is_turn_end() is False

        # Third silent chunk - should now be turn end
        vad.is_speech(silence_chunk)
        assert vad.is_turn_end() is True

    def test_vad_interrupt_during_speech(self):
        """Verify interruption detection when speech detected during speaking state."""
        vad = VoiceActivityDetector(energy_threshold=0.01)
        # Simulate "speaking" state by having speech in history
        speech_chunk = np.random.randn(1600).astype(np.float32) * 0.1
        vad.is_speech(speech_chunk)

        # New speech chunk should be detected as interrupt
        new_speech = np.random.randn(1600).astype(np.float32) * 0.1
        assert vad.is_interrupt(new_speech) is True
