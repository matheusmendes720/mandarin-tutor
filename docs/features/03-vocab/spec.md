# F3 — Vocabulary & Spaced Repetition: Spec

## Purpose

The vocab feature carries a learner's flashcard deck + its scheduling state,
and renders the cards interactively in the Gradio UI. The FSRS algorithm
decides when each card is due; the JSON store round-trips Card objects to
disk; the deck browser parses the bundled `palavras-essenciais/guia.html`
into rich card metadata that gets reviewed and persisted.

## Public API

### `lingua.vocab.scheduler`

```python
class ReviewQuality(Enum):
    AGAIN = 0   # reset; show again in 10 minutes
    HARD = 1    # smaller interval, decrease ease
    GOOD = 2    # standard FSRS interval
    EASY = 3    # 1.3x interval bonus

@dataclass
class Card:
    id: str
    front: str
    back: str
    ease_factor: float = 2.5
    interval_days: int = 1
    repetitions: int = 0
    due_date: datetime = field(default_factory=datetime.now)
    # Optional rich metadata
    pinyin: str | None = None
    context: str | None = None
    cat: str | None = None
    tones: list[int] = field(default_factory=list)
    audio_path: str | None = None

def fsrs_schedule(card: Card, quality: ReviewQuality) -> Card
def get_due_cards(cards: list[Card]) -> list[Card]
def create_card(id: str, front: str, back: str) -> Card
```

### `lingua.vocab.store`

```python
class JsonStore:
    def __init__(self, path: Path | None = None) -> None
    def save(self, cards: list[Card]) -> None
    def load(self) -> list[Card]

def card_to_dict(card: Card) -> dict
def dict_to_card(dct: dict) -> Card
```

The store path defaults to `~/.lingua/cards.json` (override by passing `path`).

### `lingua.vocab.decks`

Implements `DeckBrowser` Protocol from `lingua.core.config`:

```python
@dataclass
class ParsedWord:
    hanzi: str
    pinyin: str
    slug: str
    tones: list[int]
    pt: str
    context: str
    cat: str

@dataclass
class ParsedCategory:
    key: str
    icon: str
    name_pt: str
    subtitle: str

def parse_guia_html(path: Path) -> tuple[list[ParsedWord], list[ParsedCategory]]

class PalavrasEssenciaisDeck:
    def __init__(self, config: DeckConfig) -> None
    def categories(self) -> list[dict]
    def cards_by_category(self, category_key: str | None = None) -> list[dict]
    def card(self, card_id: str) -> dict | None
    def audio_path(self, card_id: str) -> str | None
    def get_audio_data_uri(self, card_id: str) -> str  # base64 Data URI
    def render_card_html(self, card_id: str, revealed: bool = False, autoplay_audio: bool = False) -> str
    def render_deck_table_html(self, cards: list[dict], active_ids: set[str] | None = None) -> str
```

### `lingua.vocab.importers`

Helper functions to convert `ParsedWord` → `Card` and to add cards to a deck
in a way that ensures unique IDs.

## Card schema (12 fields)

| Field          | Type      | Notes |
|----------------|-----------|-------|
| `id`           | str       | UUID or `pe_<slug>` for deck-imported cards |
| `front`        | str       | Prompt (hanzi) |
| `back`         | str       | Answer (Portuguese) |
| `ease_factor`  | float     | FSRS ease, default 2.5 |
| `interval_days`| int       | FSRS interval, default 1 |
| `repetitions`  | int       | FSRS streak count, default 0 |
| `due_date`     | datetime  | Next review time |
| `pinyin`       | str?      | Optional |
| `context`      | str?      | Optional example sentence (PT) |
| `cat`          | str?      | Optional category key |
| `tones`        | list[int] | Optional tone markers, default `[]` |
| `audio_path`   | str?      | Optional absolute or repo-relative path |

## FSRS state transitions

| Input state                                              | ReviewQuality | Output state                              |
|----------------------------------------------------------|---------------|-------------------------------------------|
| `repetitions==0`                                         | AGAIN         | `repetitions=0, interval=1, due=+10min, ease=max(1.3, ef-0.2)` |
| any                                                      | HARD          | `repetitions+=1, interval=1, due=+1d, ease=max(1.3, ef+ease_delta)` where ease_delta<0 |
| `repetitions==0`                                         | GOOD          | `repetitions=1, interval=1, due=+1d`      |
| `repetitions==1`                                         | GOOD          | `repetitions=2, interval=6, due=+6d`      |
| `repetitions>=2`                                         | GOOD          | `repetitions+=1, interval=int(interval*ease), due=+interval*d` |
| any                                                      | EASY          | same as GOOD but `interval=int(int(interval*ease)*1.3)` |

## Contracts

| ID | Contract |
|---|---|
| **C-3.1** | Reviewing a card removes it from the due queue and DOES NOT shrink the active list. |
| **C-3.2** | ID collision-free across 100 mixed create-card / deck-add operations. |
| **C-3.3** | `JsonStore.save()` + `JsonStore.load()` round-trips all 12 Card fields, including `tones` (list[int]). |
| **C-3.4** | `parse_guia_html(default_path)` from any CWD yields 50 cards / 11 categories. |
| **C-3.5** | For every card parsed from the deck, `audio_path(<card_id>)` resolves to an existing file. |
| **C-3.6** | `JsonStore` is schema-versioned; old payloads missing `version` are read back with version=1 defaults so the existing data is not lost. |

## Why FSRS and not SM-2

The codebase uses a small, deterministic FSRS variant. It is simpler to test,
does not require supermemo state vectors, and matches the contract that
`repetitions=0 → interval=1, repetitions=1 → interval=6, repetitions>=2 →
interval=int(prev*ease)`. Wikipedia "SuperMemo-2 algorithm" does not produce
the `1 → 6` jump the FSRS spec defines, so unit tests can rely on the exact
6-day interval after the first successful review.

## Persistence location

By default, cards live at `~/.lingua/cards.json` so a single install survives
across worktrees and CLI runs. The UI passes an explicit `path` to share
state with the `lingua.vocab.store` callers in tests.
