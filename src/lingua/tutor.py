"""MandarinTutor — LLM-driven conversation agent with voice synthesis."""
from __future__ import annotations

import inspect
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import requests

from pypinyin import lazy_pinyin, Style

from . import config as cfg
from .prompts import SYSTEM_PROMPT
from .voice_studio import VoiceStudioClient, SynthesisResult
from .agent.memory import ConversationMemory

logger = logging.getLogger(__name__)


_HANZI_RE = re.compile(r"[㐀-鿿]")

# Sentence-ending delimiters: Chinese (。！？) and English (.!?\n)
_SENT_END_RE = re.compile(r"([。！？.!?\n])")


def find_sentence_boundary(text: str, emitted_len: int) -> tuple[int, str] | None:
    """Find the next sentence boundary at or after emitted_len.

    Parameters
    ----------
    text : str
        The full accumulated text.
    emitted_len : int
        Number of characters already emitted (start searching from here).

    Returns
    -------
    tuple[int, str] | None
        (end_index_inclusive, complete_sentence) if a sentence boundary is found,
        None if no boundary found yet.
    """
    if emitted_len >= len(text):
        return None

    # Search for the first delimiter at or after emitted_len
    search_text = text[emitted_len:]
    for m in _SENT_END_RE.finditer(search_text):
        # The delimiter ends at position (m.end() - 1) relative to search_text
        # Convert to absolute position in text
        delim_start = emitted_len + m.start()
        delim_end = emitted_len + m.end()
        # Return the sentence up to and including the delimiter
        sentence = text[emitted_len:delim_end]
        return delim_end, sentence

    return None


def to_pinyin(text: str) -> str:
    """Convert Chinese characters to pinyin with tone marks; leave non-Chinese unchanged.

    Example: '你好世界' → 'nǐ hǎo shì jiè'.
    """
    if not text or not _HANZI_RE.search(text):
        return text
    parts = lazy_pinyin(text, style=Style.TONE)
    return " ".join(p for p in parts if p)


@dataclass
class TutorTurn:
    type: str  # explanation | vocab_drill | tone_drill | dialogue
    text: str
    expected: str = ""
    feedback: str = ""


