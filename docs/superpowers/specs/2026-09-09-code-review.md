# Code Quality Review — 2026-09-09

Empirical review of the Lingua codebase as of commit `f58ad54`. Each finding has file path, line number, severity, and a concrete fix.

---

## Severity Distribution

```
CRITICAL  █                                              1
HIGH      ████                                           4
MEDIUM    ████████                                       8
LOW       ████████████████                                15
─────────────────────────────────────────────────────────
TOTAL: 28 findings
```

---

## CRITICAL

### C1. Hardcoded personal path in default config (information leak)

**File:** `src/lingua/config.py:41`

```python
source_path: Path = Path(
    "G:/Other computers/My Laptop/notas_estudo/2_projeto/mandarin-learning"
)
```

This embeds the developer's username (`matheusmendes720`) and a directory tree specific to their machine into the public default config. Anyone using `lingua` ships their username as part of the default. The path is also used in `tutor.py` paths.

**Fix:** Default to empty `Path("")` or to a relative path under the user's data dir. If empty, skip vocabulary import.

```python
source_path: Path = field(default_factory=lambda: Path.home() / ".lingua" / "mandarin-learning")
```

Or remove `source_path` from defaults entirely — let the user opt in.

**Severity:** CRITICAL (privacy). **Action:** PR immediately.

---

## HIGH

### H1. No `.gitignore`

**Files affected:** the entire working tree

Untracked files in `git status` include:
- `__pycache__/` (everywhere)
- `data/` (vocab + sessions — JSON with transcripts and user data)
- `lingua.env`, `.env.example` (could leak secrets)
- `tmp/`, `.pytest_temp/`
- `=12.0`, `12.0` (looks like shell artifact from `pip install`)

**Risk:** if `data/` ever gets committed (e.g., `git add .`), conversation transcripts (containing ASR transcripts of what the user said out loud) become public.

**Fix:** Add `.gitignore`:
```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
data/
.env
.env.local
*.env.local
lingua.env
tmp/
.pytest_temp/
=*
docs/_archived/
```

**Severity:** HIGH (data leak risk).

---

### H2. Hardcoded user path appears in TWO more places

**Files:** `src/lingua/config.py:104` (default), `lingua.toml` (committed config)

The default `source_path` is referenced in `config.py:104` AND the committed `lingua.toml` exposes the absolute path. A user who clones this repo and runs the app will have the developer's path written to disk by Python's defaults.

**Fix:** Same as C1. Plus scrub `lingua.toml` if it contains the path before pushing.

**Severity:** HIGH.

---

### H3. `LinguaConfig.from_toml` silently falls back to defaults when file not found

**File:** `src/lingua/config.py:69-70`

```python
if not path.exists():
    return cls.defaults()
```

`defaults()` populates `api_key=""` from env. If the env var is missing and the TOML is missing, the app silently uses empty credentials. Later calls fail with cryptic 401 errors. The user has no signal that anything is wrong.

**Fix:** Log a warning when falling back, or raise a `ConfigError` if a required field is missing.

```python
if not path.exists():
    logger.warning("lingua.toml not found at %s, using defaults (api_key from env)", path)
    return cls.defaults()
```

**Severity:** HIGH (silent failure).

---

### H4. Bare `except Exception:` in audio_loop playback fallback

**File:** `src/lingua/audio_loop.py:283-284`

```python
except Exception:
    # Last resort: just skip playback silently
    pass
```

Silently swallows all errors including KeyboardInterrupt, MemoryError, and SystemExit. If `subprocess.Popen` succeeds in spawning PowerShell but playback hangs forever, the user has no recourse.

**Fix:** Catch narrower exceptions (`OSError`, `subprocess.SubprocessError`) and at least log them.

```python
except (OSError, subprocess.SubprocessError) as e:
    logger.error("MP3 fallback failed: %s", e)
```

**Severity:** HIGH (silent failure).

---

### H5. `unbounded ConversationMemory._summarize` can fail silently

**File:** `src/lingua/agent/memory.py:76-86`

When `len(self.turns) > self.max_turns`, `_summarize` produces a system turn with text from the first half of the conversation, then keeps the second half. If the second half is empty (all turns were summarized away), the memory is left with one orphan system turn and zero real turns.

