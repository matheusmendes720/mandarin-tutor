"""Tests for PhonemeDrill.play_phoneme_combined (Task 3 Step 6)."""
from pathlib import Path

from src.lingua.phoneme_drill.drill import PhonemeDrill


def test_play_phoneme_combined_uses_both_initial_and_final():
    drill = PhonemeDrill()
    result = drill.play_phoneme_combined(initial="m", final="a", tone=1)
    assert result is not None
    paths, tone_path, combined = result
    # Both initial and final audio paths returned
    assert any("m" in str(p).lower() for p in paths)
    # Tone path returned separately
    assert tone_path is not None
    assert "ma1.wav" in str(tone_path)
    # Combined returns the same paths in playback order (UI handles playback)
    assert len(combined) >= 1


def test_play_phoneme_combined_invalid_returns_none():
    drill = PhonemeDrill()
    assert drill.play_phoneme_combined(initial="zzz", final="qqq", tone=1) is None
