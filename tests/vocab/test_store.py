"""Tests for JSON flashcard persistence."""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from src.lingua.vocab.scheduler import Card
from src.lingua.vocab.store import JsonStore, card_to_dict, dict_to_card


class TestJsonStore:
    """Tests for JsonStore class."""

    @pytest.fixture
    def temp_store(self):
        """Create a JsonStore with a temporary file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cards.json"
            store = JsonStore(path=path)
            yield store

    def test_save_and_load_roundtrip(self, temp_store):
        """Test that save/load preserves card data."""
        cards = [
            Card(id="1", front="hello", back="nihao", ease_factor=2.5, interval_days=1, repetitions=0, due_date=datetime.now()),
            Card(id="2", front="world", back="shijie", ease_factor=2.6, interval_days=5, repetitions=2, due_date=datetime.now() + timedelta(days=3)),
        ]
        temp_store.save(cards)
        loaded = temp_store.load()

        assert len(loaded) == 2
        # Check first card
        assert loaded[0].id == "1"
        assert loaded[0].front == "hello"
        assert loaded[0].back == "nihao"
        assert loaded[0].ease_factor == 2.5
        assert loaded[0].interval_days == 1
        assert loaded[0].repetitions == 0
        # Check second card
        assert loaded[1].id == "2"
        assert loaded[1].front == "world"
        assert loaded[1].back == "shijie"
        assert loaded[1].ease_factor == 2.6
        assert loaded[1].interval_days == 5
        assert loaded[1].repetitions == 2

    def test_load_missing_file_returns_empty_list(self, temp_store):
        """Test that loading from non-existent file returns empty list."""
        result = temp_store.load()
        assert result == []

    def test_load_corrupt_json_returns_empty_list(self, temp_store):
        """Test that loading corrupt JSON returns empty list."""
        # Write invalid JSON
        with open(temp_store._path, "w") as f:
            f.write("{ invalid json }")
        result = temp_store.load()
        assert result == []

    def test_load_partial_json_returns_empty_list(self, temp_store):
        """Test that loading partial/incomplete JSON returns empty list."""
        # Write truncated JSON
        with open(temp_store._path, "w") as f:
            json.dump([{"id": "1", "front": "test"}], f)
        result = temp_store.load()
        assert result == []


class TestCardSerialization:
    """Tests for card serialization utilities."""

    def test_card_to_dict(self):
        """Test card_to_dict converts Card to dict."""
        due = datetime(2024, 1, 15, 10, 30, 0)
        card = Card(id="test-id", front="front", back="back", ease_factor=2.5, interval_days=3, repetitions=2, due_date=due)
        result = card_to_dict(card)

        assert result["id"] == "test-id"
        assert result["front"] == "front"
        assert result["back"] == "back"
        assert result["ease_factor"] == 2.5
        assert result["interval_days"] == 3
        assert result["repetitions"] == 2
        assert result["due_date"] == due

    def test_dict_to_card(self):
        """Test dict_to_card converts dict to Card."""
        due = datetime(2024, 1, 15, 10, 30, 0)
        dct = {"id": "test-id", "front": "front", "back": "back", "ease_factor": 2.5, "interval_days": 3, "repetitions": 2, "due_date": due}
        result = dict_to_card(dct)

        assert result.id == "test-id"
        assert result.front == "front"
        assert result.back == "back"
        assert result.ease_factor == 2.5
        assert result.interval_days == 3
        assert result.repetitions == 2
        assert result.due_date == due

    def test_dict_to_card_with_defaults(self):
        """Test dict_to_card handles missing keys with defaults."""
        dct = {"id": "test-id", "front": "front", "back": "back"}
        result = dict_to_card(dct)

        assert result.id == "test-id"
        assert result.front == "front"
        assert result.back == "back"
        assert result.ease_factor == 2.5  # default
        assert result.interval_days == 1  # default
        assert result.repetitions == 0  # default
