# Lingua — Current Architecture (as of 2026-09-09)

This document describes what the system actually does today. It is the baseline before any new design work. Read this first if you're new to the codebase.

## High-level goal

A voice-first Mandarin Chinese tutor. The user speaks into a microphone; the system:

1. Transcribes their speech (ASR)
2. Sends the transcript + conversation history to an LLM
3. Plays the LLM's response through the speakers (TTS)

The loop runs continuously until Ctrl+C.

## Components

### 1. Audio capture (`src/lingua/audio_loop.py`)

`stream_audio_chunks(sample_rate=16000, channels=1)` is an async generator that yields raw PCM int16 little-endian chunks (~5KB each, ~160ms of audio). It opens a `sounddevice.InputStream` and uses a callback queue pattern to read from the mic without blocking the event loop.

**Notable detail:** captures at the device's native sample rate (typically 44.1kHz) and resamples to 16kHz via `np.interp` before yielding. Without this resample, PortAudio produces silent output on Windows.

### 2. ASR (`src/lingua/asr.py`)

`stream_transcribe(chunks, vs)` connects to VoiceStudio's WebSocket at `ws://127.0.0.1:3900/v1/audio/transcriptions/stream?sr=16000&format=webm_opus`. Sends audio as WebM/Opus containers (encoded incrementally by `PcmToOpusEncoder`).

**Notable detail:** the server expects WebM, but the `?format=webm_opus` query param is *advisory* — the server still saves partial chunks as `.webm` and tries to decode. **We send only chunks >= 8KB accumulated**, otherwise the server fails EBML parsing.

Yields a stream of dicts: `{"type": "status" | "partial" | "final" | "error", "text": "...", ...}`.

### 3. VAD (`src/lingua/agent/vad.py`)

`VoiceActivityDetector(energy_threshold=0.01)` is **defined but unused**. The harness uses raw silence detection from `audio_loop.stream_audio_chunks` instead, which breaks silence after 1.5s of background noise. This is one source of the "phantom turns" bug from earlier debugging.

### 4. Tutor (`src/lingua/tutor.py`)

`MandarinTutor` is the LLM client.

- `_ask_llm(user_message)` — synchronous, single-shot. Calls MiniMax OpenAI-compatible API at `https://api.minimax.io/v1/text/chatcompletion_v2`.
- `stream_response(messages, on_sentence=None)` — streaming variant. Iterates SSE chunks, detects sentence boundaries (`。！？.!?\n`), fires `on_sentence` callback. At end, if no delimiter was hit, emits the buffered remainder as a final sentence.

System prompt: `src/lingua/prompts/tutor.py` — `SYSTEM_PROMPT`. Instructs the LLM to respond in JSON with `{"type", "text", "expected", "feedback"}` schema.

Memory: `src/lingua/agent/memory.py` — `ConversationMemory` persists turns to `data/conversation.json`. **Heals** the first turn on load if it was stored as `role="user"` (legacy bug from earlier code).

### 5. TTS (`src/lingua/voice_studio.py`)

`synthesize(text, voice_profile, speed=1.0)` POSTs to VoiceStudio's `/v1/audio/speech` endpoint. **Critical**: `response_format="pcm"` (raw int16 LE, 24kHz). Returns `SynthesisResult(audio_bytes, duration_ms, sample_rate=24000)`.

Harness plays the bytes via `sd.play(np.frombuffer(audio_bytes, dtype=np.int16), samplerate=24000)`. The `sample_rate` parameter is essential — PCM at 24kHz played as 16kHz produces a slow, deep, distorted voice (the bug we fixed).

Voice profiles in `src/lingua/config.py`: `voice_mandarin="8c53222c"`, `voice_english="demo0001"`.

### 6. Harness (`src/lingua/agent/harness.py`)

`VoiceAgentHarness` orchestrates everything. **This is the file that needs the most attention.**

```
async def run(self):
    while True:                              # ← one big loop
        capture_task = audio_capture()
        asr_task = asr_transcribe()
        await asyncio.gather(capture_task, asr_task)   # ← blocks until silence
        # (then synchronously)
        await self._process_transcript(...)
        # (then synchronously)
        sd.wait()   # ← blocks until tutor finishes speaking
```

