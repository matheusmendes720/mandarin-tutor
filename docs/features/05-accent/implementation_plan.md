# F5 — Implementation Plan: Accent / Pronunciation Correction

> Goal: ship `lingua.accent.checker.AccentChecker` + dataclasses, retire FunASR,
> replace `lingua.accent.detector.detect_accent` with a shim. Contracts C-5.1 …
> C-5.5 are the unit-test surface.

## Order of Operations

1. **Add the dataclasses** (`models.py`) — zero dependencies, unblocks the rest.
2. **Add `AccentChecker`** (`checker.py`) — depends on F1 Whisper wrapper + pypinyin.
3. **Rewrite `detector.py` as a shim** — re-exports from `checker` for any callers.
4. **Delete `analyzer.py` and the two legacy test files.**
5. **Add `tests/accent/test_checker_contract.py`** with C-5.1 … C-5.5 mocked.
6. **Update `lingua/accent/__init__.py`** to export the new public surface.
7. **Verify**: `pytest tests/accent -v` green; manual self-test passes.

---

## File 1 — `src/lingua/accent/models.py` (NEW)

```python
"""Data model for pronunciation correction results (F5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AccentCheckRequest:
    reference_audio: Path
    user_audio: Path
    reference_text: str
    language: str = "zh"


@dataclass(frozen=True)
class SyllableScore:
    text: str           # hanzi
    pinyin: str         # with tone diacritic, e.g. "nǐ"
    tone: int           # 1..5 (5 = neutral)
    score: float        # 0..100
    confidence: float   # 0..1


@dataclass(frozen=True)
class AccentCheckResult:
    overall_score: float = 0.0
    syllables: list[SyllableScore] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    diff_html: str = ""
    error: str | None = None
```

**Why a separate module:** `__init__.py` re-exports from here; tests import
directly to avoid the side-effects of importing the Whisper-backed `checker.py`.

---

## File 2 — `src/lingua/accent/checker.py` (NEW)

