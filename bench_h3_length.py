"""H3: How does TTS latency scale with text length?

Test: TTS for texts of varying lengths, measure latency.
Hypothesis: longer text → significantly longer synthesis.
"""
import statistics
import time

import requests

URL = "http://127.0.0.1:3900/v1/audio/speech"


def tts(text: str) -> tuple[float, int]:
    t0 = time.monotonic()
    r = requests.post(URL, json={"input": text, "voice": "8c53222c", "response_format": "pcm"}, timeout=30)
    dt = (time.monotonic() - t0) * 1000
    r.raise_for_status()
    return dt, len(r.content)


samples = [
    ("short", "你好"),
    ("medium", "你好世界"),
    ("long", "你好世界今天天气怎么样"),
    ("xlong", "你好世界今天天气怎么样我喜欢吃苹果"),
    ("paragraph", "你好！我叫小明，我来自巴西，我想学中文。我每天都说一点点中文。今天我们学什么？"),
]


def main():
    print("=== H3: TTS latency vs text length ===")
    for label, text in samples:
        timings = []
        for i in range(3):
            ms, n = tts(text)
            timings.append(ms)
            time.sleep(0.5)
        mean_ms = statistics.mean(timings)
        print(f"  {label} ({len(text)} chars, {mean_ms/1000:.1f}s avg):")
        for ms in timings:
            print(f"    {ms:.0f}ms")


main()