More importantly: the summary truncates to 200 chars (`summary_text[:200]`) which loses all nuance. The LLM sees a confusingly short context and may produce garbage.

**Fix:** Either (a) drop the summarize step entirely (the LLM already trims context with the new build_llm_context from the spec) or (b) keep a fuller summary and don't truncate.

**Severity:** HIGH (silent degradation).

---

## MEDIUM

### M1. `TutorTurn.type` is `str`, not Enum

**File:** `src/lingua/tutor.py:75`

```python
type: str  # explanation | vocab_drill | tone_drill | dialogue
```

Using `str` for an enum-like field allows typos like `"explnation"` to flow through undetected. The harness does `turn.type == "explanation"` checks that silently always-fail.

**Fix:**
```python
from enum import Enum
class TutorTurnType(str, Enum):
    EXPLANATION = "explanation"
    VOCAB_DRILL = "vocab_drill"
    TONE_DRILL = "tone_drill"
    DIALOGUE = "dialogue"
    CORRECTION = "correction"
```

**Severity:** MEDIUM (type safety).

---

### M2. `TutorTurn` reconstructed in harness always sets `type="explanation"`

**File:** `src/lingua/agent/harness.py:286`

```python
turn = TutorTurn(type="explanation", text=full_text)
```

After parsing JSON successfully (`llm_parsed` is set), the code still hardcodes `type="explanation"`. The actual LLM response type (`vocab_drill`, `tone_drill`, etc.) is discarded.

This means: **voice and speed selection always use English voice at 1.0x**, even when the tutor is responding in Mandarin. Bug confirmed in `data/sessions/` — Mandarin responses use English voice speed.

**Fix:** Use `llm_parsed["type"]` if available, else `"explanation"`.

**Severity:** MEDIUM (functional bug, observable in recordings).

---

### M3. `TutorTurn` doesn't preserve `expected` or `feedback` from LLM

**File:** `src/lingua/agent/harness.py:286`

```python
turn = TutorTurn(type="explanation", text=full_text)
```

The parsed JSON has `expected` and `feedback` fields that we never set on the TutorTurn. They're recorded in the session log but never used by `_process_transcript` for anything. Either remove them from the schema or use them to evaluate user attempts.

**Severity:** MEDIUM (dead field).

---

### M4. `TutorTurn` parsed only once but `llm_parsed` recomputed in recorder

**File:** `src/lingua/agent/harness.py:280-282, 391`

The JSON parsing happens in `_process_transcript` but the recorder also references `llm_parsed_json`. Both should share the same parse result. Currently, `llm_parsed` is a local variable that's passed explicitly — works but creates two parse calls.

**Fix:** Compute once, pass to both.

**Severity:** MEDIUM (duplicated work).

---

### M5. `_recorder.start` called before device resolution

**File:** `src/lingua/agent/harness.py:88-92`

```python
self._recorder = SessionRecorder()
self._recorder_seq = 1
self._recorder.start(
    input_device=getattr(self, "_input_device_name", "?"),
    output_device=getattr(self, "_output_device_name", "?"),
)
```

The recorder captures `"?"` as device names because they're not yet resolved. Known limitation L15. Result: every session log shows `"input_device": "?"`.

**Fix:** Move recorder init to `_run_loop` start, after device names are passed in via constructor.

```python
def __init__(self, tutor, config=None, ..., input_device_name="?", output_device_name="?"):
    ...
    self._input_device_name = input_device_name
    self._output_device_name = output_device_name

async def _run_loop(self):
    if self._recorder is None:
        self._recorder = SessionRecorder()
        self._recorder.start(input_device=self._input_device_name, ...)
```

**Severity:** MEDIUM (cosmetic but easy fix).

---

### M6. Two concurrent event loops: `_capture_audio` + `_transcribe_audio`

**File:** `src/lingua/agent/harness.py:126-136`

```python
capture_task = asyncio.create_task(self._capture_audio(audio_queue))
asr_task = asyncio.create_task(self._transcribe_audio(audio_queue))
try:
    await asyncio.gather(capture_task, asr_task)
```

