# Feature 01 — Pronunciation Scoring

> Mandarin pronunciation scoring: learner audio → ground-truth pinyin/tones → score 0–100.

---

## Purpose

The pronunciation subsystem takes a learner's recorded audio plus an expected Mandarin
phrase (pinyin or hanzi), transcribes the audio with OpenAI Whisper, tokenises both
the expected phrase and the transcribed text into phoneme-style sequences with g2p,
aligns the two sequences via Levenshtein, and returns an integer score in [0, 100]
plus diagnostics. This is the core of the Pronunciation tab in the Gradio app.

**Out of scope** (see [Out of scope](#out-of-scope) below): cross-speaker voice conversion,
prosody/rhythm scoring, real-time streaming scoring, speaker diarisation, language ID.

---

## Data model

### `PronunciationResult` (proposed — currently the scorer returns a `dict`)

| Field | Type | Description |
|---|---|---|
| `score` | `int` (0–100) | Integer pronunciation score derived from `compute_phoneme_score()`. |
| `transcription` | `str` | Raw text Whisper heard (may be empty on error). |
| `expected_phonemes` | `list[str]` | Tokenised expected phrase. |
| `transcribed_phonemes` | `list[str]` | Tokenised Whisper transcription. |
| `alignment` | `list[tuple[int, str]]` | Per-position labels from `align_phonemes` (`MATCH`/`DELETE`/`INSERT`). |
| `error` | `str \| None` | `None` on success; populated on transcription or audio failure. |
| `model_name` | `str` | Whisper model used (for diagnostics). |
| `language` | `str` | Language hint passed to Whisper (`"zh"` for this app). |

**Current state:** `WhisperPhonemeScorer.score()` returns a plain `dict[str, Any]` —
no alignment, no model_name, no language. Migration target: replace the dict with a
`@dataclass PronunciationResult` so callers get static type checking and missing fields
are loud. Keep the dict shape for backward compat (callers in `ui/app.py` use
`result["score"]`, `result["transcription"]`, `result["error"]`).

### Input shape (caller → subsystem)

| Field | Type | Description |
|---|---|---|
| `audio` | `str` (path) | Path to a WAV/MP3/M4A file. Gradio provides the path from its `gr.Audio` component. |
| `expected_text` | `str` | Mandarin phrase the learner is attempting. Accepts either pinyin (`"nǐ hǎo"`) or hanzi (`"你好"`). |
| `expected_tones` | `list[int]` (proposed) | Optional tone sequence (`[3, 3]`). Currently ignored by the scorer; reserved for a future tone-aware scorer. |

The score path the user enters in the UI is `expected_text` only — no tones are passed.
Adding the `expected_tones` field would let us replace the `0.70` threshold in
`PronunciationConfig.scoring_threshold` with a tone-aware threshold later.

---

## Interaction map

| Trigger | Function | Inputs | Outputs | Side effects |
|---|---|---|---|---|
| Gradio **Score Pronunciation** button | `ui/app.py::score_pronunciation` (line 125) | `(audio: str, text: str)` | `str` (feedback message) | None (read-only). |
| (called by above) | `whisper_scoring.WhisperPhonemeScorer.__init__` (line 10) | `model_name="medium"`, `PronunciationConfig()` | `WhisperPhonemeScorer` instance | **Eagerly loads Whisper model** into RAM (~1.5 GB at "medium") — see bug P-NEW-2. |
| (called by above) | `whisper_scoring.WhisperPhonemeScorer.score` (line 64) | `(audio_path: str, target_text: str)` | `dict` (`score`, `transcription`, `expected_phonemes`, `transcribed_phonemes`, optional `error`) | Lazy g2p import per call (whisper_scoring.py:38). |
| (called by above) | `whisper_scoring.WhisperPhonemeScorer._transcribe` (line 45) | `audio_path: str` | `str \| None` | Whisper inference. |
| (called by above) | `whisper_scoring.WhisperPhonemeScorer._g2p` (line 28) | `text: str` | `list[str]` | Lazy g2p import. |
| (called by above) | `scorer.compute_phoneme_score` (scorer.py:22) | `(expected: list[str], actual: list[str])` | `float` (0.0–1.0) | None. |
| (called by above) | `scorer.align_phonemes` (scorer.py:31) | `(expected: list[str], actual: list[str])` | `list[tuple[int, str]]` | None. |

The `DefaultPhonemeAnalyzer.analyze` (scorer.py:90) path is the offline test path; it is
**not** currently wired into `WhisperPhonemeScorer.score` (which uses `_g2p` instead).
See review.md item P-NEW-4.

---

## External deps

| Dependency | Status | Role |
|---|---|---|
| `openai-whisper>=20231117` | **Hard dependency** (pyproject.toml:8) | Audio → text transcription. Loaded lazily in `WhisperPhonemeScorer._load_model`. |
| `g2p>=1.0` | **Optional**, behind `[asr]` extra (pyproject.toml:14) | Text → ARPAbet phoneme sequence. Currently imported lazily per call in both `scorer.py:91` and `whisper_scoring.py:37`; lazy import alone is *not* enough — see review.md P-NEW-5. |
| `pypinyin` (proposed) | **Not yet added** | Fallback when g2p is missing. Pure-python, lightweight, Mandarin-native. See `pinyin_baseline_investigation.md`. |

`edge-tts` and `scipy` are also hard deps (pyproject.toml:7,9) but are unrelated to
the pronunciation path.

---

## Testable contracts

Each contract is phrased as exactly one test assertion (see
`tests/pronunciation/test_scorer_contracts.py`).

### C-1.1 — Levenshtein identity
`levenshtein_distance(["n", "i3"], ["n", "i3"]) == 0`
Levenshtein distance of `["n", "i3"]` vs itself is 0.

### C-1.2 — `align_phonemes` same-length alignment
`len(align_phonemes(["a", "b"], ["a", "b"])) == len(expected)`
Alignment returns one entry per expected position when lengths match.

### C-1.3 — `DefaultPhonemeAnalyzer.analyze("你好")` returns non-empty token list
The current implementation:
- **with g2p installed**: calls `G2p()("你好")` and filters `" "`, `"_"`, `"EOS"`. The
  Kyubyong `g2p` library is English-trained; behaviour on CJK input is undefined and
  typically returns the input chars unchanged or with garbage tokens.
- **with g2p missing**: returns `list("你好")` → `["你", "好"]` (character-level fallback,
  see scorer.py:102).

The contract captures the documented *current* behaviour:
`assert isinstance(result, list) and len(result) > 0`. Anything stricter
(specific token shapes) is left for a future Mandarin-native analyser — see
`implementation_plan.md` step 3 (pypinyin fallback).

### C-1.4 — `WhisperPhonemeScorer` construction does NOT load a model (lazy)
After `__init__`, `scorer._model is None`. Currently the constructor calls
`self._load_model()` at line 18, which violates this contract. Fix is in
`implementation_plan.md` step 2.

### C-1.5 — `score()` returns dict with `score`, `recognized` (alias), `expected`
The contract asserts `result["score"]` is `int` in [0, 100] and that the dict carries
the canonical keys `transcription`, `expected_phonemes`, `transcribed_phonemes`. The
"`recognized`" alias referenced in the brief is satisfied via the `transcription` key —
the rename to `recognized` is a future-cleanup item, not part of C-1.5 (current callers
in `ui/app.py:136-137` use `result["transcription"]`).

### C-1.6 — `score()` never raises on missing audio file
`scorer.score("/nonexistent/audio.wav", "hello")` returns a dict with
`score == 0` and a non-empty `error` key. No exception propagates to the caller.

### C-1.7 — `model_name` default is `"base"` (was `"medium"`)
`WhisperPhonemeScorer().model_name == "base"`. The previous default `"medium"` loads
~1.5 GB at import time; `"base"` loads ~140 MB and is the correct default for the
bundled deck's small-vocabulary Mandarin tasks.

### C-1.8 — `language="zh"` passed to `model.transcribe()`
`scorer._model.transcribe` is called with `language="zh"` (in addition to the
existing `fp16=False`). Without this hint, Whisper tends to bias toward English
transcripts for short Mandarin utterances, making the Levenshtein comparison
meaningless for this app.

---

## Out of scope

- **Cross-speaker voice conversion** — no resynthesis / voice cloning pipeline.
- **Prosody / rhythm scoring** — we compare phoneme sequences, not durations or F0
  contours. Tone sandhi (e.g. `nǐ hǎo` → `[ní, hǎo]` in context) is **not** modelled —
  the expected phoneme sequence comes from the deck metadata's pinyin field, which
  already reflects citation tones. See `pinyin_baseline_investigation.md` §3.
- **Real-time streaming scoring** — Whisper operates on full audio files; we do not
  implement partial hypotheses.
- **Speaker diarisation** — handled by the Accent subsystem (`accent/detector.py`),
  not by pronunciation scoring.
- **Language identification** — language is fixed at `"zh"` (see C-1.8).
