# F5 — Code Review: Accent Subsystem (Pre-Rewrite Snapshot)

> **Scope note.** This review audits the legacy `lingua.accent` package as it exists
> on disk today. The new F5 brief is "linear pronunciation correction" — the bug
> table below motivates the rewrite defined in `spec.md`.

## Snapshot

| File | Lines | Status |
|---|---|---|
| `src/lingua/accent/detector.py` | 203 | Broken (FunASR path); will become a shim |
| `src/lingua/accent/analyzer.py` | 67 | Dead code; will be deleted |
| `src/lingua/accent/__init__.py` | 1 | Empty; will be repopulated |
| `tests/accent/test_detector.py` | 171 | Tests the broken FunASR path; replaced |
| `tests/accent/test_analyzer.py` | 56 | Tests the dead-code path; deleted with `analyzer.py` |

## Bug Table

| ID | Location | Severity | Symptom | Root cause | Fix | Contract |
|---|---|---|---|---|---|---|
| **B-5.1** | `accent/detector.py::FunASRAccentDetector.detect` (lines 99-127) | **High** | `UnboundLocalError: local variable 'dialect' referenced before assignment` whenever the FunASR model returns an empty result list `[]` or a non-dict first element. | `dialect` is only assigned inside the `if result and len(result) > 0` block, then referenced later when building `AccentDetectionResult`. When the block is skipped (empty / malformed), `dialect` is unbound. | Add `dialect: str \| None = None` initialiser before the `if`. In the new F5 cut, the entire `FunASRAccentDetector` class is removed; the bug disappears. | **C-5.4** |
| **B-5.2** | `accent/detector.py::_analyze_dialect` (line 161) | **High** | Returns the literal string `"Mandarin"` for any input whose first character is in the CJK Unified Ideographs range — even if the audio is English with embedded Chinese characters, or random Han characters in non-Mandarin languages (Japanese, Korean Hanja). The hardcoded claim was never implementable; the comment on line 149 admits "Real accent detection would require acoustic analysis". | The function does no acoustic analysis; it is a Unicode-range heuristic masquerading as dialect classification. The literal `"Mandarin"` is hardcoded. | Remove the function. In the new F5 cut, there is no "dialect" field at all. | (no contract — feature removed) |
| **B-5.3** | `accent/detector.py` vs `accent/analyzer.py` (whole files) | **High** | Two functions named `detect_accent` exist in the package. `accent.detector.detect_accent(audio_path: str) -> dict` returns FunASR-style dict. `accent.analyzer.detect_accent(audio_bytes, model, config) -> AccentResult` returns a dataclass with `language="en"` hardcoded. Importing one shadows the other depending on `from lingua.accent import …` ordering. | Two parallel implementations were developed without consolidation. Neither works without `funasr` + `DiarizationModel`. | Delete `accent/analyzer.py`. Rewrite `accent/detector.py` as a shim re-exporting `from lingua.accent.checker`. | **C-5.2** (single public symbol `check_accent` in `lingua.accent` namespace) |
| **B-5.4** | `accent/analyzer.py::detect_accent` (line 39) | **Medium** | Returns `language="en"` regardless of input audio. The voice-agent tab's accent indicator is therefore a permanent lie. | The function never inspects the audio. It calls `model.segment(...)`, discards the segments (only the count is used), and hardcodes `"en"`. | Delete `analyzer.py`. New F5 has no concept of detected language — the language is **given** by `AccentCheckRequest.language` and the score is per-syllable, not per-language. | (no contract — feature removed) |
| **B-5.5** | `accent/detector.py::FunASRAccentDetector._ensure_model_loaded` (lines 35-69) | **Medium** | Module-level `ACCENT_MODEL_DIR = os.environ.get(...)` at line 5 plus eager `from funasr import AutoModel` inside the method. Importing `lingua.accent.detector` itself succeeds, but instantiating `FunASRAccentDetector()` is fine; first call to `.detect()` triggers a model download from ModelScope (~1 GB). Forcing CI to skip with `@skipIf` is the only path. | The detector was designed for a model-server deployment, not the offline desktop use case Lingua targets. | Drop the FunASR class. Reuse `lingua.pronunciation.whisper_scoring.WhisperPhonemeScorer` (F1 already lazy-loads Whisper). | (covered by F1 C-1.3: `Construction does NOT load a model`) |
| **B-5.6** | `accent/detector.py::_analyze_dialect` (line 154) | **Low** | CJK Unified Ideographs range is hardcoded as `"一" <= char <= "鿿"` (U+4E00..U+9FFF). This excludes Extension A/B/CJK compatibility ideographs. The check is also wrong for strings of *pure punctuation* (returns `None`, which then propagates as "unknown dialect"). | The Unicode range was copied without verification; the function is irrelevant after B-5.2's fix. | Removed with the function. | n/a |
| **B-5.7** | `accent/analyzer.py::detect_accent_from_file` (line 46) | **Low** | Calls the *other* `detect_accent` (FunASR one) but catches **everything** with `except Exception:`, returning `{"language": "unknown", ...}`. This swallows genuine bugs (e.g. permission errors on the audio file) and presents them as "language unknown". | The blanket `except` is a debuggability anti-pattern. | File deleted. New F5 surfaces errors via `AccentCheckResult.error` field with a discriminator (`"missing_audio:user"`, `"missing_audio:reference"`, `"transcription_failed"`). | **C-5.4**, **C-5.5** |
| **B-5.8** | `core/config.py::AccentConfig.supported_languages` (line 54-56) | **Low** | Field exists but is unused. No code in the package reads it. The original F5 plan to "transcribe + return language confidence" never consumed this list. | Speculative configuration. | Drop the field from `AccentConfig` in the rewrite, or document it as reserved for F7+. | (no test — non-functional) |
| **B-5.9** | `accent/detector.py::detect_accent` (lines 176-202) | **Low** | Convenience function has no `language` parameter, no `model` parameter — every call instantiates a fresh `FunASRAccentDetector()` and triggers `_ensure_model_loaded()`. Two consecutive calls from the same UI render → two model loads, ~2 GB RAM peak. | The function is a leaky wrapper. | Removed with the FunASR class. The new `AccentChecker` is a singleton via `core.registry.get_accent_checker()`. | (covered by X5 lazy-init) |
| **B-5.10** | `tests/accent/test_detector.py::test_graceful_import_error` (lines 90-103) | **Low** | The "test" does nothing — it imports `from funasr import AutoModel` inside a try block and asserts nothing. It exists only to silence the test runner. | Test was a placeholder left when the original implementer couldn't reproduce the ImportError reliably. | Deleted with the file. Replaced by `test_checker_contract.py` which uses `monkeypatch` to remove `pypinyin`/`whisper` cleanly. | (no test — removed) |
| **B-5.11** | `accent/detector.py` top of file (line 1 docstring) | **Cosmetic** | Docstring says "FunASR-based accent detection for Mandarin Chinese". After the rewrite, the module will be a 5-line shim, not an implementation. The docstring becomes misleading. | Stale. | Replace with a one-line docstring: "Backward-compat shim. See `lingua.accent.checker` for the implementation." | n/a |

