"""Tests for vocabulary importers."""
from datetime import datetime

from src.lingua.vocab.importers import load_palavras_essenciais


class TestLoadPalavrasEssenciais:
    """Tests for load_palavras_essenciais function."""

    def test_returns_non_empty_list(self):
        """Test that the importer returns a non-empty list."""
        path = "palavras-essenciais/guia.html"
        cards = load_palavras_essenciais(path)

        assert isinstance(cards, list)
        assert len(cards) > 0, "Expected non-empty list of cards"

    def test_each_card_has_front_and_back(self):
        """Test that each card has non-empty front and back."""
        path = "palavras-essenciais/guia.html"
        cards = load_palavras_essenciais(path)

        for card in cards:
            assert card.front, f"Card {card.id} has empty front"
            assert card.back, f"Card {card.id} has empty back"
            assert len(card.front) > 0, f"Card {card.id} has empty front string"
            assert len(card.back) > 0, f"Card {card.id} has empty back string"

    def test_cards_are_immediately_due(self):
        """Test that cards are immediately due (due_date <= now)."""
        path = "palavras-essenciais/guia.html"
        cards = load_palavras_essenciais(path)
        now = datetime.now()

        for card in cards:
            assert card.due_date <= now, f"Card {card.id} is not immediately due"

    def test_cards_have_correct_defaults(self):
        """Test that cards have the expected default values for new cards."""
        path = "palavras-essenciais/guia.html"
        cards = load_palavras_essenciais(path)

        for card in cards:
            assert card.ease_factor == 2.5, f"Card {card.id} has wrong ease_factor"
            assert card.interval_days == 0, f"Card {card.id} has wrong interval_days"
            assert card.repetitions == 0, f"Card {card.id} has wrong repetitions"

    def test_cards_have_valid_ids(self):
        """Test that each card has a valid ID."""
        path = "palavras-essenciais/guia.html"
        cards = load_palavras_essenciais(path)

        for card in cards:
            assert card.id, f"Card missing ID"
            assert card.id.startswith("pe_"), f"Card {card.id} has invalid ID format"

    def test_audio_path_is_mapped(self):
        """Test that audio_path is mapped correctly."""
        path = "palavras-essenciais/guia.html"
        cards = load_palavras_essenciais(path)

        for card in cards:
            assert hasattr(card, "audio_path"), f"Card {card.id} missing audio_path"
            assert card.audio_path.startswith("palavras-essenciais/audio/"), (
                f"Card {card.id} has invalid audio_path"
            )
            assert card.audio_path.endswith(".mp3"), (
                f"Card {card.id} audio_path should be .mp3"
            )

    def test_file_not_found(self):
        """Test that FileNotFoundError is raised for missing files."""
        import pytest

        with pytest.raises(FileNotFoundError):
            load_palavras_essenciais("nonexistent/path/guia.html")
