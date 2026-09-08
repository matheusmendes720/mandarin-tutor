# F2 — Code Review: Speech Synthesis Subsystem (Pre-Rewrite Snapshot)

> **Scope note.** This review audits the legacy `lingua.tts` package as it
> exists on disk today, before the edge-tts migration defined in
> `spec.md`. The bug table below motivates the rewrite.

## Snapshot

| File | Lines | Status |
|---|---|---|
| `src/lingua/tts/engine.py` | 72 | Broken signature (`text_or_model2`); rewrites to text-first with backend selection. |
| `src/lingua/tts/coqui.py` | 80 | Eagerly imports `TTS.api.TTS` at module load on Python 3.14 (PyTorch wheel missing); hardcodes `language="en"`; broken. |
| `tests/tts/test_engine.py` | 78 | Passes — tests the broken legacy signature; updated in this PR. |
| `tests/tts/test_coqui.py` | 107 | All tests guarded by `pytest.mark.skipif(not TTS_AVAILABLE)`; pass (skipped) on this machine. |

## Bug Table

| ID | Location | Severity | Symptom | Root cause | Fix | Contract |
|---|---|---|---|---|---|---|
| **B-2.1** | `src/lingua/tts/coqui.py` line 60 (`CoquiTTSModel.synthesize`) | **High** | Every Mandarin phrase (`"你好"`, `"谢谢"`) is synthesised with an English accent. The Coqui XTTS v2 multilingual model is asked to speak Chinese with `language="en"`. | The `language` parameter is hardcoded to `"en"` (line 60). The model's multilingual capability is wasted. | Pass the language through from the constructor (defaulting to `"zh"` from `TTSConfig`). Or remove the parameter and let XTTS auto-detect. | **C-2.1** (verifies audio output exists) + future C-2.8 (zh language is honoured) |
| **B-2.2** | `src/lingua/tts/coqui.py` lines 1-7 (module top) | **High** | `from src.lingua.tts.coqui import CoquiTTSModel` succeeds on Python 3.13/3.12 where `TTS` installs, but on **Python 3.14.7** (this machine) the import of `TTS.api.TTS` itself crashes because PyTorch does not publish wheels for 3.14. The whole `tts` subsystem becomes unusable. | Top-level eager import. The class body references `_CoquiTTS` directly without a fallback. | Wrap the import in `try/except ImportError`; expose `COQUI_AVAILABLE = False`; `synthesize()` raises `NotImplementedError` if unavailable. Module load never fails. | **C-2.6** |
| **B-2.3** | `src/lingua/tts/engine.py` lines 22-71 (`synthesize_text`) | **High** | The first positional parameter is named `text_or_model`. Callers can't pass `text` without inspecting the function body. The docstring on line 47 advertises a `model=` keyword that does not exist — the only way to pass a model is as the first positional arg. There are two `@overload` stubs that disagree on the signature. | Function designed to accept both `(text, model=)` and `(model, text)` calling conventions; the second is undocumented and detected via `hasattr(text_or_model, "synthesize")` (line 57) which is brittle. | Single canonical signature: `synthesize_text(text, *, config=None, model=None) -> SynthesisResult`. Model selection is driven by `TTSConfig.backend`. Drop the `@overload` hacks. | covered by API redesign (see spec.md §Interaction map) |
| **B-2.4** | `src/lingua/ui/app.py::play_tts` lines 154-155 | **High** | Audible noise when playing synthesised audio. `wav_data = np.frombuffer(result.audio_bytes, dtype=np.int16)` reads the bytes as raw int16 PCM, but `result.audio_bytes` is already a full WAV file (44-byte RIFF header followed by PCM). The 22 samples that came from the RIFF header become garbage waveform data; `wavfile.write` then re-emits a new WAV containing that garbage. | Double-wrap: backend returns WAV → `play_tts` treats WAV as raw PCM → re-wraps as WAV. | Either (a) make `synthesize_text` return raw PCM and have `play_tts` write it with `scipy.io.wavfile.write`, or (b) keep WAV output and have `play_tts` write `result.audio_bytes` to disk unchanged. This PR picks (b) and documents the UI fix as a follow-up. | **C-2.2** |
| **B-2.5** | `src/lingua/tts/engine.py::estimate_duration` lines 15-18 | **Medium** | `estimate_duration(wav_bytes, 22050)` overcounts because it does not skip the 44-byte WAV header. For a real WAV file of 1 second (44 header + 22050*2 PCM = 44144 bytes), `frames = 44144 // 2 = 22072` and the function reports `1.0010` seconds instead of `1.0`. `duration_seconds` propagated through `SynthesisResult` is therefore wrong whenever the input is WAV. | The function was written assuming raw PCM only, but all backends (`coqui` line 76, future `edge-tts`) produce WAV. | Detect the 44-byte RIFF/WAVE header and skip it before counting frames. | **C-2.5** |
| **B-2.6** | `src/lingua/ui/app.py::play_tts` line 158 | **Medium** | On TTS failure, `play_tts` returns the string `"TTS error: {e}"`. Gradio's `gr.Audio` component receives a string instead of a file path and surfaces it as an unreadable error in the player. The user can't tell what went wrong. | Exception handler returns a string where the contract requires a path or `None`. | Return `None` on failure (per **C-2.7**); log the exception to stderr so debugging is still possible. | **C-2.7** |
| **B-2.7** | `src/lingua/tts/coqui.py::CoquiTTSModel.synthesize` lines 49-79 (entire method body) | **Medium** | On Python 3.14 where `TTS` cannot be imported, `CoquiTTSModel.synthesize` is never even reachable — the module fails to import (B-2.2). When the import succeeds on 3.13, the method works but always produces English output (B-2.1). Either way the class is unusable for Mandarin. | Compounding bugs: hardcoded language + broken install path. | Mark the class as the "optional alternate" backend in spec.md. New `synthesize()` raises `NotImplementedError` if `COQUI_AVAILABLE is False`. The default path uses `edge-tts`. | **C-2.6** |
| **B-2.8** | `src/lingua/core/config.py::TTSConfig` lines 33-37 | **Low** | `TTSConfig.sample_rate = 22050` but `CoquiTTSModel` produces audio at 24000 Hz (`XTTS_SAMPLE_RATE = 24000` in `coqui.py` line 10). The configured sample rate is never read by the model; the consumer assumes the value matches what the backend actually emitted. | Magic-number drift between the config default and the model constant. | Either (a) drive the sample rate from the config and let each model read it, or (b) document that `sample_rate` is reserved for future use and remove it from the dataclass. This PR keeps the field for forward compatibility. | (no test — non-functional) |
| **B-2.9** | `src/lingua/tts/engine.py::estimate_duration` lines 15-18 | **Low** | No guard against `sample_rate == 0` → `ZeroDivisionError`. Not exploitable today (callers always pass positive ints) but a future caller that hasn't initialised the config could crash. | Defensive programming gap. | Add `if sample_rate <= 0: return 0.0`. Out of scope for this PR — tracked separately. | (no test — defensive) |
| **B-2.10** | `src/lingua/tts/__init__.py` (entire file) | **Cosmetic** | Module docstring is fine; but the package exposes nothing — `from lingua.tts import synthesize_text` requires knowing the submodule path. | No `__all__` re-exports. | Optional cleanup: add `from .engine import SynthesisResult, synthesize_text, estimate_duration` re-exports. Not part of this PR. | n/a |

