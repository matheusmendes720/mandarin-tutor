# Voice Tutor Live HUD — Design Spec

**Date:** 2026-09-09
**Status:** Approved
**Author:** Claude (brainstorming session with user)

## Problem

`python -m lingua` launches a voice-first tutor but the user is flying blind:

- No live feedback — can't tell if the mic is actually capturing audio
- "silence detected — processing..." prints every 0.5s even when nobody is talking
- No way to see what ASR heard, what the LLM generated, or whether TTS is playing
- Windows audio device selection is implicit; wrong device silently captures nothing
- Output is intermixed with logs, hard to follow

The user described the current experience as "primitivo... não consigo ver logs de nada acontecendo".

## Goal

Make the state of the voice pipeline continuously visible in the terminal, with zero ambiguity about:

1. **Is my mic picking up audio right now?** → RMS meter
2. **Did ASR get a transcript?** → partial + final transcript stream
3. **Is the LLM thinking or stuck?** → pipeline status with latency
4. **Is TTS playing?** → playback indicator + duration
5. **Which audio devices am I using?** → startup banner

## Non-Goals

- Web UI / Gradio — Rich TUI only
- Multiple simultaneous users
- Audio recording / export to disk
- Voice activity classification beyond RMS threshold
- TUI configurability (color themes, layouts) — defaults only

## Architecture

Single-screen `Live` display, fed by typed event callbacks from the harness.

```
                        ┌────────────────────────────────┐
                        │  events.Queue[Event] (asyncio) │
                        └────────────────┬───────────────┘
                                         │
        ┌──────────────┬─────────────────┼─────────────────┐
        │              │                 │                 │
   AudioCapture    ASRResult        LLMEvent          TTSEvent
   (RMS each       (partial/final)  (start/done)     (start/done)
    chunk)                              │                 │
        └──────────────┴─────────────────┴─────────────────┘
                                         │
                                  ┌──────▼──────┐
                                  │   HUD       │ ← Live display,
                                  │  (Rich)     │   redraws 10×/s
                                  └─────────────┘
```

Each pipeline component pushes typed events to a shared queue. A HUD task consumes them and updates the `Live` display.

## Components

### 1. `src/lingua/hud/events.py` — Event types

```python
@dataclass
class Event:
    ts: float  # monotonic
    kind: str  # "rms" | "vad" | "asr_partial" | "asr_final" | "llm_start" | "llm_done" | "tts_start" | "tts_done" | "log"

@dataclass
class RmsEvent(Event):
    rms: float
    is_speech: bool

@dataclass
class AsrPartialEvent(Event):
    text: str

@dataclass
class AsrFinalEvent(Event):
    text: str
    language: str

@dataclass
class LlmStartEvent(Event):
    prompt_chars: int

@dataclass
class LlmDoneEvent(Event):
    response_chars: int
    duration_ms: int

@dataclass
class TtsStartEvent(Event):
    text_chars: int
    voice: str

@dataclass
class TtsDoneEvent(Event):
    duration_ms: int

@dataclass
class VadEvent(Event):
    state: str  # "silence" | "speech" | "turn_end"

@dataclass
class LogEvent(Event):
    level: str  # "info" | "warn" | "error"
    message: str
```

### 2. `src/lingua/hud/display.py` — Rich Live display

Public API:

```python
class Hud:
    def __init__(self, input_device: str, output_device: str) -> None: ...
    def run(self, events: AsyncIterator[Event]) -> None: ...
```

Layout (3 panels + log footer):

- **Header:** `🎙️ Lingua Voice Tutor` + uptime counter
- **Left top:** Mic panel — RMS bar (last 60 samples), threshold marker, current state badge
- **Left bottom:** Pipeline panel — rows for ASR/LLM/TTS with status icon + latency
- **Right:** Transcript panel — rolling list of recent exchanges (last 6 turns)
- **Bottom:** Log panel — rolling last 20 events with timestamp

`Live` auto-refreshes 10×/sec. Coalesces RMS samples to one update per 100ms.

