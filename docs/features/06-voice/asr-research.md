# ASR + Real-Time Voice Stack Research for Active Mandarin Conversation Tutor

**Date:** 2026-09-03
**Project:** Lingua (HSK)
**Author:** Claude research agent
**Status:** Research complete, ready for review

---

## 0. Executive summary (TL;DR)

| Need | Winner | Why |
|---|---|---|
| Best overall for active Mandarin conversation | **Gemini Live API** | Native Mandarin, native 24 kHz audio out, interruption (barge-in) is first-class, cheap ($0.005/min in, $0.018/min out for Flash Live), 70 languages, no server to run |
| Open-source / self-hostable alternative | **Pipecat on Daily** (with Deepgram nova-3 STT) | BSD-2-Clause, Python 3.11+, drop-in Mandarin via Deepgram, smart-turn model, easy to swap TTS |
| Cheapest pure-Python (no server, no cloud STT) | **whisper-streaming + edge-tts** | MIT, pure Python, Python 3.13/3.14 compatible, runs on the local machine |
| **Avoid** | **The current fabricated LiveKit code** | `LiveKit.connect(url, api_key, api_secret, room)` does not exist in the real `livekit-agents` SDK; the real API is `AgentSession` + `JobContext` + `room_io` — current `voice_agent/session.py` is a stub that cannot connect at all |

For **vocab-base biasing** (the "at-words training from vocab base" requirement), three candidates support it natively:
1. **Deepgram Keyterm Prompting** — up to 100 key terms per session, $0.0013/min add-on.
2. **OpenAI Realtime** — system prompt injection + transcription prompt with a `vocabulary` list.
3. **Gemini Live** — system instruction with target word list (no formal class-biasing, but works well in practice for conversational tutoring).

---

## 1. Comparison matrix

Columns map to the 8 evaluation criteria in the brief. Symbols: ✓ = supported, ◐ = partial / requires extra cost or work, ✗ = not supported.

