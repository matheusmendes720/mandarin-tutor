"""Conversation memory with persistence and auto-summarization."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime


@dataclass
class MemoryTurn:
    id: str
    role: str  # "user" | "assistant" | "system"
    text: str
    pinyin: str | None = None
    language: str = "zh"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class ConversationMemory:
    def __init__(self, path: Path, max_turns: int = 30):
        self.path = path
        self.max_turns = max_turns
        self.turns: list[MemoryTurn] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Handle both old format (list) and new format (dict with "turns")
            if isinstance(data, list):
                self.turns = [MemoryTurn(**t) for t in data]
            else:
                self.turns = [MemoryTurn(**t) for t in data.get("turns", [])]
            # Sanitize: legacy bug stored the system prompt under role="user".
            # Heuristic: the very first turn (which is the initial system prompt
            # by convention) and the text starts with "You are a" — the start of
            # all our tutor system prompts. Refuse to heal any other user turn.
            if (
                self.turns
                and self.turns[0].role == "user"
                and self.turns[0].text.lstrip().startswith("You are a")
                and self.turns[0].text != "You are an idiot"
            ):
                first = self.turns[0]
                self.turns[0] = MemoryTurn(
                    id=first.id,
                    role="system",
                    text=first.text,
                    pinyin=first.pinyin,
                    language=first.language,
                    timestamp=first.timestamp,
                )
                self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"turns": [asdict(t) for t in self.turns]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_turn(self, role: str, text: str, **kwargs) -> MemoryTurn:
        turn = MemoryTurn(id=str(uuid.uuid4()), role=role, text=text, **kwargs)
        self.turns.append(turn)
        if len(self.turns) > self.max_turns:
            self._summarize()
        self.save()
        return turn

    def _summarize(self) -> None:
        if len(self.turns) < self.max_turns // 2:
            return
        summary_text = " ".join(t.text for t in self.turns[: len(self.turns) // 2])
        self.turns = [
            MemoryTurn(
                id=str(uuid.uuid4()),
                role="system",
                text=f"[Earlier conversation summary: {summary_text[:800]}...]",
            )
        ] + self.turns[len(self.turns) // 2 :]

    def get_conversation_for_llm(self) -> list[dict]:
        return [{"role": t.role, "content": t.text} for t in self.turns]

    @classmethod
    def load(cls, path: Path) -> "ConversationMemory":
        inst = cls(path)
        inst._load()
        return inst
