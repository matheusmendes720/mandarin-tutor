"""Tests for RMS computation helpers in audio_loop."""
import numpy as np
from lingua.audio_loop import compute_rms, is_speech


def test_compute_rms_silence_is_zero():
    chunk = (np.zeros(1600, dtype=np.int16)).tobytes()
    assert compute_rms(chunk) == 0.0


def test_compute_rms_loud_chunk_high():
    # 1600 samples of max amplitude int16 = 32767
    samples = np.full(1600, 32767, dtype=np.int16)
    rms = compute_rms(samples.tobytes())
    assert rms > 0.9  # should be ~1.0 normalized


def test_is_speech_threshold_default():
    assert is_speech(0.10) is True   # above 0.05 default
    assert is_speech(0.01) is False  # below 0.05 default


def test_is_speech_custom_threshold():
    assert is_speech(0.04, threshold=0.03) is True
    assert is_speech(0.04, threshold=0.05) is False
