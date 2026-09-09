"""Lingua — voice-first Mandarin Chinese tutor."""
from __future__ import annotations

import os
import logging
import asyncio
from pathlib import Path

from .config import LinguaConfig
from .voice_studio import VoiceStudioClient
from .tutor import MandarinTutor


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


async def async_main() -> None:
    from lingua.agent.harness import VoiceAgentHarness
    config = LinguaConfig.from_toml("lingua.toml")
    harness = VoiceAgentHarness(tutor=MandarinTutor(config), config=config)
    print("🎙️  Voice Agent ready — speak Mandarin or English!")
    print("   Ctrl+C to exit.")
    try:
        await harness.run()
    except KeyboardInterrupt:
        print("\n👋 goodbye!")


def main() -> None:
    _load_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    # Check VoiceStudio availability first
    config = LinguaConfig.from_toml("lingua.toml")
    vs = VoiceStudioClient(config.voicestudio.url)
    if not vs.is_available():
        raise RuntimeError(f"VoiceStudio not reachable at {config.voicestudio.url}")

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