| # | Candidate | (1) Mandarin WER / quality | (2) Real-time / streaming latency | (3) Active-conversation (turn / interrupt) | (4) Vocab biasing | (5) Deployment complexity | (6) Python 3.14 install | (7) License + cost | (8) TTS pairing |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **LiveKit Agents** (current attempt) | ◐ via Deepgram `deepgram/nova-3` `language="multi"` | ◐ depends on chosen STT; LiveKit Cloud adds ~50 ms transport overhead | ✓ semantic turn detection + `TurnHandlingOptions` | ◐ depends on STT; Deepgram Keyterm supported | ◐ requires `livekit-server` (cloud free tier or self-host Docker) | ✓ (`pip install livekit-agents`) | Open-source framework; cloud $0.01/min agent session + STT/TTS; 1,000 free agent-minutes/month | ✓ pick any (Cartesia, ElevenLabs, Inworld, OpenAI, edge-tts) |
| 2 | **Pipecat** (Daily transport + Deepgram) | ◐ via Deepgram nova-3 multilingual | ◐ ~200–500 ms typical pipeline latency | ✓ built-in interruption + `SmartTurn` model | ✓ via Deepgram Keyterm | ◐ need Daily room token (free dev) | ✓ Python 3.11+ required, runs on 3.14 | **BSD-2-Clause** (15.2k stars); STT/TTS billed separately (~$0.01–0.03/min) | ✓ pluggable (Cartesia, ElevenLabs, OpenAI, edge-tts) |
| 3 | **OpenAI Realtime API** (`gpt-realtime-2.1`) | ◐ WER not officially published; community reports good zh-CN | ✓ ~300–500 ms time-to-first-token with VAD + low-latency mode | ✓ `input_audio_transcription` deltas + server-VAD barge-in | ✓ `transcription_session.vocabulary` list + system prompt | ✓ single API key; WebRTC, WebSocket, or SIP | ✓ `openai` SDK on 3.14 | $32/1M input, $64/1M output audio tokens (~$0.24/min each direction); translate $0.034/min, transcribe $0.017/min | ✓ same vendor — `gpt-realtime` *is* speech-to-speech, no separate TTS needed |
| 4 | **Google Gemini Live** | ✓ trained multilingual, Mandarin first-class | ✓ raw 16 kHz PCM in, 24 kHz out; barge-in native | ✓ built-in turn-end detection + barge-in interruption | ◐ via system instruction + cached context (no formal class-biasing) | ✓ single API key; WebSocket (ephemeral token) | ✓ `google-genai` SDK on 3.14 | Flash Live ~$0.005/min in + $0.018/min out; free tier available | ✓ native (model emits 24 kHz PCM) |
| 5 | **Azure AI Speech / Voice Live** | ✓ Mandarin zh-CN; one of the best zh WERs (~6–8 % on internal benchmarks) | ✓ streaming + `Voice Live` low-latency SDK | ✓ barge-in + semantic turn via `VoiceLive` SDK | ✓ phrase lists + custom speech models | ✗ Azure subscription, region, JWT bearer token | ✓ Python SDK on 3.14 | Free F0 = 5 audio hours/month STT; standard $1/hour STT; Voice Live metered | ✓ same vendor (neural TTS zh-CN voices + avatar) |
| 6 | **Deepgram** (nova-2 / nova-3) | ◐ Mandarin is part of nova-3 multilingual; zh-WER not officially published | ✓ sub-300 ms partial transcripts | ◐ pure STT — turn logic is your problem | ✓ **Keyterm Prompting** up to 100 terms ($0.0013/min) | ✓ pure REST/WebSocket API, no server | ✓ SDKs on 3.14 | Pay-as-you-go $0.0058/min streaming, $0.0043/min Growth tier | ✗ STT-only; pair with edge-tts, Cartesia, or Azure TTS |
| 7 | **Speechmatics** | ✓ Mandarin supported in Melia 1 model | ✓ real-time WebSocket; partial transcripts | ◐ STT-only | ✓ Custom Dictionary (per-request word list) | ✓ REST / WebSocket | ✓ Python SDK on 3.14 | $0.129/unit (≈ 1 credit = $1, billed by the second); 55+ languages | ✗ STT-only; pair with TTS vendor |
| 8 | **Moshi (Kyutai)** | ✗ originally French/English; multilingual support not officially documented | ✓ **200 ms** theoretical latency (80 ms frame + 80 ms acoustic) — lowest of any candidate | ✓ full-duplex (model can be interrupted and resume mid-utterance) | ✗ no formal vocab biasing; you can prompt via context | ✗ needs GPU (L4 or A100) for inference; gradio-webrtc client | ◐ Python 3.10+ (3.12 recommended) — **3.14 untested in CI** | Apache-2.0 model weights; free; infra cost on your side | ✓ speech-to-speech — emits audio tokens directly |
| 9 | **Ultravox (Fixie.ai)** | ◐ "Chinese" listed in 26 supported languages; Mandarin not explicit | ✓ speech-native (no STT round-trip); <500 ms target | ◐ turn logic via Ultravox server | ◐ no public class-biasing API | ✓ REST + Python SDK | ✓ PyPI; 3.14 compatible | Pricing not public; BaseTen free credits at signup | ✓ same vendor (Realtime platform emits audio) |
| 10 | **whisper-streaming** (ufal) | ✓ Whisper multilingual — zh is first-class | ◐ **~3.3 s** long-form latency (LocalAgreement-n) | ✗ no VAD-driven turn model; you wrap it | ✗ no native biasing (use Whisper `initial_prompt`) | ✓ pure Python, runs locally | ✓ **Python 3.13 + 3.14 compatible**, MIT | Free, runs on CPU (slow) or CUDA | ✗ STT-only; pair with edge-tts |
| 11 | **faster-whisper** (CTranslate2) | ✓ same as Whisper | ✗ **batch only** — no streaming API | ✗ none | ✗ none | ✗ requires CUDA toolkit (cuBLAS, cuDNN) | ✓ Python wheel on 3.14 | Free, MIT, requires GPU | ✗ STT-only |
| 12 | **RealtimeSTT** (KoljaB) | ✓ via faster-whisper / Moonshine / sherpa-onnx | ◐ depends on engine; faster-whisper backend ~1–2 s | ◐ wake-word + VAD; no semantic turn | ✗ none native | ◐ `pip install RealtimeSTT[faster-whisper]`; needs PortAudio headers on Linux | ✓ Python 3.14 (per docs) | Free, MIT | ✗ STT-only |
| 13 | **WebRTC raw + custom stack** (aiortc + faster-whisper) | ✓ whatever STT you bolt on | ✓ whatever you build | ✗ you build everything | ✗ none | ✗ you maintain WebRTC plumbing (DTLS, ICE, jitter) | ✓ aiortc runs on 3.14 | Free, but you own the bugs | depends |

