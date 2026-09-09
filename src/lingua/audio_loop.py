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


# ---------------------------------------------------------------------------
# RMS computation helpers
# ---------------------------------------------------------------------------
def compute_rms(chunk: bytes) -> float:
    """Compute normalized RMS of int16 PCM chunk.

    Returns a value in [0.0, 1.0].
    """
    arr = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)) / 32768.0)


def is_speech(rms: float, threshold: float = 0.05) -> bool:
    """True if RMS exceeds speech threshold (raised from 0.01)."""
    return rms > threshold


# ---------------------------------------------------------------------------
# Audio streaming
# ---------------------------------------------------------------------------
async def stream_audio_chunks(
    sample_rate: int = 16000,
    channels: int = 1,
    chunk_ms: int = 160,
    silence_threshold: float = 150.0,
    max_seconds: float = 30.0,
    min_speech_seconds: float = 0.3,
    on_rms: Callable[[float, bool], None] | None = None,
) -> AsyncIterator[bytes]:
    """Yield raw PCM chunks (int16, mono, 16kHz) while recording. Stops on silence.

    Opens the device at its NATIVE sample rate and channel count (avoiding
    PortAudio resample artifacts on Windows that caused the silent-mic bug),
    then resamples to `sample_rate` and downmixes to `channels` before yielding.

    Parameters
    ----------
    sample_rate : int
        Target output sample rate (default 16000).
    channels : int
        Target output channel count (default 1 = mono).
    chunk_ms : int
        Output chunk duration in milliseconds.
    silence_threshold : float
        Raw int16 RMS below which audio is silence. Default 150 — calibrated
        for the Microphone Array (Intel Smart Sound) on Windows where loud
        speech peaks ~400-800 and ambient noise stays <50. Raise if ambient
        noise triggers false speech; lower if speech doesn't trigger.
    max_seconds : float
        Maximum recording duration in seconds.
    min_speech_seconds : float
        Minimum duration of speech required before stopping on silence.
    on_rms : callable, optional
        Callback called with (rms, is_speech) for each chunk.

    Yields
    ------
    bytes
        Raw PCM int16 audio at `sample_rate`, `channels`.
    """
    # Resolve device native format to avoid PortAudio resample breakage
    in_dev = sd.query_devices(kind="input")
    native_sr = int(in_dev.get("default_samplerate", 44100))
    native_ch = max(channels, min(2, in_dev.get("max_input_channels", 1)))

    resample_needed = native_sr != sample_rate

    output_frames_per_chunk = int(sample_rate * (chunk_ms / 1000))
    native_frames_per_chunk = int(native_sr * (chunk_ms / 1000))
    required_silent_frames = int(sample_rate * 1.5)  # 1.5s silence to stop
    running = True

    def audio_gen():
        """Blocking generator that reads from sounddevice."""
        nonlocal running
        q: list[np.ndarray] = []
        silence_frames = 0
        had_speech = False
        speech_chunks_ago = 0

        def callback(indata: np.ndarray, _frame_count: int, _time_info, _status: sd.CallbackFlags) -> None:
            q.append(indata.copy())

        import time
        stream = sd.InputStream(
            samplerate=native_sr,
            channels=native_ch,
            dtype="int16",
            callback=callback,
            blocksize=native_frames_per_chunk,
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

                    # Take channel 0 only (Windows 4-channel devices have broken ch 2-3)
                    if chunk.ndim > 1 and chunk.shape[1] > 1:
                        mono = chunk[:, 0]
                    else:
                        mono = chunk.flatten()

                    rms_raw = float(np.sqrt(np.mean(mono.astype(np.float32) ** 2)))
                    speech = rms_raw > silence_threshold

                    if speech:
                        had_speech = True
                        speech_chunks_ago = 0
                    else:
                        speech_chunks_ago += 1

                    if on_rms is not None:
                        on_rms(rms_raw, speech)

                    # Only stop on silence if we've heard real speech in the last 30 chunks
                    speech_recently = had_speech and speech_chunks_ago <= 30
                    if rms_raw < silence_threshold and speech_recently:
                        silence_frames += native_frames_per_chunk
                        if silence_frames >= required_silent_frames:
                            running = False
                            break
                    else:
                        silence_frames = 0

                    # Resample native_sr -> sample_rate if needed (linear interp, fine for speech)
                    if resample_needed:
                        ratio = sample_rate / native_sr
                        n_out = max(1, int(len(mono) * ratio))
                        x_old = np.arange(len(mono))
                        x_new = np.linspace(0, len(mono) - 1, n_out)
                        out = np.interp(x_new, x_old, mono.astype(np.float32)).astype(np.int16)
                    else:
                        out = mono.astype(np.int16)

                    yield out
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
        yield chunk.tobytes()


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
                # Use extracted RMS helper
                rms = compute_rms(chunk.flatten().tobytes())
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
