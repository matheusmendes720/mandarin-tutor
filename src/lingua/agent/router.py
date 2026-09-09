"""TurnRouter - multi-lingual turn routing for ZH/EN code-switch."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoutedTurn:
    """A turn routed to the appropriate handler."""

    type: str  # "explanation" | "vocab_drill" | "tone_drill" | "dialogue"
    language: str  # "zh" | "en" | "mixed"
    full_text: str
    segments: list[dict]

    def is_mandarin(self) -> bool:
        """Check if this turn involves Mandarin."""
        return self.language in ("zh", "mixed")


class TurnRouter:
    """Routes turns based on detected language in ASR segments."""

    def route(self, segments: list[dict]) -> RoutedTurn:
        """Route segments to the appropriate turn type.

        Parameters
        ----------
        segments : list[dict]
            List of ASR segment dicts with "text" and "language" keys.

        Returns
        -------
        RoutedTurn
            A routed turn with type, language, full_text, and segments.
        """
        if not segments:
            return RoutedTurn(type="dialogue", language="zh", full_text="", segments=[])

        full_text = " ".join(s["text"] for s in segments)
        languages = {s.get("language", "zh") for s in segments}

        if "en" in languages and "zh" in languages:
            primary_lang = "mixed"
        elif "zh" in languages:
            primary_lang = "zh"
        else:
            primary_lang = "en"

        if primary_lang == "en":
            return RoutedTurn(type="explanation", language="en", full_text=full_text, segments=segments)
        elif primary_lang == "mixed":
            return RoutedTurn(type="dialogue", language="mixed", full_text=full_text, segments=segments)
        else:
            return RoutedTurn(type="vocab_drill", language="zh", full_text=full_text, segments=segments)