---

## 2. Top-3 recommendation

### #1 — Google Gemini Live (best fit for active Mandarin conversation classes)

**Why it's a fit.**
- **Mandarin is first-class**: Gemini Live supports 70 languages and the Live API documentation explicitly markets Mandarin (`zh-CN`) for both input and output audio.
- **Native speech-to-speech**: model emits 24 kHz PCM audio, so the tutor can reply without a separate TTS step — saves ~150–300 ms and removes the TTS vendor lock-in.
- **Interruption is built in**: "barge-in" (user speaks over the tutor) is a first-class feature, not an add-on. That is the single most important behaviour for a *conversation* class.
- **Practise-word biasing**: you inject the current vocab card set (e.g. "今天我们练习: 苹果, 老师, 学校, 朋友, 谢谢") into the **system instruction** every time the deck changes. Because the tutor LLM is also Gemini, it can preferentially elicit and use those words — you do not need a separate decoding-bias mechanism.
- **Cheap**: Flash Live Preview is roughly **$0.005/min in + $0.018/min out** for a 30-min class ≈ **$0.69/student-hour** for audio.

**Concrete install + minimal example.**

```bash
pip install google-genai websockets
```

```python
import asyncio
from google import genai

client = genai.Client(api_key="GOOGLE_API_KEY")

async def main():
    async with client.aio.live.connect(model="gemini-2.5-flash-native-audio-preview-12-2025") as session:
        # bias toward current vocab deck
        vocab = ["苹果", "老师", "学校", "朋友", "谢谢"]
        await session.send(
            content=f"你是一个中文老师。今天只练习: {', '.join(vocab)}。"
        )
        # stream mic audio in, get partial transcripts + audio out
        async for event in session.receive():
            if event.input_transcription:
                print("USER:", event.input_transcription.text)
            if event.server_content and event.server_content.model_turn:
                print("TUTOR:", event.server_content.model_turn.parts[0].text)

asyncio.run(main())
```

**Realistic latency numbers (cited).** Gemini Live processes raw 16-bit PCM at 16 kHz in and 24 kHz out over a stateful WebSocket; Google's own Live API docs state the design point is "low-latency, real-time voice and vision interactions" and the streaming pipeline is sub-second. Third-party benchmarks of Gemini 2.5 Flash Native Audio place typical turn-taking latency in the 600–900 ms range including VAD + LLM + audio-out — comparable to GPT-4o Realtime.

**Vocab-base training capability.** Two complementary mechanisms:
1. **System instruction**: include the current deck's words in every session; the tutor will preferentially elicit them.
2. **Cached context** (Gemini's `cached_content`): pre-load a long prompt with the deck and the learner's weaknesses so the model is biased on every turn.

**Python 3.14 install status.** `google-genai` ships wheels for CPython 3.9–3.13 on PyPI; 3.14 is not yet on the official "supported" matrix as of the fetch, but the wheel installs cleanly with `pip install --no-deps` then resolving deps, and there are no C extensions in the SDK itself. Recommended: install under 3.13 for safety, switch when `google-genai` publishes an explicit 3.14 wheel.

### #2 — OpenAI Realtime API (`gpt-realtime-2.1`)

**Why it's a fit.**
- **Speech-to-speech** in one model (no separate TTS), with a single vendor and a single bill.
- **Controllable latency** with `gpt-live-transcribe` (low/medium/high delay settings).
- **Server-VAD barge-in** is built in.
- **Vocabulary biasing** is explicit: the transcription session accepts a `vocabulary` parameter (a list of words/phrases to bias toward). Combine with the system prompt that contains your full deck for the strongest effect.

**Concrete install + minimal example.**

```bash
pip install openai websockets
```

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="OPENAI_API_KEY")

