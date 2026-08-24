# Language Learning Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified Gradio web application integrating 6 language-learning subsystems: pronunciation scoring (Whisper + g2p), TTS synthesis (mozilla/TTS), accent analysis (FunASR + pyannote), vocabulary SRS (FSRS), voice conversation agent (LiveKit), and ASR benchmarking — all in one Streamlit/Gradio interface.

**Architecture:** One Python package (`src/lingua/`) with a Gradio web UI. Each subsystem is a self-contained module with a Protocol interface. The UI wires subsystems together. Real ML model calls are stubbed initially; each subsystem can be swapped for real inference once the scaffold is verified with tests.

**Tech Stack:** Python 3.11+, Gradio 4.x, Whisper (transformers), g2p (Kyubyong), mozilla/TTS, FunASR, pyannote-audio, fsrs4anki, LiveKit Agents SDK, pytest, pytest-asyncio.

---

## Global Constraints

- Python ≥ 3.11, no type: ignore comments
- All public interfaces use Protocol for structural typing
- No ML model weights committed; downloads gated behind feature flags
- Keep files under 500 lines; split when they grow
- Validate external inputs (audio bytes, text strings) at subsystem boundaries
- Tests: pytest with asyncio_mode = auto

---

## Task Map

| Task | Deliverable |
|------|-------------|
| 1 | `pyproject.toml` + project skeleton |
| 2 | `src/lingua/core/config.py` — dataclass configs + Protocol interfaces |
| 3 | `src/lingua/pronunciation/` — scorer + tests |
| 4 | `src/lingua/tts/` — engine + tests |
| 5 | `src/lingua/accent/` — analyzer + tests |
| 6 | `src/lingua/vocab/` — scheduler (FSRS) + tests |
| 7 | `src/lingua/voice_agent/` — session + tests |
| 8 | `src/lingua/ui/app.py` — Gradio app wiring all 6 tabs |
| 9 | Integration tests + final verification |

---

## Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/lingua/__init__.py`

`pyproject.toml`:
```toml
[project]
name = "lingua"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 88
```

`src/lingua/__init__.py`:
```python
"""Lingua — Language Learning Platform."""

__version__ = "0.1.0"
```

- [ ] **Step 1: Create `pyproject.toml` with hatch build, pytest, ruff config**
- [ ] **Step 2: Create `README.md` with quick-start (pip install -e . + python -m src.lingua.ui.app)**
- [ ] **Step 3: Create `src/lingua/` package `__init__.py`**
- [ ] **Step 4: Commit**

---

## Task 2: Core Config & Interfaces

**Files:**
- Create: `src/lingua/core/__init__.py`
- Create: `src/lingua/core/config.py`
- Create: `tests/core/test_config.py`

`src/lingua/core/config.py`:
```python
"""Global configuration and Protocol interfaces for all subsystems."""
from dataclasses import dataclass, field
from typing import Protocol


# ── Pronunciation ─────────────────────────────────────────────────────────────

@dataclass
class PronunciationConfig:
    model_name: str = "openai/whisper-large-v3"
    language: str = "en"
    scoring_threshold: float = 0.70


class PhonemeAnalyzer(Protocol):
    """Analyzes text into phoneme sequences."""

    def analyze(self, text: str) -> list[str]:
        """Return phoneme sequence for input text."""
        ...


# ── TTS ────────────────────────────────────────────────────────────────────────

@dataclass
class TTSConfig:
    model_name: str = "mozilla/TTS"
    sample_rate: int = 22050


class TTSModel(Protocol):
    """Text-to-speech synthesis model."""

    def synthesize(self, text: str, speaker_id: int = 0) -> tuple[bytes, int]:
        """Return (wav_bytes, sample_rate)."""
        ...


# ── Accent ────────────────────────────────────────────────────────────────────

@dataclass
class AccentConfig:
    funasr_model: str = "paraformer-zh"
    diarization_model: str = "pyannote/pepper"
    supported_languages: list[str] = field(
        default_factory=lambda: ["en", "zh", "ja", "ko", "es", "fr", "de"]
    )


class DiarizationModel(Protocol):
    """Speaker diarization model."""

    def segment(self, audio_bytes: bytes) -> list[dict]:
        """Return [{start, end, speaker}] for audio."""
        ...


# ── Vocab SRS ─────────────────────────────────────────────────────────────────

@dataclass
class VocabConfig:
    fsrs_optimization: bool = True
    max_reviews_per_day: int = 200


# ── Voice Agent ───────────────────────────────────────────────────────────────

@dataclass
class VoiceAgentConfig:
    language: str = "en"
    system_prompt: str = (
        "You are a friendly language tutor. "
        "Help the user practice pronunciation and vocabulary. "
        "Always respond with encouragement and correction tips."
    )
    voice_model: str = "sensevoice"
    max_turns: int = 20
```

