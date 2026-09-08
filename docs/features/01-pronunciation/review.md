# Feature 01 — Pronunciation Scoring: Bug Review

> Inventory of bugs in `src/lingua/pronunciation/` and its callers as of
> `2026-09-03`, grouped into **Old** (fixed by F0) and **New** (still open).

## Bug table

| ID | Location | Severity | Symptom | Root cause | Fix | Contract |
|---|---|---|---|---|---|---|
| **Old-1** | `core/config.py:18` (prior) | High | Whisper `"medium"` model loads at import (~1.5 GB RAM) — app cold start > 30 s, OOM on small VMs. | Hardcoded `model_name: str = "openai/whisper-large-v3"` in original config + matching `"medium"` in `whisper_scoring.py:10`. The HF-format string was nonsensical for the `openai-whisper` Python package, so the constructor silently fell back to `"medium"`. | **Fixed in F0**: `PronunciationConfig.model_name = "base"` (config.py:18). `WhisperPhonemeScorer.__init__` default still says `"medium"` — partial fix. | C-1.7 |
| **Old-2** | `whisper_scoring.py:59` | High | No language hint → Whisper biases toward English for Mandarin audio. Transcription comes back as English letters, Levenshtein score against pinyin tokens is ~0 every time. | `_transcribe` calls `self._model.transcribe(audio_path, fp16=False)` without `language=`. | **Fixed in F0** for `PronunciationConfig.language = "zh"` (config.py:19), but `WhisperPhonemeScorer._transcribe` does not read `self.config.language`. See P-NEW-3. | C-1.8 |
| **Old-3** | `scorer.py:96–102` | Medium | When `g2p` is missing, fallback returns `list(text.lower())` — character-level tokenisation. For hanzi `"你好"` → `["你", "好"]`; for pinyin `"nǐ hǎo"` → `["n", "ǐ", " ", "h", "ǎ", "o"]` after `lower()` strips the diacritic but keeps the space, which then misaligns against Whisper output. | Hardcoded fallback `return list(text_lower)` on scorer.py:102 was a quick-and-dirty test stub, not a real fallback path. Same pattern in `whisper_scoring.py:43`. | **Fixed in F0** for dependency classification (g2p now in `[asr]` extra, pyproject.toml:14). Tokeniser still broken — see P-NEW-1. | C-1.3 |
| **Old-4** | `core/config.py:18` (prior) | Critical | `PronunciationConfig.model_name = "openai/whisper-large-v3"` is an HF-format string, not a `whisper.load_model()` size. The `openai-whisper` Python package does not accept HF repo strings — load would silently fail or download the wrong asset. | Confused HF-API model id with `openai-whisper` package size keyword. | **Fixed in F0**: replaced with `"base"` (config.py:18). | C-1.7 |
| **Old-5** | `core/config.py:19` (prior) | Critical | `PronunciationConfig.language = "en"` is wrong for a Mandarin tutor app — passes English hint to Whisper for Chinese audio. | Copy-pasted from the Accent config defaults without thought. | **Fixed in F0**: replaced with `"zh"` (config.py:19). | C-1.8 |
| **Old-6** | `ui/app.py:138–139` | Medium | `score_pronunciation` wraps everything in `except Exception as e: return f"Error scoring pronunciation: {e}"`. Catches and silently swallows programming errors (e.g. `KeyError`, `AttributeError`), hiding regressions from the UI and from logs. The error message has no actionable content (no traceback, no `error` key, no log line). | Defensive blanket-catch antipattern. The proper fix is to let the scorer return structured errors (which it does — `{"error": "..."}`) and only catch the *expected* `FileNotFoundError`/`RuntimeError` paths. | **Open**: refactor to (a) trust the scorer's `error` key for expected failures, (b) re-raise unexpected exceptions, (c) log tracebacks via `logging.exception`. See `implementation_plan.md` step 5. | (covered by C-1.6) |
| **New-1** | `scorer.py:96–102`, `whisper_scoring.py:41–43` | Medium | g2p fallback path is broken for the bundled Mandarin deck (see Old-3 root cause). When `pip install -e .[asr]` is *not* run, every score collapses to character-level alignment. | `return list(text_lower)` is the only fallback and it has no Mandarin awareness. | **Open**: add `pypinyin` fallback (pure-python, no install of C++ deps). See `implementation_plan.md` step 3. | C-1.3 |
| **New-2** | `whisper_scoring.py:18` | High | `WhisperPhonemeScorer()` loads the Whisper model eagerly in `__init__`. The Gradio UI singleton at `ui/app.py:19` (`_whisper_scorer = WhisperPhonemeScorer()`) triggers load at module import time, blocking app startup. | `_load_model()` is called from `__init__` instead of lazily on first `score()` call. | **Open**: move `self._load_model()` into `score()` (or behind a property). See `implementation_plan.md` step 2. | C-1.4 |
| **New-3** | `whisper_scoring.py:10, 45–60` | High | `WhisperPhonemeScorer.__init__` ignores `PronunciationConfig` entirely. The dataclass's `language="zh"` field exists but is never read. `_transcribe` calls `self._model.transcribe(audio_path, fp16=False)` with no language hint. | Constructor signature doesn't accept `PronunciationConfig`; `_transcribe` doesn't read it. | **Open**: accept `config: PronunciationConfig` in `__init__`, store `self.config`, pass `language=self.config.language` to `transcribe`. See `implementation_plan.md` step 4. | C-1.8 |
| **New-4** | `whisper_scoring.py:28–43` | Low | `WhisperPhonemeScorer._g2p` reimplements `DefaultPhonemeAnalyzer.analyze` verbatim instead of injecting a `PhonemeAnalyzer` Protocol implementation. Two copies of the same logic, two copies of the same broken fallback. | `PhonemeAnalyzer` Protocol exists in `core/config.py:23` but `whisper_scoring.py` doesn't use it. | **Open**: inject the analyzer via `__init__(self, analyzer: PhonemeAnalyzer)`. | (future) |
| **New-5** | `scorer.py:1, 91`, `whisper_scoring.py:38` | High | Lazy g2p imports exist *inside* functions, but `scorer.py:1` has a module-level `from lingua.core.config import PhonemeAnalyzer, PronunciationConfig` and the module name `"g2p"` is referenced via `__import__` magic on scorer.py:91. The `pip install -e .[asr]` extra is *optional* per pyproject.toml:14, so a default `pip install -e .` install would have `g2p` missing — and the only consequence is the degraded fallback. **However**, the import path inside `analyze` and `_g2p` does a `from g2p import G2p` per call (hot path) when g2p IS installed — 2-attribute lookup + importlib machinery on every score. | Try/except is per-call, not module-scope. With g2p installed, you pay an import cost every score. With g2p missing, you pay an import cost *and* get a degraded result. | **Open**: at module top, do `try: from g2p import G2p as _G2p; _G2P_AVAILABLE = True; except ImportError: _G2P_AVAILABLE = False`. Then `_g2p(text)` becomes a single function call. See `implementation_plan.md` step 1. | (perf + correctness) |
| **New-6** | `tests/pronunciation/test_whisper_scoring.py:11` | Medium | `test_whisper_phoneme_scorer_instantiation` asserts `scorer._model is not None` after `__init__`. This locks in the eager-load behaviour (Old-1 / New-2). With C-1.4 in place, this assertion becomes `is None` and the test must be updated. | Test was written *after* the eager-load code and codifies the bug. | **Open**: rewrite the test to match C-1.4. See `test_scorer_contracts.py::test_C_1_4`. | C-1.4 |
| **New-7** | `scorer.py:22–28` | Low | `compute_phoneme_score` returns a raw `1.0 - errors/denominator`. For 1-phoneme expected with 1 wrong phoneme returned, score is 0.0 — no gradient. A learner who nails the tone but mistimes a consonant by 50 ms gets the same score as someone who says gibberish. | Levenshtein is a hard edit distance; no notion of "near-match". | **Defer**: out of scope for F1. Worth revisiting when we add a Mandarin-native tokenizer (pypinyin + tone-aware comparison). | (future) |

---

## Severity legend

- **Critical** — silent data corruption or always-wrong results.
- **High** — broken user-facing path or large resource leak.
- **Medium** — degraded experience, recoverable.
- **Low** — code-quality / testability issue, no user impact.

## Verification

After the fixes land, re-run:
```bash
pytest tests/pronunciation/test_scorer.py \
       tests/pronunciation/test_scorer_contracts.py \
       tests/pronunciation/test_whisper_scoring.py -v
```

C-1.4 and C-1.7 will fail with the current code; they pass after
`implementation_plan.md` steps 2 and 4 are applied.
