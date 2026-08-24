"""LiveKit voice agent session management."""
from dataclasses import dataclass
from enum import Enum
from src.lingua.core.config import VoiceAgentConfig


class ConversationRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    role: ConversationRole
    content: str


def format_conversation(messages: list[Message]) -> str:
    """Format message history for LLM context."""
    return "\n".join(f"{msg.role.value}: {msg.content}" for msg in messages)


def build_tutor_prompt(session: VoiceAgentConfig, messages: list[Message]) -> str:
    """Build system prompt with conversation history for tutor."""
    history = format_conversation(messages)
    return (
        f"{session.system_prompt}\n\n"
        f"Conversation history:\n{history}\n"
    )