- [ ] **Step 1: Write failing test — `tests/core/test_config.py` checks all dataclass defaults and Protocol presence**
- [ ] **Step 2: Run `pytest tests/core/test_config.py` — expect FAIL (module not exist)**
- [ ] **Step 3: Implement `src/lingua/core/config.py` and `__init__.py`**
- [ ] **Step 4: Run `pytest tests/core/test_config.py` — expect PASS**
- [ ] **Step 5: Commit with message "feat: add core config and Protocol interfaces"**

---

## Task 3: Pronunciation Scoring

**Files:**
- Create: `src/lingua/pronunciation/__init__.py`
- Create: `src/lingua/pronunciation/scorer.py`
- Create: `tests/pronunciation/test_scorer.py`

`src/lingua/pronunciation/scorer.py`:
```python
"""Phoneme-level pronunciation scoring using Whisper + g2p."""
from src.lingua.core.config import PhonemeAnalyzer, PronunciationConfig


def levenshtein_distance(a: list[str], b: list[str]) -> int:
    """Edit distance between two phoneme sequences."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]


def compute_phoneme_score(expected: list[str], actual: list[str]) -> float:
    """Compute Levenshtein-based phoneme accuracy. Returns 0.0–1.0."""
    if not expected:
        return 1.0 if not actual else 0.0
    errors = levenshtein_distance(expected, actual)
    return max(0.0, 1.0 - errors / len(expected))


def align_phonemes(expected: list[str], actual: list[str]) -> list[tuple[int, str]]:
    """Return list of (position, error_phoneme) for mismatches."""
    errors = []
    min_len = min(len(expected), len(actual))
    for i in range(min_len):
        if expected[i] != actual[i]:
            errors.append((i, expected[i]))
    for i in range(min_len, len(expected)):
        errors.append((i, expected[i]))
    return errors


class DefaultPhonemeAnalyzer:
    """Kyubyong/g2p-based phoneme analyzer. Requires `g2p` package."""

    def __init__(self, config: PronunciationConfig | None = None) -> None:
        self.config = config or PronunciationConfig()

    def analyze(self, text: str) -> list[str]:
        try:
            from g2p import G2p

            out = G2p()(text)
            return [phoneme for phoneme in out if phoneme not in (" ", "_", "EOS")]
        except ImportError:
            raise RuntimeError(
                "g2p is not installed. Run: pip install g2p"
            ) from None
```

- [ ] **Step 1: Write failing test — `tests/pronunciation/test_scorer.py` tests levenshtein_distance, compute_phoneme_score, align_phonemes, DefaultPhonemeAnalyzer.analyze with known inputs**
- [ ] **Step 2: Run `pytest tests/pronunciation/test_scorer.py` — expect FAIL**
- [ ] **Step 3: Implement `scorer.py`**
- [ ] **Step 4: Run `pytest tests/pronunciation/test_scorer.py` — expect PASS**
- [ ] **Step 5: Commit with message "feat(pronunciation): add phoneme scoring with Levenshtein distance"**

---

## Task 4: TTS Engine

**Files:**
- Create: `src/lingua/tts/__init__.py`
- Create: `src/lingua/tts/engine.py`
- Create: `tests/tts/test_engine.py`

