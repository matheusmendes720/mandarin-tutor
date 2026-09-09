# src/lingua/hud/events.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Event:
    ts: float
    kind: str = ""


@dataclass
class RmsEvent(Event):
    rms: float = 0.0
    is_speech: bool = False

    def __post_init__(self) -> None:
        self.kind = "rms"


@dataclass
class AsrPartialEvent(Event):
    text: str = ""

    def __post_init__(self) -> None:
        self.kind = "asr_partial"


@dataclass
class AsrFinalEvent(Event):
    text: str = ""
    language: str = "zh"

    def __post_init__(self) -> None:
        self.kind = "asr_final"


@dataclass
class LlmStartEvent(Event):
    prompt_chars: int = 0

    def __post_init__(self) -> None:
        self.kind = "llm_start"


@dataclass
class LlmDoneEvent(Event):
    response_chars: int = 0
    duration_ms: int = 0

    def __post_init__(self) -> None:
        self.kind = "llm_done"


@dataclass
class TtsStartEvent(Event):
    text_chars: int = 0
    voice: str = ""

    def __post_init__(self) -> None:
        self.kind = "tts_start"


@dataclass
class TtsDoneEvent(Event):
    duration_ms: int = 0

    def __post_init__(self) -> None:
        self.kind = "tts_done"


@dataclass
class VadEvent(Event):
    state: str = "silence"  # "silence" | "speech" | "turn_end"

    def __post_init__(self) -> None:
        self.kind = "vad"


@dataclass
class LogEvent(Event):
    level: str = "info"  # "info" | "warn" | "error"
    message: str = ""

    def __post_init__(self) -> None:
        self.kind = "log"
