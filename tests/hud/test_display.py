# tests/hud/test_display.py
import pytest
from io import StringIO
from rich.console import Console
from lingua.hud.events import (
    RmsEvent, AsrFinalEvent, LlmStartEvent, TtsStartEvent,
    VadEvent, LogEvent
)
from lingua.hud.display import Hud


def test_hud_constructs_with_devices():
    hud = Hud(input_device="Mic", output_device="HP")
    assert hud.input_device == "Mic"
    assert hud.output_device == "HP"


def test_hud_renders_to_string():
    """Build a fake event list, render once, capture output."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    hud = Hud(input_device="Mic", output_device="HP", console=console)
    hud.apply(RmsEvent(ts=0.0, rms=0.42, is_speech=True))
    hud.apply(VadEvent(ts=0.0, state="speech"))
    hud.apply(AsrFinalEvent(ts=0.0, text="你好", language="zh"))
    console.print(hud.renderable())
    output = console.file.getvalue()
    assert "Lingua" in output
    assert "你好" in output


def test_hud_rms_history_caps_at_60():
    hud = Hud(input_device="Mic", output_device="HP")
    for i in range(100):
        hud.apply(RmsEvent(ts=0.0, rms=i / 100.0, is_speech=False))
    assert len(hud.rms_history) == 60
    assert hud.rms_history[-1] == pytest.approx(0.99)


def test_hud_transcript_keeps_last_6():
    hud = Hud(input_device="Mic", output_device="HP")
    for i in range(10):
        hud.apply(AsrFinalEvent(ts=0.0, text=f"turn-{i}", language="zh"))
    assert len(hud.transcript) == 6
    assert hud.transcript[-1]["text"] == "turn-9"


def test_hud_log_keeps_last_20():
    hud = Hud(input_device="Mic", output_device="HP")
    for i in range(50):
        hud.apply(LogEvent(ts=0.0, level="info", message=f"m-{i}"))
    assert len(hud.log_lines) == 20
    assert "m-49" in hud.log_lines[-1]
