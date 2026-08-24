"""Tests for FSRS vocabulary scheduler."""
from datetime import datetime, timedelta
import pytest
from src.lingua.vocab.scheduler import (
    ReviewQuality,
    Card,
    fsrs_schedule,
    get_due_cards,
    create_card,
)


class TestFsrsSchedule:
    """Tests for fsrs_schedule function."""

    def test_again_quality_resets_repetitions(self):
        """AGAIN quality should reset repetitions to 0 and interval to 1."""
        card = Card(
            id="test-1",
            front="hello",
            back="nihao",
            ease_factor=2.5,
            interval_days=10,
            repetitions=5,
            due_date=datetime.now(),
        )
        result = fsrs_schedule(card, ReviewQuality.AGAIN)

        assert result.repetitions == 0
        assert result.interval_days == 1
        # due_date should be approximately 10 minutes from now
        expected_due = datetime.now() + timedelta(minutes=10)
        assert abs((result.due_date - expected_due).total_seconds()) < 5

    def test_good_quality_first_review(self):
        """GOOD quality on first review should give interval of 1 day."""
        card = Card(
            id="test-2",
            front="hello",
            back="nihao",
            repetitions=0,
        )
        result = fsrs_schedule(card, ReviewQuality.GOOD)

        assert result.repetitions == 1
        assert result.interval_days == 1

    def test_good_quality_second_review(self):
        """GOOD quality on second review should give interval of 6 days."""
        card = Card(
            id="test-3",
            front="hello",
            back="nihao",
            repetitions=1,
            interval_days=1,
        )
        result = fsrs_schedule(card, ReviewQuality.GOOD)

        assert result.repetitions == 2
        assert result.interval_days == 6

    def test_good_quality_third_review(self):
        """GOOD quality on third+ review should give interval increase based on ease factor."""
        card = Card(
            id="test-4",
            front="hello",
            back="nihao",
            repetitions=2,
            interval_days=6,
            ease_factor=2.5,
        )
        result = fsrs_schedule(card, ReviewQuality.GOOD)

        assert result.repetitions == 3
        # interval should be interval_days * ease_factor = 6 * 2.5 = 15
        assert result.interval_days == 15

    def test_easy_quality_gives_bonus(self):
        """EASY quality should give 1.3x bonus on interval."""
        card = Card(
            id="test-5",
            front="hello",
            back="nihao",
            repetitions=2,
            interval_days=6,
            ease_factor=2.5,
        )
        result = fsrs_schedule(card, ReviewQuality.EASY)

        # Expected: 6 * 2.5 * 1.3 = 19.5 -> 19
        assert result.interval_days == 19

    def test_hard_quality_decreases_ease(self):
        """HARD quality should decrease ease_factor."""
        card = Card(
            id="test-6",
            front="hello",
            back="nihao",
            ease_factor=2.5,
            repetitions=1,
        )
        result = fsrs_schedule(card, ReviewQuality.HARD)

        # HARD decreases ease_factor
        assert result.ease_factor < 2.5


class TestGetDueCards:
    """Tests for get_due_cards function."""

    def test_filters_future_due_cards(self):
        """get_due_cards should only return cards where due_date <= now."""
        now = datetime.now()
        cards = [
            Card(id="1", front="a", back="b", due_date=now - timedelta(days=1)),  # overdue
            Card(id="2", front="c", back="d", due_date=now),  # due now
            Card(id="3", front="e", back="f", due_date=now + timedelta(days=1)),  # future
        ]
        result = get_due_cards(cards)

        assert len(result) == 2
        assert {c.id for c in result} == {"1", "2"}


class TestCreateCard:
    """Tests for create_card factory function."""

    def test_creates_card_with_defaults(self):
        """create_card should produce Card with default values."""
        card = create_card("test-id", "front-text", "back-text")

        assert card.id == "test-id"
        assert card.front == "front-text"
        assert card.back == "back-text"
        assert card.ease_factor == 2.5  # default
        assert card.interval_days == 1  # default
        assert card.repetitions == 0  # default
        assert isinstance(card.due_date, datetime)
