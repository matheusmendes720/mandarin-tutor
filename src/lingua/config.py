"""Configuration dataclasses and TOML loading."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

try:
    import tomllib
except ImportError:
    import tomli as tomllib


@dataclass
class VoiceStudioConfig:
    url: str = "http://127.0.0.1:3900"
    # Voice profiles discovered from VoiceStudio:
    # GET /v1/audio/voices
    voice_mandarin: str = "8c53222c"  # Chinese · Male · Child · Very High
    voice_english: str = "demo0001"  # VoiceStudio Demo Voice (English)
    engine: str = "openai"


@dataclass
class LLMConfig:
    provider: str = "minimax"
    url: str = "https://api.minimax.io/v1/text"
    model: str = "MiniMax-M3"
    api_key: str = ""


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_ms: int = 100


@dataclass
class VocabConfig:
    store_path: Path = Path("data/vocab.json")
    source_path: Path = field(default_factory=lambda: Path("data/mandarin-learning"))


@dataclass
class LinguaConfig:
    voicestudio: VoiceStudioConfig = field(default_factory=VoiceStudioConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vocab: VocabConfig = field(default_factory=VocabConfig)

    @classmethod
    def defaults(cls) -> "LinguaConfig":
        return cls(
            llm=LLMConfig(
                api_key=os.environ.get("MINIMAX_API_KEY", ""),
            ),
        )

    @classmethod
    def from_toml(cls, path: Path | str) -> "LinguaConfig":
        path = Path(path)
        # If relative path doesn't exist at cwd, also check package directory
        if not path.is_absolute() and not path.exists():
            package_dir = Path(__file__).parent  # src/lingua/
            package_path = package_dir / path
            if package_path.exists():
                path = package_path
        if not path.exists():
            logger.warning("lingua.toml not found at %s, using defaults (api_key from env or empty)", path)
            return cls.defaults()
        with open(path, "rb") as f:
            raw = tomllib.load(f)

        def expand(val: str) -> str:
            if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
                return os.environ.get(val[2:-1], "")
            return val

        vs_raw = raw.get("voicestudio", {})
        llm_raw = raw.get("llm", {})
        vocab_raw = raw.get("vocab", {})

        return cls(
            voicestudio=VoiceStudioConfig(
                url=expand(vs_raw.get("url", "http://127.0.0.1:3900")),
                voice_mandarin=expand(
                    vs_raw.get("voice_mandarin", "8c53222c")
                ),
                voice_english=expand(vs_raw.get("voice_english", "demo0001")),
                engine=expand(vs_raw.get("engine", "openai")),
            ),
            llm=LLMConfig(
                provider=expand(llm_raw.get("provider", "minimax")),
                url=expand(llm_raw.get("url", "https://api.minimax.io/v1/text")),
                model=expand(llm_raw.get("model", "MiniMax-M3")),
                api_key=expand(os.environ.get("MINIMAX_API_KEY", "")),
            ),
            vocab=VocabConfig(
                store_path=Path(expand(vocab_raw.get("store_path", "data/vocab.json"))),
                source_path=Path(
                    expand(
                        vocab_raw.get("source_path", "data/mandarin-learning"),
                    )
                ),
            ),
        )
