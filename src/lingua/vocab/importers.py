"""Vocabulary importers for various formats."""
import re
from datetime import datetime
from pathlib import Path

from src.lingua.vocab.scheduler import Card


def load_palavras_essenciais(path: str) -> list[Card]:
    """Load Portuguese vocabulary from guia.html.

    Parses the embedded JS array containing Chinese-Portuguese vocabulary.

    Args:
        path: Path to the guia.html file.

    Returns:
        List of Card objects with front=hanzi, back=pt translation.
    """
    html_path = Path(path)
    if not html_path.exists():
        msg = f"File not found: {path}"
        raise FileNotFoundError(msg)

    content = html_path.read_text(encoding="utf-8")

    # Find the JS array: const words = [...]
    match = re.search(r"const\s+words\s*=\s*\[", content)
    if not match:
        msg = "Could not find 'const words = [...]' in the HTML file"
        raise ValueError(msg)

    # Extract everything from the array start to the closing ];
    # Find the matching closing bracket
    start = match.end()
    depth = 1
    i = start
    while i < len(content) and depth > 0:
        if content[i] == "[":
            depth += 1
        elif content[i] == "]":
            depth -= 1
        i += 1

    js_array = content[start : i - 1]

    # Extract individual word objects using regex
    # Pattern: { hanzi: "...", pinyin: "...", slug: "...", tones: [...], pt: "...", context: "...", cat: "..." }
    word_pattern = re.compile(
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

    cards: list[Card] = []
    now = datetime.now()

    for word_match in word_pattern.finditer(js_array):
        hanzi, pinyin, slug, tones_raw, pt, context, cat = word_match.groups()

        # Parse tones: '[3,3]' -> [3,3]; '' -> [].
        tones = _parse_tones(tones_raw)

        # Generate ID from hanzi (simple hash-like approach)
        card_id = f"pe_{slug}"

        # Map audio path
        audio_path = f"palavras-essenciais/audio/{slug}.mp3"

        # Create card with new card defaults
        card = Card(
            id=card_id,
            front=hanzi,
            back=pt,
            ease_factor=2.5,
            interval_days=0,
            repetitions=0,
            due_date=now,
            pinyin=pinyin,
            context=context,
            cat=cat,
            tones=tones,
            audio_path=audio_path,
        )

        cards.append(card)

    return cards


def _parse_tones(raw: str) -> list[int]:
    """Parse '[3,3]' -> [3,3]; '' -> []."""
    raw = raw.strip()
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]