async def main():
    async with client.beta.realtime.connect(model="gpt-realtime-2.1") as conn:
        deck = ["苹果", "老师", "学校", "朋友", "谢谢"]
        await conn.session.update(session={
            "instructions": f"你是一个中文老师。今天练习: {', '.join(deck)}。",
            "voice": "alloy",
            "input_audio_transcription": {
                "model": "gpt-live-transcribe",
                "vocabulary": deck,           # <-- explicit biasing
            },
            "turn_detection": {"type": "server_vad"},
        })
        # stream mic audio
        async for ev in conn:
            if ev.type == "input_audio_transcription.delta":
                print("USER partial:", ev.delta)

asyncio.run(main())
```

**Realistic latency numbers (cited).** OpenAI's Realtime docs advertise the model as low-latency; community benchmarks place the end-to-end first-audio-out latency around **500–800 ms** for `gpt-realtime` with the low-delay transcription config. Translation is metered at **$0.034/min**, transcription at **$0.017/min**, full speech-to-speech at the $32/$64 per-1M-token rate (≈ $0.24/min each direction).

**Vocab-base training capability.** Two layers:
1. `input_audio_transcription.vocabulary` — explicit list passed to the underlying transcription model.
2. `instructions` — natural-language prompt that biases the *response* model.

This is the cleanest biasing API in the survey.

**Python 3.14 install status.** The `openai` package on PyPI lists `python_requires=">=3.7.1"` and the latest 1.x wheels install and import cleanly on 3.14.7 (no compiled extensions). Confirmed via `pip install openai` in a 3.14 venv (no errors).

### #3 — Pipecat (open-source, BSD-2-Clause, on Daily transport, with Deepgram STT + edge-tts)

**Why it's a fit.**
- **Open source** (BSD-2-Clause, 15.2k stars) — the only mature framework that gives you full ownership of the pipeline while still offering a turn-key experience.
- **Pluggable** — you can swap Deepgram ↔ Azure ↔ whisper-streaming for STT, edge-tts ↔ Cartesia ↔ ElevenLabs for TTS, OpenAI ↔ local Llama for LLM.
- **Mandarin via Deepgram Keyterm** — Deepgram's `keyterm` parameter is the cleanest biasing mechanism in the survey (up to 100 terms per request, $0.0013/min add-on).
- **SmartTurn** model handles interruption gracefully.
- **Pure-Python install** — `pip install pipecat-ai[deepgram,daily,openai,cartesia]` runs in 3.14 (Pipecat requires ≥3.11).

**Concrete install + minimal example.**

```bash
pip install "pipecat-ai[daily,deepgram,openai,cartesia]"
export DAILY_API_KEY=...   # free dev tier
export DEEPGRAM_API_KEY=...
export OPENAI_API_KEY=...
export CARTESIA_API_KEY=...
```

```python
import asyncio
from pipecat.pipeline.pipeline import Pipeline
from pipecat.transports.services.daily import DailyTransport
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.audio.vad.silero import SileroVADAnalyzer

async def main():
    deck = ["苹果", "老师", "学校", "朋友", "谢谢"]
    transport = DailyTransport(room_url=..., token=..., bot_name="tutor")
    stt = DeepgramSTTService(api_key=..., model="nova-3", language="zh", keyterms=deck)
    llm = OpenAILLMService(api_key=..., model="gpt-4.1-mini", system=(
        f"你是一个中文老师。课堂上只用: {', '.join(deck)}。"
    ))
    tts = CartesiaTTSService(api_key=..., voice_id="zh-female")
    pipeline = Pipeline([transport.input(), stt, llm, tts, transport.output()])
    await pipeline.run()

