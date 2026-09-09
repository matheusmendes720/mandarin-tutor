# Voice Tutor Live HUD — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent CLI with a Rich TUI HUD that shows mic RMS, transcript, pipeline status, and rolling logs in real-time, and fix the phantom-turn loop caused by too-low VAD threshold.

**Architecture:** Event bus + Rich `Live` display. Each pipeline component publishes typed events; HUD consumes them and redraws 10×/sec.

**Tech Stack:** Python 3.11+, `rich>=13.0`, existing `sounddevice`/`numpy`/`asyncio`.

**Spec:** `docs/superpowers/specs/2026-09-09-voice-tutor-hud.md`

## Global Constraints

- Single new dep: `rich >= 13.0`. No other new deps.
- Backwards compatible: harness with `event_bus=None` keeps current behavior.
- VAD threshold raises from `0.01` to `0.05`. Turn-end requires real speech first.
- All new code under `src/lingua/hud/` package, tests under `tests/hud/`.
- Files under 500 lines. Tests use pytest, no live audio/network.

---

### Task 1: Event dataclasses

**Files:**
- Create: `src/lingua/hud/events.py`
- Test: `tests/hud/test_events.py`

**Step 1 — Write failing tests**

```python
# tests/hud/test_events.py
from lingua.hud.events import (
    Event, RmsEvent, AsrPartialEvent, AsrFinalEvent,
    LlmStartEvent, LlmDoneEvent, TtsStartEvent, TtsDoneEvent,
    VadEvent, LogEvent,
)

def test_event_has_timestamp():
    e = LogEvent(ts=0.0, level="info", message="hi")
    assert e.ts == 0.0
    assert e.kind == "log"

def test_rms_event_preserves_rms():
    e = RmsEvent(ts=1.0, rms=0.42, is_speech=True)
    assert e.rms == 0.42
    assert e.is_speech is True
    assert e.kind == "rms"

def test_asr_final_carries_language():
    e = AsrFinalEvent(ts=0.0, text="你好", language="zh")
    assert e.text == "你好"
    assert e.language == "zh"
    assert e.kind == "asr_final"

def test_llm_done_carries_duration():
    e = LlmDoneEvent(ts=0.0, response_chars=42, duration_ms=1100)
    assert e.duration_ms == 1100
    assert e.kind == "llm_done"

def test_tts_done_carries_duration():
    e = TtsDoneEvent(ts=0.0, duration_ms=1830)
    assert e.duration_ms == 1830

def test_vad_event_state():
    e = VadEvent(ts=0.0, state="speech")
    assert e.state == "speech"

def test_log_event_level():
    e = LogEvent(ts=0.0, level="error", message="boom")
    assert e.level == "error"
```

**Step 2 — Run, verify failure**

Run: `pytest tests/hud/test_events.py -v`
Expected: `ModuleNotFoundError: No module named 'lingua.hud'`

**Step 3 — Implement**

```python
# src/lingua/hud/events.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Event:
    ts: float
    kind: str


@dataclass
class RmsEvent(Event):
    rms: float = 0.0
    is_speech: bool = False


@dataclass
class AsrPartialEvent(Event):
    text: str = ""


@dataclass
class AsrFinalEvent(Event):
    text: str = ""
    language: str = "zh"


@dataclass
class LlmStartEvent(Event):
    prompt_chars: int = 0


@dataclass
class LlmDoneEvent(Event):
    response_chars: int = 0
    duration_ms: int = 0


@dataclass
class TtsStartEvent(Event):
    text_chars: int = 0
    voice: str = ""


@dataclass
class TtsDoneEvent(Event):
    duration_ms: int = 0


@dataclass
class VadEvent(Event):
    state: str = "silence"  # "silence" | "speech" | "turn_end"


@dataclass
class LogEvent(Event):
    level: str = "info"  # "info" | "warn" | "error"
    message: str = ""


# Make sure kind is set correctly on each subclass — use __post_init__:
```python
@dataclass
class RmsEvent(Event):
    rms: float = 0.0
    is_speech: bool = False

    def __post_init__(self) -> None:
        self.kind = "rms"
