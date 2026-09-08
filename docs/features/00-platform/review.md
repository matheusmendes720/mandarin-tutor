# F0 — Platform Foundation: Code Review

## Bug table

| ID | Location | Severity | Symptom | Root cause | Fix | Contract |
|---|---|---|---|---|---|---|
| **F-1** | `pyproject.toml:6-13` | **S0** | `pip install -e .` installs zero runtime deps | `[project.dependencies]` is not a valid PEP 621 table — pip ignored it. The codebase ran on whatever happened to be installed globally. | Moved deps under `dependencies = [...]` key inside `[project]`. Heavy backends split into optional-dependencies groups (`asr`, `tts-coqui`, `accent-funasr`, `voice-livekit`). | C-0.1 |
| **F-2** | `src/lingua/**`, `tests/**` | **S0** | Two distinct `Card` classes: `lingua.vocab.scheduler.Card` and `src.lingua.vocab.scheduler.Card` | `lingua` is editable-installed from `src/`, but `tests/conftest.py` also added the repo root, making `src.lingua.*` importable too. `isinstance(x, src.lingua.X)` silently returned False across the boundary. | Mechanical rewrite: `from src.lingua.X` → `from lingua.X` across 23 files. `tests/conftest.py` no longer mutates `sys.path`. `README.md` and `CLAUDE.md` updated to `python -m lingua`. | C-0.2 |
| **F-3** | `src/lingua/__main__.py:35` | **S0** | `python -m lingua` crashes with `TypeError: launch() got an unexpected keyword argument 'reload'` | Gradio 6 removed the `reload` parameter; the code passed it through verbatim. | Removed `--reload` arg, dropped `reload=` from `launch()`. | C-0.7 |
| **F-4** | `src/lingua/ui/app.py:484-488` | **S2** | Phoneme Drills tab renders an empty dropdown | `gr.Dropdown(choices=_phoneme_catalog.initials())` is fed `list[dict]`; Gradio 6 expects `list[str]` or `list[tuple[str, str]]`. | Tracked under F4 review.md B-4.x. Not fixed in F0 — separate feature owns it. | — |
| **F-5** | `src/lingua/tts/engine.py`, `coqui.py:60` | **S1** | TTS double-wraps WAV bytes as raw int16 PCM; Coqui hardcodes `language="en"` | `CoquiTTSModel.synthesize` returns WAV-encoded bytes; `play_tts` in app.py interprets them as raw PCM and re-wraps. | Tracked under F2 review.md B-2.4. Fix in F2. | — |
| **F-6** | `src/lingua/accent/detector.py:158` | **S1** | `_analyze_dialect` always returns "Mandarin"; empty FunASR result raises `UnboundLocalError` | Hardcoded literal + undefined variable in non-empty branch | Tracked under F5 review.md B-5.x. Fix in F5. | — |
| **F-7** | `src/lingua/voice_agent/agent.py` | **S0** | Voice tab non-functional | `asyncio.get_event_loop()` deprecated on 3.12+, fabricated `LiveKit.connect()` API, broken `@asynccontextmanager` decoration | Tracked under F6 review.md (TBD after ASR research). Fix in F6. | — |
| **F-8** | `src/lingua/ui/app.py:310` | **S1** | Review pops cards from both `_active_cards` and `_review_queue` | `_review_queue = _active_cards` aliases the same list | Tracked under F3 review.md. Fix in F3. | — |
| **F-9** | `src/lingua/ui/app.py:19` | **S1** | Importing `lingua.ui.app` blocks for 30+ seconds loading Whisper `medium` | `WhisperPhonemeScorer()` called at module import → `load_model("medium")` (~1.5 GB) | Fixed in F0 via `lingua.core.registry.get_whisper_scorer()` lazy accessor; default model size reduced to `"base"`. F1 review covers remaining lazy-load work. | C-0.5 |
| **F-10** | `src/lingua/vocab/decks.py:130` | **S1** | Deck browser inline `<audio src="palavras-essenciais/audio/x.mp3">` 404s in browser | `deck_path` / `audio_base` defaults are CWD-relative strings; Gradio only serves files under `allowed_paths` | Fixed in F0 via `lingua.core.paths` and `DeckConfig` defaults that resolve absolutely. F3 review covers remaining UI adapter. | C-0.4 |
| **F-11** | `src/lingua/phoneme_drill/drill.py` | **S1** | `play_phoneme_with_tone("ni", 3)` returns `mǎ` | Hardcoded `ma{tone}.wav` fallback for any syllable | Tracked under F4 review.md B-4.x. Fix in F4. | — |
| **F-12** | `pinyin-completo/{css,js}/*` | **S3** | Designed pinyin features (quiz, recorder, dark mode) never shipped | `guia.html` never references these files | Explicitly out-of-scope per plan; standalone HTML stays as-is for users who want full pinyin trainer UI. | — |
| **F-13** | `guia.html` (root) | **S3** | 28 KB stale artifact (0 hanzi entries, unrelated to either deck) | None — orphan from earlier work | Triage for deletion; not blocking. | — |
| **F-14** | `tests/test_integration.py:4-8` | **S0** | Integration tests passed but tested the wrong copy of the code (the `lingua.*` module object) | Same dual-identity root cause as F-2 | Fixed by F-2. Re-run integration tests in F3–F6 phases. | C-0.2 |
| **F-15** | `src/lingua/tts/engine.py` | **S1** | `synthesize_text(text, model=my_model)` raises `TypeError` | Parameter named `text_or_model2`; docstring advertises `model=` kwarg that doesn't exist | Fixed in F2 by the TTS subagent. New signature is `synthesize_text(text, *, config=None, model=None)`. | — |

## Verification commands

```bash
# C-0.1 installable package
pip install -e ".[dev]"

# C-0.2 single module identity
python -c "import lingua.vocab.scheduler as a; import sys; print('src.lingua importable?', 'src.lingua' in sys.modules)"

# C-0.3 CWD-independent REPO_ROOT
cd /tmp && python -c "from lingua.core.paths import REPO_ROOT; print(REPO_ROOT)"

# C-0.4 absolute defaults resolve
python -c "from lingua.core.config import DeckConfig, PhonemeCatalogConfig; import pathlib; print(pathlib.Path(DeckConfig().deck_path).is_file(), pathlib.Path(PhonemeCatalogConfig().guia_path).is_file())"

# C-0.5 import UI without side effects
python -c "
import sys, unittest.mock as m
with m.patch('builtins.open', side_effect=AssertionError('no file IO allowed')):
    import lingua.ui.app  # should NOT raise
print('OK — no file IO at import')
"

# C-0.7 entry point
python -m lingua --help
```

Baseline after F0: `pytest -q --tb=no` shows **147 passed, 17 skipped, 0 failed**.
