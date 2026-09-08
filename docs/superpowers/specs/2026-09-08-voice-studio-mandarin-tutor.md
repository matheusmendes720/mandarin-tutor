# VoiceStudio Mandarin Tutor — Specification

> **For agentic workers:** After spec approval, invoke `superpowers:writing-plans` to produce the implementation plan.

## 1. Concept & Vision

A voice-first Mandarin Chinese tutor that speaks to you, listens to you, and corrects you — entirely through audio. No web UI, no typing. You talk, it talks back, it grades your pronunciation and tone, it drills you on vocabulary you keep getting wrong, and it builds sentences from words you know. Think audio-only Duolingo but with an LLM that actually understands what you're trying to say.

**Audio stack only:** VoiceStudio handles TTS (voice output) and ASR (speech-to-text). The LLM drives conversation and tutoring logic. All output is spoken; all input is spoken.

**Interface:** A single CLI command `python -m lingua` that opens a voice session and talks to you.

---

## 2. System Architecture

```
User speaking
    │
    │  [mic recording → WAV]
    ▼
VoiceStudio ASR  (/dub/upload → /dub/transcribe-stream)
    │
    │  transcribed text
    ▼
MandarinTutor LLM (OpenAI-compatible / Ollama / custom)
    │
    │  tutoring decision + spoken response
    ▼
VoiceStudio TTS  (/generate)
    │
    │  audio
    ▼
Speaker / headphones
```

### Components

| Module | Responsibility | Location |
|---|---|---|
| `VoiceStudioClient` | HTTP client for all VoiceStudio API calls | `src/lingua/voice_studio.py` |
| `MandarinTutor` | LLM-driven conversation + tutoring logic | `src/lingua/tutor.py` |
| `AudioLoop` | Record → ASR → TTS → playback cycle | `src/lingua/audio_loop.py` |
| `ToneDrill` | Detect tone errors, play reference, re-drill | `src/lingua/tone_drill.py` |
| `VocabDrill` | FSRS-powered vocab practice via voice | `src/lingua/vocab_drill.py` |
| `CLI` | Single-command entry point | `src/lingua/__main__.py` |

### Data Flow

1. **Audio capture** — raw WAV from mic, sent to VoiceStudio `/clean-audio` (Demucs isolation), then `/dub/upload` for ASR
2. **ASR** — VoiceStudio SSE stream returns transcribed Mandarin text
3. **LLM decision** — Tutor agent receives transcription + conversation history, decides: respond conversationally, trigger tone drill, trigger vocab drill, or correct pronunciation
4. **TTS** — Tutor's response text sent to VoiceStudio `/generate` with appropriate voice profile, audio returned
5. **Playback** — audio played to user through speakers/headphones
6. **FSRS update** — after vocab drill turns, card intervals/ease updated in local JSON store

---

## 3. VoiceStudio API Integration

### ASR Pipeline (Conversational Turn)

```
POST /dub/upload  (multipart: audio file)
  → { job_id: string }

GET /dub/transcribe-stream/{job_id}?num_speakers=1  (SSE)
  → data: { text: "你说..." }
  → data: [DONE]
```

- Latency: ~1-2s per round-trip (upload + SSE stream)
- Audio format: WAV 16kHz mono (record via `sounddevice` or `pyaudio`)
- The `/clean-audio` endpoint can预处理 raw mic recordings before upload for better ASR accuracy

### TTS Pipeline

```
POST /generate
  multipart:
    text: "你说的很好，但声调有问题..."
    profile_id: "zh-female-tutor"    (pre-created voice profile)
    engine: "openai"                 (or "coqui", "elevenlabs")
    voice_id: "..."
```

- Voice profile must be created beforehand via `POST /profiles`
- Response: audio file bytes (MP3/WAV) — play directly via `pygame` or `sounddevice`

### Other Endpoints

- `POST /clean-audio` — Demucs vocal isolation, useful for noisy recordings
- `GET /profiles` — list available voice profiles
- `GET /engines/tts` — check which TTS engines are loaded/available

---

## 4. MandarinTutor LLM Agent

### Role

A conversational Mandarin tutor that:
- Speaks only Mandarin (configurable to include Portuguese explanations for beginners)
- Detects when the user makes tone errors and triggers targeted drill
- Detects when vocab is misused and drills it
- Builds sentences using only words the user already knows
- Adapts difficulty based on FSRS card performance

### Prompt Strategy

System prompt defines the tutor's persona and current lesson context. The LLM receives:
- User's transcribed speech
- Full conversation history
- Current FSRS due cards count
- Last pronunciation score (if any)

The LLM decides what to do: chat, drill tone, drill vocab, praise, correct.

### Example Decision Logic

```
if "tone error detected in ASR output":
    → trigger ToneDrill with the erroneous syllable
elif FSRS cards due:
    → ask user to make a sentence with a due word
elif user made semantic error:
    → correct and explain briefly
else:
    → continue natural conversation
```

### TTS Voice Profiles

| Profile ID | Use |
|---|---|
| `zh-tutor-female` | Normal tutoring responses |
| `zh-tutor-male` | Alternative voice |
| `zh-reference` | Tone drill reference pronunciation |

