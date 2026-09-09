"""Tests for PCM → Opus/WebM encoder used by streaming ASR."""
import struct

import pytest

from lingua.asr import PcmToOpusEncoder


def _silence_pcm(duration_s: float, sample_rate: int = 16000) -> bytes:
    n = int(duration_s * sample_rate)
    return b"\x00\x00" * n


def _tone_pcm(freq: float, duration_s: float, sample_rate: int = 16000, amp: int = 8000) -> bytes:
    n = int(duration_s * sample_rate)
    samples = []
    import math
    for i in range(n):
        samples.append(int(amp * math.sin(2 * math.pi * freq * (i / sample_rate))))
    return struct.pack(f"<{n}h", *samples)


def test_encoder_produces_webm_header():
    enc = PcmToOpusEncoder(sample_rate=16000, channels=1)
    out = b""
    out += enc.feed(_silence_pcm(0.5))
    out += enc.flush()
    # WebM starts with EBML magic 0x1A 0x45 0xDF 0xA3
    assert out[:4] == b"\x1a\x45\xdf\xa3", f"expected EBML header, got {out[:16].hex()}"


def test_encoder_handles_incremental_chunks():
    enc = PcmToOpusEncoder(sample_rate=16000, channels=1)
    out = b""
    for _ in range(10):
        out += enc.feed(_silence_pcm(0.1))
    out += enc.flush()
    assert len(out) > 0
    assert out[:4] == b"\x1a\x45\xdf\xa3"


def test_encoder_roundtrip_preserves_audio():
    """Encode tone, then we can decode it back to verify it's a valid Opus stream."""
    import io
    import av

    enc = PcmToOpusEncoder(sample_rate=16000, channels=1)
    blob = enc.feed(_tone_pcm(440, 1.0))
    blob += enc.flush()

    # Decode using PyAV's container (need a readable file-like)
    container = av.open(io.BytesIO(blob), mode="r", format="webm")
    # Drain — iterate until exhausted
    frames = list(container.decode(audio=0))
    assert len(frames) > 0, "no audio frames decoded"
    # Each Opus frame is 20ms = 320 samples at 16kHz. 1s ≈ 50 frames.
    total_samples = sum(f.to_ndarray().shape[-1] for f in frames)
    # Some frames will be flushed late — assert non-trivial amount decoded
    assert total_samples >= 1000, f"expected ≥1000 samples, got {total_samples}"
