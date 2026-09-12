# Harness Maintenance Guide

Target: Agent fixing bugs in `src/lingua/agent/harness.py` without reading the whole codebase.

> See [Code Review M2, M5, M6](./specs/2026-09-09-code-review.md) for bug details.

## File Map

| Method | Job | When It Runs |
|--------|-----|--------------|
| `__init__` (L44-92) | Initialize tutor, config, VAD, router, recorder | On harness creation |
| `run()` (L101-118) | Main entry: runs `_run_loop`, ensures recorder finishes on shutdown | On `harness.run()` |
| `_run_loop()` (L120-147) | Main loop: creates audio queue, spawns capture+ASR tasks, gathers them | Every voice turn |
| `_capture_audio()` (L149-172) | Reads mic via `stream_audio_chunks`, puts chunks in queue, signals silence with `b""` | Per turn, concurrent with ASR |
| `_transcribe_audio()` (L174-227) | Drains queue, sends to VoiceStudio WebSocket, yields `final` events | Per turn, concurrent with capture |
| `_process_transcript()` (L229-411) | Routes turn, adds to memory, calls LLM, parses JSON, speaks sentences, records turn | After ASR final event |

## Current Bugs to Fix

### M2: Turn Type Discarded (Line 286)

```python
# BUG: Always hardcodes "explanation"
turn = TutorTurn(type="explanation", text=full_text)
```

**Fix:** Use the parsed type from LLM response:

```python
turn_type = "explanation"
if llm_parsed and isinstance(llm_parsed, dict):
    turn_type = llm_parsed.get("type", "explanation")
if turn_type not in {"explanation", "vocab_drill", "tone_drill", "dialogue", "correction"}:
    turn_type = "explanation"
turn = TutorTurn(type=turn_type, text=full_text)
```

### M5: Recorder Init Before Device Resolution (Line 88-92)

```python
# BUG: Devices not yet known, records "?" as device names
self._recorder.start(
    input_device=getattr(self, "_input_device_name", "?"),
    output_device=getattr(self, "_output_device_name", "?"),
)
```

**Fix:** Move recorder start to `_run_loop`:

```python
async def _run_loop(self):
    if self._recorder is None:
        self._recorder = SessionRecorder()
        self._recorder.start(
            input_device=getattr(self, "_input_device_name", "?"),
            output_device=getattr(self, "_output_device_name", "?"),
        )
```

### M6: No Timeout on Concurrent Tasks (Line 136)

```python
# BUG: If WebSocket hangs, entire loop hangs forever
await asyncio.gather(capture_task, asr_task)
```

**Fix:** Add timeout:

```python
try:
    await asyncio.wait_for(
        asyncio.gather(capture_task, asr_task),
        timeout=60.0
    )
except asyncio.TimeoutError:
    logger.error("Audio capture/ASR timed out")
    capture_task.cancel()
    asr_task.cancel()
```

## Architecture Diagram

```
run()
  └─> _run_loop()
        ┌─────────────────────────────────────────────┐
        │ while True:                                 │
        │   audio_queue = Queue()                    │
        │   capture = _capture_audio(audio_queue)    │──> mic (16kHz PCM)
        │   asr = _transcribe_audio(audio_queue)    │──> VoiceStudio WS
        │   await asyncio.gather(capture, asr)       │     (blocks on silence)
        │   _process_transcript(segments)           │
        │     ├─> memory.add_turn(user)            │
        │     ├─> tutor.stream_response()           │
        │     │     └─> MiniMax LLM                 │
        │     ├─> parse JSON → TutorTurn            │
        │     ├─> for sentence in sentences:        │
        │     │     └─> tutor.speak() → TTS        │
        │     │           └─> VoiceStudio           │
        │     │               └─> sd.play()          │
        │     └─> recorder.record_turn()             │
        └─────────────────────────────────────────────┘
```

## Common Questions

### Where do I add a new event type?

1. Define in `src/lingua/hud/events.py`
2. Publish in harness via `self.event_bus.publish(NewEvent(...))`
3. Subscribe in HUD via `self.bus.subscribe(NewEvent, handler)`

### How do I add a state?

The harness uses `_state = "listening" | "speaking"` (L78). To add states:
1. Update the type annotation
2. Add state transitions in `_run_loop` or `_process_transcript`
3. Add guard checks before operations that require specific states

### Where does timing come from?

- `time.monotonic()` for relative timing (used in HUD events)
- `time.time()` for absolute timestamps (used in recorder)
- `asyncio.gather()` blocks until BOTH capture and ASR finish

## Test Coverage Gaps

| Gap | Location | How to Add |
|-----|----------|------------|
| Full harness loop | `tests/agent/test_harness.py` | Mock audio input, verify recorder output |
| JSON parsing edge cases | Same file | Feed malformed JSON to LLM response |
| Timeout behavior | New test | Mock slow ASR, verify timeout raises |

**Pattern for mocking audio:**

```python
async def test_harness_with_mock_audio():
    # Stream of audio chunks that triggers one "final" transcript
    chunks = [b"\x00" * 1600] * 10  # ~100ms each
    # ... verify behavior
```
