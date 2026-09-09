"""VoiceStudio HTTP client for TTS and ASR."""
from dataclasses import dataclass
from collections.abc import AsyncIterator
import requests


@dataclass
class TranscriptResult:
    text: str
    pinyin: str | None = None


@dataclass
class SynthesisResult:
    audio_bytes: bytes
    duration_ms: int
    sample_rate: int = 24000  # VoiceStudio PCM is 24kHz int16 LE


async def stream_synthesize(
    client: VoiceStudioClient,
    text: str,
    profile_id: str,
    engine: str = "openai",
    response_format: str = "mp3",
    speed: float = 1.0,
) -> AsyncIterator[bytes | dict]:
    """Module-level async generator for TTS streaming.

    Convenience wrapper around VoiceStudioClient.stream_synthesize().
    """
    async for chunk in client.stream_synthesize(
        text=text,
        profile_id=profile_id,
        engine=engine,
        response_format=response_format,
        speed=speed,
    ):
        yield chunk


class VoiceStudioClient:
    """Synchronous HTTP client for VoiceStudio API (TTS + ASR)."""

    def __init__(self, base_url: str = "http://127.0.0.1:3900") -> None:
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # TTS — OpenAI-compatible /v1/audio/speech endpoint
    # ------------------------------------------------------------------
    def synthesize(
        self,
        text: str,
        profile_id: str,
        engine: str = "openai",
        response_format: str = "pcm",
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Generate speech via VoiceStudio TTS.

        Uses the OpenAI-compatible /v1/audio/speech endpoint.
        profile_id can be a voice profile UUID (e.g. "8c53222c") or an
        OpenAI voice alias like "alloy".

        Returns SynthesisResult with raw PCM int16 LE bytes. For PCM format,
        sample rate is 24000 Hz (server-side default for VoiceStudio). Callers
        should pass `sample_rate` to their audio backend.
        """
        payload = {
            "input": text,
            "voice": profile_id,
            "response_format": response_format,
            "speed": speed,
        }
        resp = requests.post(
            f"{self.base_url}/v1/audio/speech",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        # VoiceStudio TTS PCM is 24kHz int16 LE (confirmed via WAV header inspection).
        sample_rate = 24000 if response_format == "pcm" else 24000
        return SynthesisResult(audio_bytes=resp.content, duration_ms=0, sample_rate=sample_rate)

    async def stream_synthesize(
        self,
        text: str,
        profile_id: str,
        engine: str = "openai",
        response_format: str = "mp3",
        speed: float = 1.0,
    ) -> AsyncIterator[bytes | dict]:
        """Stream synthesis results as async generator.

        Since VoiceStudio TTS is batch-only (no WebSocket streaming),
        this wraps the synchronous synthesize() call in an async interface.
        Yields all audio bytes at once, then yields {"done": True}.

        This interface is ready for true streaming when/if VoiceStudio
        adds WebSocket support.
        """
        result = self.synthesize(
            text=text,
            profile_id=profile_id,
            engine=engine,
            response_format=response_format,
            speed=speed,
        )
        yield result.audio_bytes
        yield {"done": True}

    # ------------------------------------------------------------------
    # ASR — /dub/upload + SSE stream
    # ------------------------------------------------------------------
    def transcribe(self, audio_bytes: bytes, num_speakers: int = 1) -> TranscriptResult:
        """Upload audio and stream back transcription via SSE."""
        # 1. Upload
        upload_resp = requests.post(
            f"{self.base_url}/dub/upload",
            files={"audio": ("recording.wav", audio_bytes, "audio/wav")},
            timeout=30,
        )
        upload_resp.raise_for_status()
        job_id = upload_resp.json()["job_id"]

        # 2. SSE stream for results
        text_parts: list[str] = []
        try:
            import sseclient
        except ImportError:
            # Fallback: manual SSE parsing
            import json as _json

            with requests.get(
                f"{self.base_url}/dub/transcribe-stream/{job_id}?num_speakers={num_speakers}",
                stream=True,
                timeout=60,
            ) as resp:
                resp.raise_for_status()
                buffer = ""
                for chunk in resp.iter_content(chunk_size=None):
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8", errors="replace")
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                obj = _json.loads(data)
                                if txt := obj.get("text", ""):
                                    text_parts.append(txt)
                            except Exception:
                                pass
                return TranscriptResult(text="".join(text_parts))

        # SSE via sseclient library
        with requests.get(
            f"{self.base_url}/dub/transcribe-stream/{job_id}?num_speakers={num_speakers}",
            stream=True,
            timeout=60,
        ) as resp:
            resp.raise_for_status()
            client = sseclient.SSEClient(resp)
            for event in client.events():
                if event.data == "[DONE]":
                    break
                try:
                    import json

                    data = json.loads(event.data)
                    if txt := data.get("text", ""):
                        text_parts.append(txt)
                except Exception:
                    pass

        return TranscriptResult(text="".join(text_parts))

    def is_available(self) -> bool:
        """Check if VoiceStudio is reachable."""
        try:
            r = requests.get(f"{self.base_url}/model/status", timeout=3)
            return r.status_code == 200
        except Exception:
            return False
