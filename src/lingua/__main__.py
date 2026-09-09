"""Lingua — voice-first Mandarin Chinese tutor."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import sounddevice as sd

from .config import LinguaConfig
from .voice_studio import VoiceStudioClient
from .tutor import MandarinTutor
from .hud.bus import EventBus
from .hud.display import Hud


def _load_env() -> None:
    for dotenv in [Path.cwd() / ".env", Path.home() / ".lingua.env"]:
        if dotenv.exists():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                os.environ[k] = v
                if k == "MINIMAX_API_KEY":
                    os.environ.setdefault("OPENAI_API_KEY", v)
            break


def _list_devices() -> None:
    print("\nAudio devices:")
    for i, d in enumerate(sd.query_devices()):
        marker = ""
        if d["max_input_channels"] > 0 and i == sd.default.device[0]:
            marker += " [default INPUT]"
        if d["max_output_channels"] > 0 and i == sd.default.device[1]:
            marker += " [default OUTPUT]"
        print(f"  [{i}] {d['name']}{marker}")
    print()


def _resolve_device(idx: int | None, kind: str) -> tuple[int | None, str]:
    if idx is None:
        if kind == "input":
            idx = sd.default.device[0]
        else:
            idx = sd.default.device[1]
    info = sd.query_devices(idx)
    return idx, info["name"]


async def async_main(args: argparse.Namespace) -> None:
    from lingua.agent.harness import VoiceAgentHarness

    config = LinguaConfig.from_toml("lingua.toml")
    bus = EventBus()

    input_idx, input_name = _resolve_device(args.input, "input")
    output_idx, output_name = _resolve_device(args.output, "output")

    # Set defaults for sounddevice
    if input_idx is not None:
        sd.default.device = (input_idx, sd.default.device[1])
    if output_idx is not None:
        sd.default.device = (sd.default.device[0], output_idx)

    tutor = MandarinTutor(config)
    harness = VoiceAgentHarness(tutor=tutor, config=config, event_bus=bus)

    hud = Hud(input_device=input_name, output_device=output_name)

    print("🎙️  Lingua Voice Tutor")
    print(f"Input:  {input_name} [device {input_idx}]")
    print(f"Output: {output_name} [device {output_idx}]")
    print("Press Ctrl+C to exit.\n")

    hud_task = asyncio.create_task(hud.run(bus.subscribe()))
    try:
        await harness.run()
    except KeyboardInterrupt:
        print("\n👋 goodbye!")
    finally:
        hud_task.cancel()
        try:
            await hud_task
        except asyncio.CancelledError:
            pass


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lingua", description="Voice-first Mandarin tutor")
    parser.add_argument("--input", "-i", type=int, default=None, help="Input device index")
    parser.add_argument("--output", "-o", type=int, default=None, help="Output device index")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    args = parser.parse_args(argv)

    _load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s")

    if args.list_devices:
        _list_devices()
        return

    # Verify VoiceStudio
    config = LinguaConfig.from_toml("lingua.toml")
    vs = VoiceStudioClient(config.voicestudio.url)
    if not vs.is_available():
        print(f"❌ VoiceStudio not reachable at {config.voicestudio.url}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