---

## 5. Tone Drill

Triggered when ASR output contains a tone error (Mandarin has 4 tones + neutral).

### Flow

```
1. LLM detects tone error → extracts the syllable + correct tone
2. TTS plays: "请听: ma1 (first tone)"
3. TTS plays: "请跟我读: ma1"
4. User speaks the syllable
5. ASR → check if tone is correct
6. If correct: praise + return to conversation
   If wrong: TTS plays "再听一次", repeat from step 2
7. After 3 failures: TTS plays explanation of mouth shape/position
```

### Tone Detection

ASR returns pinyin with tone numbers (e.g., `ma1`, `ma2`, `ma3`, `ma4`). Extract the tone marker from the transcribed pinyin and compare to expected.

---

## 6. Vocab Drill (FSRS)

Vocabulary is managed by the existing `vocab/scheduler.py` (FSRS algorithm). Each card has:
- `front`: Chinese word/phrase
- `back`: Portuguese translation
- `pinyin`: pronunciation guide
- `ease_factor`, `interval_days`, `repetitions`, `due_date`

### Voice Vocab Flow

```
1. Tutor asks user to make a sentence with word X
2. User speaks a sentence
3. ASR → LLM checks semantic correctness (not just pronunciation)
4. Pronunciation scored separately by ASR confidence or g2p alignment
5. FSRS card updated based on result
6. Next due card or return to conversation
```

---

## 7. CLI Interface

Single command:

```bash
python -m lingua
```

Or with options:

```bash
python -m lingua --tutor-level beginner  # Portuguese explanations on
python -m lingua --profile zh-tutor-female
python -m lingua --llm-provider ollama     # use local Ollama
python -m lingua --llm-url http://localhost:11434
```

On launch:
- Check VoiceStudio connectivity (`GET /model/status`)
- Connect to LLM provider
- Begin audio loop immediately — no menus, no typing

Exit: say "再见" or press Ctrl+C

---

## 8. Configuration

All config via environment variables + optional `lingua.toml`:

```toml
[voicestudio]
url = "http://127.0.0.1:3900"
profile_id = "zh-tutor-female"
reference_profile_id = "zh-reference"
engine = "openai"   # or "coqui", "elevenlabs"

[llm]
provider = "openai"   # or "ollama", "lmstudio"
url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
api_key = "${OPENAI_API_KEY}"

[audio]
sample_rate = 16000
channels = 1
chunk_duration_ms = 100

[vocab]
store_path = "data/vocab.json"
```

---

## 9. FSRS Scheduler

Existing `vocab/scheduler.py` implements FSRS. State is a JSON file at `data/vocab.json`.

Card record:
```json
{
  "id": "uuid",
  "front": "你好",
  "back": "olá / tudo bem",
  "pinyin": "nǐ hǎo",
  "ease_factor": 2.5,
  "interval_days": 1,
  "repetitions": 0,
  "due_date": "2026-09-08",
  "last_review": null
}
```

---

## 10. Error Handling

| Scenario | Behavior |
|---|---|
| VoiceStudio unreachable | TTS plays "语音服务不可用" (TTS service unavailable), exit |
| LLM unreachable | TTS plays "语言模型不可用", retry 3x then exit |
| ASR returns empty | TTS plays "我没听清，请再说一次" |
| Mic permission denied | TTS plays "麦克风不可用", exit |
| No due vocab cards | Normal conversation mode |

---

## 11. Project Structure (to be created)

```
src/lingua/
├── __init__.py
├── __main__.py          # CLI entry point
├── voice_studio.py       # VoiceStudio HTTP client (ASR + TTS)
├── tutor.py              # MandarinTutor LLM agent
├── audio_loop.py         # Record → ASR → LLM → TTS → playback
├── tone_drill.py         # Tone training loop
├── vocab_drill.py        # FSRS vocab drill via voice
├── config.py             # Config dataclasses
└── vocab/
    ├── __init__.py
    ├── scheduler.py      # FSRS implementation
    └── store.py         # JSON card store

data/                     # Runtime data (gitignored)
├── vocab.json
└── sessions/

tests/
├── test_voice_studio.py
├── test_tutor.py
├── test_tone_drill.py
└── test_vocab_drill.py
```

---

## 12. Dependencies

```
sounddevice / pyaudio     # Audio capture
requests                   # HTTP client for VoiceStudio
openai / ollama           # LLM clients
pygame / sounddevice      # Audio playback
pytest / pytest-asyncio   # Testing
```

No Gradio. No Whisper (ASR is VoiceStudio's job). No FunASR (accent analysis deferred).

---

## 13. Acceptance Criteria

- [ ] `python -m lingua` starts a voice session with no menus
- [ ] VoiceStudio ASR transcribes Mandarin speech correctly
- [ ] VoiceStudio TTS speaks Mandarin responses
- [ ] Tutor LLM responds contextually (not a static script)
- [ ] Tone drill triggers on tone errors
- [ ] Vocab drill works through FSRS due cards
- [ ] Ctrl+C or "再见" exits cleanly
- [ ] All config via env vars / lingua.toml (no hardcoding)
- [ ] Tests cover core logic with mocked VoiceStudio + LLM