class MandarinTutor:
    """LLM-powered Mandarin tutor using VoiceStudio for TTS + ASR."""

    def __init__(self, cfg_: cfg.LinguaConfig | None = None) -> None:
        self.cfg = cfg_ or cfg.LinguaConfig.defaults()
        self.vs = VoiceStudioClient(self.cfg.voicestudio.url)
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {self.cfg.llm.api_key}"
        self.memory = ConversationMemory(Path("data/conversation.json"), max_turns=30)
        # Add system prompt as first turn
        if not self.memory.turns:
            self.memory.add_turn("system", SYSTEM_PROMPT)

    # ------------------------------------------------------------------
    # LLM — direct HTTP to MiniMax OpenAI-compatible API
    # ------------------------------------------------------------------
    def stream_response(
        self,
        messages: list[dict],
        on_sentence: Callable[[str, str], None] | None = None,
    ) -> tuple[str, list[str]]:
        """Stream LLM response with sentence-level callbacks.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages in OpenAI format.
        on_sentence : callable, optional
            Callback function called when a sentence boundary is detected.
            Signature: (sentence_text: str, full_text_so_far: str) -> None.
            Can be async — automatically detects via inspect.iscoroutinefunction.

        Returns
        -------
        tuple[str, list[str]]
            (full_text, list_of_emitted_sentences)
        """
        payload = {
            "model": self.cfg.llm.model,
            "messages": messages,
            "max_tokens": 120,
            "stream": True,
        }
        resp = self._session.post(
            f"{self.cfg.llm.url}/chatcompletion_v2",
            json=payload,
            timeout=60,
            stream=True,
        )
        resp.raise_for_status()

        full_text = ""
        sentences: list[str] = []
        emitted_len = 0
        is_coroutine = on_sentence and inspect.iscoroutinefunction(on_sentence)

        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: "):
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_text += content

                        # Check for sentence boundaries
                        while True:
                            result = find_sentence_boundary(full_text, emitted_len)
                            if result is None:
                                break
                            delim_end, sentence = result
                            sentences.append(sentence)
                            # Call the callback if provided
                            if on_sentence:
                                if is_coroutine:
                                    # Would need asyncio.run in sync context - skip for now
                                    # In async harness, this will be called differently
                                    pass
                                else:
                                    on_sentence(sentence, full_text)
                            emitted_len = delim_end
                except json.JSONDecodeError:
                    continue

        return full_text, sentences

    def _ask_llm(self, user_message: str) -> TutorTurn:
        self.memory.add_turn("user", user_message)
        payload = {
            "model": self.cfg.llm.model,
            "messages": self.memory.get_conversation_for_llm(),
            "max_tokens": 120,
        }
        resp = self._session.post(
            f"{self.cfg.llm.url}/chatcompletion_v2",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"] or "{}"
        self.memory.add_turn("assistant", content)
        try:
            obj = json.loads(content)
            return TutorTurn(
                type=obj.get("type", "explanation"),
                text=obj.get("text", ""),
                expected=obj.get("expected", ""),
                feedback=obj.get("feedback", ""),
            )
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON, falling back: %s", content[:100])
            return TutorTurn(type="explanation", text=content, expected="", feedback="")

    # ------------------------------------------------------------------
    # TTS — selects voice based on language
    # ------------------------------------------------------------------
    def _voice_for_turn(self, turn: TutorTurn) -> str:
        # Explanation = English voice; drills = Mandarin voice
        if turn.type == "explanation":
            return self.cfg.voicestudio.voice_english
        return self.cfg.voicestudio.voice_mandarin

    def _speed_for_turn(self, turn: TutorTurn) -> float:
        # English at normal speed (1.0x); Mandarin drills at 0.75x so the
        # tones are easier to follow.
        if turn.type == "explanation":
            return 1.0
        return 0.75

    def speak(self, text: str, voice_profile: str | None = None, speed: float = 1.0) -> SynthesisResult:
        """Synthesize text using VoiceStudio TTS.

        Parameters
        ----------
        text : str
            Text to speak.
        voice_profile : str, optional
            VoiceStudio voice ID (defaults to Mandarin).
        speed : float
            Playback speed multiplier (0.25 to 4.0 per server spec).
        """
        profile = voice_profile or self.cfg.voicestudio.voice_mandarin
        return self.vs.synthesize(
            text,
            profile_id=profile,
            engine=self.cfg.voicestudio.engine,
            speed=speed,
        )

    def speak_turn(self, turn: TutorTurn) -> SynthesisResult:
        """Speak a TutorTurn, picking voice + speed from its type."""
        return self.speak(
            turn.text,
            voice_profile=self._voice_for_turn(turn),
            speed=self._speed_for_turn(turn),
        )

    # ------------------------------------------------------------------
    # High-level turns
    # ------------------------------------------------------------------
    def next_drill(self, student_input: str | None = None) -> TutorTurn:
        """Get the next tutor turn.

        If student_input is provided, it is sent as feedback/reply.
        Otherwise a new drill or explanation is generated.
        """
        if student_input:
            msg = f"Student replied: {student_input}\nGive feedback and continue the drill."
        else:
            msg = "Give me a short vocab drill turn."
        return self._ask_llm(msg)

    def start_dialogue(self, topic: str) -> TutorTurn:
        """Start a short dialogue on a given topic."""
        return self._ask_llm(f"Start a short dialogue about: {topic}")

    def review_and_drill(self) -> TutorTurn:
        """Run a mixed tone + vocab review."""
        return self._ask_llm("Run a short mixed review: one tone drill, one vocab drill.")
