"""Regression: legacy persisted memory had the system prompt stored as role='user'.
ConversationMemory must heal this on load so the LLM receives a real system message."""
import json
from pathlib import Path

from lingua.agent.memory import ConversationMemory


def test_memory_sanitizes_legacy_system_as_user(tmp_path: Path):
    """Simulate a stale conversation.json from before the fix."""
    path = tmp_path / "conversation.json"
    legacy = {
        "turns": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "role": "user",  # BUG: should have been 'system'
                "text": "You are a Mandarin Chinese tutor.",
                "language": "zh",
                "timestamp": "2026-01-01T00:00:00",
            },
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "role": "user",
                "text": "Say hello in Mandarin.",
                "language": "zh",
                "timestamp": "2026-01-01T00:00:01",
            },
        ]
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")

    mem = ConversationMemory(path)
    msgs = mem.get_conversation_for_llm()
    assert msgs[0]["role"] == "system", f"sanitizer failed; first role is {msgs[0]['role']}"
    assert msgs[1]["role"] == "user"  # actual user message stays user
    # Sanitizer also re-saves the file
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["turns"][0]["role"] == "system"


def test_memory_does_not_heal_real_user_turn(tmp_path: Path):
    """Sanitizer must only fix the very first turn that looks like the system
    prompt — not any random user message that happens to start with 'You are'."""
    path = tmp_path / "conversation.json"
    data = {
        "turns": [
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "role": "user",
                "text": "Please help me practice Mandarin tones.",
                "language": "en",
                "timestamp": "2026-01-01T00:00:00",
            },
        ]
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    mem = ConversationMemory(path)
    msgs = mem.get_conversation_for_llm()
    assert msgs[0]["role"] == "user"


def test_memory_heals_only_first_turn(tmp_path: Path):
    """If the second turn also starts with 'You are a', it must NOT be healed —
    only the first turn is the system prompt by convention."""
    path = tmp_path / "conversation.json"
    data = {
        "turns": [
            {
                "id": "1", "role": "user",
                "text": "You are a Mandarin tutor. Respond only in JSON.",
                "language": "zh",
                "timestamp": "",
            },
            {
                "id": "2", "role": "user",
                "text": "You are asking me to start the lesson.",
                "language": "en",
                "timestamp": "",
            },
        ]
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    mem = ConversationMemory(path)
    msgs = mem.get_conversation_for_llm()
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
