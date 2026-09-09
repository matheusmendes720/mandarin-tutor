"""VoiceAgentHarness - full-duplex voice loop orchestration."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import sounddevice as sd

from ..audio_loop import stream_audio_chunks
from ..asr import stream_transcribe
from ..tutor import MandarinTutor
from ..voice_studio import VoiceStudioClient
from .router import TurnRouter
from .vad import VoiceActivityDetector

if TYPE_CHECKING:
    from ..config import LinguaConfig

logger = logging.getLogger(__name__)


class VoiceAgentHarness:
    """Orchestrates concurrent audio capture and ASR transcription.

    Uses asyncio.gather to run audio capture and ASR transcription concurrently,
    with a shared queue for passing audio chunks from capture to ASR.
    """

    def __init__(
        self,
        tutor: MandarinTutor,
        config: LinguaConfig | None = None,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        """Initialize the voice agent harness.

        Parameters
        ----------
        tutor : MandarinTutor
            The tutor instance for processing user input.
        config : LinguaConfig, optional
            Configuration for audio and ASR.
        sample_rate : int
            Audio sample rate (default 16000).
        channels : int
            Number of audio channels (default 1).
        """
        self.tutor = tutor
        self.config = config
        self.sample_rate = sample_rate
        self.channels = channels

        # Voice activity detector for turn switching
        self._vad = VoiceActivityDetector(energy_threshold=0.01)
        # Turn router for multi-lingual routing
        self._router = TurnRouter()
        # State: "listening" | "speaking"
        self._state = "listening"

        # VoiceStudio client for ASR
        self._vs = VoiceStudioClient("http://127.0.0.1:3900")

    async def run(self) -> None:
        """Run the voice agent loop.

        Concurrently captures audio and transcribes it. When a final
        transcript with non-empty text is received, passes it to the
        tutor for processing.
        """
        # Create a queue for passing audio chunks from capture to ASR
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Create tasks for concurrent execution
        capture_task = asyncio.create_task(
            self._capture_audio(audio_queue)
        )
        asr_task = asyncio.create_task(
            self._transcribe_audio(audio_queue)
        )

        try:
            # Run both tasks concurrently
            await asyncio.gather(capture_task, asr_task)
        except asyncio.CancelledError:
            logger.info("VoiceAgentHarness cancelled, cleaning up tasks...")
            # Cancel both tasks
            capture_task.cancel()
            asr_task.cancel()
            # Wait for both to complete cancellation
            await asyncio.gather(capture_task, asr_task, return_exceptions=True)
            raise

    async def _capture_audio(self, queue: asyncio.Queue[bytes]) -> None:
        """Capture audio chunks and put them in the queue.

        Parameters
        ----------
        queue : asyncio.Queue
            Queue to put audio chunks into.
        """
        try:
            async for chunk in stream_audio_chunks(
                sample_rate=self.sample_rate,
                channels=self.channels,
            ):
                await queue.put(chunk)
        except asyncio.CancelledError:
            logger.debug("Audio capture cancelled")
            raise
        except Exception as e:
            logger.error("Error in audio capture: %s", e)
            raise
        finally:
            # Signal end of audio
            await queue.put(b"")

    async def _transcribe_audio(self, queue: asyncio.Queue[bytes]) -> None:
        """Transcribe audio from the queue.

        Parameters
        ----------
        queue : asyncio.Queue
            Queue to get audio chunks from.
        """
        async def chunk_iter() -> AsyncIterator[bytes]:
            """Iterate over chunks from the queue."""
            while True:
                chunk = await queue.get()
                if chunk == b"":
                    # End of audio signal
                    break
                yield chunk

        try:
            async for result in stream_transcribe(
                chunk_iter(),
                self._vs,
            ):
                # Handle different result types
                result_type = result.get("type")
                text = result.get("text", "")

                if result_type == "status":
                    logger.debug("ASR status: %s", text)
                elif result_type == "partial":
                    logger.debug("ASR partial: %s", text)
                elif result_type == "final":
                    logger.info("ASR final transcript: %s", text)
                    # Only process non-empty transcripts
                    if text.strip():
                        # Build segments with language detection (default to zh for now)
                        segments = [{"text": text, "language": result.get("language", "zh")}]
                        await self._process_transcript(segments)
                elif result_type == "error":
                    logger.error("ASR error: %s", text)
        except asyncio.CancelledError:
            logger.debug("ASR transcription cancelled")
            raise
        except Exception as e:
            logger.error("Error in ASR transcription: %s", e)
            raise

    async def _process_transcript(self, segments: list[dict]) -> None:
        """Process a final transcript through the tutor.

        Parameters
        ----------
        segments : list[dict]
            List of ASR segment dicts with "text" and "language" keys.
        """
        try:
            # Route the turn based on language
            routed = self._router.route(segments)
            text = routed.full_text

            # Determine turn type from routing
            turn_type = routed.type

            turn = self.tutor._ask_llm(text)
            logger.info(
                "Tutor response: type=%s, text=%s",
                turn.type,
                turn.text[:100] if turn.text else "",
            )

            # Synthesize and play TTS response (blocking fallback)
            if turn.text:
                voice_profile = self.tutor._voice_for_turn(turn)
                result = self.tutor.speak(turn.text, voice_profile)
                # Play audio using blocking playback
                sd.play(result.audio_bytes, sample_rate=16000)
                sd.wait()  # Ensure playback completes before continuing

        except Exception as e:
            logger.error("Error processing transcript: %s", e)
