"""Verify that buffered WebM sending (>= 8KB) produces valid WebM at every send."""
import io

import av
import numpy as np
import pytest

from lingua.asr import PcmToOpusEncoder


def _pcm_silence(seconds: float = 2.0, sample_rate: int = 16000) -> bytes:
    return b"\x00\x00" * int(seconds * sample_rate)


def test_each_buffered_chunk_is_valid_webm():
    """When we accumulate encoder output and only send at >= 8KB OR at end,
    every chunk we send should be a valid WebM file parseable by libav."""
    enc = PcmToOpusEncoder(sample_rate=16000, channels=1)
    pcm = _pcm_silence(3.0)
    buffered = []
    buf = b""
    SENT_THRESHOLD = 8192
    for i in range(0, len(pcm), 5120):
        chunk = pcm[i:i + 5120]
        webm = enc.feed(chunk)
        if webm:
            buf += webm
        if len(buf) >= SENT_THRESHOLD:
            buffered.append(buf)
            buf = b""
    tail = enc.flush()
    if tail:
        buf += tail
    if buf:
        buffered.append(buf)

    assert len(buffered) >= 1, "expected at least one buffered chunk"
    for i, chunk in enumerate(buffered):
        # Each chunk must be parseable as a WebM container on its own.
        try:
            container = av.open(io.BytesIO(chunk), mode="r", format="webm")
            n_streams = len(container.streams)
            assert n_streams >= 1, f"chunk {i} has no streams"
        except Exception as e:
            pytest.fail(f"chunk {i} ({len(chunk)}b) failed to parse: {e!r}")


def test_small_first_chunk_is_dropped_not_sent():
    """If the very first encoded chunk is smaller than the threshold, we don't
    send a partial WebM — we keep accumulating until we have a complete one.
    The very last flush() call should always produce a sendable WebM."""
    enc = PcmToOpusEncoder(sample_rate=16000, channels=1)
    pcm = _pcm_silence(2.0)
    sent = []
    buf = b""
    for i in range(0, len(pcm), 5120):
        chunk = pcm[i:i + 5120]
        webm = enc.feed(chunk)
        if webm:
            buf += webm
        if len(buf) >= 8192:
            sent.append(buf)
            buf = b""
    tail = enc.flush()
    if tail:
        buf += tail
    if buf:
        sent.append(buf)

    for i, chunk in enumerate(sent):
        # Must always be parseable.
        container = av.open(io.BytesIO(chunk), mode="r", format="webm")
        assert len(container.streams) >= 1


def test_naive_chunked_sending_produces_invalid_partials():
    """Reproducer for the production bug: sending encoder.feed() output
    immediately as it arrives produces invalid partial WebM containers that
    the VoiceStudio server fails to decode. This test DOCUMENTS the bug —
    the fix is to buffer and send >= 8KB at a time (see above tests)."""
    enc = PcmToOpusEncoder(sample_rate=16000, channels=1)
    pcm = _pcm_silence(2.0)
    naive_chunks = []
    for i in range(0, len(pcm), 5120):
        chunk = pcm[i:i + 5120]
        webm = enc.feed(chunk)
        if webm:
            naive_chunks.append(webm)
    tail = enc.flush()
    if tail:
        naive_chunks.append(tail)

    # At least one of the small naive chunks fails to parse.
    invalid = 0
    for i, chunk in enumerate(naive_chunks):
        if len(chunk) < 8192:  # partial WebM
            try:
                av.open(io.BytesIO(chunk), mode="r", format="webm")
            except Exception:
                invalid += 1
    assert invalid > 0, (
        "Expected at least one partial WebM to be invalid; if this fails "
        "the encoder now produces self-contained chunks and the buffer is "
        "no longer needed."
    )
