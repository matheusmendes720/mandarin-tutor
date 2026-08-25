"""Vocabulary importers for various formats."""
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
    # Imported here to avoid a circular import at module load time.
    from src.lingua.vocab.decks import parse_guia_html

    html_path = Path(path)
    if not html_path.exists():
        msg = f"File not found: {path}"
        raise FileNotFoundError(msg)

    words, _cats = parse_guia_html(html_path)
    now = datetime.now()
    cards: list[Card] = []
    for w in words:
        audio_path = f"palavras-essenciais/audio/{w.slug}.mp3"
        cards.append(
            Card(
                id=f"pe_{w.slug}",
                front=w.hanzi,
                back=w.pt,
                ease_factor=2.5,
                interval_days=0,
                repetitions=0,
                due_date=now,
                pinyin=w.pinyin,
                context=w.context,
                cat=w.cat,
                tones=w.tones,
                audio_path=audio_path,
            )
        )
    return cards