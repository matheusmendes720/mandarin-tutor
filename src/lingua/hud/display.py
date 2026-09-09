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
        # Header (3) + body (transcript-led) + log (12, roomier for rolling events)
        layout.split_column(
            Layout(self._header(), size=3),
            Layout(name="body"),
            Layout(self._log_panel(), size=12),
        )
        # Body: left rail (mic + pipeline, fixed-size) + right (transcript fills the rest)
        layout["body"].split_row(
            Layout(name="left", size=42),
            Layout(self._transcript_panel(), name="right"),
        )
        # Mic (7 rows) + Pipeline (8 rows) — exact sizes, no empty padding
        layout["body"]["left"].split_column(
            Layout(self._mic_panel(), name="mic", size=7),
            Layout(self._pipeline_panel(), name="pipeline", size=8),
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
        # Wider bar (40 chars) so RMS movement is visible at a glance.
        # Use ratio of last_rms vs the typical noise floor (0.05) for "speech" color.
        bar_width = 40
        rms_now = self.last_speech_rms
        # Cap display at 0.5 RMS — anything above that is "loud"
        display_rms = min(rms_now, 0.5) / 0.5
        filled = int(display_rms * bar_width)
        threshold_pos = int(0.05 / 0.5 * bar_width)  # threshold marker
        bar_chars = "█" * filled + "░" * (bar_width - filled)
        state_color = {
            "silence": "dim",
            "speech": "bold red",
            "turn_end": "yellow",
        }.get(self.vad_state, "white")
        # Build line by line — no padding rows
        bar_line = Text()
        bar_line.append(bar_chars[:threshold_pos], style="green")
        bar_line.append(bar_chars[threshold_pos], style="yellow")
        bar_line.append(bar_chars[threshold_pos + 1:], style="dim")
        info_line = Text()
        info_line.append(f"rms {rms_now:.3f}", style="dim")
        info_line.append("  thr 0.050  ", style="dim")
        info_line.append(f"VAD {self.vad_state.upper()}", style=state_color)
        # Compose into a single Text with embedded newline
        body = Text()
        body.append_text(bar_line)
        body.append("\n")
        body.append_text(info_line)
        body.append("\n")
        # Line 3: hint about voice profile
        body.append("input → pipeline", style="dim italic")
        return Panel(body, title="MICROPHONE", border_style="green")

    def _pipeline_panel(self) -> Panel:
        # 3 status rows + summary row at bottom = 4 useful lines + padding
        text = Text()
        for name, status, lat in (
            ("ASR", self.asr_status, self.asr_latency_ms),
            ("LLM", self.llm_status, self.llm_latency_ms),
            ("TTS", self.tts_status, self.tts_latency_ms),
        ):
            icon = {"idle": "○", "thinking": "⋯", "playing": "▶", "final": "✓", "done": "✓"}.get(status, "?")
            color = {
                "idle": "dim",
                "thinking": "yellow",
                "playing": "cyan",
                "final": "green",
                "done": "green",
            }.get(status, "white")
            # Pad status label to 8 chars so columns line up
            text.append(f"{icon} {name:<4}", style=color)
            text.append(f"  {status:<8}", style=color)
            text.append(f" {lat:>5}ms\n", style="dim")
        # Summary: total turn latency
        total = (self.asr_latency_ms or 0) + (self.llm_latency_ms or 0) + (self.tts_latency_ms or 0)
        text.append("\n")
        text.append("─" * 36, style="dim")
        text.append("\n")
        text.append(f"total ", style="dim")
        text.append(f"{total}ms", style="bold")
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
        """Consume events from an asyncio.Queue (or async iterable) and live-render."""
        with Live(self.renderable(), console=self.console, refresh_per_second=10) as live:
            while True:
                # Support both asyncio.Queue and async iterables
                if hasattr(events, "get"):
                    event = await events.get()
                else:
                    try:
                        event = await events.__anext__()
                    except StopAsyncIteration:
                        return
                self.apply(event)
                live.update(self.renderable())
