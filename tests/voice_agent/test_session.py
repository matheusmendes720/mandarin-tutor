"""Tests for voice agent session management."""
import pytest

from src.lingua.voice_agent.session import (
    ConversationRole,
    Message,
    format_conversation,
    build_tutor_prompt,
)
from src.lingua.core.config import VoiceAgentConfig


class TestFormatConversation:
    """Tests for format_conversation function."""

    def test_formats_single_message(self):
        """Test formatting a single message."""
        messages = [Message(role=ConversationRole.USER, content="Hello")]
        result = format_conversation(messages)
        assert result == "user: Hello"

    def test_formats_multiple_messages(self):
        """Test formatting multiple messages."""
        messages = [
            Message(role=ConversationRole.USER, content="Hello"),
            Message(role=ConversationRole.ASSISTANT, content="Hi there!"),
            Message(role=ConversationRole.USER, content="How are you?"),
        ]
        result = format_conversation(messages)
        expected = "user: Hello\nassistant: Hi there!\nuser: How are you?"
        assert result == expected

    def test_formats_system_message(self):
        """Test formatting system messages."""
        messages = [
            Message(role=ConversationRole.SYSTEM, content="Welcome to the tutor."),
        ]
        result = format_conversation(messages)
        assert result == "system: Welcome to the tutor."


class TestBuildTutorPrompt:
    """Tests for build_tutor_prompt function."""

    def test_includes_system_prompt_from_config(self):
        """Test that system_prompt from config is included."""
        config = VoiceAgentConfig(
            system_prompt="You are a helpful tutor.",
        )
        messages = [
            Message(role=ConversationRole.USER, content="Hello"),
        ]
        result = build_tutor_prompt(config, messages)
        assert "You are a helpful tutor." in result

    def test_includes_formatted_conversation_history(self):
        """Test that formatted conversation history is included."""
        config = VoiceAgentConfig()
        messages = [
            Message(role=ConversationRole.USER, content="Hello"),
            Message(role=ConversationRole.ASSISTANT, content="Hi!"),
        ]
        result = build_tutor_prompt(config, messages)
        assert "user: Hello" in result
        assert "assistant: Hi!" in result

    def test_combines_system_prompt_and_history(self):
        """Test combining system prompt and conversation history."""
        config = VoiceAgentConfig(
            system_prompt="Be friendly.",
        )
        messages = [
            Message(role=ConversationRole.USER, content="Test"),
        ]
        result = build_tutor_prompt(config, messages)
        assert "Be friendly." in result
        assert "user: Test" in result
        assert "Conversation history:" in result