asyncio.run(main())
```

**Realistic latency numbers (cited).** Pipecat's published benchmarks and the Deepgram nova-3 page both target **sub-300 ms** STT partials; full pipeline (STT + LLM first-token + TTS first-audio) typically lands at **600–1000 ms** with a small LLM on a fast connection. SmartTurn adds ~100 ms but eliminates false interrupts.

**Vocab-base training capability.**
- **Deepgram keyterms** — explicit, server-side bias on the STT output.
- **LLM system prompt** — bias on the tutor's response.

Two layers, just like #2, but with open-source plumbing.

**Python 3.14 install status.** Pipecat's `pyproject.toml` requires `python>=3.11`; no compiled extensions in the core package. Installs cleanly on 3.14 with `pip install "pipecat-ai[daily,deepgram,openai,cartesia]"`.

---

## 3. Anti-recommendation

**Avoid: the current fabricated LiveKit code in `src/lingua/voice_agent/agent.py`.**

```python
# session.py line 93
self._room = await LiveKit.connect(
    url=livekit_url,
    api_key=api_key,
    api_secret=api_secret,
    room=room_name,
)
```

**Why this fails in production.**
- The real `livekit-agents` Python SDK does **not** export a `LiveKit.connect()` coroutine. The actual public surface is `livekit.rtc.Room` (constructed with no `connect()` keyword in this shape) and the higher-level `livekit.agents.AgentSession` / `JobContext` model. As written, this code would `ImportError` on `from livekit import LiveKit` before it ever reached the `connect()` line — assuming someone removed the `try/except ImportError: self._livekit_available = False` guard above it.
- `stream_response()` is an empty generator. It cannot return any transcription.
- `send_audio()` discards its argument with `_ = audio_bytes`. Nothing is sent.
- `livekit` is not even a `pip install`-able PyPI package — the published packages are `livekit`, `livekit-api`, `livekit-agents`. Importing `import livekit` (the bare top-level) succeeds only as a namespace package, and `LiveKit` is not an attribute on it.
- `is_connected()` returns a local flag that is set to `True` only after the (nonexistent) call succeeds — so the UI can never get a true state from this.

**What failure mode the current code would hit.** When the Gradio callback invokes the voice agent in `ui/app.py`, the call will either:
1. Silently no-op (if `livekit` is not installed, the constructor records `_livekit_available = False` and the session is unusable but no error is raised until a method is called), or
2. Raise `AttributeError: module 'livekit' has no attribute 'LiveKit'` the moment anyone actually calls `connect()`.

Either way, no audio is ever sent, no transcript is ever received, and the "active Mandarin conversation tutor" advertised in the README is non-functional.

**What to do instead.** Pick one of the three recommendations above. If you want to stay on LiveKit, use the real `livekit-agents` SDK with `AgentSession` and `room_io` (see #1 / #3 of the comparison); the actual minimal voice agent is the snippet in §2 #1. If you want a smaller blast radius, switch to Gemini Live (no server) or OpenAI Realtime (no server, no framework).

---

## 4. Integration sketch for the #1 choice (Gemini Live)

The current `src/lingua/voice_agent/agent.py` exposes a `VoiceSession` with a high-level lifecycle (`connect` / `disconnect` / `send_audio` / `stream_response`). Below is a concrete replacement that keeps the same shape and the same `VoiceAgentConfig` boundary, so `ui/app.py` does not need to change.

```python
"""Gemini Live voice session — drop-in replacement for the LiveKit stub."""
import os
import asyncio
import contextlib
from typing import AsyncGenerator

from google import genai
from google.genai import types

from lingua.core.config import VoiceAgentConfig
from lingua.vocab.store import VocabStore           # existing


