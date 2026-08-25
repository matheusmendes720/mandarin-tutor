"""Tests for backwards-compatible JsonStore migration to rich Card schema."""
import json
from pathlib import Path

from src.lingua.vocab.scheduler import Card
from src.lingua.vocab.store import JsonStore


def test_old_card_without_rich_fields_loads(tmp_path: Path):
    """Cards written by the old schema (no pinyin/context/cat/tones/audio_path)
    must still load after the schema extension."""
    store_path = tmp_path / "cards.json"
    old_data = [
        {
            "id": "old_1",
            "front": "你好",
            "back": "olá",
            "ease_factor": 2.5,
            "interval_days": 0,
            "repetitions": 0,
            "due_date": {"__datetime__": True, "iso": "2026-08-25T10:00:00"},
        }
    ]
    store_path.write_text(json.dumps(old_data), encoding="utf-8")
    cards = JsonStore(store_path).load()
    assert len(cards) == 1
    c = cards[0]
    assert c.id == "old_1"
    assert c.pinyin is None
    assert c.context is None
    assert c.cat is None
    assert c.tones == []
    assert c.audio_path is None


def test_new_card_round_trip(tmp_path: Path):
    """A card with rich fields persists and reloads intact."""
    store = JsonStore(tmp_path / "cards.json")
    card = Card(
        id="pe_nihao",
        front="你好",
        back="olá",
        pinyin="nǐ hǎo",
        context="Cumprimento universal",
        cat="saudacoes",
        tones=[3, 3],
        audio_path="palavras-essenciais/audio/nihao.mp3",
    )
    store.save([card])
    loaded = store.load()
    assert loaded[0].pinyin == "nǐ hǎo"
    assert loaded[0].tones == [3, 3]
    assert loaded[0].audio_path == "palavras-essenciais/audio/nihao.mp3"