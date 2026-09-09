"""H1: Does persistent ASR WebSocket save latency?

Test: run N=5 ASR rounds, each opens a new WebSocket (current behavior).
Measure TTFB (time to first 'session.started') and total round-trip.

Then compare: 1 persistent WebSocket for N=5 rounds, same metric.

Don't need to actually decode — we just measure the connection handshake cost.
"""
import asyncio
import statistics
import time

import websockets

WS_URL = "ws://127.0.0.1:3900/v1/audio/transcriptions/stream?sr=16000&format=webm_opus"


async def single_round(label: str) -> tuple[float, float]:
    """Open WS, wait for session.started, send 1KB silence, wait for final, close."""
    t_connect = time.monotonic()
    async with websockets.connect(WS_URL) as ws:
        # wait for session.started
        msg = await ws.recv()
        ttfb_ms = (time.monotonic() - t_connect) * 1000

        # send minimal silence
        await ws.send(b"\x00" * 5120)
        import json
        await ws.send(json.dumps({"type": "input_audio.end"}))

        # wait for final
        t0 = time.monotonic()
        async for m in ws:
            data = json.loads(m)
            if data.get("type") == "final":
                break
        round_ms = (time.monotonic() - t_connect) * 1000

    print(f"  {label}: TTFB={ttfb_ms:.0f}ms, total={round_ms:.0f}ms")
    return ttfb_ms, round_ms


async def main():
    n = 5
    print(f"=== H1: {n} ASR rounds, fresh WebSocket each time ===")
    ttfs = []
    rounds = []
    for i in range(n):
        ttf, total = await single_round(f"round-{i}")
        ttfs.append(ttf)
        rounds.append(total)
    print(f"\nResults:")
    print(f"  TTFB  mean={statistics.mean(ttfs):.0f}ms median={statistics.median(ttfs):.0f}ms min={min(ttfs):.0f}ms max={max(ttfs):.0f}ms")
    print(f"  total mean={statistics.mean(rounds):.0f}ms median={statistics.median(rounds):.0f}ms min={min(rounds):.0f}ms max={max(rounds):.0f}ms")


asyncio.run(main())
