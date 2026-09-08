# Interoperability Contract — pronunciation × tts × accent × voice_agent × vocab

> **Status:** canonical. The F7 unified-interface rebuild (`src/lingua/ui/app.py` →
> `src/lingua/ui/features/*.py`) references this document. Where a feature spec
> (`docs/features/0X-*/spec.md`) and this document disagree about a *cross-subsystem*
> boundary, this document wins; where they disagree about a subsystem's *internals*,
> the feature spec wins.

## 0. Why this document exists

Today the five subsystems are five islands. `ui/app.py` has one tab per subsystem and
zero data flow between them: the Pronunciation tab scores a phrase the user types by
hand; the Vocabulary tab schedules cards that nothing ever listens to; the Accent tab
analyses audio that no card asked for; the Voice tab tries to connect to LiveKit and
fails. The user's requirement — *"interoperabilidade entre algumas feats pra serem
unificadas"* — is that these become **one loop**:

> **vocab decides *what* to practice → tts/deck audio presents it → the user speaks →
> pronunciation + accent decide *how well* → vocab records the result and decides what
> comes next.**

The voice tutor (`voice_agent`) is that same loop driven conversationally instead of
by button clicks.

This document defines the three things that make the loop possible:
1. the **flows** (Section 1) — what actually happens, in order;
2. the **shared state** (Section 2) — the one object that crosses every boundary;
3. the **audio shape** (Section 3) — the one representation every subsystem accepts.

Everything else (Sections 4–8) is wiring, failure, and scope.

---

## Section 1 — Use-case flows

### Flow A — Solo pronunciation drill (button-driven)

The core loop. No conversation, no LLM, no network beyond TTS. This is the flow that
must work first, because Flow B is Flow A with a tutor wrapped around it.

| # | Step | Owner | Call |
|---|---|---|---|
| A1 | User opens the Practice tab; the due queue is computed | `vocab` | `get_due_cards(store.load())` |
| A2 | User picks (or "Next"s into) a card | `vocab` | `SessionContext.target_card = card` |
| A3 | Reference audio plays | `vocab` deck asset, `tts` fallback | `deck.audio_path(card.id)` → if `None`, `tts.synthesize(card.front)` |
| A4 | User records themselves | UI | `gr.Audio(sources=["microphone"], type="filepath")` |
| A5 | ASR + phoneme score | `pronunciation` | `get_whisper_scorer().score(user_audio, card.front)` |
| A6 | Per-syllable check + corrections | `accent` | `get_accent_checker().check(AccentCheckRequest(...))` |
| A7 | Map score → `ReviewQuality` | **interop layer** (see below) | `quality_from_score(overall)` |
| A8 | FSRS advance + persist | `vocab` | `fsrs_schedule(card, quality)` → `store.save(cards)` |
| A9 | UI updates: score badge, per-syllable diff, corrections, new due count | UI | — |

**Scoring → quality mapping (the single interop decision that binds the two halves).**
This function is the *only* place a pronunciation score becomes an SRS grade. It lives
in `lingua/core/interop.py`, not in `vocab` (which must stay ignorant of audio) and not
in `pronunciation` (which must stay ignorant of SRS).

```python
def quality_from_score(score: float, threshold: float = 70.0) -> ReviewQuality:
    """Map a 0..100 pronunciation score to an FSRS grade.

    threshold comes from PronunciationConfig.scoring_threshold (0..1, scaled ×100).
    """
    if score < threshold:
        return ReviewQuality.AGAIN     # stays in the due queue, interval resets
    if score < threshold + 10:
        return ReviewQuality.HARD
    if score < 95.0:
        return ReviewQuality.GOOD
    return ReviewQuality.EASY
```

Consequences, stated as contracts:
- **A-1** `score < threshold` ⇒ `ReviewQuality.AGAIN` ⇒ `fsrs_schedule` returns a card
  with `interval_days == 1` and `due_date ≈ now + 10min` ⇒ the card **reappears in the
  due queue in this session**. This is the "stays in due queue, shows corrections"
  requirement.
