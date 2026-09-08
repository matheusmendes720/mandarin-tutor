# F0 — Platform Foundation: Verification Checklist

This feature is "done" when **all** of the following are true.

## Mechanical checks (run from any directory)

```bash
# All commands should exit 0 unless noted.
cd C:\Users\mathe\code_space\HSK

# Install cleanly
pip install -e ".[dev]"
echo "exit=$?"

# CWD-independent import
cd C:\
python -c "from lingua.core.paths import REPO_ROOT; assert REPO_ROOT.is_dir(), REPO_ROOT"
cd "C:\Users\mathe\code_space\HSK"

# Single module identity
python -c "
import sys
assert 'src.lingua' not in sys.modules, 'conftest.py is leaking src/ onto sys.path'
import lingua.vocab.scheduler
print('lingua.vocab.scheduler from:', lingua.vocab.scheduler.__file__)
"

# Config defaults resolve
python -c "
from pathlib import Path
from lingua.core.config import DeckConfig, PhonemeCatalogConfig, AppConfig
assert Path(DeckConfig().deck_path).is_file()
assert Path(DeckConfig().audio_base).is_dir()
assert Path(PhonemeCatalogConfig().guia_path).is_file()
assert Path(PhonemeCatalogConfig().audio_base).is_dir()
assert AppConfig(title='T').title == 'T'
"

# No eager model load at import
python -c "
import unittest.mock as m
with m.patch('whisper.load_model', side_effect=AssertionError('eager load!')):
    import lingua.ui.app  # must not raise
print('OK: no eager Whisper load')
"

# Entry point runs without TypeError
python -m lingua --help
```

## Baseline test suite

```bash
# Must show: passed == baseline (147), skipped == baseline (17), failed == 0
pytest -q --tb=no --ignore=tests/accent/test_checker_contract.py
```

`tests/accent/test_checker_contract.py` is skipped (not failed) until the F5
implementation lands; it imports `lingua.accent.checker` and
`lingua.accent.models` which are scheduled for F5.

## Manual smoke (optional, in a real browser)

```bash
python -m lingua --port 7860 --host 127.0.0.1
# Open http://127.0.0.1:7860
# Verify: title in browser tab reads "Lingua — Mandarin Tutor" (NOT empty, NOT "Gradio")
# Verify: all 5 tabs present
# Verify: clicking between tabs does not load Whisper model (check RAM usage)
```

## Definition of done

- [ ] All mechanical checks above exit 0.
- [ ] `pytest -q` passes with no new failures and no new skips vs the F0 baseline.
- [ ] `docs/features/00-platform/{spec,review,checklist,interop}.md` exist.
- [ ] `tests/platform/{test_imports,test_pyproject,test_paths}.py` exist.
- [ ] `git grep "from src.lingua"` returns nothing (only mentions inside
      docstrings explaining why we removed it).
- [ ] `python -m lingua --help` exits 0 with `--port`, `--host`, no `--reload`.