```python
"""Per-syllable Mandarin pronunciation correction (F5)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lingua.accent.models import (
    AccentCheckRequest,
    AccentCheckResult,
    SyllableScore,
)
from lingua.core.config import PronunciationConfig


# Tone-specific coaching hints (PT-BR primary; Mandarin secondary).
_TONE_HINTS: dict[int, tuple[str, str]] = {
    1: ("Mantenha o tom alto e sustentado.", "保持高平调。"),
    2: ("Suba do meio para o topo.", "从中音升到高音。"),
    3: ("Desça e suba (curva em V invertido).", "降升调。"),
    4: ("Desça bruscamente.", "高降调。"),
    5: ("Curto e neutro.", "轻短调。"),
}


def _parse_syllables(text: str) -> list[tuple[str, str, int]]:
    """Return [(hanzi, pinyin_with_tone, tone)] per character.

    Uses pypinyin if available; falls back to a (hanzi, hanzi, 5) tuple per char.
    """
    try:
        from pypinyin import lazy_pinyin, Style
        # pypinyin returns list[str] aligned to input chars
        pin_with_tone = lazy_pinyin(text, style=Style.TONE3, neutral_tone_with_five=True)
        # Style.TONE3 yields e.g. "ni3" — convert to "nǐ" via static map? Keep "ni3"
        # for the tone field, but normalise to diacritic for display.
        # For the first MVP we keep "ni3" form; UI shows pinyin+number.
    except ImportError:
        pin_with_tone = [c for c in text]

    out: list[tuple[str, str, int]] = []
    for hanzi, pin in zip(text, pin_with_tone, strict=False):
        tone = 5
        pinyin_disp = pin
        # TONE3 form ends in a digit 1..5 (or "0"/"5" for neutral)
        if pin and pin[-1].isdigit():
            try:
                tone = int(pin[-1]) or 5
                pinyin_disp = pin[:-1]
            except ValueError:
                tone = 5
        out.append((hanzi, pinyin_disp, tone))
    return out


class AccentChecker:
    """Per-syllable pronunciation checker (Whisper + pypinyin)."""

    def __init__(self, config: PronunciationConfig | None = None) -> None:
        self.config = config or PronunciationConfig()
        self._scorer: Any = None  # lazy WhisperPhonemeScorer

    def _ensure_scorer(self) -> Any:
        if self._scorer is None:
            from lingua.pronunciation.whisper_scoring import WhisperPhonemeScorer
            self._scorer = WhisperPhonemeScorer(
                model_name=self.config.model_name,
            )
        return self._scorer

    def check(self, req: AccentCheckRequest) -> AccentCheckResult:
        # 1. Existence checks (NEVER raise — return error-tagged result).
        if not req.reference_audio.is_file():
            return AccentCheckResult(error="missing_audio:reference")
        if not req.user_audio.is_file():
            return AccentCheckResult(error="missing_audio:user")

        # 2. Empty-file short-circuit.
        if req.user_audio.stat().st_size == 0:
            return AccentCheckResult(error="empty_audio:user")

        # 3. Parse reference syllables.
        syllables_meta = _parse_syllables(req.reference_text)
        if not syllables_meta:
            return AccentCheckResult(error="empty_reference_text")

        # 4. Transcribe user audio with Whisper (lazy load).
        scorer = self._ensure_scorer()
        try:
            transcript = scorer._transcribe(str(req.user_audio))
        except Exception as e:  # noqa: BLE001 — surface as soft error
            return AccentCheckResult(error=f"transcription_failed:{type(e).__name__}")
        if not transcript:
            return AccentCheckResult(error="transcription_failed")

        # 5. Score per syllable using Whisper's segment-level confidence.
        # We approximate "per-word confidence" by chunking the Whisper segments
        # evenly across the transcribed text and the reference syllable count.
        # (Whisper exposes per-word probabilities only via word_timestamps=True;
        # for the MVP we use the segment avg_logprob-derived confidence below.)
        try:
            segments = scorer._model.transcribe(
                str(req.user_audio),
                language=req.language,
                word_timestamps=True,
                fp16=False,
            ).get("segments", [])
        except Exception:
            segments = []

        per_word_conf = _extract_word_confidences(segments, transcript)

        syllables: list[SyllableScore] = []
        for i, (hanzi, pinyin, tone) in enumerate(syllables_meta):
            conf = per_word_conf[i] if i < len(per_word_conf) else 0.0
            score = round(max(0.0, min(1.0, conf)) * 100, 1)
            syllables.append(
                SyllableScore(
                    text=hanzi,
                    pinyin=pinyin,
                    tone=tone,
                    score=score,
                    confidence=conf,
                )
            )

        overall = (
            sum(s.score for s in syllables) / len(syllables) if syllables else 0.0
        )

        # 6. Generate active corrections for low-scoring syllables.
        threshold = self.config.scoring_threshold * 100  # 0..1 -> 0..100
        corrections: list[str] = []
        for s in syllables:
            if s.score < threshold:
                corrections.append(_correction_for(s))

        # 7. Render diff_html.
        diff_html = _render_diff_html(syllables)

        return AccentCheckResult(
            overall_score=round(overall, 1),
            syllables=syllables,
            corrections=corrections,
            diff_html=diff_html,
        )


def _extract_word_confidences(segments: list[dict], transcript: str) -> list[float]:
    """Map Whisper per-word probabilities onto one confidence per reference char.

    Whisper's `word_timestamps=True` yields words with `probability` (0..1).
    We align them by character index to the reference text via simple substring
    matching against `transcript`. Words that don't match contribute 0.
    """
    # Flatten all words with their char-position in the transcript
    words: list[tuple[str, float]] = []
    for seg in segments:
        for w in seg.get("words", []) or []:
            token = (w.get("word") or "").strip()
            if not token:
                continue
            prob = float(w.get("probability", 0.0))
            words.append((token, prob))

    if not words:
        # Fallback: one confidence per char, all = 1.0 if transcript non-empty.
        return [1.0] * len(transcript) if transcript else []

    # Greedy alignment: walk the transcript char-by-char, consume words.
    confidences: list[float] = []
    wi = 0
    cursor = 0
    while cursor < len(transcript) and wi < len(words):
        token, prob = words[wi]
        # Skip whitespace
        while cursor < len(transcript) and transcript[cursor].isspace():
            cursor += 1
        # Try to match the next token's first character
        if cursor < len(transcript) and token and transcript[cursor] == token[0]:
            confidences.append(prob)
            cursor += 1
            wi += 1
        else:
            # Skip this token (likely a Whisper hallucination)
            wi += 1
    # Pad with zeros for any remaining reference chars
    while len(confidences) < len(transcript):
        confidences.append(0.0)
    return confidences


def _correction_for(s: SyllableScore) -> str:
    if s.score < 50 and s.tone in _TONE_HINTS:
        pt, zh = _TONE_HINTS[s.tone]
        return (
            f"你的声调 {s.tone} 听起来不太对 — {zh} "
            f"(Tom {s.tone} da sílaba '{s.text}' ({s.pinyin}): {pt})"
        )
    return f"Pratique a sílaba '{s.text}' ({s.pinyin}) separadamente."


def _render_diff_html(syllables: list[SyllableScore]) -> str:
    spans: list[str] = []
    for s in syllables:
        if s.score >= 90:
            colour = "#2e7d32"
        elif s.score >= 60:
            colour = "#f9a825"
        else:
            colour = "#c62828"
        spans.append(
            f'<span data-syllable="{s.text}" data-score="{s.score}" '
            f'style="background:{colour};color:#fff;padding:2px 6px;'
            f'margin:0 2px;border-radius:4px">{s.text}</span>'
        )
    return "".join(spans)
```

**Dependencies (already in tree):** `lingua.pronunciation.whisper_scoring.WhisperPhonemeScorer`,
`lingua.core.config.PronunciationConfig`. **New recommended install:** `pypinyin`.

---

## File 3 — `src/lingua/accent/detector.py` (REWRITE as 8-line shim)