### 3. `src/lingua/hud/bus.py` — Event bus

```python
class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Queue[Event]] = []

    def subscribe(self) -> Queue[Event]: ...
    def publish(self, event: Event) -> None: ...
```

Thread-safe and asyncio-safe. Multiple subscribers allowed (HUD + tests).

### 4. Modified `src/lingua/audio_loop.py`

`stream_audio_chunks()` gains optional `on_chunk: Callable[[bytes], None] | None = None`. Each chunk emitted → callback fires with raw bytes (or with precomputed RMS via a separate `on_rms` hook to avoid recomputation in the VAD).

Two new functions:
- `compute_rms(chunk: bytes) -> float` — moved out of the generator so HUD can reuse it
- `is_speech(rms: float, threshold: float = 0.05) -> bool` — extracted for reuse

### 5. Modified `src/lingua/agent/harness.py`

- Constructor accepts `event_bus: EventBus | None = None`
- `_capture_audio` publishes `RmsEvent` every chunk, `VadEvent` on state change
- `_transcribe_audio` publishes `AsrPartialEvent` and `AsrFinalEvent`
- `_process_transcript` publishes `LlmStartEvent` before `_ask_llm`, `LlmDoneEvent` after
- `tutor.speak()` publishes `TtsStartEvent` before, `TtsDoneEvent` after playback
- VAD threshold raised: `0.01 → 0.05`
- Turn-end detection: require at least one `RmsEvent(is_speech=True)` in last 30 chunks before silence counts as end-of-turn (eliminates phantom turns)

### 6. Modified `src/lingua/__main__.py`

- Lists audio devices at startup, lets user pick with `--input N --output M`
- Defaults to `sd.query_devices(kind='input')` and `kind='output'`
- Constructs `EventBus`, `Hud`, passes bus to harness, runs `Hud.run()` as the asyncio task

### 7. New `pyproject.toml` dep

`rich >= 13.0`

## Files Touched

| File | Change |
|---|---|
| `src/lingua/hud/events.py` | CREATE |
| `src/lingua/hud/display.py` | CREATE |
| `src/lingua/hud/bus.py` | CREATE |
| `src/lingua/audio_loop.py` | MODIFY — extract RMS, add on_chunk hook |
| `src/lingua/agent/harness.py` | MODIFY — publish events, raise VAD threshold |
| `src/lingua/__main__.py` | MODIFY — wire bus + HUD, device picker |
| `pyproject.toml` | MODIFY — add `rich` dep |
| `tests/hud/test_events.py` | CREATE |
| `tests/hud/test_bus.py` | CREATE |
| `tests/hud/test_display.py` | CREATE |

## Behavioral Spec

1. **Startup banner:**
   ```
   🎙️ Lingua Voice Tutor
   Input:  Microphone Array (Intel® Smart Sound Technology for Digital Microphones) [device 1]
   Output: Headphones (Realtek(R) Audio) [device 3]
   Press Ctrl+C to exit.
   ```

2. **Live display** redraws 10×/sec showing: mic RMS, pipeline status, transcript, rolling logs.

3. **VAD:** turn-end fires only after a real speech segment + 1.5s silence. No phantom turns on background noise.

4. **Event latency:** HUD reflects state changes within 100ms (the display refresh interval).

5. **No silent failures:** if VoiceStudio is unreachable, HUD shows red `ASR ✗ offline` status + log entry. If mic fails to open, HUD shows red `MIC ✗ error` and exits cleanly.

## Testing

- `test_events.py`: each Event type round-trips; `RmsEvent` preserves RMS; `AsrFinalEvent` carries text + language
- `test_bus.py`: `publish()` reaches all `subscribe()`rs; subscribers isolated; no event loss under burst (10k events)
- `test_display.py`: HUD renders without error given synthetic event stream; RMS bar reflects last 60 samples; transcript panel keeps ≤6 turns
- Existing `test_harness.py` continues passing — event bus is optional, harness works with `event_bus=None`

## Open Questions

None — all decisions confirmed with user.