```

Apply the same `__post_init__` pattern (setting `self.kind = "<lowercase-name>"`) to every event class. No class-attribute loop hack.

**Step 4 — Run, verify pass**

Run: `pytest tests/hud/test_events.py -v`
Expected: 7 passed

**Step 5 — Commit**

```bash
git add src/lingua/hud/__init__.py src/lingua/hud/events.py tests/hud/test_events.py
git commit -m "feat(hud): add typed event dataclasses for voice pipeline"
```

Also create empty `src/lingua/hud/__init__.py` and `tests/hud/__init__.py`.

---

### Task 2: Event bus

**Files:**
- Create: `src/lingua/hud/bus.py`
- Test: `tests/hud/test_bus.py`

**Step 1 — Failing tests**

```python
# tests/hud/test_bus.py
import asyncio
from lingua.hud.events import LogEvent
from lingua.hud.bus import EventBus


def test_subscribe_returns_queue():
    bus = EventBus()
    q = bus.subscribe()
    assert isinstance(q, asyncio.Queue)


def test_publish_reaches_subscriber():
    bus = EventBus()
    q = bus.subscribe()
    bus.publish(LogEvent(ts=0.0, level="info", message="hi"))
    e = q.get_nowait()
    assert e.message == "hi"


def test_multiple_subscribers_each_receive():
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    bus.publish(LogEvent(ts=0.0, level="info", message="x"))
    assert q1.get_nowait().message == "x"
    assert q2.get_nowait().message == "x"


def test_burst_publish_does_not_drop():
    bus = EventBus()
    q = bus.subscribe()
    for i in range(10_000):
        bus.publish(LogEvent(ts=0.0, level="info", message=str(i)))
    received = [q.get_nowait().message for _ in range(10_000)]
    assert received == [str(i) for i in range(10_000)]
```

**Step 2 — Run, verify failure**

Run: `pytest tests/hud/test_bus.py -v`
Expected: `ModuleNotFoundError: No module named 'lingua.hud.bus'`

**Step 3 — Implement**

```python
# src/lingua/hud/bus.py
from __future__ import annotations
import asyncio
from queue import Queue
from threading import Lock

from .events import Event


