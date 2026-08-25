"""Phoneme catalog implementation (Protocol in core.config)."""
from __future__ import annotations

import re
from pathlib import Path

from src.lingua.core.config import PhonemeCatalogConfig


# Mapping from pinyin-completo's group headers (Portuguese) to canonical groups.
# The HTML categorizes initials as "Grupo 1" / "Grupo 2" and finals as
# "Simples" / "Compostos" / "Nasais (-n)" / "Nasais (-ng)" / "Com med. i-/u-/ü-".
_INITIAL_GROUP_RE = re.compile(r"Grupo\s+(\d+)", re.IGNORECASE)
_FINAL_GROUP_RE = re.compile(
    r"(Simples|Compostos|Nasais\s*\(-n\)|Nasais\s*\(-ng\)|Com\s+med\.\s*i-|Com\s+med\.\s*u-|Com\s+med\.\s*ü-)",
    re.IGNORECASE,
)

_TONE_INFO: list[tuple[int, str, str]] = [
    (1, "Tone 1 - 阴平 (alto e nivelado)", "第一声"),
    (2, "Tone 2 - 阳平 (ascendente)", "第二声"),
    (3, "Tone 3 - 上声 (mergulhante)", "第三声"),
    (4, "Tone 4 - 去声 (descendente)", "第四声"),
    (5, "Tone 5 - 轻声 (neutro)", "轻声"),
]


class PinyinCompletoCatalog:
    """PhonemeCatalog implementation backed by pinyin-completo/audio/."""

    def __init__(self, config: PhonemeCatalogConfig) -> None:
        self._config = config
        self._audio_base = Path(config.audio_base)
        # Parse guia.html for group orderings (best-effort; fall back to
        # directory listings).
        self._initial_groups: dict[str, str] = {}
        self._final_groups: dict[str, str] = {}
        self._initial_order: list[str] = []
        self._final_order: list[str] = []
        self._parse_guia(Path(config.guia_path))

    def initials(self) -> list[dict]:
        iniciais = self._audio_base / "iniciais"
        if not iniciais.exists():
            return []
        keys = self._initial_order or sorted(p.stem for p in iniciais.glob("*.wav"))
        return [
            {
                "key": k,
                "group": self._initial_groups.get(k, "Outros"),
                "name_pt": k,
                "audio_path": str(iniciais / f"{k}.wav"),
            }
            for k in keys
            if (iniciais / f"{k}.wav").exists()
        ]

    def finals(self) -> list[dict]:
        finais = self._audio_base / "finais"
        if not finais.exists():
            return []
        keys = self._final_order or sorted(p.stem for p in finais.glob("*.wav"))
        return [
            {
                "key": k,
                "group": self._final_groups.get(k, "Outros"),
                "name_pt": k,
                "audio_path": str(finais / f"{k}.wav"),
            }
            for k in keys
            if (finais / f"{k}.wav").exists()
        ]

    def tones(self) -> list[dict]:
        tones_dir = self._audio_base / "tonalidades"
        out: list[dict] = []
        for number, name_pt, name_zh in _TONE_INFO:
            audio_path = tones_dir / f"ma{number}.wav"
            out.append(
                {
                    "number": number,
                    "name_pt": name_pt,
                    "name_zh": name_zh,
                    "audio_path": str(audio_path) if audio_path.exists() else None,
                }
            )
        return out

    def _parse_guia(self, path: Path) -> None:
        """Best-effort: extract the order + group of initials/finals from the
        guia.html. Falls back to directory sort if the HTML is not parseable."""
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, target, groups in [
            ("Iniciais", "initial", self._initial_groups),
            ("Finais", "final", self._final_groups),
        ]:
            section_re = re.compile(
                rf'<h2[^>]*id="{label.lower()}"[^>]*>(.+?)(?=<h2|$)',
                re.DOTALL | re.IGNORECASE,
            )
            sec = section_re.search(text)
            if not sec:
                continue
            section = sec.group(1)
            for stem in re.findall(r"[\"']?(\w+)[\"']?\.wav", section):
                order = self._initial_order if target == "initial" else self._final_order
                if stem not in order:
                    order.append(stem)
            current_group = "Outros"
            for chunk in re.split(r"(<h\d[^>]*>[^<]*</h\d>)", section):
                gm = (
                    _INITIAL_GROUP_RE.search(chunk)
                    if target == "initial"
                    else _FINAL_GROUP_RE.search(chunk)
                )
                if gm:
                    current_group = gm.group(0)
                for stem in re.findall(r"[\"']?(\w+)[\"']?\.wav", chunk):
                    groups.setdefault(stem, current_group)
