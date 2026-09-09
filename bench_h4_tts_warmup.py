"""H4: Is first TTS request much slower than subsequent (model warmup)?

Test: send 10 sequential TTS requests with short Mandarin text.
If first >> rest, warmup is the bottleneck → keep model hot.
"""
import statistics
import time

import requests

URL = "http://127.0.0.1:3900/v1/audio/speech"


def tts(text: str) -> tuple[float, int]:
    t0 = time.monotonic()
    r = requests.post(URL, json={"input": text, "voice": "8c53222c", "response_format": "pcm"}, timeout=20)
    dt = (time.monotonic() - t0) * 1000
    r.raise_for_status()
    return dt, len(r.content)


def main():
    text = "你好世界"
    print(f"=== H4: {10} sequential TTS requests, text={text!r} ===")
    timings = []
    for i in range(10):
        # wait 5s between requests to simulate "user paused then spoke again"
        if i > 0:
            time.sleep(5)
        ms, n_bytes = tts(text)
        timings.append(ms)
        print(f"  request-{i}: {ms:.0f}ms ({n_bytes} bytes)")

    print(f"\nResults:")
    print(f"  all    mean={statistics.mean(timings):.0f}ms median={statistics.median(timings):.0f}ms")
    print(f"  first  {timings[0]:.0f}ms")
    print(f"  rest   mean={statistics.mean(timings[1:]):.0f}ms median={statistics.median(timings[1:]):.0f}ms")
    print(f"  diff   {timings[0] - statistics.mean(timings[1:]):.0f}ms")


main()
