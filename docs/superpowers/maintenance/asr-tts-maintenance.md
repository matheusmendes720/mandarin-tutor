# ASR/TTS Voice Pipeline Maintenance Guide

Target: Agent fixing bugs in `src/lingua/asr.py`, `src/lingua/audio_loop.py`, `src/lingua/voice_studio.py`.

> See [Current Architecture](./specs/2026-09-09-current-architecture.md) for overview.

## The Format Dance

```
User speaks (mic)
    │
    ▼
audio_loop.stream_audio_chunks()
    │ 44.1kHz → 16kHz (resample)
    ▼
asr.PcmToOpusEncoder
    │ PCM int16 → WebM/Opus
    ▼
VoiceStudio WebSocket ASR
    │ returns transcript
    ▼
tutor.stream_response()
    │ LLM generates text
    ▼
voice_studio.synthesize()
    │ text → PCM 24kHz int16
    ▼
sd.play(audio, samplerate=24000)
```

## Why Each Format Is Needed

| Format | Location | Why |
|--------|----------|-----|
| PCM int16 44.1kHz | `audio_loop.py` L82-84 | Mic captures at native rate (Windows hardware) |
| PCM int16 16kHz | `audio_loop.py` L156-163 | ASR model expects 16kHz |
| WebM/Opus | `asr.py` L35-85 | VoiceStudio WebSocket requires container |
| PCM int16 24kHz | `voice_studio.py` L48 | TTS returns 24kHz PCM |
| `sd.play(..., 24000)` | `harness.py` L369 | Must match TTS sample rate |

**Critical:** Playing 24kHz audio at 16kHz produces slow, deep, distorted voice.

## Critical Bugs Fixed

### Bug D: WebM Partial Chunks

**Problem:** Server failed with EBML parsing error on small chunks.

**Location:** `asr.py` L136-146

**Fix:** Buffer until >= 8KB before sending:

```python
SEND_THRESHOLD = 8192
webm_buffer = b""

async for chunk in chunks:
    webm = encoder.feed(chunk)
    webm_buffer += webm
    if len(webm_buffer) >= SEND_THRESHOLD:
        await ws.send(webm_buffer)  # Only send complete chunks
        webm_buffer = b""
```

### Bug: PCM int16 vs MP3

**Problem:** TTS returns raw PCM but playback code assumed WAV/MP3.

**Location:** `voice_studio.py` returns `SynthesisResult(audio_bytes, duration_ms, sample_rate=24000)`

**Fix:** `harness.py` L368-370:

```python
audio_arr = np.frombuffer(result.audio_bytes, dtype=np.int16)
sd.play(audio_arr, samplerate=result.sample_rate)  # 24000 Hz
```

### Bug: 16kHz vs 24kHz (Pitch)

**Problem:** Sample rate mismatch caused slow playback.

**Location:** `harness.py` L369

**Fix:** Always use `result.sample_rate` from TTS response, never hardcode.

### Bug: Event Type Parsing

**Problem:** Server sends different event shapes; code didn't handle all.

**Location:** `asr.py` L162-187

**Fix:** Handle each type explicitly:

```python
msg_type = data.get("type", "")

if msg_type == "session.started":
    yield {"type": "status", "text": "Session started"}
elif msg_type == "partial":
    yield {"type": "partial", "text": data.get("text", "")}
elif msg_type == "final":
    yield {"type": "final", "text": data.get("text", "")}
elif msg_type == "error":
    yield {"type": "error", "text": data.get("message", "Unknown error")}
```

## Latency Bottlenecks (Measured)

| Component | Latency | Source |
|-----------|---------|--------|
| ASR (faster-whisper-large-v3) | 0.5-2s | Architecture doc |
| LLM (MiniMax-M3) TTFB | ~1.5s | Architecture doc |
| LLM total | ~3s | Architecture doc |
| TTS (server) | **3.5s fixed + 80ms/char** | Fixed server cost |
| Playback | 1-3s | Audio duration |
| **End-to-end** | 6-8s short, 12-18s long | Architecture doc |

**Key insight:** TTS is the bottleneck — 3.5s server overhead before any audio generated.

## How to Test Without Live Server

### Mock Fixtures Pattern

```python
# tests/asr/test_stream_transcribe.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    # Simulate server returning final transcript
    ws.__aenter__ = AsyncMock(return_value=ws)
    ws.__aexit__ = AsyncMock(return_value=None)
    ws.send = AsyncMock()
    ws.recv = AsyncMock(return_value='{"type": "final", "text": "你好"}')
    return ws

async def test_transcribe_with_mock(mock_websocket):
    with patch("websockets.connect", return_value=mock_websocket):
        # ... test stream_transcribe behavior
```

### VoiceStudio Mock

```python
# For TTS testing
class MockVoiceStudioClient:
    def synthesize(self, text, profile_id, engine, speed):
        # Return fake PCM
        return SynthesisResult(
            audio_bytes=b"\x00" * 24000,  # 1 second
            duration_ms=1000,
            sample_rate=24000
        )
```

### Audio Loop Mock

```python
# For capture testing
async def mock_audio_chunks():
    yield b"\x00" * 1600  # 50ms of silence
    yield b""  # sentinel
```

## Key Files

| File | LOC | Purpose |
|------|-----|---------|
| `src/lingua/asr.py` | 187 | WebSocket streaming ASR |
| `src/lingua/audio_loop.py` | 296 | Mic capture, resample, RMS |
| `src/lingua/voice_studio.py` | 191 | TTS client |
| `src/lingua/harness.py` | 406 | Orchestrates all three |

## Common Issues

### "VoiceStudio not reachable" despite server running

Check `voice_studio.py` L178-185 — 3-second timeout may be too short under load. Fix: bump to 5s.

### Silent audio output

Usually sample rate mismatch — verify `sd.play(arr, samplerate=result.sample_rate)` not hardcoded.

### ASR returns empty transcript

Check WebM buffer size — too-small chunks cause server parse failures. Verify `SEND_THRESHOLD = 8192`.
