"""Tests for TurnRouter - multi-lingual turn routing."""
from __future__ import annotations

import pytest

from lingua.agent.router import RoutedTurn, TurnRouter


class TestTurnRouter:
    """Test TurnRouter for ZH/EN code-switch routing."""

    @pytest.fixture
    def router(self):
        """Create a TurnRouter instance."""
        return TurnRouter()

    def test_routes_mandarin_to_vocab_drill(self, router):
        """All ZH segments should route to vocab_drill with language=zh."""
        segments = [
            {"text": "你好", "language": "zh"},
            {"text": "学习", "language": "zh"},
        ]
        result = router.route(segments)

        assert result.type == "vocab_drill"
        assert result.language == "zh"
        assert result.full_text == "你好 学习"

    def test_routes_english_to_explanation(self, router):
        """All EN segments should route to explanation with language=en."""
        segments = [
            {"text": "Hello", "language": "en"},
            {"text": "How are you", "language": "en"},
        ]
        result = router.route(segments)

        assert result.type == "explanation"
        assert result.language == "en"
        assert result.full_text == "Hello How are you"

    def test_routes_mixed_to_dialogue(self, router):
        """Mixed ZH/EN segments should route to dialogue with language=mixed."""
        segments = [
            {"text": "Hello", "language": "en"},
            {"text": "你好", "language": "zh"},
        ]
        result = router.route(segments)

        assert result.type == "dialogue"
        assert result.language == "mixed"
        assert result.full_text == "Hello 你好"

    def test_routes_empty_segments(self, router):
        """Empty segments should default to dialogue with language=zh."""
        segments = []
        result = router.route(segments)

        assert result.type == "dialogue"
        assert result.language == "zh"
        assert result.full_text == ""
        assert result.segments == []

    def test_is_mandarin_helper(self, router):
        """Test is_mandarin helper method."""
        segments_zh = [{"text": "你好", "language": "zh"}]
        segments_en = [{"text": "hello", "language": "en"}]
        segments_mixed = [{"text": "hello", "language": "en"}, {"text": "你好", "language": "zh"}]

        result_zh = router.route(segments_zh)
        result_en = router.route(segments_en)
        result_mixed = router.route(segments_mixed)

        assert result_zh.is_mandarin() is True
        assert result_en.is_mandarin() is False
        assert result_mixed.is_mandarin() is True

    def test_segments_with_missing_language_default_to_zh(self, router):
        """Segments without language field should default to zh."""
        segments = [
            {"text": "你好"},  # No language field
            {"text": "学习", "language": "zh"},
        ]
        result = router.route(segments)

        assert result.type == "vocab_drill"
        assert result.language == "zh"