- **A-2** `score ≥ threshold` ⇒ interval advances per FSRS ⇒ the card leaves the queue.
- **A-3** A failed *score* (exception, missing model, empty audio) is **not** a failed
  *review*: `fsrs_schedule` is never called, the card is untouched, and the UI shows a
  retry affordance. See Section 5.
- **A-4** Corrections are shown on **every** review, not only failures — a `GOOD` with
  one weak syllable still surfaces that syllable's hint.

The user may also override the machine grade with the manual `again/hard/good/easy`
radio. When they do, the manual grade wins and the score is recorded as advisory only.

### Flow B — Voice tutor conversation class

Flow A, driven by the tutor rather than by buttons. The critical requirement: **the
tutor's target words come from the vocab due-set, never from a random word list.**

| # | Step | Owner | Detail |
|---|---|---|---|
| B1 | User clicks "Start conversation class" | `voice_agent` | `OfflineTutor(config)` created; `SessionContext` initialised with `turn_number = 0` |
| B2 | Tutor selects the turn's target | `voice_agent` **reads** `vocab` | `ctx.target_card = tutor.pick_target(due_cards)` — first unseen due card this session; falls back to lowest-scoring card already seen; falls back to `None` (free conversation) when the queue is empty |
| B3 | Tutor utters the prompt | `tts` | `synthesize("请跟我读: " + card.front)` → WAV path → `gr.Audio(autoplay=True)` |
| B4 | Turn appended to history | `voice_agent` | `Message(role=ConversationRole.ASSISTANT, content=...)` |
| B5 | User speaks | UI | push-to-talk → `ctx.user_audio` |
| B6 | Transcribe + score | `pronunciation` | fills `ctx.transcription`, `ctx.pronunciation_score` |
| B7 | Per-syllable check | `accent` | fills `ctx.accent_corrections`, `ctx.diff_html` |
| B8 | Grade the card | `vocab` | same `quality_from_score` → `fsrs_schedule` → `store.save` |
| B9 | Tutor replies | `voice_agent` + `tts` | encouragement templated from the score band + the first correction; `Message(role=USER, ...)` then `Message(role=ASSISTANT, ...)` appended |
| B10 | `turn_number += 1`; loop to B2 | `voice_agent` | until `turn_number >= VoiceAgentConfig.max_turns` or the user stops |
| B11 | Session summary | `voice_agent` | mean score, per-card best/worst, cards graded `AGAIN`, total turns |

Contracts:
- **B-1** The tutor's target selection reads the *live* due queue at each turn — a card
  graded `AGAIN` in turn *n* is eligible again in turn *n+k*.
- **B-2** N user turns produce N+1 assistant turns (opening prompt + one reply per turn).
  This matches contract C-6.6 in the plan.
- **B-3** Every turn writes through to `JsonStore`. Closing the browser mid-class must
  not lose graded reviews.
- **B-4** With an empty due queue the tutor degrades to free conversation and grades
  nothing. It never invents a card.
- **B-5** The tutor is **offline** (F6a): no LiveKit, no `asyncio.get_event_loop()`. The
  turn loop is driven by Gradio events, not by an async transport.

### Flow C — At-words training (constrained ASR)

The user reads a sentence built only from words they are currently learning, and ASR is
biased toward those words so that a near-miss is scored as the intended word rather than
silently re-transcribed into an unrelated homophone.

1. `vocab` supplies the **at-words set**: `{c.front for c in active_cards}` (optionally
   narrowed to the due set).
2. `voice_agent` composes a target sentence from that set (template-based in F7 — no
   generative sentence construction is in scope).
