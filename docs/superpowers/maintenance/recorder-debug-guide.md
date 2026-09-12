# Recorder Debug Guide

Target: Agent given a session log JSON file who needs to diagnose what went wrong.

> See [Recorder schema]((./specs/2026-09-09-current-architecture.md)) for architecture.

## Session Log Schema

Location: `data/sessions/session_YYYYMMDD_HHMMSS.json`

```json
{
  "session_id": "20260909_181033",
  "start_ts": "2026-09-09T18:10:33.718466",
  "uptime_s": 462.829,
  "metadata": {
    "input_device": "?",          // <-- BUG M5: should be device name
    "output_device": "?",         // <-- BUG M5
    "end_ts": 462.829,
    "end_wall": "2026-09-09T18:18:16.547490",
    "n_turns": 20
  },
  "turns": [
    {
      "ts": 1788988255.1214578,    // unix timestamp
      "seq": 1,                     // 1-based turn number

      // ASR
      "asr_text": "สวัสดีครับ",
      "asr_language": "zh",
      "asr_latency_ms": 0,
      "asr_error": null,

      // LLM
      "llm_response": "{\"type\": \"explanation\", ...}",
      "llm_parsed_json": {
        "type": "explanation",
        "text": "...",
        "expected": "...",
        "feedback": "..."
      },
      "llm_latency_ms": 3153,
      "llm_error": null,

      // TTS
      "tts_sentences": ["sentence 1", "sentence 2"],
      "tts_latency_ms_per_sentence": [1095, 1163],
      "tts_total_bytes": [88320, 99840],

      // Display
      "pinyin_displayed": "That isn't Mandarin.",

      // Flags
      "flags": []
    }
  ]
}
```

## Field Reference

| Field | Type | Meaning |
|-------|------|---------|
| `ts` | float | Unix timestamp when turn started |
| `seq` | int | Turn sequence number (1-based) |
| `asr_text` | string | What the ASR heard |
| `asr_language` | string | Detected language code (`zh`, `en`, etc.) |
| `llm_response` | string | Raw LLM response (often JSON) |
| `llm_parsed_json` | object | Parsed JSON from LLM |
| `llm_latency_ms` | int | Time from request to full response |
| `tts_sentences` | list | What was spoken (after sentence splitting) |
| `tts_latency_ms_per_sentence` | list | TTS server time per sentence |
| `tts_total_bytes` | list | Audio size per sentence |
| `pinyin_displayed` | string | What showed on HUD |
| `flags` | list | Anomaly indicators |

## How to Read Latency

### When is something "slow"?

Compare against baseline:

| Component | Baseline | "Slow" Threshold |
|-----------|----------|------------------|
| ASR | 0.5-2s | > 5s |
| LLM | 1.5-3s | > 8s |
| TTS (per sentence) | 80ms/char + 3.5s | > 5s |
| End-to-end | 6-12s | > 20s |

### Latency Across a Turn

```
Turn N:
  ASR:     asr_text captured at t=0
              │
              ▼ (0.5-2s)
  LLM:      llm_latency_ms measured from request start
              │
              ▼ (3-5s)
  TTS:      sum(tts_latency_ms_per_sentence)
              │
              ▼
  Total:    sum of all above
```

### Finding Slow Turns

```python
import json

with open("data/sessions/session_20260909_181033.json") as f:
    session = json.load(f)

for turn in session["turns"]:
    total = turn["llm_latency_ms"] + sum(turn["tts_latency_ms_per_sentence"])
    if total > 10000:  # 10s threshold
        print(f"Turn {turn['seq']}: {total}ms (SLOW)")
```

## Common Flag Patterns

| Flag | Meaning | Likely Cause |
|------|---------|--------------|
| `tts_empty_audio` | TTS returned 0 bytes | Server error, empty text, or speed=0 |
| `no_sentences_emitted` | LLM response had no sentence boundaries | Malformed JSON or single word |
| `empty_llm_response` | LLM returned empty | API error or timeout |
| `tts_error:Timeout` | TTS call timed out | Server overloaded |
| `tts_error:ConnectionError` | Cannot reach VoiceStudio | Server down |

### Flag Extraction

```python
# Find all problematic turns
for turn in session["turns"]:
    if turn["flags"]:
        print(f"Turn {turn['seq']}: {turn['flags']}")
```

## Red Flags

### User Stuck Pattern

Same `expected` repeated 5+ times = user is stuck in a loop:

```python
# Find repeated expected values
from collections import Counter

expected_counts = Counter(
    turn.get("llm_parsed_json", {}).get("expected", "")
    for turn in session["turns"]
)

for phrase, count in expected_counts.items():
    if count >= 5 and phrase:
        print(f"STUCK: '{phrase}' repeated {count} times")
```

### No Progress Pattern

Multiple consecutive `type: vocab_drill` with same `expected`:

```python
prev_expected = None
stuck_count = 0
for turn in session["turns"]:
    parsed = turn.get("llm_parsed_json", {})
    if parsed.get("type") == "vocab_drill":
        if parsed.get("expected") == prev_expected:
            stuck_count += 1
        else:
            stuck_count = 0
        prev_expected = parsed.get("expected")
    else:
        stuck_count = 0
        prev_expected = None
```

## Worked Example: Diagnosing a Session

Given `session_20260909_181033.json`:

### Step 1: Quick Stats

```python
print(f"Session: {session['session_id']}")
print(f"Duration: {session['uptime_s']:.0f}s")
print(f"Turns: {len(session['turns'])}")
print(f"Devices: {session['metadata']['input_device']} / {session['metadata']['output_device']}")
```

Output:
```
Session: 20260909_181033
Duration: 463s (7.7 min)
Turns: 20
Devices: ? / ?  <-- BUG M5: devices not captured
```

### Step 2: Check for Flags

```python
flagged = [t for t in session["turns"] if t["flags"]]
print(f"Flagged turns: {len(flagged)}")
for t in flagged:
    print(f"  Turn {t['seq']}: {t['flags']}")
```

### Step 3: Find Stuck Drills

```python
from collections import Counter
expected = [t.get("llm_parsed_json",{}).get("expected") for t in session["turns"]]
print(Counter(expected).most_common(3))
```

### Step 4: Latency Timeline

```python
import matplotlib.pyplot as plt

llm_lats = [t["llm_latency_ms"] for t in session["turns"]]
tts_lats = [sum(t["tts_latency_ms_per_sentence"]) for t in session["turns"]]

plt.plot(llm_lats, label="LLM")
plt.plot(tts_lats, label="TTS")
plt.xlabel("Turn")
plt.ylabel("Latency (ms)")
plt.legend()
plt.show()
```

### Diagnosis from Example Session

Looking at turn 1-8 in the sample:
- User tries Thai, Portuguese, English — all rejected as "not Mandarin"
- Same phrase expected repeatedly: `nǐ hǎo` then `nǐ zǎo`
- No conversation — just quiz loop

**Root cause:** System prompt enforces Mandarin-only, no fallback for multilingual users.

## Quick Debug Commands

```bash
# Find sessions with errors
grep -l '"flags":' data/sessions/*.json | xargs grep -l 'error'

# Show longest latency turns
python -c "
import json, sys
for f in sys.argv[1:]:
    s = json.load(open(f))
    for t in s['turns']:
        total = t['llm_latency_ms'] + sum(t['tts_latency_ms_per_sentence'])
        if total > 10000:
            print(f'{f}: turn {t[\"seq\"]} = {total}ms')
" data/sessions/*.json
```
