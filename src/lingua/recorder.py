"""Session recorder — writes JSON file per app run for offline analysis.

Usage in VoiceAgentHarness:
    self.recorder = SessionRecorder(path=Path("data/sessions"))
    self.recorder.start(input_device="...", output_device="...")
    # ... per turn ...
    self.recorder.record_turn({...})
    self.recorder.finish()  # on shutdown
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Turn:
    """One user→assistant exchange."""
    ts: float
    seq: int  # 1-based turn number within the session

    # ASR
    asr_text: str = ""
    asr_language: str = ""
    asr_latency_ms: int = 0
    asr_error: str | None = None

    # LLM
    llm_response: str = ""
    llm_parsed_json: dict | None = None
    llm_latency_ms: int = 0
    llm_error: str | None = None

    # TTS
    tts_sentences: list[str] = field(default_factory=list)
    tts_latency_ms_per_sentence: list[int] = field(default_factory=list)
    tts_total_bytes: list[int] = field(default_factory=list)

    # User-visible
    pinyin_displayed: str = ""

    # Anomaly flags — useful for post-mortem
    flags: list[str] = field(default_factory=list)


class SessionRecorder:
    """Writes a single JSON file per app run."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path("data/sessions")
        self.path.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_path = self.path / f"session_{self.session_id}.json"
        self.start_ts = time.monotonic()
        self.start_wall = datetime.now().isoformat()
        self.turns: list[Turn] = []
        self.metadata: dict[str, Any] = {}

    def start(self, **metadata: Any) -> None:
        """Open the session; record metadata."""
        self.metadata.update(metadata)
        # Persist initial frame so even a crash leaves a traceable file.
        self._write()

    def record_turn(self, turn: Turn) -> None:
        self.turns.append(turn)
        self._write()

    def finish(self) -> Path | None:
        """Close the session. Returns the file path written."""
        self.metadata["end_ts"] = time.monotonic() - self.start_ts
        self.metadata["end_wall"] = datetime.now().isoformat()
        self.metadata["n_turns"] = len(self.turns)
        self._write()
        return self.session_path

    def _write(self) -> None:
        payload = {
            "session_id": self.session_id,
            "start_ts": self.start_wall,
            "uptime_s": round(time.monotonic() - self.start_ts, 3),
            "metadata": self.metadata,
            "turns": [asdict(t) for t in self.turns],
        }
        self.session_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