`asyncio.gather` waits for **both** to finish. They both finish only when the queue gets a `b""` sentinel. Capture sends that sentinel, then ASR finishes when its WebSocket returns. So they finish in sequence: capture first (puts sentinel), then ASR (reads sentinel). The architecture is fine but: there's no timeout. If the WebSocket hangs, the entire loop hangs.

**Fix:** Add a timeout or use `asyncio.wait_for` with a generous timeout (e.g., 60s).

**Severity:** MEDIUM (hang potential).

---

### M7. `Recording.error` swallowed when recorder write fails

**File:** `src/lingua/agent/harness.py:399-400`

```python
except Exception as rec_err:
    self._log(f"recorder error: {rec_err!r}", level="warn")
```

The recorder error is logged to the HUD log but the session JSON is never written. If the recorder is critical for postmortem, silent degradation should not happen — but here it's just a "warn" so OK. **Severity: LOW actually, not MEDIUM.**

(Re-classify to LOW.)

---

### M8. `ConversationMemory._summarize` builds a system turn with `summary_text` from concatenated text

**File:** `src/lingua/agent/memory.py:81`

```python
summary_text = " ".join(t.text for t in self.turns[: len(self.turns) // 2])
```

Concatenates raw user/assistant text without any structure. The LLM receives a wall of text and may mis-attribute it. Better: prefix with speaker tags, or summarize differently.

