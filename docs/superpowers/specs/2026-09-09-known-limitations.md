# Known Limitations — Empirical Observations

Compiled from analysis of `data/sessions/session_20260909_181033.json`, `182249.json`, `184845.json`. Each limitation has trace evidence and a proposed fix in `2026-09-09-conversational-harness.md`.

## L1. Quiz loop, not conversation

```
   USER SAYS                                  LLM RESPONDS
   ─────────                                   ─────────────
                                                ┌─────────────────────────┐
   "another phrase please"        ────────────▶ │  Same drill phrase       │
   "how do you say thank you"     ────────────▶ │  "nǐ kàn guò nà běn shū  │
   "Beijo mano" (PT)              ────────────▶ │   ma" (Have you read     │
   "N'est pas un roi" (FR)        ────────────▶ │   that book?)            │
   "Washing" (EN)                 ────────────▶ │                         │
   "Fuck this"                   ────────────▶ │  Every turn, the same    │
   ...                                       │  expected phrase.        │
   (8 consecutive turns)                      └─────────────────────────┘
```

**Symptom:** User says "another phrase please" or "how do you say thank you" or random words → LLM responds with the same drill phrase.

**Evidence (session 181033, turns 12-20):**
```
turn 12: asr="Another phrase, please."  expected="nǐ kàn guò nà běn shū ma"
turn 13: asr="Ok, tuviera que ver."      expected="nǐ kàn guò nà běn shū ma"
turn 14: asr="N'est pas un roi..."       expected="nǐ kàn guò nà běn shū ma"
turn 15: asr="你跟我那边说嘛。"          expected="nǐ kàn guò nà běn shū ma"
turn 16: asr="Shabbat Shummah."          expected="nǐ kàn guò nà běn shū ma"
turn 17: asr="Beijo, mano."              expected="nǐ kàn guò nà běn shū ma"
turn 18: asr="你跟我哪里出门。"          expected="nǐ kàn guò nà běn shū ma"
turn 19: asr="Fuck off. ..."              expected="nǐ kàn guò nà běn shū ma"
turn 20: asr="Bem quebrado ainda."       expected="nǐ kàn guò nà běn shū ma"
```

8 consecutive turns. The LLM offered the **same Mandarin phrase** despite the user asking for a new phrase, speaking 7 different languages, or expressing frustration.

**Root cause:** No intent classification. Every ASR result goes through the same LLM call. The LLM has no awareness that "another phrase please" is a meta-instruction.

**Proposed fix:** Intent router classifies each user turn into `DRILL_ATTEMPT`, `QUESTION`, `SWITCH_TOPIC`, `FRUSTRATION`, `GREETING`, `OFF_TOPIC`, `SILENCE`. Each intent has a different handler.

---

## L2. Stuck on same phrase — no repetition detection

**Symptom:** When the user fails to say a phrase correctly, the tutor keeps offering the same phrase.

**Evidence:** Same as L1. No mechanism tracks "we've tried this phrase N times".

**Root cause:** No state. The harness has no concept of "we're mid-drill with phrase X and the user has failed N times".

**Proposed fix:** `DrillingState.context` tracks `consecutive_failures`. After 3 failures, inject a system message into the LLM context: "user has failed 3 times on phrase X, offer a NEW related phrase". Reset counter.

---

## L3. TTS plays filler

```
   LLM output:       "Sure! That isn't Mandarin. The phrase is: nǐ kàn guò nà běn shū ma."
                    │     │                   │                       │
   split on:        .   .                  .                       │
                    ▼     ▼                   ▼                       ▼
   TTS calls:      [1]   [2]                 [3]                     [4]
                   ↓     ↓                   ↓                       ↓
                   ⚡⚡   ⚡⚡                  ⚡⚡⚡⚡                  ⚡⚡
                   0.5s   0.5s                 1.2s                    0.4s

   TOTAL TTS time:  2.6s for one short response
   EXPECTED:        0.5s — just the actual content, no filler
```

**Symptom:** Tutor says "Sure!" then "That isn't Mandarin." then "Try: nǐ kàn guò nà běn shū ma" — three TTS calls for what should be one thought.

**Evidence (session 181033, turn 11):**
```json
"tts_sentences": [
  "That isn't Mandarin.",
  " The phrase is: tā měitiān qù xuéxiào — 'She/He goes to school every day.",
  "'"
]
```
3 TTS calls × ~1s each = 3s to say what could be one sentence in 1s.

**Root cause:** `find_sentence_boundary` splits on every `.`, `!`, `?`, `。`, etc. The system prompt says "Keep each turn short" but LLM still writes multi-sentence responses.

**Proposed fix:** Either (a) tighten the system prompt to forbid filler ("NEVER begin a turn with 'Sure!' or 'Great!'"), (b) post-process the LLM response to remove filler, or (c) concatenate all sentences into one TTS call.