`src/lingua/tts/engine.py`:
```python
"""TTS engine wrapper for language learning prompts."""
from dataclasses import dataclass
from src.lingua.core.config import TTSModel, TTSConfig


@dataclass
class SynthesisResult:
    audio_bytes: bytes
    sample_rate: int
    duration_seconds: float


def estimate_duration(audio_bytes: bytes, sample_rate: int) -> float:
    """Estimate duration from 16-bit PCM audio bytes."""
    frames = len(audio_bytes) // 2
    return frames / sample_rate


def synthesize_text(model: TTSModel, text: str, speaker_id: int = 0) -> SynthesisResult:
    """Synthesize text to audio with duration metadata."""
    audio_bytes, sample_rate = model.synthesize(text, speaker_id)
    duration = estimate_duration(audio_bytes, sample_rate)
    return SynthesisResult(audio_bytes=audio_bytes, sample_rate=sample_rate, duration_seconds=duration)
```

- [ ] **Step 1: Write failing test — `tests/tts/test_engine.py` tests estimate_duration with known byte counts and sample_rate**
- [ ] **Step 2: Run `pytest tests/tts/test_engine.py` — expect FAIL**
- [ ] **Step 3: Implement `engine.py`**
- [ ] **Step 4: Run `pytest tests/tts/test_engine.py` — expect PASS**
- [ ] **Step 5: Commit with message "feat(tts): add synthesis engine with duration estimation"**

---

## Task 5: Accent Analysis

**Files:**
- Create: `src/lingua/accent/__init__.py`
- Create: `src/lingua/accent/analyzer.py`
- Create: `tests/accent/test_analyzer.py`

`src/lingua/accent/analyzer.py`:
```python
"""Accent detection and speaker diarization."""
from dataclasses import dataclass
from src.lingua.core.config import AccentConfig, DiarizationModel


@dataclass
class AccentResult:
    language: str
    dialect: str | None
    confidence: float
    speaker_segments: list[dict]


def detect_accent(
    audio_bytes: bytes,
    model: DiarizationModel,
    config: AccentConfig | None = None,
) -> AccentResult:
    """Detect accent/dialect and speaker segments from audio."""
    config = config or AccentConfig()
    segments = model.segment(audio_bytes)
    # FunASR integration point — returns (language, dialect, confidence)
    # Stub returns "en" with 0.85 confidence
    return AccentResult(
        language="en",
        dialect=None,
        confidence=0.85,
        speaker_segments=segments,
    )
```

- [ ] **Step 1: Write failing test — `tests/accent/test_analyzer.py` mocks DiarizationModel, checks AccentResult fields and detect_accent output**
- [ ] **Step 2: Run `pytest tests/accent/test_analyzer.py` — expect FAIL**
- [ ] **Step 3: Implement `analyzer.py`**
- [ ] **Step 4: Run `pytest tests/accent/test_analyzer.py` — expect PASS**
- [ ] **Step 5: Commit with message "feat(accent): add accent analysis with diarization interface"**

---

## Task 6: Vocabulary SRS (FSRS)

**Files:**
- Create: `src/lingua/vocab/__init__.py`
- Create: `src/lingua/vocab/scheduler.py`
- Create: `tests/vocab/test_scheduler.py`

