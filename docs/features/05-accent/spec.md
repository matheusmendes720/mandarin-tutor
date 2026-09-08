# F5 — Accent Analysis (Mandarin Pronunciation Correction)

> **Scope pivot (2026-09):** the original F5 brief ("Whisper transcription + per-segment
> confidence, no dialect") has been redefined by the user to
> **"linear checking per recording of user voice and active corrections"**. The new
> feature is **per-syllable pronunciation correction** against a reference Mandarin
> utterance, not language identification. The legacy `FunASRAccentDetector` path is
> dropped entirely.

## Purpose

A Mandarin learner records themselves saying a word or short phrase. The system
transcribes the recording with Whisper, splits the ground-truth text (`reference_text`)
into per-syllable units with their pinyin + tones, derives a per-syllable score from
Whisper's per-word confidence, and emits **active corrections** — short, actionable
natural-language hints (e.g. *"你的声调 3 听起来像 2 — 试着把声调升高"* / *"O seu tom 3
soa como 2 — tente levantar o pitch"*) — for any syllable whose score falls below the
threshold. The UI renders a colour-coded per-syllable diff via `diff_html`. No dialect
detection, no cross-language comparison, no prosody/rhythm scoring.

## Data Model

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AccentCheckRequest:
    """Inputs to one pronunciation check."""
    reference_audio: Path            # target audio (e.g. palavras-essenciais/audio/nihao.mp3)
    user_audio: Path                 # learner recording (WAV or MP3)
    reference_text: str              # ground truth, e.g. "你好"
    language: str = "zh"             # ISO 639-1; only "zh" is implemented in F5


@dataclass(frozen=True)
class SyllableScore:
    """Per-syllable scoring output."""
    text: str           # hanzi, e.g. "你"
    pinyin: str         # with tone diacritic, e.g. "nǐ"
    tone: int           # 1..5 (5 = neutral)
    score: float        # 0..100, per-syllable score
    confidence: float   # 0..1, ASR-derived confidence for this syllable


@dataclass(frozen=True)
class AccentCheckResult:
    """Aggregate result of one pronunciation check."""
    overall_score: float                        # 0..100
    syllables: list[SyllableScore] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)   # actionable feedback
    diff_html: str = ""                                    # colour-coded spans
    error: str | None = None                               # populated on soft failure
```

`SyllableScore.tone` is `5` for the neutral tone (轻声); `SyllableScore.score` is
**0..100** (UI-friendly, not 0..1 like `pronunciation.scorer.compute_phoneme_score`).

## Behaviour

1. **Reference syllable extraction.** Parse `reference_text` (e.g. `"你好"`) into
   characters. For each character, look up pinyin + tone using `pypinyin` (preferred,
   no extra install beyond `pip install pypinyin`). Fallback to `g2p` if `pypinyin`
   is unavailable. The number of `SyllableScore` rows equals the number of hanzi
   characters in `reference_text`.
2. **User audio transcription.** Run Whisper with `language="zh"` and
   `word_timestamps=True` (lazy-loaded via the existing F1 `WhisperPhonemeScorer`).
   Pull per-word text + per-word `probability` (Whisper's segment-level token
   probabilities). If transcription fails or returns `""`, return
   `AccentCheckResult(overall_score=0, error="transcription_failed")`.
3. **Per-syllable score.** For each reference syllable, find the corresponding
   transcribed word by character-index alignment. If the matched word is missing or
   has zero confidence, set `score=0`, `confidence=0`. Otherwise
   `score = round(confidence * 100, 1)`.
4. **Overall score.** `overall_score = mean(score_i for s in syllables)`.
5. **Active corrections.** For any `SyllableScore.score < threshold`
   (`PronunciationConfig.scoring_threshold`, default 70, expressed as 0..100),
   emit a feedback string. Tone-specific hints are produced when `score < 50`:
   - tone `1` → "Mantém o tom alto e sustentado" / "保持高平调"
   - tone `2` → "Sobe do meio para o topo" / "从中音升到高音"
   - tone `3` → "Desce e sobe (curva em V invertido)" / "降升调"
   - tone `4` → "Desce bruscamente" / "高降调"
   - tone `5` → "Curto e neutro" / "轻短调"
   Generic fallback when tone is unknown or score is between threshold and 50:
   `"Pratique a sílaba '{text}' ({pinyin}) separadamente."`
6. **diff_html.** For each syllable, emit a `<span>` with inline `style` reflecting
   `score`: green (`#2e7d32`) for `≥ 90`, amber (`#f9a825`) for `60..89`,
   red (`#c62828`) for `< 60`. Each span carries `data-syllable="{text}"` and
   `data-score="{score}"` so the UI can hover-tooltips.
7. **Failure modes.** Missing reference audio or missing user audio returns
   `AccentCheckResult(overall_score=0, error="missing_audio:reference"|"missing_audio:user")`
   — **never raises**.

## Interaction Map

| Trigger | Function | Inputs | Outputs | Side effects |
|---|---|---|---|---|
| User clicks "Check my pronunciation" in UI | `AccentChecker.check(req)` | `AccentCheckRequest` (paths + text) | `AccentCheckResult` | Lazy-loads Whisper model on first call (cached); reads both audio files |
| First call to `check()` | `AccentChecker._ensure_model()` | self | None | Downloads/loads Whisper into `self._model`; subsequent calls reuse it |
| App startup | `get_accent_checker()` (registry) | none | `AccentChecker` singleton | Constructed lazily; importing `lingua.accent.checker` loads no model |
| UI render | Gradio displays `result.diff_html` + `result.corrections` list | result | HTML/list shown | None |

## External Dependencies

| Package | Status | Notes |
|---|---|---|
| `openai-whisper` | **installed** (per F1) | Reuse F1 wrapper; lazy load; `language="zh"` |
| `edge-tts` | installed, unused here | F5 reads audio files; does not synthesize |
| `pypinyin` | **NOT installed** | Recommended install: `pip install pypinyin`. Tiny (~50 KB), pure Python, no model download |
| `g2p` | NOT installed | Fallback only — character-list fallback if `pypinyin` missing |
| `funasr` | NOT installed | **Dropped** — no code in `lingua.accent` may import `funasr` |

If `pypinyin` is missing the checker must still work: pinyin fields default to
`pinyin=text` (no diacritics) and `tone=5` (neutral); corrections fall back to
the generic message. The `pypinyin` install is recommended but not blocking.

## Testable Contracts

Each contract below is phrased so that **exactly one test** in
`tests/accent/test_checker_contract.py` asserts it.

- **C-5.1** Given `reference_text="你好"` and a user audio that transcribes exactly
  to `"你好"` with per-word confidence 1.0, `result.overall_score ≥ 95`.
- **C-5.2** Given `reference_text="你好"` and a user audio where the first syllable
  ("你") has per-word confidence `0.1` (mimicking wrong tone), then
  `result.syllables[0].score < 50` **AND** `len(result.corrections) >= 1` and
  `"你"` appears in the corrections.
- **C-5.3** `result.diff_html` contains exactly one `<span>` per reference syllable
  and each `<span>` has a `style` attribute whose colour matches the score bucket.
- **C-5.4** Empty user audio (zero-byte file) returns
  `AccentCheckResult(overall_score=0, ...)` with `error != None`; the call does not
  raise.
- **C-5.5** Missing reference audio path returns
  `AccentCheckResult(overall_score=0, error="missing_audio:reference")`; the call
  does not raise.

## Out of Scope

- Cross-language accent comparison (e.g. "English speaker learning Mandarin").
- Prosody, rhythm, or intonation scoring.
- Native-speaker corpus comparison.
- Dialect identification (Cantonese vs Mandarin vs Shanghainese, etc.).
- Real-time streaming analysis — single-shot file input only.
- Speaker diarization / multi-speaker recordings.

## Critical Files

**New (greenfield):**
- `src/lingua/accent/checker.py` — `AccentChecker` class, `check()` method, lazy
  Whisper load, per-syllable scoring, correction generation, `diff_html` rendering.
- `src/lingua/accent/models.py` — the three dataclasses above.
- `tests/accent/test_checker_contract.py` — C-5.1 through C-5.5 with mocked Whisper.

**Modified:**
- `src/lingua/accent/detector.py` — rewrite as a thin shim that re-exports
  `from lingua.accent.checker import AccentChecker, check_accent` so any leftover
  import path still works.
- `src/lingua/accent/__init__.py` — export `AccentChecker`, `check_accent`,
  `AccentCheckResult`, `SyllableScore`, `AccentCheckRequest`.
- `src/lingua/core/config.py` — `AccentConfig` already simplified in F0; just
  confirm `whisper_model`, `language`, `scoring_threshold` are present (the
  latter is on `PronunciationConfig`; we read it from there).

**Deleted:**
- `src/lingua/accent/analyzer.py` — dead-code legacy with hardcoded `language="en"`
  and no FunASR wiring. Replaced wholesale.
- `tests/accent/test_analyzer.py` — covers the deleted file.
- `tests/accent/test_detector.py` — covers the legacy FunASR path; the new
  `test_checker_contract.py` supersedes it.

## Reused Utilities (do not reinvent)

- `lingua.pronunciation.whisper_scoring.WhisperPhonemeScorer` — Whisper wrapper with
  lazy load. AccentChecker composes this rather than re-importing `whisper`.
- `lingua.pronunciation.scorer.align_phonemes` — pure function, deterministic;
  useful for visualising syllable alignment if a future contract needs it.
- `lingua.core.paths.REPO_ROOT`, `DEFAULT_DECK_AUDIO` — for default reference audio
  lookup when caller passes only `reference_text`.
- `lingua.vocab.decks.parse_guia_html` / `ParsedWord` — already parses `tones: [3,3]`
  per card; if the UI passes a `card_id` instead of paths, look up
  `ParsedWord.tones` here.

## Verification

```bash
pytest tests/accent -v
pytest tests/accent -k "missing_audio or empty_audio or diff_html or score_below_threshold" -v

# Manual: with the deck present, run a real recording
python -c "
from lingua.accent.checker import AccentChecker, AccentCheckRequest
from lingua.core.paths import DEFAULT_DECK_AUDIO
checker = AccentChecker()
req = AccentCheckRequest(
    reference_audio=DEFAULT_DECK_AUDIO / 'nihao.mp3',
    user_audio=DEFAULT_DECK_AUDIO / 'nihao.mp3',   # self-test, should score high
    reference_text='你好',
)
print(checker.check(req))
"
```
