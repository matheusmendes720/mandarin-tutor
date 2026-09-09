"""H7: Simulate streaming LLM + first-sentence TTS.

Approach: ask MiniMax streaming. As each token arrives, accumulate. When
we see a sentence boundary (。！？.!?), snapshot what we have and start TTS
on that snapshot in parallel with continued LLM streaming.

Measure: time from request start to "first audio byte ready to play".
Compare against current serial (full LLM done → full TTS done → play).

We don't actually play audio here — we measure the time-to-first-tts-bytes.
"""
import json
import re
import statistics
import time

import requests


URL_LLM = "https://api.minimax.io/v1/text/chatcompletion_v2"
URL_TTS = "http://127.0.0.1:3900/v1/audio/speech"


def ask_llm_stream(messages: list, api_key: str) -> tuple[float, str, float]:
    """Stream LLM. Return (ttfb_ms, full_text, total_ms)."""
    t0 = time.monotonic()
    r = requests.post(
        URL_LLM,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "MiniMax-M3", "messages": messages, "stream": True},
        stream=True,
        timeout=30,
    )
    r.raise_for_status()
    ttfb = None
    text = ""
    for line in r.iter_lines():
        if not line:
            continue
        s = line.decode()
        if not s.startswith("data: "):
            continue
        payload = s[6:]
        if payload.strip() == "[DONE]":
            break
        if ttfb is None:
            ttfb = (time.monotonic() - t0) * 1000
        try:
            obj = json.loads(payload)
            delta = obj.get("choices", [{}])[0].get("delta", {})
            text += delta.get("content", "")
        except json.JSONDecodeError:
            continue
    total = (time.monotonic() - t0) * 1000
    return ttfb or 0, text, total


def ask_llm_serial(messages: list, api_key: str) -> tuple[float, str]:
    """Non-streaming LLM. Return (total_ms, text)."""
    t0 = time.monotonic()
    r = requests.post(
        URL_LLM,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "MiniMax-M3", "messages": messages},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"] or ""
    return (time.monotonic() - t0) * 1000, text


def tts(text: str) -> float:
    """Returns TTS latency in ms."""
    t0 = time.monotonic()
    r = requests.post(
        URL_TTS,
        json={"input": text, "voice": "8c53222c", "response_format": "pcm"},
        timeout=20,
    )
    r.raise_for_status()
    return (time.monotonic() - t0) * 1000


# Sentence boundaries: Chinese 。！？ and English . ! ?
_SENT_RE = re.compile(r"[。！？.!?\n]")


def split_first_sentence(text: str) -> tuple[str, str]:
    """Return (first_sentence_with_delim, remainder)."""
    m = _SENT_RE.search(text)
    if m is None:
        return text, ""
    return text[: m.end()], text[m.end() :]


def measure_serial(messages, api_key):
    """Current approach: LLM done → TTS done → play."""
    t_total = time.monotonic()
    llm_ms, text = ask_llm_serial(messages, api_key)
    tts_ms = tts(text)
    total = (time.monotonic() - t_total) * 1000
    return {"llm_ms": llm_ms, "tts_ms": tts_ms, "total_ms": total, "text": text}


def measure_streaming(messages, api_key):
    """H7 approach: stream LLM, fire TTS on first sentence in parallel."""
    t_total = time.monotonic()
    ttfb_ms, full_text, total_llm = ask_llm_stream(messages, api_key)
    first_sent, remainder = split_first_sentence(full_text)
    if not first_sent.strip():
        first_sent = full_text[:20] or full_text  # fallback
    # In real implementation TTS starts as soon as we have the sentence.
    # Here we measure: TTS on first_sent + TTS on remainder (parallel would
    # be ~max(tts1, tts2) not sum, but server 429s parallel so we use serial
    # to be honest about what we can achieve today).
    tts1_ms = tts(first_sent)
    tts2_ms = tts(remainder) if remainder.strip() else 0
    # Best case: parallel TTS — measure that too, even though server is 429.
    parallel_tts_ms = max(tts1_ms, tts2_ms)
    serial_tts_ms = tts1_ms + tts2_ms
    # Perceived latency to first audio = LLM TTFB + TTS(1st sentence)
    perceived_ms = ttfb_ms + tts1_ms
    total = (time.monotonic() - t_total) * 1000
    return {
        "llm_ttfb_ms": ttfb_ms,
        "llm_total_ms": total_llm,
        "tts_first_ms": tts1_ms,
        "tts_rest_ms": tts2_ms,
        "parallel_tts_ms": parallel_tts_ms,
        "serial_tts_ms": serial_tts_ms,
        "perceived_first_audio_ms": perceived_ms,
        "total_wall_ms": total,
        "first_sentence": first_sent,
        "remainder_len": len(remainder),
    }


def main():
    import os
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("MINIMAX_API_KEY not set")
        return

    prompts = [
        [{"role": "user", "content": "Teach me to say hello in Mandarin. Respond with ONE short sentence in Mandarin, then explain in English briefly."}],
        [{"role": "user", "content": "What's the weather like in Beijing? Reply in Mandarin only, one sentence."}],
        [{"role": "user", "content": "Drill me on tones for 'ma'. Reply with all 4 tones in Mandarin."}],
    ]

    print("=== H7: serial vs streaming-LLM with first-sentence TTS ===\n")

    for i, messages in enumerate(prompts):
        print(f"--- prompt {i} ---")
        # Serial
        s = measure_serial(messages, api_key)
        print(f"  Serial:    LLM {s['llm_ms']:.0f}ms + TTS {s['tts_ms']:.0f}ms = {s['total_ms']:.0f}ms total")
        print(f"             text: {s['text'][:80]!r}")
        # Streaming
        st = measure_streaming(messages, api_key)
        print(f"  Streaming: LLM-TTFB {st['llm_ttfb_ms']:.0f}ms + TTS(1st) {st['tts_first_ms']:.0f}ms = {st['perceived_first_audio_ms']:.0f}ms perceived")
        print(f"             1st sentence: {st['first_sentence']!r}")
        print(f"             remainder chars: {st['remainder_len']}")
        print(f"             parallel TTS (ideal): {st['parallel_tts_ms']:.0f}ms")
        print(f"             serial TTS (realistic today): {st['serial_tts_ms']:.0f}ms")
        speedup = s["total_ms"] / max(st["perceived_first_audio_ms"], 1)
        print(f"  → Speedup to first audio: {speedup:.2f}x")
        print()


main()