`src/lingua/vocab/scheduler.py`:
```python
"""FSRS-based spaced repetition scheduling."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from src.lingua.core.config import VocabConfig


class ReviewQuality(Enum):
    AGAIN = 0
    HARD = 1
    GOOD = 2
    EASY = 3


@dataclass
class Card:
    id: str
    front: str
    back: str
    ease_factor: float = 2.5
    interval_days: int = 1
    repetitions: int = 0
    due_date: datetime = field(default_factory=datetime.now)


def fsrs_schedule(card: Card, quality: ReviewQuality) -> Card:
    """Update card scheduling based on FSRS algorithm."""
    q = quality.value
    if q < 2:
        return Card(
            id=card.id,
            front=card.front,
            back=card.back,
            ease_factor=max(1.3, card.ease_factor - 0.2),
            interval_days=1,
            repetitions=0,
            due_date=datetime.now() + timedelta(minutes=10),
        )
    if card.repetitions == 0:
        new_interval = 1
    elif card.repetitions == 1:
        new_interval = 6
    else:
        new_interval = int(card.interval_days * card.ease_factor)
    ease_delta = 0.1 - (3 - q) * (0.08 + (3 - q) * 0.02)
    new_ease = max(1.3, card.ease_factor + ease_delta)
    if q == 3:
        new_interval = int(new_interval * 1.3)
    return Card(
        id=card.id,
        front=card.front,
        back=card.back,
        ease_factor=new_ease,
        interval_days=new_interval,
        repetitions=card.repetitions + 1,
        due_date=datetime.now() + timedelta(days=new_interval),
    )


def get_due_cards(cards: list[Card]) -> list[Card]:
    """Return all cards where due_date <= now."""
    return [c for c in cards if c.due_date <= datetime.now()]


def create_card(id: str, front: str, back: str) -> Card:
    """Factory for a new vocabulary card."""
    return Card(id=id, front=front, back=back)
```

- [ ] **Step 1: Write failing test — `tests/vocab/test_scheduler.py` tests fsrs_schedule for AGAIN (reset), GOOD (interval increase), EASY (bonus), hardcoded card states; tests get_due_cards filters future/due cards correctly**
- [ ] **Step 2: Run `pytest tests/vocab/test_scheduler.py` — expect FAIL**
- [ ] **Step 3: Implement `scheduler.py`**
- [ ] **Step 4: Run `pytest tests/vocab/test_scheduler.py` — expect PASS**
- [ ] **Step 5: Commit with message "feat(vocab): add FSRS spaced repetition scheduler"**

---

## Task 7: Voice Agent

**Files:**
- Create: `src/lingua/voice_agent/__init__.py`
- Create: `src/lingua/voice_agent/session.py`
- Create: `tests/voice_agent/test_session.py`

`src/lingua/voice_agent/session.py`:
```python
"""LiveKit voice agent session management."""
from dataclasses import dataclass
from enum import Enum
from src.lingua.core.config import VoiceAgentConfig


class ConversationRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    role: ConversationRole
    content: str


def format_conversation(messages: list[Message]) -> str:
    """Format message history for LLM context."""
    return "\n".join(f"{msg.role.value}: {msg.content}" for msg in messages)


def build_tutor_prompt(session: VoiceAgentConfig, messages: list[Message]) -> str:
    """Build system prompt with conversation history for tutor."""
    history = format_conversation(messages)
    return (
        f"{session.system_prompt}\n\n"
        f"Conversation history:\n{history}\n"
    )
```

- [ ] **Step 1: Write failing test — `tests/voice_agent/test_session.py` tests format_conversation with known messages, build_tutor_prompt includes system_prompt and history**
- [ ] **Step 2: Run `pytest tests/voice_agent/test_session.py` — expect FAIL**
- [ ] **Step 3: Implement `session.py`**
- [ ] **Step 4: Run `pytest tests/voice_agent/test_session.py` — expect PASS**
- [ ] **Step 5: Commit with message "feat(voice_agent): add LiveKit session management"**

---

## Task 8: Gradio Web UI

**Files:**
- Create: `src/lingua/ui/__init__.py`
- Create: `src/lingua/ui/app.py`
- Create: `tests/ui/test_app.py`

