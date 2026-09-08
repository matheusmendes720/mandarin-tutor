# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Lingua** is a unified language learning platform built with Python + Gradio. It provides pronunciation scoring, TTS synthesis, accent analysis, vocabulary spaced repetition (FSRS), phoneme drills, and a voice conversation tutor.

- **Entry point**: `python -m lingua.ui.app` or `python -m lingua` (via `__main__.py`)
- **UI framework**: Gradio — the app is built via `build_app()` in `src/lingua/ui/app.py`
- **Python**: 3.11+, uses `g2p`, `TTS`, `scipy`, `openai-whisper`, `funasr`, `livekit`

## Commands

```bash
# Install
pip install -e .

# Run the app
python -m lingua.ui.app          # or: python -m lingua
python -m lingua.ui.app --port 7860 --host 0.0.0.0

# Run tests
pytest
pytest tests/vocab/test_scheduler.py  # single test file
pytest -k test_fsrs                  # single test by name
```

## Architecture

### Subsystems

| Module | Responsibility |
|---|---|
| `pronunciation/` | Phoneme scoring using Whisper + g2p Levenshtein alignment |
| `tts/` | Coqui TTS engine wrapper, synthesis result dataclass |
| `accent/` | FunASR accent detection + diarization |
| `vocab/` | FSRS-based flashcard scheduler, JSON store, deck importers |
| `voice_agent/` | LiveKit-based voice session + tutor agent |
| `phoneme_drill/` | Chinese pinyin tone/combination drill player |
| `ui/` | Gradio Blocks app — all UI logic lives here |
| `core/config.py` | Protocol interfaces (PhonemeAnalyzer, TTSModel, DiarizationModel) + dataclass configs for each subsystem |

### Key Design Points

- **Protocol-based**: `core/config.py` defines `PhonemeAnalyzer`, `TTSModel`, `DiarizationModel` as Protocol interfaces — implementations are injected.
- **Module-level singletons in UI**: The app module (`app.py`) creates module-level globals (`_whisper_scorer`, `_voice_session`, etc.) at import time. This is intentional for Gradio's callback model.
- **FSRS scheduler**: `vocab/scheduler.py` implements the Free Spaced Repetition Scheduler algorithm. Cards have `ease_factor`, `interval_days`, `repetitions`, `due_date`.
- **Voice agent**: Uses LiveKit for real-time voice sessions; requires `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` env vars.
- **Bundled deck**: On first run, `app.py` imports `palavras-essenciais/guia.html` (Portuguese-Chinese deck) if no saved cards exist.

### Adding a New Subsystem

1. Define a Protocol + Config dataclass in `core/config.py`
2. Implement the subsystem in its own package under `src/lingua/`
3. Wire it into `ui/app.py` following the existing pattern (module-level singleton, Gradio callback)
4. Add tests under `tests/<subsystem>/`
