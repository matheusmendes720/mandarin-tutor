# Feature 01 — Implementation Plan

> Concrete code changes for the open items in `review.md`.
> Steps 1–5 are independent and can ship in any order; step 0 is a precondition.

---

## Step 0 — Add `pypinyin` dependency

**File:** `pyproject.toml`

Add `pypinyin>=0.51` to the `asr` extra so it stays optional with g2p:

```toml
[project.optional-dependencies]
asr = ["g2p>=1.0", "pypinyin>=0.51"]
```

**Why optional, not hard:** pypinyin pulls nothing but itself (~50 KB), but the
project's pattern is "keep heavy ML deps behind feature flags". F1 follows that.

**Acceptance:**
```bash
pip install -e .[asr]
python -c "import pypinyin; print(pypinyin.lazy_pinyin('你好'))"
# → ['ni', 'hao']
```

---

## Step 1 — Hoist the g2p import in `scorer.py`

**File:** `src/lingua/pronunciation/scorer.py`

Replace the lazy import inside `DefaultPhonemeAnalyzer.analyze` with a module-scope
import. Same pattern for `whisper_scoring._g2p`.

### Before (scorer.py:91–102)

```python
def analyze(self, text: str) -> list[str]:
    try:
        from g2p import G2p
        out = G2p()(text)
        return [phoneme for phoneme in out if phoneme not in (" ", "_", "EOS")]
    except ImportError:
        # Return hardcoded phonemes for testing
        text_lower = text.lower()
        if text_lower in self._PHONEME_MAP:
            return self._PHONEME_MAP[text_lower]
        # Return character-based fallback for unknown words
        return list(text_lower)
```

### After

```python
# Module top (after existing imports)
try:
    from g2p import G2p as _G2p
    _G2P_AVAILABLE = True
except ImportError:
    _G2P_AVAILABLE = False

try:
    from pypinyin import lazy_pinyin as _lazy_pinyin
    _PYPINYIN_AVAILABLE = True
except ImportError:
    _PYPINYIN_AVAILABLE = False


def _pinyin_tokens(text: str) -> list[str]:
    """Tokenize to pinyin syllables (with tone numbers) for Mandarin input.
    
    Falls back through: g2p → pypinyin → character list. Returns one
    token per syllable, with tone numbers (e.g. "ni3" not "nǐ").
    """
    if _G2P_AVAILABLE:
        out = _G2p()(text)
        return [p for p in out if p not in (" ", "_", "EOS")]
    if _PYPINYIN_AVAILABLE:
        # lazy_pinyin returns base syllables without tones by default; use
        # pinyin(..., style=Style.TONE3) for "ni3" form.
        from pypinyin import Style
        return _lazy_pinyin(text, style=Style.TONE3, errors=lambda x: list(x))
    # Last resort: character-level fallback (current behaviour).
    return list(text.lower())


class DefaultPhonemeAnalyzer:
    def __init__(self, config: PronunciationConfig | None = None) -> None:
        self.config = config or PronunciationConfig()

    _PHONEME_MAP: dict[str, list[str]] = {
        "hello": ["h", "ə", "l", "oʊ"],
        "hi": ["h", "aɪ"],
    }

    def analyze(self, text: str) -> list[str]:
        text_lower = text.lower()
        if text_lower in self._PHONEME_MAP:
            return self._PHONEME_MAP[text_lower]
        return _pinyin_tokens(text)
```

**Acceptance:** `pytest tests/pronunciation/test_scorer.py -v` passes, plus the new
C-1.3 contract test.

---

## Step 2 — Lazy-load Whisper model

**File:** `src/lingua/pronunciation/whisper_scoring.py`

Move `self._load_model()` out of `__init__` and into `score()` (only first call pays
the cost; cached on the instance after that).

### Before (whisper_scoring.py:10–27)

```python
def __init__(self, model_name: str = "medium") -> None:
    self.model_name = model_name
    self._model: Any = None
    self._load_model()

def _load_model(self) -> None:
    try:
        import whisper
        self._model = whisper.load_model(self.model_name)
    except ImportError:
        self._model = None
```

### After

```python
def __init__(
    self,
    model_name: str = "base",
    config: PronunciationConfig | None = None,
) -> None:
    self.model_name = model_name
    self.config = config or PronunciationConfig()
    self._model: Any = None  # lazy

def _ensure_model(self) -> None:
    if self._model is not None:
        return
    try:
        import whisper
        self._model = whisper.load_model(self.model_name)
    except ImportError:
        self._model = None
```

Then in `score()`:

