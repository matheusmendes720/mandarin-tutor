"""Tests for the Gradio UI app."""
import pytest
import gradio as gr
from src.lingua.ui.app import build_app, add_flashcard, review_card


def test_build_app_returns_blocks():
    """Test that build_app returns a gr.Blocks object."""
    app = build_app()
    assert isinstance(app, gr.Blocks)


def test_app_has_five_tabs():
    """Test that the app has 5 tabs with correct names."""
    app = build_app()

    # Find the Tabs component
    tabs = [c for c in app.children if 'Tabs' in type(c).__name__][0]

    # Get all tab labels
    tab_names = [c.label for c in tabs.children if hasattr(c, 'label')]

    assert "🎤 Pronunciation" in tab_names
    assert "📚 Vocabulary" in tab_names
    assert "🗣️ Accent Analysis" in tab_names
    assert "🔤 Phoneme Drills" in tab_names
    assert "💬 Voice Practice" in tab_names
    assert len(tab_names) == 5


def test_add_flashcard_returns_tuple():
    """Test that add_flashcard returns tuple of two lists."""
    result = add_flashcard("hello", "hola")

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], list)
    assert isinstance(result[1], list)


def test_review_card_no_cards_returns_message():
    """Test that review_card returns 'No cards due!' when no queue."""
    # Clear any existing state
    from src.lingua.ui import app as ui_app
    ui_app._review_queue.clear()
    ui_app._active_cards.clear()

    result = review_card("good")
    assert result == "No cards due!"


def test_review_card_processes_quality():
    """Test that review_card processes review quality correctly."""
    from src.lingua.ui import app as ui_app

    # Clear and set up a card in the queue
    ui_app._review_queue.clear()
    ui_app._active_cards.clear()

    # Add a card
    add_flashcard("test", "prueba")

    # Now review it
    result = review_card("good")

    # Should return a message about the reviewed card
    assert "Reviewed:" in result
    assert "test" in result
    assert "days" in result
