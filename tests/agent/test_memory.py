"""Tests for ConversationMemory."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lingua.agent.memory import ConversationMemory, MemoryTurn


class TestConversationMemory:
    def test_saves_and_loads_turns(self):
        """Write turns, reload, verify they persist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "conversation.json"
            memory = ConversationMemory(path, max_turns=10)

            memory.add_turn("user", "Hello")
            memory.add_turn("assistant", "Hi there!")

            # Create new instance to test persistence
            memory2 = ConversationMemory.load(path)
            assert len(memory2.turns) == 2
            assert memory2.turns[0].text == "Hello"
            assert memory2.turns[1].text == "Hi there!"

    def test_summarizes_when_too_large(self):
        """Add more than max_turns, verify summary created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "conversation.json"
            memory = ConversationMemory(path, max_turns=5)

            # Add more turns than max_turns
            for i in range(7):
                memory.add_turn("user", f"Message {i}")

            # Should have a summary turn at the start
            conversation = memory.get_conversation_for_llm()
            assert len(conversation) <= 5
            # Check that there's a system turn with summary
            has_summary = any(
                c["role"] == "system" and "summary" in c["content"].lower()
                for c in conversation
            )
            assert has_summary, "Expected summary in conversation"

    def test_get_conversation_for_llm(self):
        """Verify format for LLM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "conversation.json"
            memory = ConversationMemory(path, max_turns=10)

            memory.add_turn("user", "Test message")
            memory.add_turn("assistant", "Test response")

            conversation = memory.get_conversation_for_llm()
            assert len(conversation) == 2
            assert conversation[0] == {"role": "user", "content": "Test message"}
            assert conversation[1] == {"role": "assistant", "content": "Test response"}
