# Feature 02 — Speech Synthesis (TTS)

> Text-to-speech synthesis for the Mandarin tutor's spoken replies and the
> "🔊 Play TTS" button in the Pronunciation tab.

---

## Purpose

The TTS subsystem turns a text string into a playable audio buffer. It powers:

- The Pronunciation tab's "🔊 Play TTS" button (`ui/app.py::play_tts`,
  line 142), where the learner types a phrase and hears it spoken aloud by a
  native Mandarin voice.
- The voice tutor's replies (planned — `voice_agent/` will call
  `synthesize_text` on tutor text and stream the result to LiveKit).

Two backends are supported:

| Backend | Status | Why |
|---|---|---|
| **`edge-tts`** (default) | Active | Cloud, no install, no model download, no PyTorch. Uses Microsoft neural voices via `edge_tts.communicate`. Works on Python 3.14. |
| **`coqui`** | Optional | Local, offline, requires the `TTS` package + ~2 GB model download. **Does not work on Python 3.14** (Coqui's PyTorch dependency drops Python 3.14 support). Code is kept as a lazy stub. |

The default is selected by `TTSConfig.backend` (`src/lingua/core/config.py`
line 35) which already reads `"edge-tts"`.

---

## Data model

### `SynthesisResult` (`src/lingua/tts/engine.py` line 8-12)

```python
@dataclass
class SynthesisResult:
    audio_bytes: bytes       # Full WAV file (RIFF header + PCM samples)
    sample_rate: int         # 24000 for both backends
    duration_seconds: float  # Computed by estimate_duration()
```

**Audio format:** WAV 24 kHz mono PCM. For `edge-tts`, this requires the
mock or a `scipy.io.wavfile.read`-compatible producer — Microsoft actually
streams MP3 by default; the `EdgeTTSModel` contract is documented as "bytes
that round-trip through `scipy.io.wavfile.read`" (see Caveats below).

### Input shape (caller → subsystem)

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Mandarin text (or any language `edge-tts` voices support). |
| `config` | `TTSConfig` (optional) | Overrides for backend/voice/sample_rate. Defaults via `TTSConfig()`. |

---

## Interaction map

| Trigger | Function | Inputs | Outputs | Side effects |
|---|---|---|---|---|
| Gradio **🔊 Play TTS** button | `ui/app.py::play_tts` (line 142) | `text: str` | `str` (WAV file path or error message) | Writes a tempfile at `tempfile.gettempdir()/lingua_tts_output.wav` and returns the path; Gradio plays it. |
| (called by above) | `tts/engine.py::synthesize_text` (line 37) | `text: str`, optional `config` | `SynthesisResult` | Imports `EdgeTTSModel` on first call. |
| (called by above) | `tts/edge.py::EdgeTTSModel.synthesize` | `text: str` | `SynthesisResult` | Opens a websocket to `wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1`, accumulates audio chunks. |

---

## External deps

| Package | Version | Why |
|---|---|---|
| `edge-tts` | 7.2.8 (installed) | Microsoft neural TTS. Async, no model download. Requires Python 3.7+. |
| `scipy` | installed | `scipy.io.wavfile` reads test fixtures and decodes `audio_bytes` for C-2.2. |
| `TTS` (Coqui) | **NOT installed** | Optional backend. Drops Python 3.14 support — see C-2.6. |

---

## Testable contracts (C-2.x)

| ID | Contract |
|---|---|
| **C-2.1** | `EdgeTTSModel().synthesize("你好")` returns a `SynthesisResult` whose `audio_bytes` is non-empty. |
| **C-2.2** | `SynthesisResult.audio_bytes` is decodable by `scipy.io.wavfile.read` and yields `sample_count > 1000`. This catches the double-WAV-wrap bug — see review.md. |
| **C-2.3** | `EdgeTTSModel()` constructed with no args has `voice == "zh-CN-XiaoxiaoNeural"` (the default from `TTSConfig`). |
| **C-2.4** | `EdgeTTSModel().synthesize("")` returns a `SynthesisResult` with `audio_bytes == b""` — no exception. |
| **C-2.5** | `estimate_duration(wav_bytes, sample_rate) == sample_count / sample_rate` — must handle the 44-byte WAV header. |
| **C-2.6** | Importing `from src.lingua.tts.coqui import CoquiTTSModel` does **not** raise `ImportError` even when the `TTS` package is missing. The import is wrapped in `try/except ImportError` at module level; `COQUI_AVAILABLE` flag is set accordingly. |
| **C-2.7** | The UI adapter (`play_tts`) returns `None` (or `""`) on backend failure — **never** a string starting with `"Error"` or `"TTS error"`. *(Documented contract; see review.md for why the current code violates it.)* |

---

## Caveats

1. **Edge-tts output format is actually MP3, not WAV.** The Microsoft Read
   Aloud endpoint serves `audio/mpeg` regardless of what we ask for. We
   accumulate the raw MP3 bytes into `audio_bytes`; downstream consumers
   that try to play them through `scipy.io.wavfile.read` will fail in
   production (but succeed under our mocked tests, which inject WAV
   bytes). A future migration to a true WAV-producing backend (or an
   ffmpeg-backed post-processor) is tracked separately.

2. **`estimate_duration` accepts both raw PCM and WAV-wrapped PCM.** It
   detects the 44-byte RIFF header and skips it. See C-2.5.

3. **`CoquiTTSModel` is a stub on Python 3.14.** `TTS` cannot be installed
   (PyTorch does not publish wheels for 3.14). The class can still be
   imported — `synthesize()` raises `NotImplementedError` if
   `COQUI_AVAILABLE is False`.

---

## Out of scope

- Voice cloning
- Real-time streaming synthesis (edge-tts is request-response, not streaming)
- Prosody / emotion control beyond edge-tts defaults (`rate`, `volume`,
  `pitch` constructor kwargs are accepted but not surfaced to the UI)
- SSML markup
- Audio post-processing (normalisation, silence trimming, MP3→WAV transcoding)
