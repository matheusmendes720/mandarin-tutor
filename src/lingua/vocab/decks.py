"""Browsable deck implementations (DeckBrowser Protocol in core.config)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.lingua.core.config import DeckConfig


@dataclass
class ParsedWord:
    hanzi: str
    pinyin: str
    slug: str
    tones: list[int]
    pt: str
    context: str
    cat: str


@dataclass
class ParsedCategory:
    key: str
    icon: str
    name_pt: str
    subtitle: str


_WORD_PATTERN = re.compile(
    r"""\{[\s\S]*?
        hanzi:\s*"([^"]+)"[\s\S]*?
        pinyin:\s*"([^"]+)"[\s\S]*?
        slug:\s*"([^"]+)"[\s\S]*?
        tones:\s*\[([^\]]*)\][\s\S]*?
        pt:\s*"([^"]+)"[\s\S]*?
        context:\s*"([^"]+)"[\s\S]*?
        cat:\s*"([^"]+)"
    \s*\}""",
    re.VERBOSE,
)


def _parse_tones(raw: str) -> list[int]:
    """Parse '[3,3]' -> [3,3]; '' -> []."""
    raw = raw.strip()
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def parse_guia_html(path: Path) -> tuple[list[ParsedWord], list[ParsedCategory]]:
    """Parse palavras-essenciais/guia.html. Returns (words, categories)."""
    content = path.read_text(encoding="utf-8")
    words: list[ParsedWord] = []
    for m in _WORD_PATTERN.finditer(content):
        hanzi, pinyin, slug, tones_raw, pt, context, cat = m.groups()
        words.append(
            ParsedWord(
                hanzi=hanzi,
                pinyin=pinyin,
                slug=slug,
                tones=_parse_tones(tones_raw),
                pt=pt,
                context=context,
                cat=cat,
            )
        )
    # Categories object: const categories = { saudacoes: {icon, name, subtitle}, ... }
    cats: list[ParsedCategory] = []
    cat_block = re.search(
        r"const\s+categories\s*=\s*\{(.+?)^\}\s*$", content, re.M | re.S
    )
    if cat_block:
        block = cat_block.group(1)
        for m in re.finditer(
            r'(\w+):\s*\{\s*icon:\s*"([^"]+)",\s*name:\s*"([^"]+)",\s*subtitle:\s*"([^"]+)"\s*\}',
            block,
        ):
            cats.append(
                ParsedCategory(
                    key=m.group(1),
                    icon=m.group(2),
                    name_pt=m.group(3),
                    subtitle=m.group(4),
                )
            )
    return words, cats


class PalavrasEssenciaisDeck:
    """DeckBrowser implementation backed by palavras-essenciais/guia.html."""

    def __init__(self, config: DeckConfig) -> None:
        self._config = config
        self._words, self._categories = parse_guia_html(Path(config.deck_path))
        self._by_id: dict[str, ParsedWord] = {f"pe_{w.slug}": w for w in self._words}

    def categories(self) -> list[dict]:
        counts: dict[str, int] = {}
        for w in self._words:
            counts[w.cat] = counts.get(w.cat, 0) + 1
        return [
            {
                "key": c.key,
                "icon": c.icon,
                "name_pt": c.name_pt,
                "subtitle": c.subtitle,
                "count": counts.get(c.key, 0),
            }
            for c in self._categories
        ]

    def cards_by_category(self, category_key: str | None = None) -> list[dict]:
        out: list[dict] = []
        for w in self._words:
            if category_key is not None and w.cat != category_key:
                continue
            out.append(self._word_to_dict(w))
        return out

    def card(self, card_id: str) -> dict | None:
        w = self._by_id.get(card_id)
        return self._word_to_dict(w) if w else None

    def audio_path(self, card_id: str) -> str | None:
        w = self._by_id.get(card_id)
        if not w:
            return None
        return f"{self._config.audio_base.rstrip('/')}/{w.slug}.mp3"

    def _word_to_dict(self, w: ParsedWord) -> dict:
        return {
            "id": f"pe_{w.slug}",
            "hanzi": w.hanzi,
            "pinyin": w.pinyin,
            "pt": w.pt,
            "context": w.context,
            "tones": w.tones,
            "audio_path": self.audio_path(f"pe_{w.slug}"),
            "cat": w.cat,
        }