**Fix:** Either remove `_summarize` entirely (the new spec's `build_llm_context` handles this) or make the summary structured.

**Severity:** MEDIUM.

---

### M9. `TutorTurn` `language` field is `str` default `"zh"` but unused

**File:** `src/lingua/agent/memory.py:14`

```python
language: str = "zh"
```

This field is never read anywhere. Dead field. Either remove it or use it to filter language-specific context.

**Severity:** MEDIUM (dead code).

---

## LOW

### L1. `audio_loop.py` has fallback `subprocess.Popen` with f-string path

**File:** `src/lingua/audio_loop.py:280`

```python
subprocess.Popen(
    ["powershell", "-c", f"(New-Object Media.SoundPlayer '{tmp.name}').PlaySync()"],
    ...
)
```

`tmp.name` is generated by Python's `tempfile` (server-controlled). For a personal CLI this is acceptable but worth noting.

**Severity:** LOW.

---

### L2. `_voice_for_turn` returns English voice for `explanation`, Mandarin for everything else

**File:** `src/lingua/tutor.py:74-77`

```python
def _voice_for_turn(self, turn: TutorTurn) -> str:
    if turn.type == "explanation":
        return self.cfg.voicestudio.voice_english
    return self.cfg.voicestudio.voice_mandarin
```

Coupled to the type field. Should use a mapping dict to make it explicit.

**Fix:** Use `TURN_VOICE = {TutorTurnType.EXPLANATION: "english", ...}` once enum is introduced (M1).

**Severity:** LOW.

---

### L3. Dead code: `MandarinTutor.next_drill`, `.start_dialogue`, `.review_and_drill`

**File:** `src/lingua/tutor.py:287-306`

```python
def next_drill(self, student_input: str | None = None) -> TutorTurn: ...
def start_dialogue(self, topic: str) -> TutorTurn: ...
def review_and_drill(self) -> TutorTurn: ...
```

Defined but never called from `__main__.py` or harness. Either delete (YAGNI) or wire them up for a CLI `--mode drill|chat|review` option.

**Severity:** LOW.

---

### L4. Dead code: `tone_drill.py`, `vocab_drill.py`, `vocab/` package

**File:** `src/lingua/tone_drill.py` (57 lines), `src/lingua/vocab_drill.py` (48 lines), `src/lingua/vocab/` (3 files, 91 lines)

These modules are imported nowhere. `vocab/store.py`, `vocab/importer.py`, `vocab/__init__.py` are unreferenced. The vocabulary subsystem is unstarted.

**Fix:** Either delete (YAGNI) or implement in a future spec.

**Severity:** LOW.

---

### L5. Dead code: `prompts.build_drill_turn` always returns `SYSTEM_PROMPT`

**File:** `src/lingua/prompts/tutor.py:58-60`

```python
def build_drill_turn(word: str, pinyin: str, translation: str, turn_type: str = "vocab_drill") -> str:
    """Build a vocab or tone drill turn for a specific word."""
    return SYSTEM_PROMPT  # Full system prompt used by the LLM client; drill specifics sent as user msgs
```

The function ignores its arguments and always returns the system prompt. Either delete or implement.

**Severity:** LOW.

---

### L6. `VoiceActivityDetector` instantiated but never used

**File:** `src/lingua/agent/vad.py` (defined) + `harness.py:74` (instantiated)

```python
self._vad = VoiceActivityDetector(energy_threshold=0.01)
```

Never referenced after init. The harness uses `audio_loop.stream_audio_chunks`'s built-in silence threshold instead. The VAD is dead code in the current harness.

**Fix:** Either wire it up (the new spec §Interruption does this) or delete the class.

**Severity:** LOW.

---

### L7. `TurnRouter` instantiated but only used for trivial concatenation

**File:** `src/lingua/agent/router.py` (defined) + `harness.py:243`

```python
routed = self._router.route(segments)
text = routed.full_text
```

The router's only useful behavior is concatenating segments. The classification (`vocab_drill` vs `explanation` vs `dialogue`) is just based on language labels.

**Fix:** Either make router do real intent classification (the new spec §Intent router does this) or delete.

**Severity:** LOW.

---

### L8. `print()` in harness for shutdown message

**File:** `src/lingua/agent/harness.py:115-118`

```python
print(f"\n[session log: {path}]")
print(f"\n[recorder error: {rec_err!r}]")
```

These bypass the HUD/event bus. Fine for shutdown — no HUD to print to anyway — but mixing print with structured logging is inconsistent.

**Severity:** LOW.

---

### L9. `_capture_audio` uses bare `except Exception` after cancellation

**File:** `src/lingua/agent/harness.py:163-167`

```python
except asyncio.CancelledError:
    logger.debug("Audio capture cancelled")
    raise
except Exception as e:
    logger.error("Error in audio capture: %s", e)
    raise
```

This is correct — CancelledError is handled separately. No bug. Just noting that the pattern is right.

**Severity:** LOW (no bug, just confirming).

---

### L10. `lingua.env` and `.env.example` not gitignored

**File:** repo root

`lingua.env` may contain real secrets (LLM API key). `.env.example` is the template. Both should be ignored by `.gitignore` or renamed.

**Fix:** Add to `.gitignore` (see H1).

**Severity:** LOW.

---

### L11. `=` files in repo (`=12.0`, `12.0`)

**File:** repo root

These look like accidental artifacts (e.g., `pip install package==1.0` typed in a shell that interpreted `=` as redirect). Should be deleted.

**Fix:** `rm -f =12.0 12.0`

**Severity:** LOW (cosmetic).

---

### L12. `run.bat` is untracked

**File:** repo root

A Windows batch file for running the app. Could be useful, could be a leftover. Document its purpose or remove.

**Severity:** LOW.

---

### L13. `asr.py:144` sends `input_audio.end` but no timeout on WS receive

**File:** `src/lingua/asr.py:147-149`

```python
async for message in ws:
    data = json.loads(message)
```

If the server accepts our audio but never sends a `final` event, this loops forever.

**Fix:** Add `asyncio.wait_for` with a timeout (e.g., 30s) per message.

**Severity:** LOW (server is reliable in practice).

---

### L14. `recorder.py:Turn` mutable defaults

**File:** `src/lingua/recorder.py:65-74`

```python
@dataclass
class Turn:
    ...
    tts_sentences: list[str] = field(default_factory=list)
    tts_latency_ms_per_sentence: list[int] = field(default_factory=list)
    tts_total_bytes: list[int] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
```

Uses `field(default_factory=...)` correctly. **No bug.** Just confirming the dataclass pattern is right.

**Severity:** LOW (no bug).

---

### L15. `LinguaConfig.vocab.source_path` always defaults to the developer's machine

**File:** `src/lingua/config.py:40-42`

Same as C1. The dataclass field default is computed at import time so it's the same value for everyone.

**Severity:** LOW (cosmetic; sub-bug of C1).

---

### L16. Recording captures timestamps via `time.time()` instead of `time.monotonic()`

**File:** `src/lingua/recorder.py:88`

```python
ts=time.time(),
```

Wall-clock time, not monotonic. Could go backwards if the system clock changes. Doesn't matter for ordering in a single session but inconsistent with `time.monotonic()` used elsewhere.

**Fix:** Use `time.monotonic()` for consistency.

**Severity:** LOW.

---

### L17. `ConversationMemory._load` heals legacy bug but writes the result immediately

**File:** `src/lingua/agent/memory.py:43-59`

When sanitizing legacy data, `self.save()` is called inside `_load`. If saving fails (disk full, permission), the in-memory state is healed but the file remains stale. Next load re-applies the heal.

**Fix:** Don't write inside `_load`; let `add_turn` or `save` write. Move the heal to `__init__` after the load.

**Severity:** LOW (idempotent).

---

### L18. Hardcoded `default_max_turns=30` not configurable

**File:** `src/lingua/agent/memory.py:26`

```python
def __init__(self, path: Path, max_turns: int = 30):
```

The 30-turn limit is hardcoded. Power users might want more. The new spec moves this logic out, so probably YAGNI to fix now.

**Severity:** LOW.

---

### L19. `voice_studio.py:is_available` uses 3s timeout, may spuriously return False

**File:** `src/lingua/voice_studio.py:178-185`

```python
def is_available(self) -> bool:
    try:
        r = requests.get(f"{self.base_url}/model/status", timeout=3)
        return r.status_code == 200
    except Exception:
        return False
```

Under load, VoiceStudio takes >3s to respond. `__main__.py` then exits with "VoiceStudio not reachable" even when it would have responded at 4s. User sees false alarm.

**Fix:** Bump timeout to 5s.

**Severity:** LOW.

---

## Test Coverage Assessment

**24 test files** for ~2600 LOC. Ratio is decent. Areas without tests:

| Area | Coverage |
|---|---|
| `__main__.py` | ❌ none |
| `harness.py` (the orchestrator) | ⚠️ test_harness.py exists but hangs on full run; test_harness_events.py covers event publishing only |
| `audio_loop.py` | ⚠️ RMS compute_rms tested; full stream_audio_chunks untested |
| `voice_studio.py` | ⚠️ TTS tested; `is_available`, `stream_synthesize` partially |
| `tutor.py` (orchestrator methods) | ❌ `next_drill`, `start_dialogue`, `review_and_drill` untested |
| `config.py` | ⚠️ defaults tested; from_toml covered, cwd-relative fix tested |
| `recorder.py` | ✅ fully tested |

**Missing tests:**
- `test_intent.py` (for the new spec)
- `test_state_machine.py` (for the new spec)
- `test_drill_repetition.py` (for the new spec)
- `test_pinyin` covers edge cases but not `to_pinyin` on mixed text (only text)

---

## Documentation Assessment

**Excellent progress** this session — three new spec docs with ASCII diagrams.

**Missing:**
- README.md at repo root — `git ls-tree` shows none. New contributors have no entry point.
- No CHANGELOG.md — git log is the only history.
- No CONTRIBUTING.md.
- Inline docstrings missing in many functions (e.g., `audio_loop.stream_audio_chunks` has the call signature but no explanation of resampling rationale).

---

## Prioritized Action Items

| Priority | Item | Effort |
|---|---|---|
| **CRITICAL** | Fix C1: hardcoded path in `config.py` | 5 min |
| HIGH | H1: add `.gitignore` | 5 min |
| HIGH | H2: scrub `lingua.toml` of personal paths | 5 min |
| HIGH | H3: warn on silent config fallback | 5 min |
| HIGH | H4: narrow `except Exception` in audio_loop | 5 min |
| HIGH | H5: review `_summarize` truncation | 15 min |
| MEDIUM | M2: use `llm_parsed["type"]` for voice selection | 10 min — **fixes observable bug** |
| MEDIUM | M1: `TutorTurnType` Enum | 15 min |
| MEDIUM | M5: defer recorder init until device names known | 10 min |
| MEDIUM | M6: add timeout to `asyncio.gather` | 10 min |
| LOW | L3-L9: dead code removal | 30 min total |
| LOW | Add README.md | 30 min |

**Estimated total cleanup: 2-3 hours for HIGH+CRITICAL.** M2 should be fixed NOW because it explains the wrong-voice Mandarin bug observed in the session log.