## Net Effect

- **Three** high-severity bugs (B-5.1, B-5.2, B-5.3) and **three** medium/low bugs
  (B-5.5, B-5.7, B-5.9) are eliminated by the file-level deletion of `analyzer.py`
  and the rewrite of `detector.py`.
- **No** behaviour from the legacy `detect_accent` is preserved — the function had
  no working implementation (it raised on empty input, hardcoded "Mandarin",
  required an uninstalled model, and shadowed a sibling function that always
  returned `language="en"`). F5's new surface area is `check_accent(req) -> result`
  with **five** named contracts (C-5.1 through C-5.5).
- **No** code outside `lingua.accent/` calls `detect_accent` today (verified by
  `grep -rn "from lingua.accent" src/ tests/` — no production callers; only the
  legacy tests). The shim is therefore purely defensive and can be deleted in a
  later cleanup pass if desired.

## Verification of Review

```bash
# Reproduce B-5.1 (UnboundLocalError on empty FunASR result)
python -c "
from unittest.mock import MagicMock, patch
from lingua.accent.detector import FunASRAccentDetector
d = FunASRAccentDetector()
d._model = MagicMock(); d._model.generate.return_value = []
try:
    d.detect('x.wav')
except UnboundLocalError as e:
    print('Reproduced:', e)
"

# Reproduce B-5.4 (analyzer.py hardcodes 'en')
python -c "
from unittest.mock import MagicMock
from lingua.accent.analyzer import detect_accent
r = detect_accent(b'fake', MagicMock())
assert r.language == 'en'
print('Reproduced: language hardcoded to en')
"

# Reproduce B-5.3 (two detect_accent symbols)
python -c "
from lingua.accent.detector import detect_accent as a
from lingua.accent.analyzer import detect_accent as b
print('a is b:', a is b)  # False — two parallel implementations
"
```

After the rewrite, all three reproductions fail to reproduce (the code no longer
exists).