## Net Effect

- **Two** high-severity bugs (B-2.1, B-2.2, B-2.3) are fixed in this PR —
  Coqui gets a graceful stub, the engine gets a clean signature, and
  edge-tts becomes the default backend.
- **One** high-severity bug (B-2.4 — the double-WAV wrap in `play_tts`)
  is **documented here and the contract C-2.2 added**, but the UI-side
  fix is left as a one-line follow-up to keep this PR scoped to `tts/`.
- **One** medium-severity bug (B-2.5 — `estimate_duration` header) is
  fixed by detecting the RIFF/WAVE magic.
- **One** medium-severity bug (B-2.6 — error string returns) is
  documented and the contract C-2.7 is reserved; the UI fix is the
  same follow-up as B-2.4.
- **Three** low / cosmetic issues (B-2.8, B-2.9, B-2.10) are tracked
  but not addressed in this PR.

## Verification of Review

```bash
# Reproduce B-2.2 (Coqui crashes import on Python 3.14)
python -c "import sys; sys.version_info >= (3,14) and __import__('importlib').import_module('TTS')" 2>&1
# Expect: ModuleNotFoundError: No module named 'TTS'

# Reproduce B-2.4 (double-wrap in play_tts — read WAV bytes as int16)
python -c "
import numpy as np
# Fake WAV: 44-byte header + 4 bytes of PCM
fake_wav = b'RIFF' + b'\\x24\\x00\\x00\\x00' + b'WAVE' + b'fmt ' + b'\\x00'*16 + b'data' + b'\\x04\\x00\\x00\\x00' + b'\\x00\\x00\\x00\\x00'
samples = np.frombuffer(fake_wav, dtype=np.int16)
print('frames read:', len(samples))  # 24 (22 of header + 2 of PCM) — the 22 header frames are garbage
"

# Reproduce B-2.5 (estimate_duration overcounts on WAV)
python -c "
from src.lingua.tts.engine import estimate_duration
# 1-second WAV at 22050 Hz: 44 byte header + 22050*2 PCM = 44144 bytes
fake = b'RIFF' + b'\\x00'*4 + b'WAVE' + b'fmt ' + b'\\x00'*16 + b'data' + b'\\x00'*4 + b'\\x00' * (22050 * 2)
print('reported duration:', estimate_duration(fake, 22050))  # ~1.001, not 1.0
"

# Reproduce B-2.1 (Coqui hardcodes English) — see coqui.py line 60
grep -n 'language=' src/lingua/tts/coqui.py
# Expect: wav = self.model.synthesize(text, language=\"en\")
```

After the rewrite, all four reproductions are no longer valid:

- B-2.2 reproduction fails — `from src.lingua.tts.coqui import CoquiTTSModel`
  succeeds on Python 3.14 (try/except ImportError).
- B-2.4 reproduction is moot — `estimate_duration` is updated to skip
  the header (C-2.5), and `audio_bytes` will be the full WAV.
- B-2.5 reproduction fails — `estimate_duration(fake_wav, 22050)` returns
  `1.0` (C-2.5).
- B-2.1 reproduction is moot — the hardcoded `language="en"` is replaced
  with a configurable parameter, and the default backend is now
  `edge-tts` which does not have this bug.
