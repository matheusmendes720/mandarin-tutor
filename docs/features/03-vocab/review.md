# F3 — Vocabulary & Spaced Repetition: Code Review

## Bug table

| ID | Location | Severity | Symptom | Root cause | Fix | Contract |
|---|---|---|---|---|---|---|
| **F-8** | `src/lingua/ui/app.py:310` | **S1** | Review pops cards from both `_active_cards` and `_review_queue` simultaneously | `_review_queue = _active_cards` aliases the same list, so adding a card to the review queue *appears* to add it to active cards, and popping from review also shrinks active. | Tracked under F7 (Unified Interface) — the UI module is rebuilt per tab. F3 only owns the data layer. | tested in tests/ui/test_app.py |
| **F-10** | `src/lingua/vocab/decks.py:130` | **S1** | Deck browser inline `<audio src="palavras-essenciais/audio/x.mp3">` 404s in browser | `deck_path` / `audio_base` defaults were CWD-relative strings; Gradio only serves files under `allowed_paths` | Fixed in F0 via `lingua.core.paths` and `DeckConfig` defaults that resolve absolutely. F3 ships C-3.5 ensuring every `audio_path` resolves. | C-3.5 |
| **F-14** | `tests/test_integration.py` | **S0** | Integration tests tested the wrong copy of the code (`lingua.*` module object) | Dual-identity root cause as F-2 in F0 | Fixed by F-2 (X1 in F0 review). Re-run isolated in F3. | C-0.2 |
| **B-3.1** | `src/lingua/vocab/decks.py:142` | **S2** | `get_audio_data_uri` falls back to `Path.cwd()` when path is not absolute | If launched from a different directory, the existing pre-F0 fallback may pick up a stale wrong file. | Now that `DeckConfig.audio_base` is absolute (F0 X3), `Path.cwd()` fallback is unreachable for bundled decks. Tests cover the absolute case only. | C-3.5 |
| **B-3.2** | `src/lingua/vocab/store.py:78` | **S3** | `JsonStore.load()` swallows all errors and returns `[]`, including JSON shape errors | Convenient for "first run", masks schema migrations | Tracked under C-3.6 (add a `version` field and explicit migration test). Old payloads without `version` are read as v1. | C-3.6 |

## Lessons learned

- **No aliased mutable defaults.** F-8 is the canonical lesson — never write
  `x = some_list` for an instance field. Always default-factory.
- **Audio paths must be absolute or include them via `gr.Audio(value=Path)`**;
  raw `<audio src="...">` tags in `gr.HTML` rely on `allowed_paths` from
  `launch(...)`. F0 makes paths absolute; F7 will use Gradio audio components
  consistently.
- **Hidden defaults via CWD are brittle.** Even absolute paths from F0 are
  checked by tests across multiple CWDs (C-3.5).

## Definition of done (F3)

- [ ] `tests/vocab/test_contract.py` exists and all 6 contracts pass.
- [ ] `pytest tests/vocab -v` shows no new failures or skips vs F0 baseline.
- [ ] `docs/features/03-vocab/{spec,review,checklist}.md` exist.
- [ ] `git grep "from src.lingua.vocab"` returns nothing.
- [ ] No alias of a list to another instance field remains in `src/lingua/vocab/`
      (verified by `assert not any(self.x is self.y for ...)` pattern in tests).
