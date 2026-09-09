"""VoiceStudio WebSocket streaming ASR."""
from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator

import av
import numpy as np
import websockets

from .voice_studio import VoiceStudioClient


# WebSocket endpoint for streaming ASR
WS_URL = "ws://127.0.0.1:3900/v1/audio/transcriptions/stream"


class PcmToOpusEncoder:
    """Streaming PCM int16 → Opus-in-WebM encoder using PyAV.

    VoiceStudio's WebSocket ASR expects audio/webm;codecs=opus. We have raw
    int16 PCM at 16kHz mono. Feed PCM chunks via `feed()` and flush at end of
    turn to get a complete WebM/Opus blob suitable for the server.

    Uses `av.open` in memory with a custom writeable buffer so we can encode
    incrementally without an actual file.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1, bit_rate: int = 64_000) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.bit_rate = bit_rate
        self._buf = io.BytesIO()
        self._container = av.open(self._buf, mode="w", format="webm")
        self._stream = self._container.add_stream("libopus", rate=sample_rate)
        self._stream.bit_rate = bit_rate
        self._stream.sample_rate = sample_rate
        self._stream.layout = "mono" if channels == 1 else "stereo"
        self._resampler = av.AudioResampler(
            format="s16", layout="mono" if channels == 1 else "stereo", rate=sample_rate
        )
        self._closed = False
        self._total_written = 0

    def feed(self, pcm_bytes: bytes) -> bytes:
        """Feed PCM int16 bytes; returns any newly-encoded WebM bytes."""
        if self._closed or not pcm_bytes:
            return b""
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        # PyAV expects (channels, samples) layout for from_ndarray — mono must still be 2D
        arr = arr.reshape(-1, self.channels).T
        frame = av.AudioFrame.from_ndarray(arr, format="s16", layout="mono" if self.channels == 1 else "stereo")
        frame.sample_rate = self.sample_rate
        for resampled in self._resampler.resample(frame):
            for pkt in self._stream.encode(resampled):
                if pkt:
                    self._container.mux(pkt)
        # Read only NEWLY-written bytes (delta since last call)
        self._buf.seek(0, 2)  # end
        end_pos = self._buf.tell()
        self._buf.seek(self._total_written)
        out = self._buf.read(end_pos - self._total_written)
        self._total_written = end_pos
        return out

    def flush(self) -> bytes:
        """Flush encoder and return remaining WebM bytes."""
        if self._closed:
            return b""
        for resampled in self._resampler.resample(None):
            for pkt in self._stream.encode(resampled):
                if pkt:
                    self._container.mux(pkt)
        for pkt in self._stream.encode(None):
            if pkt:
                self._container.mux(pkt)
        self._container.close()
        self._closed = True
        self._buf.seek(0, 2)
        end_pos = self._buf.tell()
        self._buf.seek(self._total_written)
        out = self._buf.read(end_pos - self._total_written)
        self._total_written = end_pos
        return out


async def stream_transcribe(
    chunks: AsyncIterator[bytes],
    vs: VoiceStudioClient,
    num_speakers: int = 1,
    sample_rate: int = 16000,
    channels: int = 1,
) -> AsyncIterator[dict]:
    """Consume audio chunks, yield transcripts via VoiceStudio WebSocket ASR.

    VoiceStudio's WebSocket ASR expects audio/webm;codecs=opus. Raw PCM is
    encoded to WebM/Opus incrementally via PcmToOpusEncoder before sending.

    Parameters
    ----------
    chunks : AsyncIterator[bytes]
        Async iterator yielding raw PCM audio chunks (int16 mono).
    vs : VoiceStudioClient
        VoiceStudio client instance for availability check.
    num_speakers : int
        Expected number of speakers (for diarization).
    sample_rate : int
        PCM sample rate in Hz (default 16000).
    channels : int
        PCM channel count (default 1).

    Yields
    ------
    dict
        Dict with "type" and "text" keys.

    Raises
    ------
    ConnectionError
        If VoiceStudio is not available.
    """
    # Check availability first
    if not vs.is_available():
        raise ConnectionError("VoiceStudio is not available")

    # Build the WebSocket URL — server requires ?sr and ?format=webm_opus
    url = f"{WS_URL}?num_speakers={num_speakers}&sr={sample_rate}&format=webm_opus"

    encoder = PcmToOpusEncoder(sample_rate=sample_rate, channels=channels)

    # Buffer WebM output and only send when we have a self-contained chunk.
    # Partial WebM containers fail to decode on the server (EBML header
    # parsing error). Buffering until >= 8KB guarantees every send is a
    # valid WebM stream.
    webm_buffer = b""
    SEND_THRESHOLD = 8192

    async with websockets.connect(url) as ws:
        async for chunk in chunks:
            webm = encoder.feed(chunk)
            if webm:
                webm_buffer += webm
            if len(webm_buffer) >= SEND_THRESHOLD:
                await ws.send(webm_buffer)
                webm_buffer = b""
        # Flush encoder and send remaining WebM bytes
        tail = encoder.flush()
        if tail:
            webm_buffer += tail
        if webm_buffer:
            await ws.send(webm_buffer)

        # Signal end of audio
        await ws.send(json.dumps({"type": "input_audio.end"}))

        # Receive and yield transcriptions
        async for message in ws:
            data = json.loads(message)

            # Handle different event types
            msg_type = data.get("type", "")

            if msg_type == "session.started":
                yield {"type": "status", "text": "Session started"}
                continue

            if msg_type == "input_audio.end":
                continue

            if msg_type == "partial":
                # payload: {"type": "partial", "text": "...", ...}
                yield {"type": "partial", "text": data.get("text", "")}
                continue

            if msg_type == "final":
                # payload: {"type": "final", "text": "...", "segments": [...], ...}
                yield {"type": "final", "text": data.get("text", "")}
                continue

            if msg_type == "status":
                yield {"type": "status", "text": data.get("message", data.get("text", ""))}
                continue

            if msg_type == "error":
                yield {"type": "error", "text": data.get("message", "Unknown error")}
                continue