class EventBus:
    """Thread-safe + asyncio-safe event bus.

    `publish()` is non-blocking and may be called from any thread.
    `subscribe()` returns an `asyncio.Queue` for an async consumer.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._lock = Lock()

    def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def publish(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop on overflow — HUD coalesces anyway.
                pass
```

**Step 4 — Run, verify pass**

Run: `pytest tests/hud/test_bus.py -v`
Expected: 4 passed

**Step 5 — Commit**

```bash
git add src/lingua/hud/bus.py tests/hud/test_bus.py
git commit -m "feat(hud): add thread-safe event bus for pipeline events"
```

---

### Task 3: Extract RMS computation from audio_loop

**Files:**
- Modify: `src/lingua/audio_loop.py:18-109` — extract `compute_rms()`, `is_speech()`, add `on_chunk`/`on_rms` hooks
- Test: `tests/audio/test_compute_rms.py` (or extend existing audio tests)

**Step 1 — Failing tests**

```python
# tests/audio/test_compute_rms.py
import numpy as np
from lingua.audio_loop import compute_rms, is_speech


def test_compute_rms_silence_is_zero():
    chunk = (np.zeros(1600, dtype=np.int16)).tobytes()
    assert compute_rms(chunk) == 0.0


def test_compute_rms_loud_chunk_high():
    # 1600 samples of max amplitude int16 = 32767
    samples = np.full(1600, 32767, dtype=np.int16)
    rms = compute_rms(samples.tobytes())
    assert rms > 0.9  # should be ~1.0 normalized


def test_is_speech_threshold_default():
    assert is_speech(0.10) is True   # above 0.05 default
    assert is_speech(0.01) is False  # below 0.05 default


def test_is_speech_custom_threshold():
    assert is_speech(0.04, threshold=0.03) is True
    assert is_speech(0.04, threshold=0.05) is False
```

**Step 2 — Run, verify failure**

Run: `pytest tests/audio/test_compute_rms.py -v`
Expected: `ImportError: cannot import name 'compute_rms'`

**Step 3 — Implement**

Edit `src/lingua/audio_loop.py`:

```python
# Add module-level helpers
def compute_rms(chunk: bytes) -> float:
    """Compute normalized RMS of int16 PCM chunk.

    Returns a value in [0.0, 1.0].
    """
    arr = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)) / 32768.0)


def is_speech(rms: float, threshold: float = 0.05) -> bool:
    """True if RMS exceeds speech threshold (raised from 0.01)."""
    return rms > threshold
```

Modify `stream_audio_chunks()` signature:

```python
async def stream_audio_chunks(
    sample_rate: int = 16000,
    channels: int = 1,
    chunk_ms: int = 160,
    silence_threshold: float = 0.05,   # was 0.01
    max_seconds: float = 30.0,
    min_speech_seconds: float = 0.3,    # new: ignore phantom speech
    on_rms: Callable[[float, bool], None] | None = None,
) -> AsyncIterator[bytes]:
```

Replace inline RMS computation inside `audio_gen()` with calls to `compute_rms()` and `is_speech()`. Track `had_speech = True` flag. Only break on silence if `had_speech` was set in the last N chunks (use 30-chunk rolling window).

When `on_rms` is provided, call `on_rms(rms, speech)` per chunk (synchronously — callback must be fast, no I/O).

**Step 4 — Run, verify pass**

Run: `pytest tests/audio/ -v`
Expected: existing tests still pass + 4 new ones

**Step 5 — Commit**

```bash
git add src/lingua/audio_loop.py tests/audio/test_compute_rms.py
git commit -m "refactor(audio): extract RMS helpers and raise silence threshold"
```

---

### Task 4: Harness publishes pipeline events

**Files:**
- Modify: `src/lingua/agent/harness.py`
- Test: `tests/agent/test_harness_events.py`

**Step 1 — Failing tests**

```python
# tests/agent/test_harness_events.py
import asyncio
from unittest.mock import MagicMock
from lingua.hud.events import (
    AsrFinalEvent, LlmStartEvent, LlmDoneEvent, TtsStartEvent, TtsDoneEvent
)
from lingua.hud.bus import EventBus
from lingua.agent.harness import VoiceAgentHarness


def test_harness_accepts_event_bus():
    bus = EventBus()
    # Just construction — doesn't actually run
    mock_tutor = MagicMock()
    harness = VoiceAgentHarness(tutor=mock_tutor, event_bus=bus)
    assert harness.event_bus is bus


def test_harness_event_bus_optional():
    mock_tutor = MagicMock()
    harness = VoiceAgentHarness(tutor=mock_tutor)
    assert harness.event_bus is None
```

**Step 2 — Run, verify failure**

Run: `pytest tests/agent/test_harness_events.py -v`
Expected: `TypeError: __init__() got an unexpected keyword argument 'event_bus'`

**Step 3 — Modify harness**

Edit `src/lingua/agent/harness.py`:

- Add `event_bus: EventBus | None = None` to `__init__`
- Store `self.event_bus = event_bus`
- In `_transcribe_audio`, when final received:
  ```python
  if self.event_bus:
      self.event_bus.publish(AsrFinalEvent(ts=time.monotonic(), text=text, language=...))
  ```
- In `_process_transcript`, before `self.tutor._ask_llm(text)`:
  ```python
  if self.event_bus:
      self.event_bus.publish(LlmStartEvent(ts=..., prompt_chars=len(text)))
  ```
- After `_ask_llm`:
  ```python
  if self.event_bus:
      self.event_bus.publish(LlmDoneEvent(ts=..., response_chars=len(turn.text), duration_ms=int((time.monotonic()-t0)*1000)))
  ```
- Before `tutor.speak(...)`:
  ```python
  if self.event_bus:
      self.event_bus.publish(TtsStartEvent(ts=..., text_chars=len(turn.text), voice=voice_profile))
  ```
- After `sd.wait()`:
  ```python
  if self.event_bus:
      self.event_bus.publish(TtsDoneEvent(ts=..., duration_ms=int((time.monotonic()-t1)*1000)))
  ```

**Step 4 — Run, verify pass**

Run: `pytest tests/agent/ -v`
Expected: existing tests pass + 2 new

**Step 5 — Commit**

```bash
git add src/lingua/agent/harness.py tests/agent/test_harness_events.py
git commit -m "feat(harness): publish typed events to optional EventBus"
```

---

### Task 5: Rich Live HUD display

**Files:**
- Create: `src/lingua/hud/display.py`
- Test: `tests/hud/test_display.py`
- Modify: `pyproject.toml` — add `rich>=13.0`

**Step 1 — Failing tests**

```python
# tests/hud/test_display.py
from io import StringIO
from rich.console import Console
from lingua.hud.events import (
    RmsEvent, AsrFinalEvent, LlmStartEvent, TtsStartEvent,
    VadEvent, LogEvent
)
from lingua.hud.display import Hud


def test_hud_constructs_with_devices():
    hud = Hud(input_device="Mic", output_device="HP")
    assert hud.input_device == "Mic"


def test_hud_renders_to_string():
    """Build a fake event list, render once, capture output."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    hud = Hud(input_device="Mic", output_device="HP", console=console)
    hud.apply(RmsEvent(ts=0.0, rms=0.42, is_speech=True))
    hud.apply(VadEvent(ts=0.0, state="speech"))
    hud.apply(AsrFinalEvent(ts=0.0, text="你好", language="zh"))
    output = console.file.getvalue()
    assert "Lingua" in output
    assert "你好" in output


