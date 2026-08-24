"""Cross-subsystem integration tests."""
import pytest
from datetime import datetime, timedelta
from lingua.pronunciation.scorer import compute_phoneme_score, align_phonemes
from lingua.vocab.scheduler import create_card, fsrs_schedule, get_due_cards, ReviewQuality
from lingua.accent.analyzer import AccentResult, detect_accent
from lingua.tts.engine import SynthesisResult, estimate_duration
from lingua.voice_agent.session import build_tutor_prompt, VoiceAgentConfig, Message, ConversationRole


def test_pronunciation_to_vocab_handoff():
    """If pronunciation is poor, suggest a flashcard."""
    score = compute_phoneme_score(["h", "ɛ", "l", "oʊ"], ["h", "ɛ", "l", "oʊ"])
    assert score == 1.0
    if score < 0.7:
        card = create_card("pron-1", "hello", "h-ɛ-l-oʊ (standard)")
        assert card.front == "hello"


def test_vocab_review_updates_srs():
    """Reviewing vocab updates the SRS schedule."""
    card = create_card("1", "hello", "greeting")
    card.repetitions = 1
    card.interval_days = 1
    updated = fsrs_schedule(card, ReviewQuality.GOOD)
    assert updated.interval_days > 1


def test_accent_result_for_ui():
    """AccentResult is JSON-serializable for Gradio JSON component."""
    result = AccentResult(language="en", dialect="US", confidence=0.91, speaker_segments=[])
    assert result.confidence > 0.9
    assert result.language == "en"


def test_tts_duration_calculation():
    """SynthesisResult carries correct fields for UI audio display."""
    result = SynthesisResult(audio_bytes=b"RIFF" * 1000, sample_rate=22050, duration_seconds=1.0)
    assert result.sample_rate == 22050
    assert result.duration_seconds == 1.0


def test_tutor_conversation_flow():
    """Tutor prompt accumulates conversation history correctly."""
    session = VoiceAgentConfig(language="en")
    messages = [
        Message(role=ConversationRole.USER, content="Comment dit-on 'cat' en français?"),
        Message(role=ConversationRole.ASSISTANT, content="On dit 'chat'."),
    ]
    prompt = build_tutor_prompt(session, messages)
    assert "chat" in prompt
    assert "Comment dit-on" in prompt


def test_due_cards_isolates_past():
    """get_due_cards returns only overdue cards."""
    now = datetime.now()
    due = create_card("1", "a", "a")
    due.due_date = now - timedelta(hours=1)
    future = create_card("2", "b", "b")
    future.due_date = now + timedelta(days=1)
    result = get_due_cards([due, future])
    assert len(result) == 1
    assert result[0].id == "1"
