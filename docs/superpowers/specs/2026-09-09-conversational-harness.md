# Conversational Harness — Refactor Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rigid single-loop harness with a state machine that supports real conversational behavior: drilling when the user wants to drill, answering when they ask, switching topic when they're bored, and being interruptible while speaking.

**Architecture:** Event-sourced state machine with explicit states, transitions, and per-state handlers. A small intent router classifies each user turn and dispatches to the right handler.

**Tech Stack:** Python 3.11+, asyncio, existing tutor / ASR / TTS.

**Spec:** This document is the design — implement it as specified.

## Global Constraints

- No new runtime deps. `rich` (already used by HUD) is the only new dep for the optional event log view.
- Backwards compatible: `python -m lingua` must continue to work without flags.
- No breaking changes to the recorder, HUD, or tutor API surface — only harness internals.
- All existing tests must pass.

---

## Problem Statement

The current `VoiceAgentHarness` runs a single `while True` loop that:

1. Runs `audio_capture_task` and `asr_task` in parallel until one ends
2. Calls `_process_transcript` synchronously
3. Blocks on `sd.wait()` (full TTS playback) before returning to step 1

Symptoms observed in `data/sessions/session_20260909_181033.json` (20 turns, 7min46s):

- The system repeats the same drill phrase (`nǐ kàn guò nà běn shū ma — "Have you read that book?"`) regardless of what the user says. 8 consecutive turns of the user failing at the same phrase, with the LLM offering it again each time.
- When the user asks "could you speak a bit slower?", the LLM responds "Sure! Slowly: ..." — but actual TTS speed does not change.
- When the user switches languages (Portuguese, French, Romanian) or random words ("Beijo mano", "N'est pas un roi", "Washing"), the LLM rejects with "That isn't Mandarin" instead of engaging.
- The user cannot interrupt the tutor while it's speaking.

Root causes:

1. **No intent classification** — every ASR result goes through the same LLM call regardless of user intent.
2. **No state** — the harness has no concept of "we're mid-drill" vs "user is asking a question" vs "user is confused".
3. **No repetition detection** — the tutor offers the same phrase over and over without realizing the user is stuck.
4. **No interruptibility** — `sd.wait()` blocks the entire event loop until playback ends.

---

## New Architecture: Event-Sourced State Machine

### Top-level structure

```
┌─────────────────────────────────────────────────────────────┐
│ VoiceSession                                                │
│   ┌──────────┐                                              │
│   │ events   │  asyncio.Queue of SessionEvent                │
│   └────┬─────┘                                              │
│        │                                                    │
│   ┌────▼──────────────────────────────────────────────────┐ │
│   │ StateMachine (driven by SessionEvent)                  │ │
│   │   - listens to events                                  │ │
│   │   - owns current state + context                       │ │
│   │   - transitions to new state based on event            │ │
│   └────┬──────────────────────────────────────────────────┘ │
│        │                                                    │
│   ┌────▼─────────────┐    ┌─────────────────────────────┐  │
│   │ StateRegistry    │    │ Always-running tasks         │  │
│   │ - IdleState      │    │   - audio_capture (always)   │  │
│   │ - DrillingState │    │   - interruption_watcher     │  │
│   │ - ExplainingState│    └─────────────────────────────┘  │
│   │ - AskingState    │                                      │
│   │ - ConfusedState  │                                      │
│   └──────────────────┘                                      │
└─────────────────────────────────────────────────────────────┘
```

### SessionEvent types

```python
class SessionEvent:
    """Anything that flows through the session."""

class AudioFrame(SessionEvent):
    """PCM bytes from the mic. Fired ~10×/sec regardless of state."""
    pcm: bytes
    rms: float

class TranscriptFinal(SessionEvent):
    """ASR returned a final transcript."""
    text: str
    language: str

class UtteranceStart(SessionEvent):
    """User started speaking — VAD detected speech onset."""

class UtteranceEnd(SessionEvent):
    """User stopped speaking — VAD detected silence > 0.5s after speech."""

class TutorDoneSpeaking(SessionEvent):
    """TTS playback finished."""

class Interrupt(SessionEvent):
    """User started speaking while tutor was playing."""

class Tick(SessionEvent):
    """Periodic timer for state timeouts."""
```

