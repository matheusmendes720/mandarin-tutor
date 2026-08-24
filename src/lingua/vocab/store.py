"""JSON-based flashcard persistence."""
import json
from datetime import datetime
from pathlib import Path

from src.lingua.vocab.scheduler import Card


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, obj: object) -> object:
        if isinstance(obj, datetime):
            return {"__datetime__": True, "iso": obj.isoformat()}
        return super().default(obj)


def datetime_decoder(dct: dict) -> dict:
    """JSON object hook to decode datetime objects."""
    if "__datetime__" in dct:
        return datetime.fromisoformat(dct["iso"])
    return dct


def card_to_dict(card: Card) -> dict:
    """Convert a Card to a dictionary for JSON serialization."""
    return {
        "id": card.id,
        "front": card.front,
        "back": card.back,
        "ease_factor": card.ease_factor,
        "interval_days": card.interval_days,
        "repetitions": card.repetitions,
        "due_date": card.due_date,
    }


def dict_to_card(dct: dict) -> Card:
    """Convert a dictionary to a Card object."""
    return Card(
        id=dct["id"],
        front=dct["front"],
        back=dct["back"],
        ease_factor=dct.get("ease_factor", 2.5),
        interval_days=dct.get("interval_days", 1),
        repetitions=dct.get("repetitions", 0),
        due_date=dct.get("due_date", datetime.now()),
    )


class JsonStore:
    """JSON-based flashcard storage persisted to ~/.lingua/cards.json."""

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the store with optional custom path."""
        if path is None:
            self._path = Path.home() / ".lingua" / "cards.json"
        else:
            self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, cards: list[Card]) -> None:
        """Persist cards to the JSON file."""
        data = [card_to_dict(card) for card in cards]
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, cls=DateTimeEncoder, indent=2)

    def load(self) -> list[Card]:
        """Load cards from the JSON file. Returns empty list on failure."""
        if not self._path.exists():
            return []
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f, object_hook=datetime_decoder)
            return [dict_to_card(d) for d in data]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return []
