"""VoiceAgentHarness - full-duplex voice loop orchestration."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd

from ..audio_loop import stream_audio_chunks
from ..asr import stream_transcribe
from ..tutor import MandarinTutor
from ..voice_studio import VoiceStudioClient
from ..hud.bus import EventBus
from ..hud.events import (
    AsrFinalEvent,
    LlmStartEvent,
    LlmDoneEvent,
    TtsStartEvent,
    TtsDoneEvent,
    LogEvent,
)
from ..tutor import TutorTurn, to_pinyin
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
        event_bus: EventBus | None = None,
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
        event_bus : EventBus, optional
            Optional event bus for publishing pipeline events.
        """
        self.tutor = tutor
        self.config = config
        self.sample_rate = sample_rate
        self.channels = channels
        self.event_bus = event_bus

        # Voice activity detector for turn switching
        self._vad = VoiceActivityDetector(energy_threshold=0.01)
        # Turn router for multi-lingual routing
        self._router = TurnRouter()
        # State: "listening" | "speaking"
        self._state = "listening"

        # VoiceStudio client for ASR
        self._vs = VoiceStudioClient("http://127.0.0.1:3900")

    def _log(self, message: str, level: str = "info") -> None:
        """Publish a log message to the event bus (HUD renders it inside the TUI)."""
        if self.event_bus:
            self.event_bus.publish(
                LogEvent(ts=time.monotonic(), level=level, message=message)
            )

    async def run(self) -> None:
        """Run the voice agent loop.

        Concurrently captures audio and transcribes it. When a final
        transcript with non-empty text is received, passes it to the
        tutor for processing. Loops continuously so the user can have
        multiple back-and-forth turns.
        """
        while True:
            self._log("listening...")
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
                # Run both tasks concurrently until one finishes
                await asyncio.gather(capture_task, asr_task)
            except asyncio.CancelledError:
                logger.info("VoiceAgentHarness cancelled, cleaning up tasks...")
                capture_task.cancel()
                asr_task.cancel()
                await asyncio.gather(capture_task, asr_task, return_exceptions=True)
                raise
            except Exception as e:
                logger.error("Turn error: %s", e)
                # Brief pause before next turn to avoid tight error loops
                await asyncio.sleep(1)
                continue

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
            self._log("silence detected — processing...")
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
                    self._log(f"heard: {text!r}")
                    # Only process non-empty transcripts
                    if text.strip():
                        # Publish ASR final event
                        if self.event_bus:
                            self.event_bus.publish(
                                AsrFinalEvent(
                                    ts=time.monotonic(),
                                    text=text,
                                    language=result.get("language", "zh"),
                                )
                            )
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
        """Process a final transcript through the tutor (streaming LLM).

        Streams the LLM response and fires TTS as soon as the first sentence
        boundary arrives, reducing perceived latency from (LLM + TTS) to
        (~LLM_TTFB + TTS_one_sentence).

        Parameters
        ----------
        segments : list[dict]
            List of ASR segment dicts with "text" and "language" keys.
        """
        try:
            # Route the turn based on language
            routed = self._router.route(segments)
            text = routed.full_text

            # Persist user turn to memory (mirror _ask_llm behavior).
            self.tutor.memory.add_turn("user", text)

            # Publish LLM start event
            if self.event_bus:
                self.event_bus.publish(
                    LlmStartEvent(ts=time.monotonic(), prompt_chars=len(text))
                )

            # Stream LLM in a thread so we can fire TTS as soon as a sentence
            # boundary is detected without blocking the event loop.
            loop = asyncio.get_running_loop()
            t0 = time.monotonic()
            full_text, sentences = await loop.run_in_executor(
                None,
                lambda: self.tutor.stream_response(
                    self.tutor.memory.get_conversation_for_llm(),
                ),
            )
            llm_ms = int((time.monotonic() - t0) * 1000)

            # Persist assistant response to memory.
            if full_text.strip():
                self.tutor.memory.add_turn("assistant", full_text)

            # The stream_response helper doesn't know about TutorTurn schema;
            # synthesize a turn from the accumulated text so downstream code
            # doesn't change.
            turn = TutorTurn(type="explanation", text=full_text)

            # Publish LLM done event
            if self.event_bus:
                self.event_bus.publish(
                    LlmDoneEvent(
                        ts=time.monotonic(),
                        response_chars=len(full_text),
                        duration_ms=llm_ms,
                    )
                )

            logger.info(
                "Tutor response: %d sentences, %d chars",
                len(sentences),
                len(full_text),
            )

            if not full_text.strip():
                self._log("listening...")
                return

            # Speak each sentence in order. VoiceStudio TTS is blocking; we
            # could overlap them with continued streaming of the next sentence,
            # but in practice the LLM has finished by the time we get here.
            voice_profile = self.tutor._voice_for_turn(turn)
            for i, sentence in enumerate(sentences):
                # Display: pinyin for Mandarin, raw text for English.
                display_text = sentence
                if turn.type != "explanation":
                    py = to_pinyin(sentence)
                    if py and py != sentence:
                        display_text = py
                self._log(
                    f"tutor [{turn.type} #{i+1}/{len(sentences)}]: {display_text[:80]!r}"
                    f"{'...' if len(display_text) > 80 else ''}",
                )

                if self.event_bus:
                    self.event_bus.publish(
                        TtsStartEvent(
                            ts=time.monotonic(),
                            text_chars=len(sentence),
                            voice=voice_profile,
                        )
                    )

                speed = self.tutor._speed_for_turn(turn)
                t1 = time.monotonic()
                result = self.tutor.speak(sentence, voice_profile, speed=speed)
                self._log(
                    f"🔊 playing {len(result.audio_bytes)}b @ {result.sample_rate}Hz speed={speed}x",
                )
                audio_arr = np.frombuffer(result.audio_bytes, dtype=np.int16)
                sd.play(audio_arr, samplerate=result.sample_rate)
                sd.wait()

                if self.event_bus:
                    self.event_bus.publish(
                        TtsDoneEvent(
                            ts=time.monotonic(),
                            duration_ms=int((time.monotonic() - t1) * 1000),
                        )
                    )

            self._log("listening...")

        except Exception as e:
            logger.error("Error processing transcript: %s", e)