3. `pronunciation` transcribes with a **bias hint**: Whisper's `initial_prompt`
   parameter is set to the space-joined at-words set, truncated to 200 characters
   (Whisper's prompt window is small and a long prompt degrades accuracy).
   ```python
   scorer.score(user_audio, target_text, bias_words=list(at_words))
   # → whisper.transcribe(..., language="zh", initial_prompt=" ".join(bias_words)[:200])
   ```
4. `accent` checks per-syllable against the composed sentence exactly as in Flow A.
5. Grading applies **per word**, not per sentence: each at-word that appears in the
   sentence receives its own `ReviewQuality` from the syllables that belong to it.

Contracts:
- **C-1** `bias_words` is optional and additive. Omitting it must produce the same
  behaviour as today (no regression for Flows A and B).
- **C-2** True class-based decoding bias (LM shallow fusion) is **out of scope**;
  `initial_prompt` prefixing is the F7 implementation. The signature is designed so a
  real biased decoder can be swapped in behind it later.
- **C-3** A word in the sentence that is *not* in the at-words set is scored but never
  graded — it cannot create a card.

---

## Section 2 — Shared state contract

### 2.1 `SessionContext`

One mutable object per practice/conversation session, owned by the UI layer, passed by
reference into every subsystem adapter. It lives in `src/lingua/core/interop.py`.

```python
# src/lingua/core/interop.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lingua.vocab.scheduler import Card, ReviewQuality
from lingua.voice_agent.session import Message


@dataclass
class SessionContext:
    """Mutable state shared across pronunciation, tts, accent, voice_agent and vocab
    for the duration of one practice or conversation session.

    Not persisted. Not thread-safe. One instance per Gradio session (held in
    ``gr.State``), never a module global.
    """

    # ── target (owned by vocab / voice_agent) ─────────────────────────────
    target_card: Card | None = None
    target_pinyin: str = ""
    target_audio: Path | None = None

    # ── user input (owned by the UI) ──────────────────────────────────────
    user_audio: Path | None = None

    # ── analysis (owned by pronunciation / accent) ────────────────────────
    transcription: str = ""
    pronunciation_score: float | None = None      # 0..100, None = not yet scored
    accent_score: float | None = None             # 0..100, per-syllable mean
    accent_corrections: list[str] = field(default_factory=list)
    diff_html: str = ""

    # ── conversation (owned by voice_agent) ───────────────────────────────
    conversation_history: list[Message] = field(default_factory=list)
    turn_number: int = 0

    # ── outcome (owned by vocab) ──────────────────────────────────────────
    last_quality: ReviewQuality | None = None
    error: str | None = None                      # soft-failure marker, see §5
```

Notes on shape:
- `target_pinyin` is denormalised from `Card.pinyin` because `accent` needs it even when
  the target came from a free-text box rather than a card (`target_card is None`).
- `pronunciation_score` and `accent_score` are **both** 0..100 and both retained. They
  measure different things (whole-utterance phoneme edit distance vs per-syllable ASR
  confidence) and the grading function consumes their combination:
  `overall = 0.5 * pronunciation_score + 0.5 * accent_score`, falling back to whichever
  is non-`None` when the other failed.
- `Message` is reused from `lingua.voice_agent.session` — do not define a second
  message type.

### 2.2 Ownership table

"Writes" means the subsystem is the *only* one permitted to assign that field.

| Field | Writes | Reads |
|---|---|---|
| `target_card` | `vocab` (Flow A), `voice_agent` (Flow B) | `tts`, `pronunciation`, `accent`, UI |
| `target_pinyin` | `vocab` (from `Card.pinyin`), `accent` (pypinyin fallback) | `accent`, UI |
| `target_audio` | `vocab` (deck asset), `tts` (synthesised fallback) | UI |
| `user_audio` | UI only | `pronunciation`, `accent` |
| `transcription` | `pronunciation` | `accent`, `voice_agent`, UI |
| `pronunciation_score` | `pronunciation` | interop grading, `voice_agent`, UI |
| `accent_score` | `accent` | interop grading, UI |
| `accent_corrections` | `accent` | `voice_agent` (reply text), UI |
| `diff_html` | `accent` | UI |
| `conversation_history` | `voice_agent` | UI |
| `turn_number` | `voice_agent` | `voice_agent`, UI |
| `last_quality` | `vocab` (via interop grading) | UI |
| `error` | any subsystem, on soft failure | UI |

Rules:
- **S-1** No subsystem writes a field it does not own. Violations are the mechanism by
  which the current `_review_queue = _active_cards` class of bug reappears.
- **S-2** No subsystem imports another subsystem. `pronunciation` must not import
  `vocab`; `vocab` must not import `tts`. All cross-talk goes through
  `lingua/core/interop.py` and the UI adapters. The only permitted exception is
  `accent` composing `pronunciation.whisper_scoring.WhisperPhonemeScorer`, which is an
  explicit reuse decision already recorded in the F5 spec.
- **S-3** `SessionContext` is never a module global and never persisted. Card state is
  persisted (by `JsonStore`); session state is not.
- **S-4** Every analysis step is idempotent with respect to the context: re-running
  `score()` on the same `user_audio` overwrites the score fields and nothing else.

### 2.3 Subsystem-facing adapter signatures

The six functions in `lingua/core/interop.py` that the UI calls. These are the whole
public interop surface.

```python
def load_target(ctx: SessionContext, card: Card, deck, tts_model=None) -> SessionContext:
    """Fill target_card / target_pinyin / target_audio. Clears prior analysis fields."""

def attach_recording(ctx: SessionContext, audio_path: str | Path) -> SessionContext:
    """Set user_audio, clear transcription/scores/corrections."""

def analyse(ctx: SessionContext, scorer, checker) -> SessionContext:
    """Run pronunciation.score then accent.check; fill all analysis fields.
    Never raises — sets ctx.error on soft failure."""

def overall_score(ctx: SessionContext) -> float | None:
    """Combine pronunciation_score and accent_score, or None if both failed."""

def quality_from_score(score: float, threshold: float = 70.0) -> ReviewQuality: ...

def commit_review(ctx: SessionContext, cards: list[Card], store,
                  quality: ReviewQuality | None = None) -> list[Card]:
    """Apply fsrs_schedule and persist. quality=None derives it from the score.
    Raises nothing; returns the updated card list unchanged on failure."""
```

---

## Section 3 — Audio I/O shape

**The rule: every audio value that crosses a subsystem boundary is a `Path` to a WAV
file on disk.** Raw bytes and NumPy arrays are internal to a subsystem. This is not an
aesthetic preference — it is what makes `SessionContext` serialisable into `gr.State`,
what makes the F5 `AccentCheckRequest(reference_audio: Path, user_audio: Path)`
signature work unchanged, and what avoids the double-WAV-wrapping bug (F-5) that
currently corrupts TTS output in `play_tts`.

| Producer | Native form | Sample rate | Boundary form |
|---|---|---|---|
| Deck reference audio (`palavras-essenciais/audio/*.mp3`) | MP3 on disk | 24 kHz mono (source) | decoded → WAV 24 kHz mono in the session temp dir |
| Phoneme catalog (`pinyin-completo/audio/*.wav`) | WAV on disk | as shipped | passed through as-is |
| `edge-tts` synthesis | MP3 byte stream | 24 kHz mono | decoded → WAV 24 kHz mono, temp file |
| Coqui synthesis (optional) | float32 array | `TTSConfig.sample_rate` (22050) | int16 WAV, temp file |
| User microphone (`gr.Audio(type="filepath")`) | WAV | browser-dependent | resampled → **WAV 16 kHz mono** |
| Whisper input | float32 mono | 16 kHz | consumes the WAV path directly |

Rules:
- **AU-1** Whisper resamples internally, but `pronunciation` and `accent` must be handed
  16 kHz mono WAV so both subsystems score the *same* signal. Resampling happens once,
  in `attach_recording`, not twice in two subsystems.
- **AU-2** `SynthesisResult.audio_bytes` is **already-encoded WAV**, not raw PCM. The
  current `play_tts` does `np.frombuffer(result.audio_bytes, dtype=np.int16)` and
  re-wraps it with `wavfile.write` — that treats a 44-byte RIFF header as 22 audio
  samples and produces a click plus a shifted waveform. F7 must write
  `result.audio_bytes` straight to the temp file. `estimate_duration` must likewise
  subtract the 44-byte header (contract C-2.2).
- **AU-3** Temp files live under one per-session directory
  (`tempfile.mkdtemp(prefix="lingua_")`), are named deterministically per card
  (`ref_<card_id>.wav`, `user_turn<N>.wav`) so a repeat play does not accumulate files,
  and the directory is registered in `launch(allowed_paths=[...])` (X4).
- **AU-4** No subsystem writes to the repository tree. Reference assets are read-only.
- **AU-5** MP3 decoding needs `ffmpeg` on `PATH` (already a Whisper prerequisite). If
  decoding fails, the deck audio degrades to a TTS-synthesised reference; if that also
  fails, `target_audio` is `None` and the UI hides the play control rather than
  erroring.

---

## Section 4 — Callback wiring (Gradio)

Every row is one Gradio event handler in `src/lingua/ui/features/*.py`. `ctx` is the
`gr.State`-held `SessionContext`; it is both an input and an output of every handler
that mutates it.

### 4.1 Practice tab (Flow A)

| User action | Handler | Subsystems fired | Reads from ctx | Writes to ctx | UI outputs updated |
|---|---|---|---|---|---|
| Tab load | `on_load` | `vocab` | — | — | due count, card table, first target |
| Click **Next card** / pick from due list | `on_pick_card` → `load_target` | `vocab` (`get_due_cards`), `deck.audio_path`, `tts` fallback | — | `target_card`, `target_pinyin`, `target_audio` | hanzi label, pinyin label, reference `gr.Audio`, progress bar, score badge cleared |
| Click **▶ Reference** | `on_play_reference` | `tts` (only if no deck asset) | `target_card`, `target_audio` | `target_audio` | reference `gr.Audio` |
| Stop recording (mic) | `on_record` → `attach_recording` | — (UI + resample) | — | `user_audio`; clears analysis fields | record indicator, **Score** button enabled |
| Click **Score** | `on_score` → `analyse` | `pronunciation.score`, `accent.check` | `target_card`, `user_audio` | `transcription`, `pronunciation_score`, `accent_score`, `accent_corrections`, `diff_html`, `error` | score badge, transcription box, per-syllable diff `gr.HTML`, corrections list, **Commit** enabled |
| Click **Commit** (or auto-commit) | `on_commit` → `commit_review` | `vocab.fsrs_schedule`, `JsonStore.save` | `pronunciation_score`, `accent_score`, `target_card` | `last_quality` | due count, card table, next/lapsed bucket, status line |
| Click a manual grade (`again/hard/good/easy`) | `on_manual_grade` | `vocab` only | `target_card` | `last_quality` | same as **Commit**; score badge annotated "manual" |
| Click **Retry** (after an `error`) | `on_retry` | — | — | clears `error`, `user_audio` | error banner hidden, mic re-armed |

### 4.2 Voice tab (Flow B)

| User action | Handler | Subsystems fired | UI outputs updated |
|---|---|---|---|
| Click **Start conversation** | `on_start_class` | `voice_agent` (`OfflineTutor`), `vocab` (due set), `tts` (greeting + first prompt) | chat log seeded, tutor `gr.Audio(autoplay=True)`, mic enabled, turn counter = 0, **Start** → **Stop** |
| Stop recording (push-to-talk) | `on_user_turn` | `pronunciation`, `accent`, `vocab` (grade+persist), `voice_agent` (append turns, pick next target), `tts` (reply) | chat log (user turn + tutor reply), score badge, corrections panel, tutor audio, turn counter, due count |
| Click **Skip word** | `on_skip` | `voice_agent`, `vocab` (no grade written) | chat log, new target, tutor audio |
| Click **Stop** | `on_end_class` | `voice_agent` (summary), `JsonStore` (final save) | summary panel (mean score, weakest syllables, cards graded AGAIN), mic disabled, **Stop** → **Start** |
| `turn_number == max_turns` | auto-fires `on_end_class` | as above | as above |

### 4.3 At-words tab (Flow C)

| User action | Handler | Subsystems fired | UI outputs updated |
|---|---|---|---|
| Click **Build sentence** | `on_build_sentence` | `vocab` (at-words set), `voice_agent` (template composer) | sentence display, at-words chips, reference `gr.Audio` (TTS) |
| Stop recording | `on_record` | — | **Score** enabled |
| Click **Score** | `on_score_sentence` | `pronunciation` (with `bias_words`), `accent` | per-word score table, diff HTML, corrections |
| Click **Commit all** | `on_commit_sentence` | `vocab` × N (one `fsrs_schedule` per at-word) | due count, card table, per-word grade chips |

### 4.4 Wiring invariants

- **W-1** Every handler takes `ctx` as its first input and returns it as its first
  output. No handler reads a module global for session state.
- **W-2** Handlers never construct subsystems. They call `lingua.core.registry`
  accessors (`get_store`, `get_deck`, `get_whisper_scorer`, `get_accent_checker`,
  `get_tts_model`, `get_tutor`). Importing a feature module loads no model (C-7.3).
- **W-3** A handler that can fail returns an `error` string in `ctx` plus a
  `gr.update(visible=True)` on the error banner. Handlers do not raise into Gradio.
- **W-4** `Score` and `Commit` are separate events. Auto-commit is a checkbox that
  chains them; it is never the only path, so a user can always inspect corrections
  before the card advances.

---

## Section 5 — Error propagation

The governing principle: **an analysis failure must never mutate SRS state, and an SRS
write failure must never be silent.**

| Failure | Detection | Behaviour | User sees |
|---|---|---|---|
| `pronunciation.score` raises or returns `{"error": ...}` | `analyse` catches | `pronunciation_score = None`; `accent` still attempted; **no** `fsrs_schedule`; card untouched | score badge "—", banner "Scoring failed — [Retry]" |
| Whisper model missing / download fails | `WhisperPhonemeScorer._load_model` | `ctx.error = "asr_unavailable"`; scoring disabled for the session; manual grading still available | banner "Speech recognition unavailable — you can still grade manually" |
| `accent.check` soft failure (`AccentCheckResult.error != None`) | `analyse` reads `.error` | `accent_score = None`; grading falls back to `pronunciation_score` alone | corrections panel "No per-syllable feedback for this attempt" |
| **Both** scores `None` | `overall_score()` returns `None` | `commit_review` refuses to derive a quality; requires manual grade | **Commit** disabled, hint "Grade manually to continue" |
| `tts.synthesize` fails (network, missing voice) | adapter catches | Flow A: falls back to deck audio, else hides play control. Flow B: **conversation pauses** — the turn is not consumed, `turn_number` does not advance | banner "TTS unavailable — [Retry] / [Continue without audio]" |
| MP3 decode fails (no `ffmpeg`) | decode helper | `target_audio = None`, reference playback hidden; scoring unaffected | play control absent, tooltip "Reference audio unavailable" |
| ASR times out in a voice turn (> 30 s) | `voice_agent` turn guard | Turn is abandoned, **not** graded; tutor re-prompts the same target; `turn_number` unchanged | tutor says "请再说一次" / "Say that once more" |
| `max_turns` reached | `voice_agent` | Session ends cleanly, final `store.save` runs | summary panel |
| `JsonStore.save` raises (disk full, permissions) | `commit_review` catches | **Loudest failure in the system.** In-memory card list keeps the updated card; a retry is scheduled on the next commit; the session is marked dirty | red persistent banner "Progress not saved — [Retry save]", not dismissible while dirty |
| `JsonStore.load` returns `[]` because the file is corrupt | `load` already swallows | The corrupt file is **renamed** to `cards.json.corrupt-<ts>` before an empty store is used, so user data is never overwritten in place | banner "Card file could not be read — a backup was kept" |

Contracts:
- **E-1** No code path calls `fsrs_schedule` when `overall_score()` is `None` and no
  manual grade was given.
- **E-2** `analyse` never raises. `commit_review` never raises.
- **E-3** A save failure never clears the in-memory card list, and never resets
  `dirty`. The dirty flag is the only thing standing between a transient disk error and
  lost reviews.
- **E-4** Failures are typed by a short machine key in `ctx.error`
  (`asr_unavailable`, `tts_unavailable`, `missing_audio:user`, `save_failed`, …) and
  rendered to prose in the UI layer, so tests assert on the key, not the sentence.

---

## Section 6 — Feature-flag matrix

Optional dependencies and what breaks without them. `edge-tts`, `openai-whisper`,
`scipy` and `pypinyin` are the *supported* baseline; `Coqui TTS`, `g2p`, `funasr` and
`livekit` are all optional or dropped.

| Capability | `edge-tts` | `openai-whisper` | `pypinyin` | `g2p` | Coqui `TTS` | `ffmpeg` |
|---|---|---|---|---|---|---|
| Deck reference playback (MP3 asset) | — | — | — | — | — | **required** (decode) |
| Phoneme-drill playback (WAV asset) | — | — | — | — | — | — |
| TTS tutor replies / synthesised reference | **required**¹ | — | — | — | optional alt | needed to decode MP3 |
| Whole-utterance pronunciation score | — | **required** | — | degraded² | — | required |
| Per-syllable accent check + corrections | — | **required** | degraded³ | fallback³ | — | required |
| Tone-specific correction hints | — | — | **required** | — | — | — |
| Voice conversation class (offline tutor) | required for spoken replies⁴ | **required** | degraded³ | — | — | required |
| At-words biased ASR | — | **required** | — | — | — | required |
| Vocab browsing / FSRS / manual grading | — | — | — | — | — | — |

¹ Without `edge-tts` the tutor falls back to Coqui if installed, else to text-only
replies (Flow B still runs, silently).
² Without `g2p`, `DefaultPhonemeAnalyzer` falls back to character-level splitting; the
phoneme score becomes a character edit distance — coarser, still monotone, still usable
for grading.
³ Without `pypinyin`, `SyllableScore.pinyin` degrades to the hanzi itself and `tone`
defaults to `5`; per-syllable scores and `diff_html` still render, but tone-specific
hints collapse to the generic "practise this syllable separately" message.
⁴ Text-only tutor replies are a legitimate degraded mode, not an error state.

Rules:
- **FF-1** Availability is declared per **capability**, not per tab. A tab whose primary
  capability is unavailable renders an explanatory panel plus whatever degraded
  capabilities remain (the Practice tab without Whisper still browses cards and grades
  manually).
- **FF-2** Availability checks are `importlib.util.find_spec` probes plus a binary probe
  for `ffmpeg`. They must not import the heavy package, and must be memoised for the
  process lifetime.
- **FF-3** `funasr` and `livekit` appear nowhere. `lingua.accent` importing `funasr` or
  `lingua.voice_agent` importing `livekit` is a test failure (C-5 / C-6.2), not a
  degraded mode.
- **FF-4** Every degraded mode is *silent-safe*: it produces a correct but coarser
  result, never a wrong one presented as precise. A degraded score is labelled as such
  in the UI.

---

## Section 7 — UI unification scope (the minimum F7 rebuild)

After F1–F6 land, `src/lingua/ui/app.py` shrinks to a shell and the tabs are
reorganised around **flows**, not around subsystems. This is the substantive change the
user asked for: the current five tabs mirror the package layout, which is why nothing
interoperates.

**New tab layout (4 tabs, down from 5):**

| Tab | Flow | Replaces |
|---|---|---|
| 🎯 **Practice** | Flow A + card browser | today's 📚 Vocabulary + 🎤 Pronunciation + 🗣️ Accent |
| 💬 **Class** | Flow B + Flow C | today's 💬 Voice Practice |
| 🔤 **Drills** | phoneme catalog (standalone, no interop) | today's 🔤 Phoneme Drills, unchanged |
| ⚙️ **Library** | deck browser, import, card CRUD, settings | the deck accordion inside today's Vocabulary tab |

**Files:**

```
src/lingua/core/interop.py          NEW  — SessionContext + the 6 adapter functions
src/lingua/core/registry.py         MOD  — add get_accent_checker, get_tts_model, get_tutor
src/lingua/core/audio.py            NEW  — to_wav16k(), decode_mp3(), session temp dir
src/lingua/ui/app.py                REWRITE (~70 lines) — Blocks shell, config, allowed_paths
src/lingua/ui/context.py            NEW  — AppContext (lazy accessors + feature flags)
src/lingua/ui/features/practice.py  NEW  — Flow A
src/lingua/ui/features/klass.py     NEW  — Flow B + C
src/lingua/ui/features/drills.py    NEW  — port of the existing drills tab
src/lingua/ui/features/library.py   NEW  — deck browser + card CRUD
src/lingua/ui/render.py             NEW  — HTML renderers (card list, diff, corrections)
```

**Minimum work, enumerated:**
1. Write `core/interop.py` and `core/audio.py` — both pure, both unit-testable without
   Gradio.
2. Add the three missing registry accessors.
3. Replace the module globals in `app.py` (`_store`, `_active_cards`, `_review_queue`,
   `_whisper_scorer`, `_voice_session`, `_current_review_card`) with `gr.State` +
   registry accessors. `_review_queue = _active_cards` (F-8) dies here.
4. Split the five tab bodies into four feature modules, each exposing
   `build_tab(ctx: AppContext) -> None` and `available() -> bool`.
5. Rewrite `play_tts` to stop double-wrapping WAV (AU-2).
6. Move every inline `<audio src=...>` string in `_render_deck_card_list` to
   `gr.Audio` values or `allowed_paths`-served URLs (X4/F-10).
7. `build_app(config: AppConfig)` calls `registry.set_config(config)` and applies
   `config.title`.

**Explicitly not part of F7:** restyling, theming, the phoneme-drill tab's internals,
and porting `pinyin-completo/js/*`.

**Acceptance:**
- `pytest tests/ui tests/platform -v` green; `pytest -q` shows no new skips.
- `python -m lingua --port 7860` launches from any CWD with no eager model load.
- A full Flow A round-trip (pick card → play reference → record → score → commit)
  changes `~/.lingua/cards.json` and moves the card out of the due queue.
- A full Flow B round-trip of 3 turns produces 4 assistant messages and 3 persisted
  reviews.

---

## Section 8 — Out of scope

- **Multi-user / accounts.** One user, one `~/.lingua/cards.json`. No auth, no per-user
  namespacing, no session isolation beyond the Gradio session.
- **Persistent conversation history.** `SessionContext.conversation_history` is
  in-memory and dies with the session. Only *card state* is persisted. A future
  "class transcript export" is a separate feature.
- **Cross-device sync.** No server, no cloud store, no conflict resolution.
- **Leaderboards, streaks, gamification.** No aggregate stats beyond the per-session
  summary in B11.
- **Real LiveKit voice transport (F6b).** The class is offline and turn-based.
- **Generative sentence composition for Flow C.** Templates only.
- **True class-based ASR decoding bias.** `initial_prompt` prefixing only (C-2).
- **Prosody, rhythm, dialect, or speaker diarization scoring.** Inherited from the F5
  out-of-scope list.
- **Multi-language.** `target_language="zh"` is threaded everywhere, but only Mandarin
  is implemented and tested.
- **Concurrency.** `SessionContext` is not thread-safe and the registry singletons are
  process-wide; a second simultaneous browser session shares the Whisper model and the
  card file. Acceptable for single-user local use, explicitly not hardened.
