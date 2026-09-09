"""Tests for VoiceAgentHarness - full-duplex voice loop."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lingua.audio_loop import stream_audio_chunks
from lingua.asr import stream_transcribe
from lingua.tutor import MandarinTutor, TutorTurn
from lingua.voice_studio import SynthesisResult


def create_async_iter(items: list[Any]) -> AsyncIterator[Any]:
    """Create an async iterator from a list."""
    async def _iter():
        for item in items:
            yield item
    return _iter()


class TestVoiceAgentHarness:
    """Test VoiceAgentHarness async orchestration."""

    @pytest.fixture
    def mock_tutor(self):
        """Create a mock MandarinTutor."""
        tutor = MagicMock(spec=MandarinTutor)
        tutor._ask_llm = MagicMock(return_value=TutorTurn(
            type="explanation",
            text="Hello! This is a test response.",
            expected="",
            feedback="",
        ))
        return tutor

    @pytest.fixture
    def sample_audio_chunk(self):
        """Create a sample PCM chunk."""
        # 16000 Hz * 0.16s = 2560 samples = 5120 bytes (int16 mono)
        return b"\x00\x00" * 2560

    @pytest.mark.asyncio
    async def test_harness_runs_without_error(self, mock_tutor, sample_audio_chunk):
        """Verify VoiceAgentHarness.run() completes without error."""
        from lingua.agent.harness import VoiceAgentHarness

        # Mock stream_audio_chunks to yield one chunk then stop
        mock_audio_chunks = create_async_iter([sample_audio_chunk])

        # Mock stream_transcribe to yield a final transcript
        mock_transcribe = create_async_iter([
            {"type": "final", "text": "Hello world"}
        ])

        with patch("lingua.agent.harness.stream_audio_chunks", return_value=mock_audio_chunks):
            with patch("lingua.agent.harness.stream_transcribe", return_value=mock_transcribe):
                harness = VoiceAgentHarness(tutor=mock_tutor)

                # Run should complete without raising
                await harness.run()

    @pytest.mark.asyncio
    async def test_harness_calls_llm_on_final_transcript(self, mock_tutor, sample_audio_chunk):
        """Verify LLM is called when final transcript received."""
        from lingua.agent.harness import VoiceAgentHarness

        # Mock stream_audio_chunks to yield one chunk then stop
        mock_audio_chunks = create_async_iter([sample_audio_chunk])

        # Mock stream_transcribe to yield a final transcript
        transcript_text = "What is hello in Chinese?"
        mock_transcribe = create_async_iter([
            {"type": "final", "text": transcript_text}
        ])

        with patch("lingua.agent.harness.stream_audio_chunks", return_value=mock_audio_chunks):
            with patch("lingua.agent.harness.stream_transcribe", return_value=mock_transcribe):
                harness = VoiceAgentHarness(tutor=mock_tutor)
                await harness.run()

        # Verify LLM was called with the transcript text
        mock_tutor._ask_llm.assert_called_once_with(transcript_text)

    @pytest.mark.asyncio
    async def test_harness_handles_partial_transcripts(self, mock_tutor, sample_audio_chunk):
        """Verify harness processes partial transcripts without calling LLM."""
        from lingua.agent.harness import VoiceAgentHarness

        # Mock stream_audio_chunks
        mock_audio_chunks = create_async_iter([sample_audio_chunk])

        # Mock stream_transcribe that yields partial then final
        mock_transcribe = create_async_iter([
            {"type": "partial", "text": "Hel"},
            {"type": "partial", "text": "Hello"},
            {"type": "final", "text": "Hello world"},
        ])

        with patch("lingua.agent.harness.stream_audio_chunks", return_value=mock_audio_chunks):
            with patch("lingua.agent.harness.stream_transcribe", return_value=mock_transcribe):
                harness = VoiceAgentHarness(tutor=mock_tutor)
                await harness.run()

        # LLM should be called only once (for final, not partial)
        mock_tutor._ask_llm.assert_called_once()
        mock_tutor._ask_llm.assert_called_with("Hello world")

    @pytest.mark.asyncio
    async def test_harness_ignores_empty_transcripts(self, mock_tutor, sample_audio_chunk):
        """Verify empty transcripts don't trigger LLM calls."""
        from lingua.agent.harness import VoiceAgentHarness

        # Mock stream_audio_chunks
        mock_audio_chunks = create_async_iter([sample_audio_chunk])

        # Mock stream_transcribe that yields empty final transcript
        mock_transcribe = create_async_iter([
            {"type": "final", "text": ""}
        ])

        with patch("lingua.agent.harness.stream_audio_chunks", return_value=mock_audio_chunks):
            with patch("lingua.agent.harness.stream_transcribe", return_value=mock_transcribe):
                harness = VoiceAgentHarness(tutor=mock_tutor)
                await harness.run()

        # LLM should not be called for empty transcript
        mock_tutor._ask_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_harness_calls_tts_playback_on_response(self, sample_audio_chunk):
        """Verify TTS playback is called after LLM returns a response."""
        from lingua.agent.harness import VoiceAgentHarness
        from unittest.mock import call

        # Create mock tutor with speak method
        mock_tutor = MagicMock(spec=MandarinTutor)
        mock_tutor._ask_llm = MagicMock(return_value=TutorTurn(
            type="explanation",
            text="Hello! This is a test response.",
            expected="",
            feedback="",
        ))
        # Mock speak to return a fake SynthesisResult
        mock_tutor.speak = MagicMock(return_value=SynthesisResult(
            audio_bytes=b"fake_audio_data",
            duration_ms=1000,
        ))
        # Mock _voice_for_turn to return a voice profile
        mock_tutor._voice_for_turn = MagicMock(return_value="alloy")

        # Mock stream_audio_chunks
        mock_audio_chunks = create_async_iter([sample_audio_chunk])

        # Mock stream_transcribe to yield a final transcript
        mock_transcribe = create_async_iter([
            {"type": "final", "text": "Hello world"}
        ])

        with patch("lingua.agent.harness.stream_audio_chunks", return_value=mock_audio_chunks):
            with patch("lingua.agent.harness.stream_transcribe", return_value=mock_transcribe):
                with patch("lingua.agent.harness.sd") as mock_sd:
                    harness = VoiceAgentHarness(tutor=mock_tutor)
                    await harness.run()

        # Verify speak was called with the response text and voice profile
        mock_tutor.speak.assert_called_once_with(
            "Hello! This is a test response.",
            "alloy",
        )
        # Verify sounddevice.play was called
        mock_sd.play.assert_called_once_with(b"fake_audio_data", sample_rate=16000)
        # Verify sounddevice.wait was called to ensure playback completes
        mock_sd.wait.assert_called_once()
