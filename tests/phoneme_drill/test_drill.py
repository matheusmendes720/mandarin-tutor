"""Tests for phoneme drill functionality."""
import pytest
from pathlib import Path
from src.lingua.phoneme_drill.drill import PhonemeDrill


class TestPhonemeDrill:
    """Test suite for PhonemeDrill class."""

    @pytest.fixture
    def drill(self) -> PhonemeDrill:
        """Create a PhonemeDrill instance for testing."""
        return PhonemeDrill()

    def test_list_initials_returns_non_empty_list(self, drill: PhonemeDrill) -> None:
        """Test that list_initials() returns a non-empty list."""
        initials = drill.list_initials()
        assert isinstance(initials, list)
        assert len(initials) > 0
        assert "ma" in initials

    def test_list_finals_returns_non_empty_list(self, drill: PhonemeDrill) -> None:
        """Test that list_finals() returns a non-empty list."""
        finals = drill.list_finals()
        assert isinstance(finals, list)
        assert len(finals) > 0
        assert "a" in finals

    def test_play_phoneme_ma_returns_path(self, drill: PhonemeDrill) -> None:
        """Test that play_phoneme("ma") returns a path."""
        result = drill.play_phoneme("ma")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], Path)
        assert result[0].exists()

    def test_play_tone_returns_path(self, drill: PhonemeDrill) -> None:
        """Test that play_tone(1) returns path to ma1.wav."""
        result = drill.play_tone(1)
        assert result is not None
        assert isinstance(result, Path)
        assert result.exists()
        assert result.name == "ma1.wav"

    def test_play_tone_all_tones(self, drill: PhonemeDrill) -> None:
        """Test that all tone numbers 1-5 return valid paths."""
        for tone in range(1, 6):
            result = drill.play_tone(tone)
            assert result is not None, f"Tone {tone} should return a path"
            assert result.exists(), f"Tone {tone} file should exist"
            assert result.name == f"ma{tone}.wav"

    def test_play_phoneme_ba(self, drill: PhonemeDrill) -> None:
        """Test play_phoneme for "ba"."""
        result = drill.play_phoneme("ba")
        assert result is not None
        assert len(result) > 0
        assert result[0].exists()

    def test_play_phoneme_with_tone(self, drill: PhonemeDrill) -> None:
        """Test play_phoneme_with_tone returns valid path."""
        result = drill.play_phoneme_with_tone("ma", 2)
        assert result is not None
        assert result.exists()

    def test_play_phoneme_invalid_returns_none(self, drill: PhonemeDrill) -> None:
        """Test that invalid phoneme returns None."""
        result = drill.play_phoneme("xyz123")
        assert result is None

    def test_play_tone_invalid_returns_none(self, drill: PhonemeDrill) -> None:
        """Test that invalid tone number returns None."""
        result = drill.play_tone(0)
        assert result is None
        result = drill.play_tone(6)
        assert result is None
        result = drill.play_tone(-1)
        assert result is None

    def test_play_phoneme_empty_returns_none(self, drill: PhonemeDrill) -> None:
        """Test that empty phoneme returns None."""
        result = drill.play_phoneme("")
        assert result is None
        result = drill.play_phoneme("   ")
        assert result is None