### Intent router

Small, fast, heuristic-based. Lives at `src/lingua/agent/intent.py`. Returns one of:

```python
class UserIntent(Enum):
    DRILL_ATTEMPT = "drill_attempt"     # user tried to say a phrase
    QUESTION = "question"               # how do you say, what does X mean
    SWITCH_TOPIC = "switch_topic"       # another phrase, change topic, let's try X
    FRUSTRATION = "frustration"         # this is hard, fuck this, etc.
    GREETING = "greeting"               # hi, hello, oi
    OFF_TOPIC = "off_topic"             # anything else
    SILENCE = "silence"                 # empty transcript
```

Heuristics (kept simple, no LLM):
- **DRILL_ATTEMPT**: text contains CJK chars OR (last assistant turn had `expected` field AND user just typed/spoke something close).
- **QUESTION**: text starts with "how do you say", "what does", "what is", "how to", "explain", "teach me", "translate".
- **SWITCH_TOPIC**: text contains "another", "next", "different", "change", "let's try", "switch".
- **FRUSTRATION**: text matches `(?i)\b(fuck|shit|damn|suck|hate|stupid|hard|confused|lost)\b`.
- **GREETING**: text in `{"hi", "hello", "hey", "oi", "olá", "你好", "hallo"}` (after normalization).
- **OFF_TOPIC**: anything else.

### States

Each state has the same interface:

```python
class State(Protocol):
    name: str
    context: dict  # arbitrary state

    async def enter(self, ctx: Context) -> None: ...
    async def handle(self, event: SessionEvent, ctx: Context) -> None: ...
    async def exit(self, ctx: Context) -> None: ...
```

#### `IdleState`

The user is doing nothing. We're just listening.

- `enter`: clear UI "ready" indicator.
- `handle(AudioFrame)`: update RMS meter only.
- `handle(TranscriptFinal)`: classify intent, transition to `ExplainingState` or `ConfusedState`.
- `exit`: nothing.

#### `DrillingState`

The user is in a drill loop. Tutor just gave a phrase; user is attempting to repeat it.

- `enter`: announce "drill: <phrase>" in HUD.
- `handle(TranscriptFinal)`:
  - If `UserIntent.DRILL_ATTEMPT`: compare user text to expected Mandarin. Call tutor to evaluate (`type=correction`). Transition back to `DrillingState` if same phrase, or `DrillingState` with new phrase if user fails 3+ times (auto-shift).
  - If `UserIntent.SWITCH_TOPIC`: transition to `DrillingState` with new phrase (call tutor for new phrase).
  - If `UserIntent.QUESTION`: transition to `ExplainingState`.
  - If `UserIntent.FRUSTRATION`: transition to `ConfusedState`.
- `handle(Interrupt)` while tutor is speaking: stop TTS, transition back to `IdleState`.
- `exit`: clear "drill" indicator.

#### `ExplainingState`

User asked a question. Tutor explains in English (with Mandarin embedded).

- `enter`: nothing.
- `handle(TranscriptFinal)`:
  - User said something → run LLM call to answer, speak answer, transition back to `IdleState`.
- `handle(TranscriptFinal)` with `Question`-type intent: re-route to `AskingState`.

#### `AskingState`

Mid-flow Q&A: tutor asked "say X", user is supposed to answer.

- Like `DrillingState` but context is "this was a Q&A round".

#### `ConfusedState`

User is frustrated, asking meta-questions ("how does this work"), or saying random words.

- Tutor responds conversationally (no drill force). After one response, transition back to `IdleState`.

### State machine flow

```
                        ┌─────────────┐
                        │   Idle      │◀─────┐
                        └──────┬──────┘      │
                               │             │
            ┌─────┬──────┬─────┼─────┬───────┤
            ▼     ▼      ▼     ▼     ▼       │
       Drilling Explain Ask Confused Greet ──┘
            │     │      │     │
            └─────┴──────┴─────┘
              (after one response → Idle)
```

### Interruption