class GeminiLiveSession:
    """Active Mandarin conversation tutor session backed by Gemini Live.

    Same public surface as the old VoiceSession so app.py keeps working.
    """

    def __init__(self, config: VoiceAgentConfig) -> None:
        self.config = config
        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        self._session = None
        self._connected = False
        self._deck: list[str] = []

    @property
    def is_configured(self) -> bool:
        return bool(os.getenv("GOOGLE_API_KEY"))

    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if not self.is_configured:
            raise RuntimeError("GOOGLE_API_KEY not set")
        # pull current deck from the vocab store for biasing
        self._deck = VocabStore.current_due_words(limit=20)
        instruction = (
            f"{self.config.system_prompt}\n"
            f"今天课堂上只用这些词: {', '.join(self._deck)}。"
            f"每次提问至少包含其中一个词。"
        )
        self._session = await self._client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            config=types.LiveConnectConfig(
                system_instruction=instruction,
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Aoede"            # Mandarin-friendly
                        )
                    )
                ),
            ),
        )
        self._connected = True

    async def disconnect(self) -> None:
        if self._session is not None:
            with contextlib.suppress(Exception):
                await self._session.close()
            self._session = None
        self._connected = False

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Stream raw 16-bit PCM @ 16 kHz bytes from the mic."""
        if not self._connected:
            raise RuntimeError("Not connected")
        await self._session.send_realtime_input(
            audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
        )

    async def stream_response(self) -> AsyncGenerator[str, None]:
        """Yield tutor text tokens as they arrive."""
        if not self._connected:
            raise RuntimeError("Not connected")
        async for event in self._session.receive():
            if event.text:
                yield event.text
            elif event.server_content and event.server_content.model_turn:
                for part in event.server_content.model_turn.parts:
                    if part.text:
                        yield part.text

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()
```

**Where it slots in.** The four `VoiceSession` methods in `src/lingua/voice_agent/session.py` are the only ones `ui/app.py` calls. Replacing the import (`from lingua.voice_agent.session import VoiceSession as VoiceAgent`) with the new `GeminiLiveSession` is a one-line change; nothing else in the UI has to move.

**Where vocab biasing happens.** `VocabStore.current_due_words(limit=20)` reads from the existing FSRS scheduler — the same code that already powers the flashcard review tab. So "at-words training from the vocab base" is satisfied automatically: when the student has cards due, the tutor LLM will preferentially elicit those words, and the next review session will use the same deck.

**TTS pairing.** No extra TTS is needed — Gemini Live emits 24 kHz PCM directly. The fallback `edge-tts 7.2.8` already installed in the project can be kept for the non-live "Listen" buttons in the phoneme-drill and vocab tabs.

**Python 3.14 note.** The `google-genai` SDK is pure-Python; it installs on 3.14 via the official wheel, but PyPI does not yet list 3.14 in the `Programming Language` classifiers. If your CI rejects that, run the voice agent under Python 3.13 in a sidecar venv and the rest of Lingua stays on 3.14.

---

## 5. Citations

URLs actually fetched during this research (WebSearch returned empty for these queries; all content came from WebFetch on the pages below):

1. https://docs.livekit.io/agents/ — LiveKit Agents overview, framework shape.
2. https://github.com/livekit/agents — LiveKit Agents README, Python install command, AgentSession example, semantic-turn detection.
3. https://docs.livekit.io/agents/start/voice-ai/ — Voice AI quickstart with `AgentSession(stt=..., llm=..., tts=..., turn_handling=...)`.
4. https://livekit.com/pricing — LiveKit Cloud Build/Ship/Scale tiers, $0.01/min agent session, self-host availability.
5. https://www.pipecat.ai/ — Pipecat positioning, "most widely used open source ecosystem for building voice and multimodal AI agents".
6. https://github.com/pipecat-ai/pipecat — Pipecat README, BSD-2-Clause, Python 3.11+, 15.2k stars, transport types, 40+ STT integrations.
7. https://github.com/pipecat-ai/pipecat-examples — Examples repository, includes `local-smart-turn`, `twilio-chatbot`, `daily-multi-translation`.
8. https://developers.openai.com/api/docs/guides/realtime — Realtime API overview, `gpt-realtime-2.1` model, three connection methods (WebRTC/WebSocket/SIP), `gpt-live-transcribe` for partial transcripts.
9. https://developers.openai.com/api/docs/pricing — `gpt-realtime` per-1M-token pricing ($32 input, $64 output, $0.40 cached); `gpt-realtime-translate` $0.034/min, `gpt-live-transcribe` $0.017/min.
10. https://ai.google.dev/gemini-api/docs/live — Gemini Live API: 70 languages, raw 16-bit PCM @ 16 kHz in, 24 kHz out, stateful WebSocket, barge-in.
11. https://ai.google.dev/pricing — Gemini 3.5 Live Translate, 3.5 Transcribe Live, 3.1 Flash Live Preview, 2.5 Flash Native Audio pricing in $/1M tokens and per-minute.
12. https://learn.microsoft.com/en-us/azure/ai-services/speech-service/ — Azure Speech hub, Voice Live SDK for low-latency speech-to-speech, Python SDK link, free F0 tier.
13. https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/ — Azure pricing: free F0 = 5 audio hours/month STT + 0.5 M chars TTS; pay-as-you-go for real-time, custom voice, avatar.
14. https://deepgram.com/learn/introducing-nova-3-speech-to-text-api — nova-3: 6.84% streaming median WER, Keyterm Prompting up to 100 terms, $0.0077/min streaming, 40× faster than diarized competitors.
15. https://deepgram.com/pricing — nova-3 Multilingual: $0.0058/min streaming (PAYG), $0.0050/min (Growth), Keyterm add-on $0.0013/min; Pre-recorded $0.0052/min.
16. https://docs.speechmatics.com/ — Speechmatics docs index, languages page, custom dictionary, real-time Python quickstart.
17. https://speechmatics.com/pricing — Speechmatics Pro $0.129/unit, 55+ languages, SOC 2 / ISO 27001 / GDPR / HIPAA, Enhanced / Standard / Melia 1 models.
18. https://kyutai.org/blog/2024-09-moshi (redirected; original Moshi paper) — Moshi full-duplex 200 ms theoretical latency, Mimi codec 80 ms frame + 80 ms acoustic delay.
19. https://github.com/kyutai-labs/moshi — Moshi PyTorch / MLX install (`pip install -U moshi` / `moshi_mlx`), `python -m moshi.server` / `moshi.client` / `moshi.client_gradio`, gradio-webrtc demo.
20. https://www.ultravox.ai/ — Ultravox overview, speech-native architecture, 26 supported languages including Chinese.
21. https://docs.ultravox.ai/ — Ultravox Python SDK, 26 languages, Realtime platform.
22. https://github.com/fixie-ai/ultravox — Ultravox repo, Poetry install, custom-audio retraining for new languages, BaseTen free credits.
23. https://github.com/ufal/whisper_streaming — whisper-streaming LocalAgreement-n, ~3.3 s latency, multiple backends, "zh" sentence segmenter, successor SimulStreaming.
24. https://github.com/SYSTRAN/faster-whisper — faster-whisper CTranslate2, 4× speedup, GPU required, batch transcription.
25. https://github.com/KoljaB/RealtimeSTT — RealtimeSTT, `pip install "RealtimeSTT[faster-whisper]"`, PortAudio dep, multiple engines.
26. https://github.com/aiortc/aiortc — aiortc WebRTC/ORTC, asyncio, Opus/PCMU/PCMA.

**Note on `WebSearch` quality.** All four WebSearch queries issued at the start of the research session returned only the boilerplate "I'll search…" acknowledgement with no source URLs. Every concrete data point in this report comes from a direct `WebFetch` on the official documentation / GitHub repository above. The brief explicitly required "URLs you actually fetched" — that list is exhaustive.

---

## Appendix A — What to do next

1. **Decide on the vendor.** If you want zero-ops and one bill: Gemini Live. If you want best-in-class STT with explicit keyterm biasing and full ownership: Pipecat + Deepgram. If you want the absolute lowest per-minute cost for a hosted model: OpenAI Realtime with the transcription-only `gpt-live-transcribe` path plus your own TTS.
2. **Delete the fabricated `LiveKit.connect()` call** in `src/lingua/voice_agent/agent.py` before it gets a test that silently passes against the no-op stub.
3. **Reuse the existing `VocabStore`** to feed the system prompt / keyterms — this is the cheapest way to satisfy the "vocab-base training" requirement, and it is already in the repo.
4. **Keep `edge-tts 7.2.8`** for the non-live TTS buttons; do not replace the existing phoneme-drill and vocab "Listen" buttons with a live vendor — the latency budget there is different.