---

## L4. Language detection always says "zh"

**Symptom:** User speaks English, Portuguese, French → `asr_language` recorded as `"zh"` regardless of what ASR actually returned.

**Evidence:** Every single turn in every session shows `"asr_language": "zh"` — even when the user clearly spoke English ("Let's try some common daily usual phrase") or Portuguese ("Beijo, mano").

**Root cause:** `src/lingua/agent/harness.py:_transcribe_audio:218`:
```python
segments = [{"text": text, "language": result.get("language", "zh")}]
```
The `.get(..., "zh")` default is wrong — it should propagate whatever ASR returned, or use the TurnRouter which is imported but unused for language classification.

**Proposed fix:** Use `result.get("language")` directly, defaulting to `None` when missing. The router can then classify based on actual content.

---

## L5. No interruption

```
   t=0s         t=1s         t=2s         t=3s         t=4s
    │            │            │            │            │
    ▼            ▼            ▼            ▼            ▼
    ┌─TUTOR SPEAKING─────────────────────────────────────────┐
    │  sentence 1  │ sentence 2  │  sentence 3  │  sentence 4│
    └─────────────┴─────────────┴─────────────┴─────────────┘
                                                │
                                       user speaks ─┘
                                                │
                                                ✗ mic IGNORED
                                                ✗ can't stop

   CURRENT BEHAVIOR: user must wait for sentence 4 to finish
   EXPECTED BEHAVIOR: tutor stops within 1s of user speaking
```

**Symptom:** While the tutor is speaking (sd.play + sd.wait), the user cannot:
- Stop playback by speaking
- Be heard by the mic

**Root cause:** `sd.wait()` blocks the event loop. The capture task is also blocked because it shares the loop.

**Evidence:** Every turn in the session log shows `tts_latency_ms_per_sentence` summing to roughly the wall-clock time during that turn, confirming the loop was blocked.

**Proposed fix:** Run audio capture as a truly independent task (separate thread or process). When VAD detects speech onset during playback, fire `Interrupt` event. State machine stops playback via `sd.stop()` and transitions to `IdleState`.

---

## L6. LLM context window grows unbounded

```
   context size sent per LLM call

   tokens
   4000 ┤                                          ╱──
        │                                       ╱───
   3000 ┤                                   ╱───
        │                               ╱───
   2000 ┤                           ╱───
        │                       ╱───       ← LLM confused by stale history
   1000 ┤                ╱──────              → truncated responses
        │           ╱────
      0 ┤────╱────
        └────┬────┬────┬────┬────┬────┬────
            5    10   15   20   25   30 turns
            ↑
         session start

   CURRENT: every LLM call sends the full 30-turn history
   EXPECTED: send only [system, last 2 turns, current]
```

**Symptom:** Long sessions show degraded response quality.

**Evidence:** `tutor.memory.get_conversation_for_llm()` returns the full turn history (up to 30 turns). Every LLM call sends the entire history. With max_tokens=120, the LLM has to compress its own response, sometimes truncating mid-JSON.

**Root cause:** No per-state context scoping. Each LLM call gets the full history.

**Proposed fix:** `build_llm_context(state_context)` returns only relevant messages:
- Always: `[system, last 2 user turns, current user turn]`
- Drill: also include `current_phrase` + `expected` + `last_feedback`
- Never include older turns unless the user asks "what did we talk about earlier?"

---

## L7. `langsmith` and `anyio` warnings on every pytest run

**Symptom:**
```
plugins: anyio-4.14.2, langsmith-0.11.1, asyncio-1.4.0, mock-3.15.1
```

**Root cause:** Pytest auto-discovers plugins from installed packages. These are not needed.