- A separate `interruption_watcher` task always runs in parallel with the audio capture.
- It listens to the same mic feed but **only** when TTS is playing.
- When `AudioFrame.rms > 0.1` for > 200ms while TTS is active → emit `Interrupt` event.
- The current state's `handle(Interrupt)` stops playback via `sd.stop()` and transitions to `IdleState`.

### Repetition detection

In `DrillingState.context`, track:

```python
@dataclass
class DrillContext:
    current_phrase: str
    attempts: int = 0          # how many times user has tried this phrase
    last_user_text: str = ""
    consecutive_failures: int = 0
```

When `consecutive_failures >= 3`:
- Emit a HUD warning: "Stuck on X — switching topic"
- Inject a system message into LLM context: "User has failed 3× on this phrase. Offer a NEW, related phrase."
- Reset `consecutive_failures`.

### Context management

Per-state `context` is **scoped**, not global. When transitioning to a new state, only relevant context is passed to the LLM call:

```python
def build_llm_context(self, state_context: dict) -> list[dict]:
    """Construct messages list for LLM call.

    - Always: [system, last 2 user turns, current user turn]
    - Never include older turns unless relevant
    - Drill context includes `current_phrase`, `expected`, last `feedback`
    """
```

This prevents the context-window explosion that causes the LLM to lose track of what it's doing.

### Files

| File | Status | Purpose |
|---|---|---|
| `src/lingua/agent/session.py` | CREATE | `VoiceSession` orchestrator + event queue |
| `src/lingua/agent/state_machine.py` | CREATE | Generic `StateMachine` base + `Context` |
| `src/lingua/agent/states.py` | CREATE | `IdleState`, `DrillingState`, `ExplainingState`, `AskingState`, `ConfusedState` |
| `src/lingua/agent/intent.py` | CREATE | `UserIntent` enum + heuristic router |
| `src/lingua/agent/harness.py` | MODIFY | Become a thin wrapper around `VoiceSession` (or just re-export) |
| `src/lingua/agent/vad.py` | MODIFY | Add `is_speech_onset()` and `is_interrupt()` methods |
| `tests/agent/test_intent.py` | CREATE | Tests for the intent router |
| `tests/agent/test_state_machine.py` | CREATE | Tests for state transitions |
| `tests/agent/test_drill_repetition.py` | CREATE | Tests for repetition detection + auto-shift |

### Public API

```python
# Backwards compatible
from lingua.agent.harness import VoiceAgentHarness

# New (preferred)
from lingua.agent.session import VoiceSession
from lingua.agent.intent import UserIntent, classify_intent
```

`VoiceAgentHarness.__init__` keeps the same signature. Internally, it now constructs a `VoiceSession` and delegates `run()`.

### Migration

- Phase 1: Implement `VoiceSession` alongside `VoiceAgentHarness`. Both work; `__main__.py` uses `VoiceAgentHarness` for now.
- Phase 2: Switch `__main__.py` to use `VoiceSession` directly.
- Phase 3: Remove `VoiceAgentHarness`.

(All phases in the same plan; no intermediate state where one path is broken.)

### Testing strategy

- **Unit tests** for `intent.classify_intent`: feed representative user messages, assert intent.
- **Unit tests** for state transitions: instantiate `StateMachine`, feed scripted events, assert resulting state and emitted side-effects.
- **Unit tests** for repetition detection: simulate 3 failures, assert context switches.
- **Integration smoke test**: run `python -m lingua` for 10 seconds, speak a few things, assert `data/sessions/session_*.json` has multiple turns with intent annotations.

### Success criteria

A session recorded with the new harness should show:

1. User says "another phrase" → next assistant turn is a NEW phrase (not the same).
2. User says "how do you say thank you" → assistant turn is an explanation with `xiè xie` embedded.
3. User says "fuck this" → assistant turn is conversational ("I get it, this is hard. Want me to switch to a different topic?"), not another drill.
4. User speaks for > 200ms while tutor is playing → tutor stops within 1 second, next turn starts.
5. User fails same drill 3 times → next assistant turn is a different phrase in a related area.

### Out of scope

- Multi-user support
- Voice authentication
- Persistent user profile / progress tracking (vocab SRS — separate plan)
- Local LLM fallback (server is already the bottleneck; out of scope)
- Web UI / Gradio (separate plan)