```python
def score(self, audio_path: str, target_text: str) -> dict[str, Any]:
    self._ensure_model()
    if self._model is None:
        return {"score": 0, "error": "whisper not installed", ...}
    ...
```

Note: also change the default `model_name="base"` to satisfy C-1.7.

**Acceptance:** `scorer = WhisperPhonemeScorer(); scorer._model is None` (C-1.4).

---

## Step 3 — Pass `language="zh"` to `model.transcribe()`

**File:** `src/lingua/pronunciation/whisper_scoring.py`

### Before (whisper_scoring.py:57–60)

```python
try:
    import whisper
    result = self._model.transcribe(audio_path, fp16=False)
    return result.get("text", "").strip()
```

### After

```python
try:
    import whisper
    result = self._model.transcribe(
        audio_path,
        fp16=False,
        language=self.config.language,
    )
    return result.get("text", "").strip()
```

**Acceptance:** `scorer._transcribe` is called with `language="zh"`. Hard to assert
without mocking `whisper`; covered indirectly by mocking `self._model.transcribe` and
checking the kwargs (out of scope for F1 — the type-checker is the test).

---

## Step 4 — Use the shared `_pinyin_tokens` helper in `WhisperPhonemeScorer._g2p`

**File:** `src/lingua/pronunciation/whisper_scoring.py`

Delete `_g2p` (lines 28–43) and call `_pinyin_tokens` from `scorer.py` instead. This
satisfies review.md item New-4 (deduplicate the tokenizer).

```python
from lingua.pronunciation.scorer import compute_phoneme_score, _pinyin_tokens

# inside score():
expected_phonemes = _pinyin_tokens(target_text)
transcribed_phonemes = _pinyin_tokens(transcribed_text)
```

`_pinyin_tokens` is module-private (`_` prefix) but importing it across modules is
fine for this codebase — see existing precedent in `whisper_scoring.py:4`
(`from lingua.pronunciation.scorer import compute_phoneme_score`).

---

## Step 5 — Tighten the error handler in `ui/app.py`

**File:** `src/lingua/ui/app.py` (lines 125–139)

### Before

```python
def score_pronunciation(audio, text: str) -> str:
    if audio is None:
        return "Please record audio first."
    if not text:
        return "Please enter target text to score against."
    try:
        result = _whisper_scorer.score(audio, text)
        if "error" in result:
            return f"Error: {result.get('error', 'Unknown error')}"
        score = result["score"]
        transcription = result["transcription"]
        return f"Pronunciation score: {score}% — transcribed: '{transcription}'"
    except Exception as e:
        return f"Error scoring pronunciation: {e}"
```

### After

```python
import logging
logger = logging.getLogger(__name__)

def score_pronunciation(audio, text: str) -> str:
    if audio is None:
        return "Please record audio first."
    if not text:
        return "Please enter target text to score against."
    # Expected failures come back via the result["error"] key — handle those.
    try:
        result = _whisper_scorer.score(audio, text)
    except (FileNotFoundError, RuntimeError) as expected:
        logger.warning("Pronunciation scoring failed (expected): %s", expected)
        return f"Error: {expected}"
    except Exception:
        # Unexpected — log the traceback so regressions are debuggable.
        logger.exception("Unexpected error in score_pronunciation")
        return "An internal error occurred. See server logs for details."
    if result.get("error"):
        return f"Error: {result['error']}"
    score = result["score"]
    transcription = result.get("transcription", "")
    return f"Pronunciation score: {score}% — transcribed: '{transcription}'"
```

The handler now distinguishes **expected** failures (model not loaded, audio missing
— surfaced gracefully) from **unexpected** failures (programming errors — logged with
traceback, generic message to user).

**Acceptance:** Inject a `KeyError` into `_whisper_scorer.score` (mock) — verify the
generic "An internal error occurred" message reaches the UI and a traceback lands in
the log.

---

## Step 6 — Update the existing test that locks in eager load

**File:** `tests/pronunciation/test_whisper_scoring.py:11`

```python
# Before
assert scorer._model is not None

# After
assert scorer._model is None  # C-1.4: lazy
```

The other assertions in this file (`scorer.model_name == "medium"`, custom model
"small") should also be updated to match the new defaults ("base") once step 2
lands. Out of scope for F1 unless a CI run complains.

---

## Out of scope for F1

- Replacing `compute_phoneme_score` with a tone-aware scorer (review.md New-7).
- Replacing the `_PHONEME_MAP` English-only hardcoded list (lines 85–88 of scorer.py)
  with a Mandarin-native lookup.
- Adding `PronunciationResult` dataclass; current dict is fine for F1.
- Adding `expected_tones` parameter to `score()` (reserved for a future tone-aware
  scorer).