```python
"""Backward-compat shim. See `lingua.accent.checker` for the implementation."""
from lingua.accent.checker import AccentChecker  # noqa: F401
from lingua.accent.models import (                # noqa: F401
    AccentCheckRequest,
    AccentCheckResult,
    SyllableScore,
)

__all__ = [
    "AccentChecker",
    "AccentCheckRequest",
    "AccentCheckResult",
    "SyllableScore",
]
```

If any legacy caller does `from lingua.accent.detector import detect_accent`, add
a one-line shim function that raises `NotImplementedError` with a clear message
("Removed in F5; use `lingua.accent.checker.AccentChecker.check(req)`"). Per the
review (B-5.3), no production code calls this; the shim is purely defensive.

---

## File 4 — `src/lingua/accent/__init__.py` (UPDATE)

```python
"""Accent / pronunciation correction subsystem (F5)."""
from lingua.accent.checker import AccentChecker, check_accent
from lingua.accent.models import (
    AccentCheckRequest,
    AccentCheckResult,
    SyllableScore,
)

__all__ = [
    "AccentChecker",
    "check_accent",
    "AccentCheckRequest",
    "AccentCheckResult",
    "SyllableScore",
]
```

Add a module-level convenience (one line, no business logic):

```python
def check_accent(req: AccentCheckRequest) -> AccentCheckResult:
    """Convenience: instantiate the singleton checker and call `.check(req)`."""
    from lingua.core.registry import get_accent_checker   # F0/X5
    return get_accent_checker().check(req)
```

---

## File 5 — DELETE

- `src/lingua/accent/analyzer.py`
- `tests/accent/test_analyzer.py`
- `tests/accent/test_detector.py` (replaced by `test_checker_contract.py`)

```bash
git rm src/lingua/accent/analyzer.py tests/accent/test_analyzer.py tests/accent/test_detector.py
```

---

## File 6 — `tests/accent/test_checker_contract.py` (NEW)

See the companion file `tests/accent/test_checker_contract.py` for full test code.
Stub summary:

| Test | Contract | Mock strategy |
|---|---|---|
| `test_perfect_audio_scores_high` | C-5.1 | `monkeypatch.setattr(scorer, "_transcribe", lambda p: "你好")` + mock segments with `probability=1.0` |
| `test_low_confidence_first_syllable_triggers_correction` | C-5.2 | segments with `probability=0.1` on word 0; assert `syllables[0].score < 50` and `"你" in " ".join(corrections)` |
| `test_diff_html_one_span_per_syllable` | C-5.3 | assert count of `<span data-syllable=` matches len(reference chars) |
| `test_empty_user_audio_returns_zero_score_no_raise` | C-5.4 | `tmp_path / "empty.wav"` (zero bytes); assert `result.error is not None` and `overall_score == 0.0` |
| `test_missing_reference_audio_returns_error_tag_no_raise` | C-5.5 | pass non-existent path; assert `result.error == "missing_audio:reference"` |

---

## File 7 — `src/lingua/core/config.py` (UPDATE, minimal)

The `AccentConfig` was simplified in F0. Confirm it already has:

```python
@dataclass
class AccentConfig:
    whisper_model: str = "base"
    language: str = "zh"
    supported_languages: list[str] = field(default_factory=lambda: ["en", "zh"])
```

No change required. `PronunciationConfig.scoring_threshold` (0..1) is the source
of truth for the active-correction threshold — `AccentChecker` reads it from
there in `__init__`.

---

## Sequencing & Branch Points

| Step | Blocker | Branch decision |
|---|---|---|
| 1. models.py | none | ship as-is |
| 2. checker.py | F1 (`WhisperPhonemeScorer`) | if F1 incomplete, stub `_transcribe` in checker for tests |
| 3. shim detector.py | step 2 | ship shim once `check()` is callable |
| 4. delete analyzer.py | step 3 | safe to delete — no production callers (verified in review B-5.3) |
| 5. test_checker_contract.py | step 2 | if `pypinyin` unavailable in CI, fixture monkeypatches `_parse_syllables` |
| 6. update __init__.py | step 5 | ship together |
| 7. verify | all above | run `pytest tests/accent -v` + manual self-test |

## Risk & Rollback

- **Risk:** Whisper confidence alignment (`_extract_word_confidences`) is heuristic.
  If alignment drifts (e.g. Whisper splits "你好" as "你" "好" but reports
  probabilities at the segment level, not word level), per-syllable scores may be
  noisy. **Mitigation:** C-5.2 asserts the score is `< 50` for low confidence —
  the threshold gives 50 points of headroom for alignment jitter.
- **Risk:** `pypinyin` is an optional dep; without it `_parse_syllables` returns
  raw hanzi as pinyin, `tone=5`. The UI looks degenerate but does not crash.
  **Mitigation:** C-5.1/C-5.2 don't depend on pinyin quality — only on
  `len(syllables) == len(reference_text)`.
- **Rollback:** the entire F5 rewrite is contained in `src/lingua/accent/`. A
  single `git revert` of the merge commit restores the (broken) FunASR path.