**Proposed fix:** Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "-p no:langsmith -p no:anyio"
```

---

## L8. `pypinyin` emits deprecation warnings

**Symptom:** Every pytest run shows:
```
DeprecationWarning: codecs.open() is deprecated. Use open() instead.
```

**Root cause:** `pypinyin` internally uses `codecs.open()`. Not our code, but we can suppress the warning.

**Proposed fix:** `filterwarnings("ignore::DeprecationWarning", module="pypinyin.*")` in `pyproject.toml`.

---

## L9. Hardcoded `language="zh"` in segment construction

Same as L4. Repeated here because it's a one-line fix:

```python
# src/lingua/agent/harness.py:218
segments = [{"text": text, "language": result.get("language", "zh")}]
#                                                ^^^^^^^^^^^^^^^^^^^^^
#                                                defaults to "zh" when ASR returns nothing
```

Should be `result.get("language")` or `None` — let the router decide.

---

## L10. `VAD` defined but unused

**Symptom:** `src/lingua/agent/vad.py` defines `VoiceActivityDetector` but the harness never instantiates it. Silence detection happens via `stream_audio_chunks`'s built-in threshold (1.5s of silence).

**Root cause:** Earlier debugging added VAD but never wired it into the main loop.

**Proposed fix:** In the new state-machine harness, use `VadEvent` to drive `UtteranceStart`/`UtteranceEnd` events. The existing `VoiceActivityDetector` can be used directly.

---

## L11. `TurnRouter` is imported but not used for routing

**Symptom:** `TurnRouter` is instantiated in `__init__` but `route()` is called once at the top of `_process_transcript`, where it just concatenates `segments` into `text`.

**Root cause:** Router was added for multi-language support but the actual routing logic is trivial.

**Proposed fix:** Either remove `TurnRouter` (YAGNI), or make it actually classify user intent (DRILL_ATTEMPT vs QUESTION vs SWITCH_TOPIC). The new intent router proposal makes this redundant.

---

## L12. No persistent user profile / progress

**Symptom:** Every session starts fresh. The tutor doesn't remember what words/phrases the user has learned.

**Root cause:** `ConversationMemory` stores recent turns for LLM context, but there's no long-term storage of "user knows X, doesn't know Y".

**Proposed fix (separate from this spec):** A `VocabularyProgress` system that tracks which words the user has been exposed to and how often they got them right. Out of scope here — separate spec.

---

## L13. No way for the user to manually change mode

**Symptom:** If the LLM keeps drilling when the user wants to chat, there's no UI command to switch.

**Proposed fix:** Add CLI flags / keyboard shortcuts:
- `--mode drill|chat|auto` — start in a specific mode
- Hotkey `Ctrl+D` to switch to drill
- Hotkey `Ctrl+C` to switch to chat
- Voice command "stop drilling" → force mode switch

Out of scope for this spec but documented for future work.

---

## L14. TTS speed doesn't change when LLM says "Slowly"

**Symptom:** User asks "could you speak slower?" → LLM says "Sure! Slowly: wǒ xǐ huān chī píngguǒ" but actual TTS plays at full speed.

**Evidence:** `tts_latency_ms_per_sentence` in session 181033 turn #4 shows ~1100ms for the "slowly" sentence — same as other turns. No speed reduction in practice.

**Root cause:** LLM's text-based acknowledgment of "slowly" doesn't trigger any speed change. The TTS speed is hardcoded per turn-type (`vocab_drill` = 0.75, `explanation` = 1.0).

**Proposed fix:** Add a `speed` field to the JSON schema. LLM can request `speed=0.5` when teaching tones. Or: detect keywords like "slow", "slower" in user input and override speed.

---

## L15. Recorder `metadata.input_device` is always "?"

**Symptom:** All sessions show `"input_device": "?", "output_device": "?"`.

**Root cause:** The recorder is initialized in `__init__` before the device names are resolved. `__main__.py` resolves devices AFTER instantiating the harness.

**Proposed fix:** Pass device names via `recorder.update_metadata()` after device resolution, or move recorder init to `_run_loop`.

---

## Summary

```
SEVERITY DISTRIBUTION
─────────────────────────────────────────────────────
HIGH    ███████                                          3
MEDIUM  ████                                            2
LOW     ████████                                        4
DEFER   ████████                                        2
─────────────────────────────────────────────────────
```

| # | Symptom | Severity | Spec coverage |
|---|---|---|---|
| L1 | Quiz loop | **HIGH** | conversational-harness §Intent router |
| L2 | Stuck on phrase | **HIGH** | §Repetition detection |
| L5 | No interruption | **HIGH** | conversational-harness §Interruption |
| L3 | TTS filler | MEDIUM | §System prompt tightening |
| L6 | Context window unbounded | MEDIUM | §Context management |
| L4 | Hardcoded language="zh" | LOW | one-line fix |
| L7-L11 | Plumbing/cleanup | LOW | pyproject tweaks |
| L15 | Recorder metadata | LOW | one-line fix |
| L12 | No progress tracking | DEFER | separate spec |
| L13-L14 | Missing UX controls | DEFER | future work |

The next implementation cycle should address **L1, L2, L5** (the spec's three primary targets) and **L3, L4, L6** as supporting fixes. **L12** (vocabulary progress) needs its own spec — too large for this conversation.

### What changes vs. what stays

```
┌──────────────────────────────────────┬──────────────────┐
│   IN SCOPE (this cycle)              │  OUT OF SCOPE      │
├──────────────────────────────────────┼──────────────────┤
│   ✓ State machine harness            │  ✗ Vocabulary SRS │
│   ✓ Intent router                    │  ✗ Web UI         │
│   ✓ Repetition detection             │  ✗ Multi-user     │
│   ✓ Interruption                     │  ✗ Local LLM      │
│   ✓ Context scoping                  │  ✗ Voice auth     │
│   ✓ Plumb-fix language="zh" bug      │                    │
│   ✓ Stop TTS filler                  │                    │
└──────────────────────────────────────┴──────────────────┘
```
