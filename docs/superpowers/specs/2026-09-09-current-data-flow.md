# Lingua — Data Flow Trace

End-to-end trace of one user turn from `data/sessions/session_20260909_181033.json` turn #11:

User says: *"I can see that being you"* (English, misrecognized).
LLM response: *"That isn't Mandarin. The phrase is: tā měitiān qù xuéxiào — 'She/He goes to school every day.'"*

## Step-by-step

### 1. Audio capture (16kHz, ~5KB chunks)
**Code:** `src/lingua/audio_loop.py:stream_audio_chunks`

```
[mic] → sounddevice.InputStream (44.1kHz, 4ch on Intel Smart Sound)
       → np.interp resample → 16kHz mono
       → callback queue → async generator
       → yields ~5120 bytes per chunk (~160ms of audio)
```

**Observed:** 16 chunks captured per 2.5s of silence (idle state).

### 2. WebM encoding (PyAV)
**Code:** `src/lingua/asr.py:PcmToOpusEncoder`

```
5KB PCM int16 → PyAV AudioResampler → libopus encoder → mux into WebM
              → container.mux(packets)
              → BytesIO buffer
              → return newly-written bytes since last call
```

**Critical:** output is **partial WebM**. First chunks are header-only (460 bytes). Server fails EBML parsing.

### 3. Buffered WebSocket send
**Code:** `src/lingua/asr.py:stream_transcribe`

```
accumulate encoder.feed() output until >= 8KB
send as single message to ws://127.0.0.1:3900/v1/audio/transcriptions/stream?sr=16000&format=webm_opus
```

**Why the buffer:** server saves what it receives as `.webm`. Partial WebM (header only) fails decoding. Buffering ensures every send is a complete container.

### 4. VoiceStudio ASR (faster-whisper)
**Code:** server-side, not in our repo

```
WebSocket receives binary → accumulates audio_chunks
periodically calls _transcribe_buffer(chunks, pcm_sr=16000)
  → av.open(io.BytesIO(buffer), format='webm')
  → faster_whisper.transcribe(audio, language='auto')
  → returns {"text", "segments", "language", "duration_s"}
sends JSON over WebSocket: {"type": "final", "text": "...", ...}
```

**Latency:** 0.5-2s per turn (depends on GPU load + audio length).

### 5. ASR event published
**Code:** `src/lingua/agent/harness.py:_transcribe_audio`

```python
elif result_type == "final":
    self._log(f"heard: {text!r}")
    if self.event_bus:
        self.event_bus.publish(AsrFinalEvent(ts=..., text=text, language=...))
    segments = [{"text": text, "language": "zh"}]  # ← always "zh" hardcoded!
    await self._process_transcript(segments)
```

**Bug:** `language` from ASR is dropped, segments hardcoded to `"zh"`.

### 6. HUD renders ASR
**Code:** `src/lingua/hud/display.py:Hud.apply`

```
AsrFinalEvent → appends to deque(maxlen=6) → transcript panel
                appends to log_lines → log panel
Live display redraws 10×/sec
```

### 7. LLM call (streaming)
**Code:** `src/lingua/agent/harness.py:_process_transcript`

```
loop.run_in_executor(None, lambda: tutor.stream_response(messages))
```

`stream_response` does:

```python
POST https://api.minimax.io/v1/text/chatcompletion_v2
  stream: true, max_tokens: 120
  body: messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "I can see that being you"},
    {"role": "assistant", "content": <previous turns>},
    ...
  ]

iterate SSE lines:
  data: {"choices": [{"delta": {"content": "{"}}]}
  data: {"choices": [{"delta": {"content": "\"type\": ..."}}]}
  ...
  data: [DONE]

accumulate full_text
after each chunk: find_sentence_boundary(full_text, emitted_len)
  if found: emit sentence, advance emitted_len
after stream end:
  if emitted_len < len(full_text):
    emit full_text[emitted_len:] as final sentence
  try json.loads(full_text) → if parses, re-split sentences from .text field
return full_text, sentences
```

**Observed:** for this turn, `full_text` is the JSON object, `sentences` is `['', ' "type":"explanation","text":"That isn\'t Mandarin.', ' The phrase is: tā měitiān qù xuéxiào — \'She/He goes to school every day.', "'"]` — broken on commas because the JSON was the *raw text*, not the extracted `text` field.

### 8. LlmDoneEvent published
```python
self.event_bus.publish(LlmDoneEvent(ts=..., response_chars=..., duration_ms=llm_ms))
```

### 9. TTS per sentence
**Code:** `src/lingua/agent/harness.py:_process_transcript`

For each sentence in `sentences`:

```python
speed = tutor._speed_for_turn(turn)  # 0.75 for Mandarin, 1.0 for explanation
result = tutor.speak(sentence, voice_profile, speed=speed)
# result.audio_bytes = PCM int16 LE 24kHz
# result.sample_rate = 24000

audio_arr = np.frombuffer(result.audio_bytes, dtype=np.int16)
sd.play(audio_arr, samplerate=result.sample_rate)
sd.wait()  # ← BLOCKS the event loop for the entire audio duration
```

**Latency per sentence:** ~1-2s for typical short sentence.

**Critical:** `sd.wait()` is blocking. While the tutor speaks, no user input can be detected.

### 10. TutorDoneEvent + recorder writes
```python
TtsDoneEvent → EventBus → HUD log
Turn(...) → SessionRecorder → data/sessions/session_*.json
```

### 11. Loop back to step 1

## Timing for one turn

| Step | Latency |
|---|---|
| Audio capture (silence detection) | ~1.5s of silence required |
| ASR (WebSocket round-trip + faster-whisper) | 1.0-2.0s |
| LLM TTFB (streaming) | 1.0-2.0s |
| LLM total (short response) | 2.0-3.5s |
| TTS per sentence | 0.8-2.0s × N sentences |
| sd.play + wait | equals audio duration (real time) |
| **Total perceived latency** | **6-12s** for short response, **12-18s** for multi-sentence |

## Failure modes observed in session data

### Mode A: stuck on same drill phrase
Session `20260909_181033` turn #12-20: same `expected="nǐ kàn guò nà běn shū ma"` offered 8 times in a row.

Root cause: `tutor._ask_llm` (or `stream_response`) does not look at history of recent `expected` values. No repetition detection.

### Mode B: TTS sentences split inside JSON
Session `20260909_181033` turn #5, #15, #18: `llm_parsed_json: null` because LLM exceeded `max_tokens=120` mid-JSON. The raw text is cut off, but `stream_response` then runs `find_sentence_boundary` on it, splitting the **truncated JSON syntax** into multiple sentences.

Each "sentence" is then spoken individually: `{"type": "explanation", "text": "Close!`, then `You said: 'Wǒ shì Wáng Xīnbīng wáng.`, etc.

### Mode C: hardcoded language="zh"
All sessions show `asr_language: "zh"` even when user speaks English, Portuguese, or random words. The TurnRouter route() decision is made on the hardcoded value.

### Mode D: long sessions degrade
Context window grows unboundedly. Later turns in long sessions show lower-quality responses (LLM confused by stale history).

## What's right with the current flow

- ASR connection is reliable when WebM is buffered correctly.
- TTS PCM at 24kHz plays at correct pitch when `sample_rate=24000` is passed.
- pinyin_displayed in HUD shows the Mandarin with tone marks — useful for the learner.
- Recorder produces structured logs that let us diagnose issues after the fact.

The pipeline is **technically correct but socially broken**. The fix isn't in any single component — it's in how the harness composes them.