def test_hud_rms_history_caps_at_60():
    hud = Hud(input_device="Mic", output_device="HP")
    for i in range(100):
        hud.apply(RmsEvent(ts=0.0, rms=i / 100.0, is_speech=False))
    assert len(hud.rms_history) == 60
    assert hud.rms_history[-1] == pytest.approx(0.99)


def test_hud_transcript_keeps_last_6():
    hud = Hud(input_device="Mic", output_device="HP")
    for i in range(10):
        hud.apply(AsrFinalEvent(ts=0.0, text=f"turn-{i}", language="zh"))
    assert len(hud.transcript) == 6
    assert hud.transcript[-1]["text"] == "turn-9"


def test_hud_log_keeps_last_20():
    hud = Hud(input_device="Mic", output_device="HP")
    for i in range(50):
        hud.apply(LogEvent(ts=0.0, level="info", message=f"m-{i}"))
    assert len(hud.log_lines) == 20
    assert "m-49" in hud.log_lines[-1]
```

**Step 2 — Run, verify failure**

Run: `pytest tests/hud/test_display.py -v`
Expected: `ModuleNotFoundError`

**Step 3 — Add rich dep + implement**

Edit `pyproject.toml` dependencies: add `"rich>=13.0"`.
Run: `pip install rich`

Implement `src/lingua/hud/display.py`:

```python
# src/lingua/hud/display.py
from __future__ import annotations
import time
from collections import deque
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.bar import Bar

from .events import (
    Event, RmsEvent, AsrFinalEvent, LlmStartEvent, LlmDoneEvent,
    TtsStartEvent, TtsDoneEvent, VadEvent, LogEvent,
)


