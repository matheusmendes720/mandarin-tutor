# src/lingua/hud/display.py
from __future__ import annotations
import time
from collections import deque
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

from .events import (
    Event, RmsEvent, AsrFinalEvent, LlmStartEvent, LlmDoneEvent,
    TtsStartEvent, TtsDoneEvent, VadEvent, LogEvent,
)


class Hud:
    """Live HUD driven by Event stream.

    Apply events via `apply()` or stream via `run()`.
    Render with `renderable()` for testing or via `Live()` in production.
    """

    def __init__(
        self,
        input_device: str,
        output_device: str,
        console: Console | None = None,
    ) -> None:
        self.input_device = input_device
        self.output_device = output_device
        self.console = console or Console()
        self.start_ts = time.monotonic()

        self.rms_history: deque[float] = deque(maxlen=60)
        self.vad_state = "silence"
        self.last_speech_rms: float = 0.0
        self.transcript: deque[dict[str, Any]] = deque(maxlen=6)
        self.log_lines: deque[str] = deque(maxlen=20)

        # Pipeline status
        self.asr_status = "idle"
        self.asr_latency_ms = 0
        self.llm_status = "idle"
        self.llm_latency_ms = 0
        self.tts_status = "idle"
        self.tts_latency_ms = 0

    def apply(self, event: Event) -> None:
        if isinstance(event, RmsEvent):
            self.rms_history.append(event.rms)
            self.last_speech_rms = event.rms
        elif isinstance(event, VadEvent):
            self.vad_state = event.state
        elif isinstance(event, AsrFinalEvent):
            self.asr_status = "final"
            self.transcript.append({"role": "user", "text": event.text, "lang": event.language})
        elif isinstance(event, LlmStartEvent):
            self.llm_status = "thinking"
        elif isinstance(event, LlmDoneEvent):
            self.llm_status = "done"
            self.llm_latency_ms = event.duration_ms
            self.transcript.append({"role": "tutor", "text": f"[{event.response_chars} chars]", "lang": ""})
        elif isinstance(event, TtsStartEvent):
            self.tts_status = "playing"
        elif isinstance(event, TtsDoneEvent):
            self.tts_status = "done"
            self.tts_latency_ms = event.duration_ms
        elif isinstance(event, LogEvent):
            ts = time.strftime("%H:%M:%S")
            self.log_lines.append(f"{ts} [{event.level}] {event.message}")

    def renderable(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._header(), size=3),
            Layout(name="body"),
            Layout(self._log_panel(), size=8),
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(self._transcript_panel(), name="right"),
        )
        layout["body"]["left"].split_column(
            Layout(self._mic_panel(), name="mic"),
            Layout(self._pipeline_panel(), name="pipeline"),
        )
        return layout

    def _header(self) -> Panel:
        uptime = int(time.monotonic() - self.start_ts)
        m, s = divmod(uptime, 60)
        h, m = divmod(m, 60)
        text = Text()
        text.append("Lingua Voice Tutor", style="bold cyan")
        text.append(f"   {h:02d}:{m:02d}:{s:02d}", style="dim")
        text.append(f"\nInput:  {self.input_device}\n", style="dim")
        text.append(f"Output: {self.output_device}", style="dim")
        return Panel(text, border_style="cyan")

    def _mic_panel(self) -> Panel:
        # Render RMS bar as 30 chars wide
        bar_width = 30
        rms_now = self.last_speech_rms
        filled = int(min(rms_now, 1.0) * bar_width)
        bar = "=" * filled + "-" * (bar_width - filled)
        threshold_pos = int(0.05 * bar_width)
        bar_text = Text()
        bar_text.append(bar[:threshold_pos], style="green")
        bar_text.append(bar[threshold_pos], style="yellow")
        bar_text.append(bar[threshold_pos+1:], style="dim")
        state_color = {"silence": "dim", "speech": "bold red", "turn_end": "yellow"}.get(self.vad_state, "white")
        bar_text.append(f"\nrms: {rms_now:.3f}  threshold: 0.05\n", style="dim")
        bar_text.append(f"VAD: {self.vad_state.upper()}", style=state_color)
        return Panel(bar_text, title="MICROPHONE", border_style="green")

    def _pipeline_panel(self) -> Panel:
        text = Text()
        for name, status, lat in (
            ("ASR ", self.asr_status, self.asr_latency_ms),
            ("LLM ", self.llm_status, self.llm_latency_ms),
            ("TTS ", self.tts_status, self.tts_latency_ms),
        ):
            icon = {"idle": "o", "thinking": "...", "playing": ">", "final": "v", "done": "v"}.get(status, "?")
            color = {"idle": "dim", "thinking": "yellow", "playing": "cyan", "final": "green", "done": "green"}.get(status, "white")
            text.append(f"{icon} {name}", style=color)
            text.append(f"  {status:<10}", style=color)
            text.append(f" {lat}ms\n", style="dim")
        return Panel(text, title="PIPELINE", border_style="magenta")

    def _transcript_panel(self) -> Panel:
        text = Text()
        for t in self.transcript:
            role = t["role"].upper()
            text.append(f"[{role}] ", style="bold" if role == "USER" else "cyan")
            text.append(f"{t['text']}\n")
        return Panel(text, title="TRANSCRIPT", border_style="yellow")

    def _log_panel(self) -> Panel:
        text = Text()
        for line in self.log_lines:
            text.append(line + "\n")
        return Panel(text, title="LOG (rolling)", border_style="dim")

    async def run(self, events) -> None:
        """Consume events from an async iterator and live-render."""
        with Live(self.renderable(), console=self.console, refresh_per_second=10) as live:
            async for event in events:
                self.apply(event)
                live.update(self.renderable())
