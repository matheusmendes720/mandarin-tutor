# F3 — Vocabulary & SRS: Verification Checklist

This feature is "done" when **all** of the following are true.

## Contracts (run from any directory)

```bash
cd C:\Users\mathe\code_space\HSK

# C-3.1 — Reviewing a card removes it from due queue AND doesn't shrink active list
pytest tests/vocab/test_contract.py::test_review_removes_from_due_not_active -v

# C-3.2 — UUID collision-free across 100 ops
pytest tests/vocab/test_contract.py::test_id_collision_free -v

# C-3.3 — Round-trip preserves all 12 Card fields incl. tones
pytest tests/vocab/test_contract.py::test_store_roundtrip_preserves_all_fields -v

# C-3.4 — Deck parse from any CWD yields 50 cards / 11 categories
pytest tests/vocab/test_contract.py::test_deck_parse_yields_50_words_11_cats -v

# C-3.5 — Every audio_path resolves to an existing file
pytest tests/vocab/test_contract.py::test_every_audio_path_resolves -v

# C-3.6 — Schema version migration
pytest tests/vocab/test_contract.py::test_schema_version_migration -v
```

## Mechanical checks

```bash
# Full suite — must show no new failures or skips vs F0 baseline (147+, 17+ skipped)
pytest -q --tb=line --ignore=tests/accent/test_checker_contract.py

# No F-2 regression: production code uses only `lingua.*` (not `src.lingua.*`)
grep -rn "from src.lingua\|import src.lingua" src/lingua/vocab/   # must be empty
```

## Manual smoke (optional, in a Python REPL)

```python
from lingua.vocab.scheduler import Card, fsrs_schedule, ReviewQuality, get_due_cards
from lingua.vocab.store import JsonStore
from lingua.vocab.decks import PalavrasEssenciaisDeck
from lingua.core.config import DeckConfig

# Build a card
c = Card(id="x", front="你", back="você")
c2 = fsrs_schedule(c, ReviewQuality.GOOD)
print(f"interval_days after first GOOD review: {c2.interval_days}")  # 1

# Due filter
due = get_due_cards([c, c2])
print(f"due cards: {[x.id for x in due]}")

# Round-trip
import tempfile, pathlib
with tempfile.TemporaryDirectory() as d:
    store = JsonStore(path=pathlib.Path(d) / "x.json")
    store.save([c, c2])
    print(f"loaded: {[(x.id, x.front) for x in store.load()]}")

# Deck
cfg = DeckConfig()  # defaults are absolute via core.paths
deck = PalavrasEssenciaisDeck(cfg)
print(f"deck categories: {len(deck.categories())}, words: {len(deck.cards_by_category())}")
```

## Definition of done

- [ ] All 6 contract tests pass.
- [ ] `pytest -q --tb=no` shows no regressions vs the F3 starting baseline
      (whatever the suite shows before F3 work begins).
- [ ] `docs/features/03-vocab/{spec,review,checklist}.md` exist.
- [ ] No `src.lingua.vocab` imports remain in production code.
