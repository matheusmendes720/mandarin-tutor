# tests/hud/test_events.py
from lingua.hud.events import (
    Event, RmsEvent, AsrPartialEvent, AsrFinalEvent,
    LlmStartEvent, LlmDoneEvent, TtsStartEvent, TtsDoneEvent,
    VadEvent, LogEvent,
)


def test_event_has_timestamp():
    e = LogEvent(ts=0.0, level="info", message="hi")
    assert e.ts == 0.0
    assert e.kind == "log"


def test_rms_event_preserves_rms():
    e = RmsEvent(ts=1.0, rms=0.42, is_speech=True)
    assert e.rms == 0.42
    assert e.is_speech is True
    assert e.kind == "rms"


def test_asr_final_carries_language():
    e = AsrFinalEvent(ts=0.0, text="你好", language="zh")
    assert e.text == "你好"
    assert e.language == "zh"
    assert e.kind == "asr_final"


def test_llm_done_carries_duration():
    e = LlmDoneEvent(ts=0.0, response_chars=42, duration_ms=1100)
    assert e.duration_ms == 1100
    assert e.kind == "llm_done"


def test_tts_done_carries_duration():
    e = TtsDoneEvent(ts=0.0, duration_ms=1830)
    assert e.duration_ms == 1830


def test_vad_event_state():
    e = VadEvent(ts=0.0, state="speech")
    assert e.state == "speech"


def test_log_event_level():
    e = LogEvent(ts=0.0, level="error", message="boom")
    assert e.level == "error"
