"""VoiceStudio WebSocket streaming ASR."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import websockets

from .voice_studio import VoiceStudioClient


# WebSocket endpoint for streaming ASR
WS_URL = "ws://127.0.0.1:3900/v1/audio/transcriptions/stream"


async def stream_transcribe(
    chunks: AsyncIterator[bytes],
    vs: VoiceStudioClient,
    num_speakers: int = 1,
) -> AsyncIterator[dict]:
    """Consume audio chunks, yield transcripts via VoiceStudio WebSocket ASR.

    Parameters
    ----------
    chunks : AsyncIterator[bytes]
        Async iterator yielding raw PCM audio chunks (int16 mono, 16kHz).
    vs : VoiceStudioClient
        VoiceStudio client instance for availability check.
    num_speakers : int
        Expected number of speakers (for diarization).

    Yields
    ------
    dict
        Dict with "type" and "text" keys:
        - {"type": "partial", "text": "..."}
        - {"type": "final", "text": "..."}
        - {"type": "error", "text": "..."}
        - {"type": "status", "text": "..."}

    Raises
    ------
    ConnectionError
        If VoiceStudio is not available.
    """
    # Check availability first
    if not vs.is_available():
        raise ConnectionError("VoiceStudio is not available")

    # Build the WebSocket URL with query params
    url = f"{WS_URL}?num_speakers={num_speakers}"

    async with websockets.connect(url) as ws:
        # Send audio chunks
        async for chunk in chunks:
            await ws.send(chunk)

        # Signal end of audio
        await ws.send(json.dumps({"type": "input_audio.end"}))

        # Receive and yield transcriptions
        async for message in ws:
            data = json.loads(message)

            # Handle different event types
            # VoiceStudio sends: {"type": "session.started"} or {"final": {"text": "..."}}
            msg_type = data.get("type", "")

            if msg_type == "session.started":
                yield {"type": "status", "text": "Session started"}
                continue

            if msg_type == "input_audio.end":
                # This signals the end of input, not an error
                continue

            if "partial" in data:
                yield {"type": "partial", "text": data["partial"].get("text", "")}
                continue

            if "final" in data:
                yield {"type": "final", "text": data["final"].get("text", "")}
                continue

            if "status" in data:
                yield {"type": "status", "text": data["status"].get("message", "")}
                continue

            if "error" in data:
                yield {"type": "error", "text": data["error"].get("message", "Unknown error")}
                continue
