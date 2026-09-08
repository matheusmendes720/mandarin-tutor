"""Tests for async audio streaming."""
from __future__ import annotations

import asyncio
import numpy as np
import pytest
import sounddevice as sd

from lingua.audio_loop import stream_audio_chunks


class TestStreamAudioChunks:
    """Test stream_audio_chunks function."""

    def test_stream_yields_chunks(self):
        """Yields raw PCM chunks while recording. Stops on silence."""
        async def run():
            chunks = []
            max_chunks = 50  # safety limit
            async for chunk in stream_audio_chunks(
                sample_rate=16000,
                channels=1,
                chunk_ms=160,
                silence_threshold=0.01,
                max_seconds=5.0,
            ):
                chunks.append(chunk)
                if len(chunks) >= max_chunks:
                    break
            return chunks

        chunks = asyncio.run(run())
        assert len(chunks) > 0, "Should yield at least one chunk"
        for chunk in chunks:
            assert isinstance(chunk, bytes), "Each chunk must be bytes"
            assert len(chunk) > 0, "Chunk must not be empty"

    def test_stream_respects_max_seconds(self):
        """Stops automatically when max_seconds is reached."""
        async def run():
            chunks = []
            async for chunk in stream_audio_chunks(
                sample_rate=16000,
                channels=1,
                chunk_ms=160,
                silence_threshold=0.01,
                max_seconds=0.5,  # short timeout
            ):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(run())
        # Should get some chunks before hitting max_seconds
        assert len(chunks) > 0

    def test_stream_produces_pcm_data(self):
        """Produces valid PCM int16 data."""
        async def run():
            chunks = []
            async for chunk in stream_audio_chunks(
                sample_rate=16000,
                channels=1,
                chunk_ms=160,
                silence_threshold=0.01,
                max_seconds=1.0,
            ):
                chunks.append(chunk)
                if len(chunks) >= 10:
                    break
            return chunks

        chunks = asyncio.run(run())
        assert len(chunks) > 0
        # PCM 16-bit mono: 16000 Hz * 0.16s = 2560 samples = 5120 bytes
        for chunk in chunks:
            assert len(chunk) == 5120, f"Expected 5120 bytes per chunk, got {len(chunk)}"

    def test_stream_returns_async_iterator(self):
        """Returns an async iterator for use with async for."""
        iterator = stream_audio_chunks(
            sample_rate=16000,
            channels=1,
            chunk_ms=160,
            silence_threshold=0.01,
            max_seconds=1.0,
        )
        assert hasattr(iterator, "__aiter__")
        assert hasattr(iterator, "__anext__")
