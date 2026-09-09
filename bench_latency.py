"""Latency benchmark — measure each pipeline boundary.

Run: python bench_latency.py
"""
import asyncio
import json
import statistics
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from lingua.asr import stream_transcribe, PcmToOpusEncoder
from lingua.voice_studio import VoiceStudioClient
from lingua.tutor import MandarinTutor
from lingua.config import LinguaConfig


def log(tag: str, **fields):
    print(json.dumps({"tag": tag, **{k: round(v, 3) if isinstance(v, float) else v for k, v in fields.items()}}), flush=True)


def bench_speaker(n: int = 10):
    """Time how long it takes sd.play to actually start + complete."""
    sr = 16000
    sample = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 8000).astype(np.int16)
    timings = []
    for i in range(n):
        t0 = time.monotonic()
        sd.play(sample, samplerate=sr)
        sd.wait()
        dt = (time.monotonic() - t0) * 1000
        timings.append(dt)
        log("speaker", i=i, ms=dt)
    log("speaker.summary", mean=statistics.mean(timings), median=statistics.median(timings), p95=sorted(timings)[int(0.95 * n)])


def bench_tts(n: int = 5):
    """Time TTS request + synthesis."""
    vs = VoiceStudioClient()
    config = LinguaConfig.from_toml("lingua.toml")
    tutor = MandarinTutor(config)
    timings = []
    for i in range(n):
        t0 = time.monotonic()
        result = tutor.speak("你好世界", config.voicestudio.voice_mandarin)
        dt = (time.monotonic() - t0) * 1000
        timings.append(dt)
        log("tts", i=i, ms=dt, bytes=len(result.audio_bytes), sample_rate=result.sample_rate)
    log("tts.summary", mean=statistics.mean(timings), median=statistics.median(timings))


async def bench_llm(n: int = 3):
    """Time LLM response (the slowest part of the chain)."""
    config = LinguaConfig.from_toml("lingua.toml")
    tutor = MandarinTutor(config)
    timings = []
    for i in range(n):
        t0 = time.monotonic()
        turn = tutor._ask_llm("Tell me how to say hello in Mandarin.")
        dt = (time.monotonic() - t0) * 1000
        timings.append(dt)
        log("llm", i=i, ms=dt, text_len=len(turn.text))
    log("llm.summary", mean=statistics.mean(timings), median=statistics.median(timings))


async def bench_asr():
    """Time ASR round-trip with a 2s synthetic tone."""
    vs = VoiceStudioClient()
    sr = 16000
    n = sr * 2
    # 440Hz tone — server should detect silence + return quickly
    pcm = np.sin(2 * np.pi * 440 * np.linspace(0, 2, n)) * 8000
    pcm = pcm.astype(np.int16).tobytes()

    async def chunk_iter():
        for i in range(0, len(pcm), 5120):
            yield pcm[i:i+5120]

    t0 = time.monotonic()
    results = []
    async for r in stream_transcribe(chunk_iter(), vs):
        results.append(r)
    dt = (time.monotonic() - t0) * 1000
    log("asr", total_ms=dt, n_results=len(results), kinds=[r.get("type") for r in results])


async def bench_end_to_end(n: int = 3):
    """Time the full pipeline: ASR (synthetic) → LLM → TTS → playback start."""
    vs = VoiceStudioClient()
    config = LinguaConfig.from_toml("lingua.toml")
    tutor = MandarinTutor(config)
    sr = 16000
    pcm = np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2)) * 8000
    pcm = pcm.astype(np.int16).tobytes()

    totals = {"asr": [], "llm": [], "tts": [], "playback": [], "full": []}
    for i in range(n):
        t_total = time.monotonic()

        # ASR
        async def chunk_iter():
            for j in range(0, len(pcm), 5120):
                yield pcm[j:j+5120]

        t0 = time.monotonic()
        async for r in stream_transcribe(chunk_iter(), vs):
            if r.get("type") == "final":
                user_text = r.get("text", "")
                break
        else:
            user_text = ""
        asr_ms = (time.monotonic() - t0) * 1000

        # LLM
        t0 = time.monotonic()
        turn = tutor._ask_llm(user_text or "hello")
        llm_ms = (time.monotonic() - t0) * 1000

        # TTS
        t0 = time.monotonic()
        result = tutor.speak(turn.text[:60], config.voicestudio.voice_mandarin, speed=0.75)
        tts_ms = (time.monotonic() - t0) * 1000

        # Playback start (measure how long until first audio hits speakers)
        audio = np.frombuffer(result.audio_bytes, dtype=np.int16)
        t0 = time.monotonic()
        sd.play(audio, samplerate=result.sample_rate)
        # Wait for ~100ms of playback so we're sure it started
        sd.wait()
        play_ms = (time.monotonic() - t0) * 1000

        full_ms = (time.monotonic() - t_total) * 1000
        log("e2e", i=i, asr_ms=asr_ms, llm_ms=llm_ms, tts_ms=tts_ms, play_ms=play_ms, full_ms=full_ms)
        for k, v in zip(totals.keys(), [asr_ms, llm_ms, tts_ms, play_ms, full_ms]):
            totals[k].append(v)

    log("e2e.summary", **{k: {"mean": statistics.mean(v), "median": statistics.median(v), "min": min(v), "max": max(v)} for k, v in totals.items()})


async def main():
    log("bench.start")
    bench_speaker(n=5)
    await bench_llm(n=2)
    await bench_asr()
    await bench_end_to_end(n=2)
    log("bench.end")


if __name__ == "__main__":
    asyncio.run(main())