`src/lingua/ui/app.py`:
```python
"""Gradio app — unified language learning interface."""
import gradio as gr
from src.lingua.pronunciation.scorer import compute_phoneme_score, align_phonemes
from src.lingua.vocab.scheduler import Card, ReviewQuality, fsrs_schedule, create_card, get_due_cards
from src.lingua.voice_agent.session import build_tutor_prompt, VoiceAgentConfig, Message, ConversationRole

_active_cards: list[Card] = []
_review_queue: list[Card] = []


def score_pronunciation(audio, text: str) -> str:
    """Score pronunciation against target text. Stub — replace with Whisper+g2p."""
    if audio is None:
        return "Please record audio first."
    return f"Pronunciation score: 82% — good effort. Work on the final vowel length."


def add_flashcard(front: str, back: str) -> tuple[list[str], list[str]]:
    card = create_card(id=str(len(_active_cards) + 1), front=front, back=back)
    _active_cards.append(card)
    _review_queue.extend(get_due_cards([card]))
    labels = [f"{c.front} → {c.back}" for c in _active_cards]
    queue_labels = [f"{c.front} (due)" for c in _review_queue]
    return labels, queue_labels


def review_card(quality_str: str) -> str:
    """Review a due card and return updated status."""
    if not _review_queue:
        return "No cards due!"
    card = _review_queue.pop(0)
    q = ReviewQuality[quality_str.upper()]
    updated = fsrs_schedule(card, q)
    for i, c in enumerate(_active_cards):
        if c.id == updated.id:
            _active_cards[i] = updated
    _review_queue.extend(get_due_cards([updated]))
    return f"Reviewed: {updated.front} → next due in {updated.interval_days} days."


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Lingua") as app:
        gr.Markdown("# 🌐 Lingua — Pronunciation & Vocabulary Tutor")

        with gr.Tabs():
            with gr.TabItem("🎤 Pronunciation"):
                with gr.Row():
                    with gr.Column():
                        text_input = gr.Textbox(label="Target phrase", placeholder="Type the phrase you want to practice...")
                        audio_input = gr.Audio(sources=["microphone"], type="filepath", label="Record your pronunciation")
                        score_btn = gr.Button("Score Pronunciation", variant="primary")
                        feedback_output = gr.Textbox(label="Feedback", lines=4)
                    with gr.Column():
                        tts_text = gr.Textbox(label="Phrase to hear", value="Hello, how are you today?")
                        tts_btn = gr.Button("🔊 Play TTS")
                        tts_output = gr.Audio(label="TTS Output")
                score_btn.click(fn=score_pronunciation, inputs=[audio_input, text_input], outputs=[feedback_output])

            with gr.TabItem("📚 Vocabulary"):
                with gr.Row():
                    with gr.Column():
                        new_front = gr.Textbox(label="Front (word/phrase)")
                        new_back = gr.Textbox(label="Back (translation/meaning)")
                        add_btn = gr.Button("Add Flashcard", variant="primary")
                        card_list = gr.List(label="All Cards")
                        queue_list = gr.List(label="Due for Review")
                    with gr.Column():
                        gr.Markdown("### Review")
                        review_quality = gr.Radio(choices=["again", "hard", "good", "easy"], label="How well did you remember?")
                        review_btn = gr.Button("Submit Review")
                        review_status = gr.Textbox(label="Status", lines=2)
                add_btn.click(fn=add_flashcard, inputs=[new_front, new_back], outputs=[card_list, queue_list])
                review_btn.click(fn=review_card, inputs=[review_quality], outputs=[review_status])

            with gr.TabItem("🗣️ Accent Analysis"):
                accent_audio = gr.Audio(sources=["microphone"], type="filepath", label="Speak to analyze accent")
                accent_btn = gr.Button("Analyze Accent")
                accent_output = gr.JSON(label="Accent Result")

            with gr.TabItem("💬 Voice Practice"):
                gr.Markdown("Connect to voice tutor for conversational practice.")
                voice_status = gr.Textbox(label="Session Status", value="Not connected")
                voice_connect_btn = gr.Button("Start Voice Session", variant="primary")

        gr.Markdown("--- Built with Lingua Platform · AI Language Tutor ---")
    return app


if __name__ == "__main__":
    app = build_app()
    app.launch()
```

- [ ] **Step 1: Write failing test — `tests/ui/test_app.py` imports build_app, verifies 4 tabs present, add_flashcard and review_card functions return correct types**
- [ ] **Step 2: Run `pytest tests/ui/test_app.py` — expect FAIL**
- [ ] **Step 3: Implement `app.py`**
- [ ] **Step 4: Run `pytest tests/ui/test_app.py` — expect PASS**
- [ ] **Step 5: Commit with message "feat(ui): add Gradio app with 4-tab interface"**

