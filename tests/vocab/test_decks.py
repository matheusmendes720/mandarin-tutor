"""Tests for PalavrasEssenciaisDeck (DeckBrowser implementation)."""
from pathlib import Path

import pytest

from src.lingua.core.config import DeckConfig
from src.lingua.vocab.decks import PalavrasEssenciaisDeck


@pytest.fixture
def deck(tmp_path: Path) -> PalavrasEssenciaisDeck:
    """Use the real bundled deck for these tests."""
    repo_root = Path(__file__).resolve().parents[2]
    cfg = DeckConfig(
        deck_path=str(repo_root / "palavras-essenciais" / "guia.html"),
        audio_base=str(repo_root / "palavras-essenciais" / "audio"),
    )
    return PalavrasEssenciaisDeck(cfg)


def test_categories_returns_all_with_icons(deck):
    cats = deck.categories()
    assert len(cats) == 11
    keys = [c["key"] for c in cats]
    assert "saudacoes" in keys
    assert "verbos" in keys
    # Each category has an icon (emoji) and a Portuguese name
    saudacoes = next(c for c in cats if c["key"] == "saudacoes")
    assert saudacoes["icon"]  # non-empty
    assert "Saudaç" in saudacoes["name_pt"]


def test_cards_by_category_returns_50(deck):
    all_cards = deck.cards_by_category()
    assert len(all_cards) == 50
    # Each card has the rich schema
    c = all_cards[0]
    for k in ("id", "hanzi", "pinyin", "pt", "context", "tones", "audio_path", "cat"):
        assert k in c, f"missing {k}"


def test_cards_by_category_filters(deck):
    saudacoes = deck.cards_by_category("saudacoes")
    assert all(c["cat"] == "saudacoes" for c in saudacoes)
    assert len(saudacoes) >= 1


def test_card_returns_one_by_id(deck):
    c = deck.card("pe_nihao")
    assert c is not None
    assert c["hanzi"] == "你好"


def test_audio_path_uses_configured_base(deck):
    deck2 = PalavrasEssenciaisDeck(DeckConfig(
        deck_path=str(Path(__file__).resolve().parents[2] / "palavras-essenciais" / "guia.html"),
        audio_base="/tmp/custom_audio",
    ))
    assert deck2.audio_path("pe_nihao") == "/tmp/custom_audio/nihao.mp3"