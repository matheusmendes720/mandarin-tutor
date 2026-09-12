# Tutor Maintenance Guide

Target: Agent fixing bugs in `src/lingua/tutor.py` or `src/lingua/prompts/tutor.py`.

> See [Code Review E, B, A](./specs/2026-09-09-code-review.md) for bug history.

## API Surface of MandarinTutor

### Constructor

```python
tutor = MandarinTutor(cfg: LinguaConfig | None = None)
```

- Loads config (or defaults)
- Creates `VoiceStudioClient` for TTS
- Creates `ConversationMemory` at `data/conversation.json`
- Adds system prompt as first turn if memory is empty

### Key Methods

| Method | Signature | Job |
|--------|----------|-----|
| `stream_response` | `(messages, on_sentence?) -> (full_text, sentences)` | Call LLM, split sentences, fire callbacks |
| `_ask_llm` | `(user_message) -> TutorTurn` | Sync single-shot LLM call (legacy) |
| `speak` | `(text, voice_profile?, speed?) -> SynthesisResult` | Call VoiceStudio TTS |
| `_voice_for_turn` | `(turn) -> str` | Return voice ID (english/mandarin) |
| `_speed_for_turn` | `(turn) -> float` | Return speed (1.0 or 0.75) |

### TutorTurn Dataclass

```python
@dataclass
class TutorTurn:
    type: str       # explanation | vocab_drill | tone_drill | dialogue | correction
    text: str      # What the tutor says
    expected: str  # What student should reply (Mandarin)
    feedback: str  # Praise/correction
```

## LLM Message Flow

```
memory.add_turn("user", transcript)
  └─> memory.get_conversation_for_llm()
        └─> [system prompt, ...previous turns...]
            └─> tutor.stream_response(messages)
                  ├─> POST to MiniMax /chatcompletion_v2
                  ├─> Stream SSE chunks
                  ├─> find_sentence_boundary() on each delta
                  ├─> on_sentence callback (if provided)
                  └─> Parse JSON at end:
                      {
                        "type": "explanation",
                        "text": "...",
                        "expected": "...",
                        "feedback": "..."
                      }
```

### Sentence Boundary Detection (L29-59)

Finds delimiters: Chinese (`。！？`) or English (`.!?\n`)

```python
_SENT_END_RE = re.compile(r"([。！？.!?\n])")

def find_sentence_boundary(text, emitted_len):
    # Returns (end_index, sentence_text) or None
```

## System Prompt Evolution

| Commit | Change |
|--------|--------|
| Current | Mode A (drill), B (chat), C (conversation) with switch logic |
| Earlier | Quiz-only mode |

The prompt lives in `src/lingua/prompts/tutor.py`:

- Lines 3-55: Full SYSTEM_PROMPT
- Instructs LLM to respond with JSON schema
- Defines 5 turn types
- Rules: no filler, 60-word max, switch drill after 2 failures

## Bug History

### Bug E (Fixed): JSON Extraction from LLM Response

The LLM sometimes returns JSON with embedded sentence delimiters inside the `text` field. The fix (L188-208) parses the final response as JSON and re-splits sentences from the `text` field only.

```python
# Before: sentences split on raw response (broken by JSON)
# After: parse JSON, extract text field, split that
obj = json.loads(full_text)
text_field = obj.get("text", "")
# ... split text_field on boundaries ...
```

### Bug B (Fixed): Turn Type as String

Previously used bare `str` for `TutorTurn.type` (L75), allowing typos like `"explnation"` to pass. Now validated against allowed types (harness L289).

### Bug A (Fixed): Voice Selection

`_voice_for_turn()` (L243-247) selects English for `"explanation"`, Mandarin for all other types. Combined with M2 fix in harness to use actual LLM type.

## Common Fixes

### How to extend turn types

1. Add to `TutorTurn.type` docstring: `| "new_type"`
2. Add to harness L289: `if turn_type not in {"explanation", ..., "new_type"}`
3. Add voice/speed logic in tutor methods if needed
4. Update system prompt to document the new mode

### How to change max_tokens

In `stream_response()` (L121):

```python
payload = {
    "model": self.cfg.llm.model,
    "messages": messages,
    "max_tokens": 120,  # <-- change this
    "stream": True,
}
```

### How to swap LLM provider

Currently hardcoded to MiniMax (L125):

```python
resp = self._session.post(
    f"{self.cfg.llm.url}/chatcompletion_v2",  # <-- change URL
    ...
)
```

To swap:
1. Add new config field in `src/lingua/config.py`
2. Change URL construction here
3. Adjust payload format if needed (OpenAI vs MiniMax vs others)

## Test Coverage

| Method | Test Location |
|--------|---------------|
| `stream_response` | `tests/tutor/test_tutor.py` |
| `find_sentence_boundary` | `tests/tutor/test_tutor.py` |
| `_voice_for_turn` | Covered indirectly via integration |
| `to_pinyin` | `tests/tutor/test_tutor.py` |

Missing tests:
- `next_drill`, `start_dialogue`, `review_and_drill` (dead code L287-305)
- End-to-end with real MiniMax (requires API key)

## Key Files

- `src/lingua/tutor.py` — Main tutor logic (305 LOC)
- `src/lingua/prompts/tutor.py` — SYSTEM_PROMPT (60 LOC)
- `src/lingua/agent/memory.py` — ConversationMemory persistence
- `src/lingua/voice_studio.py` — TTS client