The structure is a single `while True` loop with two big blocking points: `asyncio.gather` (waits for capture + ASR to finish, which happens after silence) and `sd.wait()` (waits for full TTS playback).

### 7. HUD (`src/lingua/hud/`)

`Hud` class renders a Rich `Live` display with 5 panels: microphone RMS, pipeline status (ASR/LLM/TTS), transcript (last 6 turns), log (last 20 events), header (uptime).

Driven by `EventBus` (thread-safe pub/sub) populated by harness events. `apply(event)` mutates internal state; `renderable()` rebuilds the layout each redraw.

### 8. CLI (`src/lingua/__main__.py`)

`main()` parses args (`--input N`, `--output M`, `--list-devices`), loads env from `.env` / `~/.lingua.env`, instantiates the harness + HUD, runs them.

### 9. Recorder (`src/lingua/recorder.py`)

`SessionRecorder` writes one JSON file per app run to `data/sessions/session_YYYYMMDD_HHMMSS.json`. Captures per-turn: ASR text, LLM response, parsed JSON, TTS per-sentence latency, pinyin display, anomaly flags.

## Module dependency map

```
                          ┌──────────────────────────────────────────────────┐
                          │                  __main__.py                    │
                          │       (CLI args, env load, VoiceStudio check)   │
                          └──────────────────────┬───────────────────────┘
                                                 │
                                                 ▼
                          ┌──────────────────────────────────────────────────┐
                          │           VoiceAgentHarness  (harness.py)        │
                          │  - run() loop                                    │
                          │  - _capture_audio / _transcribe_audio /          │
                          │    _process_transcript                            │
                          └─┬───────┬───────┬───────┬───────┬───────┬─────┬─┘
                            │       │       │       │       │       │     │
                            ▼       ▼       ▼       ▼       ▼       ▼     ▼
                       ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
                       │Tutor│ │ASR  │ │VAD  │ │Rout.│ │Audio│ │Hud+ │ │Rec. │
                       │     │ │     │ │     │ │     │ │Loop │ │Bus  │ │     │
                       └──┬──┘ └──┬──┘ └─────┘ └─────┘ └──┬──┘ └──┬──┘ └──┬──┘
                          │       │                    │       │       │
              ┌───────────┼───────┼────────────┐       │       │       │
              │           │       │            │       │       │       │
              ▼           ▼       │            │       │       │       │
       ┌─────────────┐ ┌─────────┴──┐         │       │       │       │
       │ VoiceStudio │ │PcmToOpus  │         │       │       │       │
       │ Client      │ │Encoder    │         │       │       │       │
       │ (TTS API)   │ │           │         │       │       │       │
       └─────────────┘ └────────────┘         │       │       │       │
              │           │                  │       │       │       │
              ▼           ▼                  ▼       ▼       ▼       ▼
       ┌──────────────────────────────────────────────────────────────┐
       │                     VoiceStudio server                       │
       │                 http://127.0.0.1:3900                        │
       │    /v1/audio/transcriptions/stream  (WebSocket ASR)         │
       │    /v1/audio/speech                  (POST TTS)              │
       └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
       ┌──────────────────────────────────────────────────────────────┐
       │                    MiniMax LLM API                           │
       │           https://api.minimax.io/v1/text                     │
       │                  model: MiniMax-M3                           │
       └──────────────────────────────────────────────────────────────┘
```

### Detailed import graph

```
__main__.py
  └── VoiceAgentHarness  (agent/harness.py)
        ├── MandarinTutor (tutor.py)
        │     ├── VoiceStudioClient (voice_studio.py)
        │     ├── ConversationMemory (agent/memory.py)
        │     └── SYSTEM_PROMPT (prompts/tutor.py)
        ├── VoiceStudioClient (ASR)
        ├── PcmToOpusEncoder + stream_transcribe (asr.py)
        ├── VoiceActivityDetector (agent/vad.py) — defined, unused
        ├── TurnRouter (agent/router.py) — used to classify ASR language
        ├── stream_audio_chunks (audio_loop.py)
        ├── EventBus + Hud (hud/)
        └── SessionRecorder (recorder.py)
```