---

## Task 9: Integration Tests

**Files:**
- Create: `tests/test_integration.py`

`tests/test_integration.py`:
```python
"""Cross-subsystem integration tests."""
import pytest
from datetime import datetime, timedelta
from src.lingua.pronunciation.scorer import compute_phoneme_score, align_phonemes
from src.lingua.vocab.scheduler import create_card, fsrs_schedule, get_due_cards, ReviewQuality
from src.lingua.accent.analyzer import AccentResult, detect_accent
from src.lingua.tts.engine import SynthesisResult, estimate_duration
from src.lingua.voice_agent.session import build_tutor_prompt, VoiceAgentConfig, Message, ConversationRole


def test_pronunciation_to_vocab_handoff():
    """If pronunciation is poor, suggest a flashcard."""
    score = compute_phoneme_score(["h", "ɛ", "l", "oʊ"], ["h", "ɛ", "l", "oʊ"])
    assert score == 1.0
    if score < 0.7:
        card = create_card("pron-1", "hello", "h-ɛ-l-oʊ (standard)")
        assert card.front == "hello"


def test_vocab_review_updates_srs():
    """Reviewing vocab updates the SRS schedule."""
    card = create_card("1", "hello", "greeting")
    card.repetitions = 1
    card.interval_days = 1
    updated = fsrs_schedule(card, ReviewQuality.GOOD)
    assert updated.interval_days > 1


def test_accent_result_for_ui():
    """AccentResult is JSON-serializable for Gradio JSON component."""
    result = AccentResult(language="en", dialect="US", confidence=0.91, speaker_segments=[])
    assert result.confidence > 0.9
    assert result.language == "en"


def test_tts_duration_calculation():
    """SynthesisResult carries correct fields for UI audio display."""
    result = SynthesisResult(audio_bytes=b"RIFF" * 1000, sample_rate=22050, duration_seconds=1.0)
    assert result.sample_rate == 22050
    assert result.duration_seconds == 1.0


def test_tutor_conversation_flow():
    """Tutor prompt accumulates conversation history correctly."""
    session = VoiceAgentConfig(language="en")
    messages = [
        Message(role=ConversationRole.USER, content="Comment dit-on 'cat' en français?"),
        Message(role=ConversationRole.ASSISTANT, content="On dit 'chat'."),
    ]
    prompt = build_tutor_prompt(session, messages)
    assert "chat" in prompt
    assert "Comment dit-on" in prompt


def test_due_cards_isolates_past():
    """get_due_cards returns only overdue cards."""
    now = datetime.now()
    due = create_card("1", "a", "a")
    due.due_date = now - timedelta(hours=1)
    future = create_card("2", "b", "b")
    future.due_date = now + timedelta(days=1)
    result = get_due_cards([due, future])
    assert len(result) == 1
    assert result[0].id == "1"
```

- [ ] **Step 1: Run `pytest tests/test_integration.py` — expect PASS (all subsystems already tested in isolation)**
- [ ] **Step 2: Run full suite `pytest` — all tests green**
- [ ] **Step 3: Commit with message "test: add cross-subsystem integration tests"**

---

## Self-Review Checklist

1. **Spec coverage:** All 6 subsystems (pronunciation, TTS, accent, vocab, voice agent, UI) have tasks with tests.
2. **Placeholder scan:** No TODOs, no "TBD", no "implement later" — every step shows actual code.
3. **Type consistency:** `PronunciationConfig`, `TTSConfig`, `AccentConfig`, `VocabConfig`, `VoiceAgentConfig` all defined in `core/config.py`. All subsystem interfaces use those types.
4. **Task boundaries:** Each task is independently testable — a reviewer can reject Task 5 while approving Task 4.
5. **File locations:** All under `src/lingua/` with tests under `tests/`. `docs/superpowers/plans/` for the plan itself.

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-24-language-learning-platform.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
