# F0 — Platform Foundation: Spec

## Purpose

Every other feature (F1–F6) depends on F0 being correct. F0 owns three things
that have nothing to do with pronunciation, TTS, accent, vocab, drills, or
voice — but everything to do with whether those features can be trusted:

1. **Single import identity.** The codebase is no longer a mix of `lingua.X`
   and `src.lingua.X` imports that resolve to two distinct module objects.
2. **Installable package.** `pip install -e .` actually installs runtime deps.
   The old pyproject declared them under an invalid `[project.dependencies]`
   table that pip silently ignored, so the system ran with `gradio`, `scipy`,
   `openai-whisper`, and `edge-tts` only.
3. **CWD-independent paths.** `DeckConfig` and `PhonemeCatalogConfig` resolve
   their `deck_path` / `audio_base` from `__file__`, not from the process CWD.

## Data model

| Symbol | Module | Shape |
|---|---|---|
| `REPO_ROOT` | `lingua.core.paths` | `Path` computed at import |
| `AppConfig` | `lingua.core.config` | `@dataclass` with title, target_language, and per-feature configs |
| `get_store`, `get_deck`, … | `lingua.core.registry` | `@lru_cache` accessors |

## Interaction map

| Trigger | Function | Inputs | Outputs | Side effects |
|---|---|---|---|---|
| `build_app(config)` | `lingua.ui.app.build_app` | `AppConfig` | `gr.Blocks` | one-time lazy-init of subsystems on first callback |
| `get_store()` | `lingua.core.registry` | — | `JsonStore` | creates `~/.lingua/` on first call |
| `get_deck()` | `lingua.core.registry` | — | `PalavrasEssenciaisDeck` | parses `palavras-essenciais/guia.html` once |
| CLI `python -m lingua` | `lingua.__main__` | `--port`, `--host` | launches app | none before launch |

## External dependencies

| Package | Where | Why |
|---|---|---|
| `gradio>=4.0` | pyproject `[project].dependencies` | UI runtime |
| `scipy>=1.11` | same | WAV decode |
| `openai-whisper>=20231117` | same | F1 ASR |
| `edge-tts>=6.1` | same | F2 TTS |
| `g2p`, `TTS`, `funasr`, `livekit` | optional groups `[asr]`, `[tts-coqui]`, `[accent-funasr]`, `[voice-livekit]` | gated behind extras so the default install stays small |

## Testable contracts C-0.x

- **C-0.1** `pip install -e ".[dev]"` succeeds with `[project].dependencies`
  populated (no longer the invalid `[project.dependencies]` table).
- **C-0.2** `import lingua.X` and `import src.lingua.X` resolve to the **same
  module object** — or `src.lingua.X` raises `ModuleNotFoundError` because the
  repo root is no longer on `sys.path`.
- **C-0.3** `from lingua.core.paths import REPO_ROOT` returns a `Path` that
  exists regardless of `os.getcwd()`.
- **C-0.4** `DeckConfig()` and `PhonemeCatalogConfig()` defaults both point
  at real files on disk (no `FileNotFoundError` at instantiation).
- **C-0.5** `import lingua.ui.app` does **not** load any ML model and does
  **not** read or write any file outside `~/.lingua/`.
- **C-0.6** `build_app(AppConfig(title="X"))` produces a `gr.Blocks` whose
  title is `"X"`.
- **C-0.7** `python -m lingua --help` succeeds and shows `--port`, `--host`
  (no `--reload`, which Gradio 6 removed).

## Out of scope

- Frontend styling / theming
- Authentication / multi-user
- Database backend (JsonStore is fine for now)
- i18n of the UI text (PT-BR and English strings stay as authored)

See `interop.md` for how F1–F6 subsystems wire together at the SessionContext
level.
