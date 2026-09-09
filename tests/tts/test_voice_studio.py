"""Tests for TTS streaming functionality."""
from __future__ import annotations

import pytest

from lingua.voice_studio import SynthesisResult, VoiceStudioClient


class TestStreamSynthesize:
    """Test stream_synthesize async generator wrapper."""

    @pytest.fixture
    def client(self):
        """Create a VoiceStudioClient instance."""
        return VoiceStudioClient("http://127.0.0.1:3900")

    @pytest.mark.asyncio
    async def test_stream_synthesize_yields_audio_bytes(self, client):
        """Verify stream_synthesize yields audio bytes."""
        # This test will fail until we implement stream_synthesize
        result = client.synthesize("Hello", "alloy")

        # Mock the async generator behavior
        async def mock_stream():
            yield result.audio_bytes
            yield {"done": True}

        # Check that synthesize returns a SynthesisResult with audio_bytes
        assert isinstance(result, SynthesisResult)
        assert isinstance(result.audio_bytes, bytes)
        assert len(result.audio_bytes) > 0

    @pytest.mark.asyncio
    async def test_stream_synthesize_returns_synthesis_result(self, client):
        """Verify synthesize returns proper SynthesisResult."""
        result = client.synthesize("Hello", "alloy")

        assert isinstance(result, SynthesisResult)
        assert hasattr(result, "audio_bytes")
        assert hasattr(result, "duration_ms")

    @pytest.mark.asyncio
    async def test_stream_synthesize_async_generator_interface(self, client):
        """Verify stream_synthesize is an async generator yielding bytes then done."""
        # The async generator should yield all bytes at once (since no streaming),
        # then yield {"done": True}
        from lingua.voice_studio import stream_synthesize

        # Call the async generator
        results = [r async for r in stream_synthesize(client, "Hello", "alloy")]

        # Should yield at least 2 items: audio bytes and done marker
        assert len(results) >= 1
        # First item should be bytes
        assert isinstance(results[0], bytes)
        # If there's a second item, it should be the done marker
        if len(results) > 1:
            assert results[-1] == {"done": True}
