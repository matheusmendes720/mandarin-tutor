"""Audio capture and playback loop for voice interaction."""
from __future__ import annotations

import asyncio
import io
import tempfile
import threading
from collections.abc import AsyncIterator
from typing import Callable

import numpy as np
import sounddevice as sd

from . import config as cfg
from .voice_studio import VoiceStudioClient, SynthesisResult


async def stream_audio_chunks(
    sample_rate: int = 16000,
    channels: int = 1,
    chunk_ms: int = 160,
    silence_threshold: float = 0.01,
    max_seconds: float = 30.0,
) -> AsyncIterator[bytes]:
    """Yield raw PCM chunks while recording. Stops on silence.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz.
    channels : int
        Number of audio channels.
    chunk_ms : int
        Chunk duration in milliseconds.
    silence_threshold : float
        RMS threshold below which audio is considered silence.
    max_seconds : float
        Maximum recording duration in seconds.

    Yields
    ------
    bytes
        Raw PCM int16 audio chunks.
    """
    frames_per_chunk = int(sample_rate * (chunk_ms / 1000))
    required_silent_frames = int(sample_rate * 0.5)  # 0.5s silence to stop
    running = True

    def audio_gen():
        """Blocking generator that reads from sounddevice."""
        nonlocal running
        q: list[np.ndarray] = []
        silence_frames = 0

        def callback(indata: np.ndarray, _frame_count: int, _time_info, _status: sd.CallbackFlags) -> None:
            q.append(indata.copy())

        import time
        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            callback=callback,
            blocksize=frames_per_chunk,
        )

        try:
            with stream:
                start = time.monotonic()
                while running:
                    sd.sleep(int(chunk_ms))
                    if not q:
                        if time.monotonic() - start > max_seconds:
                            running = False
                        continue
                    chunk = q.pop(0)
                    elapsed = time.monotonic() - start
                    if elapsed > max_seconds:
                        running = False
                        break
                    rms = float(np.sqrt(np.mean(chunk.astype(float) ** 2)))
                    if rms < silence_threshold:
                        silence_frames += len(chunk)
                        if silence_frames >= required_silent_frames:
                            running = False
                            break
                    else:
                        silence_frames = 0
                    yield chunk
        finally:
            running = False

    loop = asyncio.get_running_loop()

    def get_next():
        try:
            return next(audio_gen_iter)
        except StopIteration:
            return None

    audio_gen_iter = audio_gen()
    while running:
        try:
            chunk = await loop.run_in_executor(None, get_next)
        except RuntimeError:
            break
        if chunk is None:
            break
        yield chunk.flatten().tobytes()


class AudioLoop:
    """Capture from microphone, play through speakers, managed by VoiceStudio."""

    def __init__(self, cfg_: cfg.LinguaConfig | None = None) -> None:
        self.cfg = cfg_ or cfg.LinguaConfig.defaults()
        self.vs = VoiceStudioClient(self.cfg.voicestudio.url)
        self._running = False
        self._recordings: list[bytes] = []

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------
    def record_until_silence(self, silence_threshold: float = 0.01, max_seconds: float = 10.0) -> bytes:
        """Capture audio from mic until silence is detected."""
        sample_rate = self.cfg.audio.sample_rate
        channels = self.cfg.audio.channels
        dtype = "int16"

        q: list[np.ndarray] = []
        silence_frames = 0
        required_silent = int(sample_rate * 0.5)  # 0.5s of silence to stop

        def callback(indata: np.ndarray, _frame_count: int, _time_info, _status: sd.CallbackFlags) -> None:
            q.append(indata.copy())

        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype=dtype,
            callback=callback,
        )

        self._running = True
        with stream:
            total_frames = 0
            max_frames = int(sample_rate * max_seconds)
            while self._running and total_frames < max_frames:
                sd.sleep(50)
                if not q:
                    continue
                chunk = q.pop(0)
                total_frames += len(chunk)
                rms = float(np.sqrt(np.mean(chunk.astype(float) ** 2)))
                if rms < silence_threshold:
                    silence_frames += len(chunk)
                    if silence_frames >= required_silent:
                        self._running = False
                        break
                else:
                    silence_frames = 0

        self._running = False
        audio = np.concatenate(q).flatten().astype(dtype)
        return self._wav_from_samples(audio, sample_rate, channels)

    def _wav_from_samples(self, samples: np.ndarray, sample_rate: int, channels: int) -> bytes:
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Playback — pure WAV via sounddevice
    # ------------------------------------------------------------------
    def play(self, audio_bytes: bytes) -> None:
        """Play audio through sounddevice. Accepts WAV or MP3 bytes."""
        import wave, struct, io as _io

        # If it's MP3, decode via simpleroute; otherwise assume WAV
        try:
            bio = _io.BytesIO(audio_bytes)
            with wave.open(bio) as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(frames, dtype=np.int16)
            sd.play(audio_data, samplerate=sample_rate, channels=n_channels)
            sd.sleep(int(len(audio_data) / sample_rate * 1000) + 200)
        except Exception:
            # Try MP3 — fall back to temp file + os media player
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(audio_bytes)
            tmp.close()
            import os, subprocess
            try:
                # Windows: use PowerShell to play via default media player
                subprocess.Popen(
                    ["powershell", "-c", f"(New-Object Media.SoundPlayer '{tmp.name}').PlaySync()"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                # Last resort: just skip playback silently
                pass
            finally:
                try: os.unlink(tmp.name)
                except Exception: pass

    # ------------------------------------------------------------------
    # Convenience — record + transcribe
    # ------------------------------------------------------------------
    def listen_and_transcribe(self, num_speakers: int = 1) -> str:
        audio = self.record_until_silence()
        result = self.vs.transcribe(audio, num_speakers=num_speakers)
        return result.text
