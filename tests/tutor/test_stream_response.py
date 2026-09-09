"""Tests for streaming LLM response and sentence boundary detection."""
import pytest

from lingua.tutor import find_sentence_boundary


class TestFindSentenceBoundary:
    """Tests for the find_sentence_boundary helper function."""

    def test_chinese_period(self):
        """Test Chinese period (。) as sentence boundary."""
        text = "你好世界。今天天气好。"
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        assert "你好世界。" in sent

    def test_chinese_multiple_sentences(self):
        """Test multiple Chinese sentences."""
        text = "你好世界。今天天气好。我很高兴。"
        # First sentence
        result1 = find_sentence_boundary(text, 0)
        assert result1 is not None
        idx1, sent1 = result1
        assert "你好世界。" == sent1

        # Second sentence
        result2 = find_sentence_boundary(text, idx1)
        assert result2 is not None
        idx2, sent2 = result2
        assert "今天天气好。" == sent2

        # Third sentence
        result3 = find_sentence_boundary(text, idx2)
        assert result3 is not None
        idx3, sent3 = result3
        assert "我很高兴。" == sent3

    def test_chinese_question_mark(self):
        """Test Chinese question mark (？) as sentence boundary."""
        text = "你好吗？我很好。"
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        assert "你好吗？" in sent

    def test_chinese_exclamation(self):
        """Test Chinese exclamation mark (！) as sentence boundary."""
        text = "太棒了！谢谢！"
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        assert "太棒了！" in sent

    def test_english_period(self):
        """Test English period as sentence boundary."""
        text = "Hello world. How are you?"
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        assert "Hello world." in sent

    def test_english_exclamation(self):
        """Test English exclamation mark as sentence boundary."""
        text = "Hello! How are you?"
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        assert "Hello!" in sent

    def test_english_question_mark(self):
        """Test English question mark as sentence boundary."""
        text = "How are you? I am fine."
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        assert "How are you?" in sent

    def test_english_newline(self):
        """Test newline as sentence boundary."""
        text = "Hello\nHow are you"
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        assert "Hello\n" in sent

    def test_mixed_chinese_english(self):
        """Test mixed Chinese and English sentences."""
        text = "你好世界！Hello world.你好吗？"

        # First: Chinese exclamation
        result1 = find_sentence_boundary(text, 0)
        assert result1 is not None
        idx1, sent1 = result1
        assert "你好世界！" == sent1

        # Second: English period
        result2 = find_sentence_boundary(text, idx1)
        assert result2 is not None
        idx2, sent2 = result2
        assert "Hello world." == sent2

        # Third: Chinese question
        result3 = find_sentence_boundary(text, idx2)
        assert result3 is not None
        idx3, sent3 = result3
        assert "你好吗？" == sent3

    def test_no_boundary_found(self):
        """Test when no sentence boundary exists in the remaining text."""
        text = "你好世界今天天气好"
        result = find_sentence_boundary(text, 0)
        assert result is None

    def test_empty_text(self):
        """Test with empty text."""
        result = find_sentence_boundary("", 0)
        assert result is None

    def test_continue_from_middle(self):
        """Test continuing from the middle of text (no boundary at start)."""
        text = "Hello world. Good"
        # Start from position after first period
        result = find_sentence_boundary(text, 12)
        assert result is None  # " Good" has no boundary

    def test_punctuation_in_middle_not_counted(self):
        """Test that punctuation in the middle of text doesn't count as boundary."""
        text = "Hello... world."  # Ellipsis contains periods, matches as boundary
        result = find_sentence_boundary(text, 0)
        assert result is not None
        idx, sent = result
        # The first period (from ellipsis) is at index 5 (0-indexed)
        # So it returns up to index 6 (exclusive), which is "Hello."
        assert idx == 6
        assert sent == "Hello."
