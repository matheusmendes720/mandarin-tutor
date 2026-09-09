"""H2: Parallel TTS chunks — does it beat serial?

Hypothesis: 3 sentences in parallel ≈ time of 1 sentence (since bottleneck
is server TTFB ~3.5s, parallel = 3.5s vs serial = 3×4s = 12s).
"""
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import requests

URL = "http://127.0.0.1:3900/v1/audio/speech"


def tts(text: str) -> tuple[float, int]:
    t0 = time.monotonic()
    r = requests.post(URL, json={"input": text, "voice": "8c53222c", "response_format": "pcm"}, timeout=30)
    dt = (time.monotonic() - t0) * 1000
    r.raise_for_status()
    return dt, len(r.content)


sentences = [
    "你好！",
    "我来自巴西。",
    "我喜欢学中文。",
]


def serial():
    t0 = time.monotonic()
    results = []
    for s in sentences:
        ms, n = tts(s)
        results.append((ms, n))
    return (time.monotonic() - t0) * 1000, results


def parallel():
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(tts, s) for s in sentences]
        results = [f.result() for f in futures]
    return (time.monotonic() - t0) * 1000, results


def main():
    print(f"=== H2: serial vs parallel TTS for {len(sentences)} short Mandarin sentences ===\n")

    print("Serial:")
    total_s, results_s = serial()
    for ms, n in results_s:
        print(f"  {ms:.0f}ms ({n} bytes)")
    print(f"  TOTAL: {total_s:.0f}ms\n")

    print("Parallel (3 workers):")
    total_p, results_p = parallel()
    for ms, n in results_p:
        print(f"  {ms:.0f}ms ({n} bytes)")
    print(f"  TOTAL: {total_p:.0f}ms\n")

    print(f"Speedup: {total_s/total_p:.2f}x ({total_s-total_p:.0f}ms saved)")
    print(f"\nInterpretation:")
    if total_p < total_s * 0.5:
        print("  Parallel is 2x+ faster — server is parallelizable. WIN.")
    elif total_p < total_s * 0.8:
        print("  Parallel is somewhat faster — moderate win.")
    else:
        print("  Server is sequential — chunking won't help much.")


main()