class Hud:
    """Live HUD driven by Event stream.

    Apply events via `apply()` or stream via `run()`.
    Render with `renderable()` for testing or via `Live()` in production.
    """

    def __init__(
        self,
        input_device: str,
        output_device: str,
        console: Console | None = None,
    ) -> None:
        self.input_device = input_device
        self.output_device = output_device
        self.console = console or Console()
        self.start_ts = time.monotonic()

        self.rms_history: deque[float] = deque(maxlen=60)
        self.vad_state = "silence"
        self.last_speech_rms: float = 0.0
        self.transcript: deque[dict[str, Any]] = deque(maxlen=6)
        self.log_lines: deque[str] = deque(maxlen=20)

        # Pipeline status
        self.asr_status = "idle"
        self.asr_latency_ms = 0
        self.llm_status = "idle"
        self.llm_latency_ms = 0
        self.tts_status = "idle"
        self.tts_latency_ms = 0

    def apply(self, event: Event) -> None:
        if isinstance(event, RmsEvent):
            self.rms_history.append(event.rms)
            self.last_speech_rms = event.rms
        elif isinstance(event, VadEvent):
            self.vad_state = event.state
        elif isinstance(event, AsrFinalEvent):
            self.asr_status = "final"
            self.transcript.append({"role": "user", "text": event.text, "lang": event.language})
        elif isinstance(event, LlmStartEvent):
            self.llm_status = "thinking"
        elif isinstance(event, LlmDoneEvent):
            self.llm_status = "done"
            self.llm_latency_ms = event.duration_ms
            self.transcript.append({"role": "tutor", "text": f"[{event.response_chars} chars]", "lang": ""})
        elif isinstance(event, TtsStartEvent):
            self.tts_status = "playing"
        elif isinstance(event, TtsDoneEvent):
            self.tts_status = "done"
            self.tts_latency_ms = event.duration_ms
        elif isinstance(event, LogEvent):
            ts = time.strftime("%H:%M:%S")
            self.log_lines.append(f"{ts} [{event.level}] {event.message}")

    def renderable(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._header(), size=3),
            Layout(name="body"),
            Layout(self._log_panel(), size=8),
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(self._transcript_panel(), name="right"),
        )
        layout["body"]["left"].split_column(
            Layout(self._mic_panel(), name="mic"),
            Layout(self._pipeline_panel(), name="pipeline"),
        )
        return layout

    def _header(self) -> Panel:
        uptime = int(time.monotonic() - self.start_ts)
        m, s = divmod(uptime, 60)
        h, m = divmod(m, 60)
        text = Text()
        text.append("🎙️  Lingua Voice Tutor", style="bold cyan")
        text.append(f"   ⏱  {h:02d}:{m:02d}:{s:02d}", style="dim")
        text.append(f"\nInput:  {self.input_device}\n", style="dim")
        text.append(f"Output: {self.output_device}", style="dim")
        return Panel(text, border_style="cyan")

    def _mic_panel(self) -> Panel:
        # Render RMS bar as 30 chars wide
        bar_width = 30
        rms_now = self.last_speech_rms
        filled = int(min(rms_now, 1.0) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        threshold_pos = int(0.05 * bar_width)
        bar_text = Text()
        bar_text.append(bar[:threshold_pos], style="green")
        bar_text.append(bar[threshold_pos], style="yellow")
        bar_text.append(bar[threshold_pos+1:], style="dim")
        state_color = {"silence": "dim", "speech": "bold red", "turn_end": "yellow"}.get(self.vad_state, "white")
        bar_text.append(f"\nrms: {rms_now:.3f}  threshold: 0.05\n", style="dim")
        bar_text.append(f"🎤 {self.vad_state.upper()}", style=state_color)
        return Panel(bar_text, title="MICROPHONE", border_style="green")

    def _pipeline_panel(self) -> Panel:
        text = Text()
        for name, status, lat in (
            ("ASR ", self.asr_status, self.asr_latency_ms),
            ("LLM ", self.llm_status, self.llm_latency_ms),
            ("TTS ", self.tts_status, self.tts_latency_ms),
        ):
            icon = {"idle": "○", "thinking": "⋯", "playing": "▶", "final": "✓", "done": "✓"}.get(status, "?")
            color = {"idle": "dim", "thinking": "yellow", "playing": "cyan", "final": "green", "done": "green"}.get(status, "white")
            text.append(f"{icon} {name}", style=color)
            text.append(f"  {status:<10}", style=color)
            text.append(f" {lat}ms\n", style="dim")
        return Panel(text, title="PIPELINE", border_style="magenta")

    def _transcript_panel(self) -> Panel:
        text = Text()
        for t in self.transcript:
            role = t["role"].upper()
            text.append(f"[{role}] ", style="bold" if role == "USER" else "cyan")
            text.append(f"{t['text']}\n")
        return Panel(text, title="TRANSCRIPT", border_style="yellow")

    def _log_panel(self) -> Panel:
        text = Text()
        for line in self.log_lines:
            text.append(line + "\n")
        return Panel(text, title="LOG (rolling)", border_style="dim")

    async def run(self, events) -> None:
        """Consume events from an async iterator and live-render."""
        with Live(self.renderable(), console=self.console, refresh_per_second=10) as live:
            async for event in events:
                self.apply(event)
                live.update(self.renderable())
```

**Step 4 — Run, verify pass**

Run: `pytest tests/hud/test_display.py -v`
Expected: 5 passed

**Step 5 — Commit**

```bash
git add pyproject.toml src/lingua/hud/display.py tests/hud/test_display.py
git commit -m "feat(hud): add Rich Live HUD with mic/pipeline/transcript panels"
```

---

### Task 6: Wire HUD into CLI + audio device picker

**Files:**
- Modify: `src/lingua/__main__.py`

**Step 1 — Implement**

```python
"""Lingua — voice-first Mandarin Chinese tutor."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import sounddevice as sd

from .config import LinguaConfig
from .voice_studio import VoiceStudioClient
from .tutor import MandarinTutor
from .hud.bus import EventBus
from .hud.display import Hud


def _load_env() -> None:
    for dotenv in [Path.cwd() / ".env", Path.home() / ".lingua.env"]:
        if dotenv.exists():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                os.environ[k] = v
                if k == "MINIMAX_API_KEY":
                    os.environ.setdefault("OPENAI_API_KEY", v)
            break


def _list_devices() -> None:
    print("\nAudio devices:")
    for i, d in enumerate(sd.query_devices()):
        marker = ""
        if d["max_input_channels"] > 0 and i == sd.default.device[0]:
            marker += " [default INPUT]"
        if d["max_output_channels"] > 0 and i == sd.default.device[1]:
            marker += " [default OUTPUT]"
        print(f"  [{i}] {d['name']}{marker}")
    print()


def _resolve_device(idx: int | None, kind: str) -> tuple[int | None, str]:
    if idx is None:
        if kind == "input":
            idx = sd.default.device[0]
        else:
            idx = sd.default.device[1]
    info = sd.query_devices(idx)
    return idx, info["name"]


async def async_main(args: argparse.Namespace) -> None:
    from lingua.agent.harness import VoiceAgentHarness

    config = LinguaConfig.from_toml("lingua.toml")
    bus = EventBus()

    input_idx, input_name = _resolve_device(args.input, "input")
    output_idx, output_name = _resolve_device(args.output, "output")

    # Set defaults for sounddevice
    if input_idx is not None:
        sd.default.device = (input_idx, sd.default.device[1])
    if output_idx is not None:
        sd.default.device = (sd.default.device[0], output_idx)

    tutor = MandarinTutor(config)
    harness = VoiceAgentHarness(tutor=tutor, config=config, event_bus=bus)

    hud = Hud(input_device=input_name, output_device=output_name)

    print("🎙️  Lingua Voice Tutor")
    print(f"Input:  {input_name} [device {input_idx}]")
    print(f"Output: {output_name} [device {output_idx}]")
    print("Press Ctrl+C to exit.\n")

    hud_task = asyncio.create_task(hud.run(bus.subscribe()))
    try:
        await harness.run()
    except KeyboardInterrupt:
        print("\n👋 goodbye!")
    finally:
        hud_task.cancel()
        try:
            await hud_task
        except asyncio.CancelledError:
            pass


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lingua", description="Voice-first Mandarin tutor")
    parser.add_argument("--input", "-i", type=int, default=None, help="Input device index")
    parser.add_argument("--output", "-o", type=int, default=None, help="Output device index")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    args = parser.parse_args(argv)

    _load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s")

    if args.list_devices:
        _list_devices()
        return

    # Verify VoiceStudio
    config = LinguaConfig.from_toml("lingua.toml")
    vs = VoiceStudioClient(config.voicestudio.url)
    if not vs.is_available():
        print(f"❌ VoiceStudio not reachable at {config.voicestudio.url}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

**Step 2 — Smoke test**

Run: `python -m lingua --list-devices`
Expected: device list printed.

Run: `python -c "from lingua.__main__ import main; print('ok')"`
Expected: `ok`

**Step 3 — Commit**

```bash
git add src/lingua/__main__.py
git commit -m "feat(cli): wire Rich HUD + audio device picker into entry point"
```

---

### Task 7: Run full test suite + manual smoke

**Step 1 — Verify all tests pass**

Run: `pytest -q`
Expected: 41+ existing + ~16 new = ~57 passed

**Step 2 — Manual smoke**

Run: `python -m lingua --list-devices` → device list

Run: `python -m lingua` for 5 seconds
Expected: HUD visible, mic RMS updating, "🎤 SILENCE" badge

Speak a word — expected: ASR row → ✓ final, transcript panel updates, LLM row → thinking → done, TTS row → playing, audible response

**Step 3 — Update progress ledger**

Edit `.claude-flow/sdd/progress.md` — mark HUD tasks complete.

---

## File Layout After Plan

```
src/lingua/
├── __main__.py             # modified — argparse, HUD wiring
├── audio_loop.py           # modified — extract RMS, hooks
├── agent/
│   └── harness.py          # modified — publish events
├── hud/
│   ├── __init__.py
│   ├── events.py           # new
│   ├── bus.py              # new
│   └── display.py          # new
└── ...

tests/
├── agent/
│   └── test_harness_events.py
├── audio/
│   └── test_compute_rms.py
└── hud/
    ├── __init__.py
    ├── test_events.py
    ├── test_bus.py
    └── test_display.py
```
