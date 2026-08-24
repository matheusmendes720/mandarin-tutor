"""FSRS-based spaced repetition scheduling."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from src.lingua.core.config import VocabConfig


class ReviewQuality(Enum):
    AGAIN = 0
    HARD = 1
    GOOD = 2
    EASY = 3


@dataclass
class Card:
    id: str
    front: str
    back: str
    ease_factor: float = 2.5
    interval_days: int = 1
    repetitions: int = 0
    due_date: datetime = field(default_factory=datetime.now)


def fsrs_schedule(card: Card, quality: ReviewQuality) -> Card:
    """Update card scheduling based on FSRS algorithm."""
    q = quality.value
    if q < 2:
        return Card(
            id=card.id,
            front=card.front,
            back=card.back,
            ease_factor=max(1.3, card.ease_factor - 0.2),
            interval_days=1,
            repetitions=0,
            due_date=datetime.now() + timedelta(minutes=10),
        )
    if card.repetitions == 0:
        new_interval = 1
    elif card.repetitions == 1:
        new_interval = 6
    else:
        new_interval = int(card.interval_days * card.ease_factor)
    ease_delta = 0.1 - (3 - q) * (0.08 + (3 - q) * 0.02)
    new_ease = max(1.3, card.ease_factor + ease_delta)
    if q == 3:
        new_interval = int(new_interval * 1.3)
    return Card(
        id=card.id,
        front=card.front,
        back=card.back,
        ease_factor=new_ease,
        interval_days=new_interval,
        repetitions=card.repetitions + 1,
        due_date=datetime.now() + timedelta(days=new_interval),
    )


def get_due_cards(cards: list[Card]) -> list[Card]:
    """Return all cards where due_date <= now."""
    return [c for c in cards if c.due_date <= datetime.now()]


def create_card(id: str, front: str, back: str) -> Card:
    """Factory for a new vocabulary card."""
    return Card(id=id, front=front, back=back)