## Data flow per turn

```
1. mic (44.1kHz PCM int16)
   ↓ stream_audio_chunks() resamples to 16kHz, yields ~5KB chunks
2. PcmToOpusEncoder → WebM/Opus
   ↓ buffered in stream_transcribe until >= 8KB
3. WebSocket → VoiceStudio faster-whisper → "final" event with text
   ↓
4. ASRFinalEvent → EventBus → HUD log + transcript
   ↓
5. _process_transcript():
   a. tutor.memory.add_turn("user", text)
   b. tutor.stream_response(messages) → SSE chunks, accumulates
   c. find_sentence_boundary(text) → fires per-sentence
   d. parse final JSON → get {type, text, expected, feedback}
   e. for each sentence: TTS via VoiceStudio /v1/audio/speech
   f. sd.play(audio) + sd.wait()
   g. tutor.memory.add_turn("assistant", full_text)
6. SessionRecorder writes the turn
7. HUD updates
8. Loop back to step 1
```

## File sizes (LOC)

```
src/lingua/
  agent/harness.py      406  ← candidate for refactor
  tutor.py              305
  audio_loop.py         296
  voice_studio.py       191
  asr.py                187
  __main__.py           130
  config.py             109
  recorder.py            92
  agent/vad.py           72  ← defined but unused
  agent/router.py        55
  tone_drill.py          57
  vocab_drill.py         48
  hud/display.py        168
  hud/bus.py             35
  hud/events.py          95
```

## External services

- **VoiceStudio** (`http://127.0.0.1:3900`) — local. Provides ASR (faster-whisper) and TTS (libopus).
- **MiniMax** (`https://api.minimax.io/v1/text`) — cloud LLM. Model `MiniMax-M3`.
- **MiniMax API key** stored in `.env` or `~/.lingua.env` as `MINIMAX_API_KEY`.

## Performance envelope (measured, see `bench_*.py`)

| Component | Latency |
|---|---|
| ASR (faster-whisper-large-v3) | 0.5-2s per turn |
| LLM (MiniMax-M3, streaming) | TTFB ~1.5s, total ~3s for short replies |
| TTS (VoiceStudio libopus) | **3.5s fixed + 80ms/char** — server-side bottleneck |
| sd.play + wait | 1-3s for typical response |
| End-to-end perceived | 6-8s for short turns, **12-18s** for multi-sentence |

## Known limitations observed in `data/sessions/`

From analysis of `session_20260909_181033.json` (20 turns, 7min46s):

1. **System repeats the same drill phrase** (`nǐ kàn guò nà běn shū ma`) regardless of user input. 8 consecutive turns of the user failing the same phrase, with the LLM offering it again each time.
2. **No recognition of user requests** — when user says "could you speak a bit slower", the LLM responds with text-only acknowledgment but actual TTS speed doesn't change.
3. **Language detection is single-label** — every turn is forced through the "drill" path. User speech in Portuguese/French/Romanian gets rejected with "That isn't Mandarin" instead of being engaged.
4. **No interruption** — user cannot stop the tutor mid-sentence. `sd.wait()` blocks the event loop until playback ends.
5. **Context window grows unbounded** — 30 turns of memory all get sent to LLM. Long sessions degrade response quality.
6. **TTS plays filler** — "Sure!", "That isn't Mandarin.", "Try again slowly" all get spoken individually, slowing perceived responsiveness.

## What the system *is* good at

- End-to-end pipeline works in the happy path.
- ASR is functional (when audio reaches it).
- HUD gives real-time visibility into pipeline state.
- Recorder produces structured logs that make post-mortem analysis tractable.
- Test coverage is decent (~80 tests passing).
- Latency is bounded; nothing hangs indefinitely.

## What the system is *not*

- Not a real conversation. It's a quiz loop.
- Not interruptible.
- Not context-aware across long sessions.
- Not robust to off-script user input (anything other than "I tried to say a phrase" gets rejected).
- Not pedagogically structured — no curriculum, no SRS, no progress tracking.

The next spec (`2026-09-09-conversational-harness.md`) proposes changes to address 1-4.
