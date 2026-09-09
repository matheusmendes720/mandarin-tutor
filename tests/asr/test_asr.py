"""Tests for VoiceStudio WebSocket streaming ASR."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lingua.asr import stream_transcribe
from lingua.voice_studio import VoiceStudioClient


class MockWebSocket:
    """Mock WebSocket that works as an async context manager and async iterator."""

    def __init__(self, messages: list[str]):
        self.messages = messages
        self.index = 0
        self.sent_messages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.messages):
            raise StopAsyncIteration()
        msg = self.messages[self.index]
        self.index += 1
        return msg

    async def recv(self):
        if self.index >= len(self.messages):
            raise StopAsyncIteration()
        msg = self.messages[self.index]
        self.index += 1
        return msg

    async def send(self, data):
        self.sent_messages.append(data)


class TestStreamTranscribe:
    """Test stream_transcribe function."""

    @pytest.fixture
    def mock_voice_studio(self):
        """Create a mock VoiceStudioClient."""
        vs = MagicMock(spec=VoiceStudioClient)
        vs.is_available.return_value = True
        return vs

    @pytest.fixture
    def sample_chunks(self):
        """Create sample PCM chunks for testing."""
        # 16000 Hz * 0.16s = 2560 samples = 5120 bytes (int16 mono)
        chunk_size = 5120
        return [b"\x00" * chunk_size for _ in range(5)]

    @pytest.mark.asyncio
    async def test_stream_transcribe_yields_final_transcript(
        self, mock_voice_studio, sample_chunks
    ):
        """Verify final transcript is yielded from WebSocket."""
        messages = [
            '{"type": "session.started"}',
            '{"type": "final", "text": "Hello world"}',
        ]
        mock_ws = MockWebSocket(messages)

        # Create async context manager mock
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("lingua.asr.websockets") as mock_websockets:
            mock_websockets.connect.return_value = mock_cm

            async def chunk_iter():
                for chunk in sample_chunks:
                    yield chunk

            results = []
            async for result in stream_transcribe(chunk_iter(), mock_voice_studio):
                results.append(result)

            # Should have received at least the final transcript
            final_results = [r for r in results if r.get("type") == "final"]
            assert len(final_results) > 0, f"Should yield final transcript, got: {results}"
            assert final_results[0].get("text") == "Hello world"

    @pytest.mark.asyncio
    async def test_stream_transcribe_handles_partial(
        self, mock_voice_studio, sample_chunks
    ):
        """Verify partial results are yielded."""
        messages = [
            '{"type": "session.started"}',
            '{"type": "partial", "text": "Hel"}',
            '{"type": "partial", "text": "Hello"}',
            '{"type": "final", "text": "Hello world"}',
        ]
        mock_ws = MockWebSocket(messages)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("lingua.asr.websockets") as mock_websockets:
            mock_websockets.connect.return_value = mock_cm

            async def chunk_iter():
                for chunk in sample_chunks:
                    yield chunk

            results = []
            async for result in stream_transcribe(chunk_iter(), mock_voice_studio):
                results.append(result)

            # Should have partial results
            partial_results = [r for r in results if r.get("type") == "partial"]
            assert len(partial_results) > 0, f"Should yield partial transcripts, got: {results}"

    @pytest.mark.asyncio
    async def test_stream_transcribe_error_handling(
        self, mock_voice_studio, sample_chunks
    ):
        """Verify errors are yielded properly."""
        messages = [
            '{"type": "session.started"}',
            '{"type": "error", "message": "Connection failed"}',
        ]
        mock_ws = MockWebSocket(messages)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("lingua.asr.websockets") as mock_websockets:
            mock_websockets.connect.return_value = mock_cm

            async def chunk_iter():
                for chunk in sample_chunks:
                    yield chunk

            results = []
            async for result in stream_transcribe(chunk_iter(), mock_voice_studio):
                results.append(result)

            # Should have error result
            error_results = [r for r in results if r.get("type") == "error"]
            assert len(error_results) > 0, f"Should yield error, got: {results}"
            assert "Connection failed" in error_results[0].get("text", "")

    @pytest.mark.asyncio
    async def test_stream_transcribe_connection_error(self, mock_voice_studio, sample_chunks):
        """Verify ConnectionError is raised when VoiceStudio unavailable."""
        mock_voice_studio.is_available.return_value = False

        async def chunk_iter():
            for chunk in sample_chunks:
                yield chunk

        with pytest.raises(ConnectionError):
            async for _ in stream_transcribe(chunk_iter(), mock_voice_studio):
                pass

    @pytest.mark.asyncio
    async def test_stream_transcribe_sends_end_signal(self, mock_voice_studio, sample_chunks):
        """Verify input_audio.end is sent after chunks complete."""
        messages = [
            '{"type": "session.started"}',
            '{"type": "final", "text": "Test"}',
        ]
        mock_ws = MockWebSocket(messages)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("lingua.asr.websockets") as mock_websockets:
            mock_websockets.connect.return_value = mock_cm

            async def chunk_iter():
                for chunk in sample_chunks:
                    yield chunk

            async for _ in stream_transcribe(chunk_iter(), mock_voice_studio):
                pass

            # Verify send was called with audio data
            assert len(mock_ws.sent_messages) > 0, "Should have sent audio chunks"
            # Verify the last send was the end signal
            last_message = mock_ws.sent_messages[-1]
            assert last_message == '{"type": "input_audio.end"}'
