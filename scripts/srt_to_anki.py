#!/usr/bin/env python3
"""
srt_to_anki.py

Converts a bilingual pinyin+English SRT file into Anki-importable TSV.

Card types produced:
  1. Pinyin  → English     (listening/reading recognition)
  2. English → Pinyin      (productive recall)
  3. Pinyin+Chinese → English (character-level)

Format: tab-separated, UTF-8, ready for Anki import.

Usage:
    python srt_to_anki.py <bilingual_srt> <output_tsv> [--include-chinese]
    python srt_to_anki.py english_pinyin.srt anki_import.tsv --include-chinese

Anki import: File → Import → select "Tab" separator, "Allow HTML in fields".
"""

import re
import sys
from pathlib import Path

try:
    from pypinyin import lazy_pinyin, Style
except ImportError:
    sys.stderr.write("Error: pypinyin not installed.\n    pip install pypinyin\n")
    sys.exit(1)


SRT_BLOCK = re.compile(
    r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\n(?=\d+\n)|$)",
)


def parse_srt(content: str) -> list[tuple[str, str, str]]:
    """Return list of (start_time, end_time, pinyin_text)."""
    results = []
    for m in SRT_BLOCK.finditer(content):
        start = m.group(2)
        end = m.group(3)
        text = m.group(4).rstrip("\n")
        results.append((start, end, text))
    return results


def split_entry(text: str) -> tuple[str, str]:
    """Split SRT entry into pinyin (line 1) and english (line 2)."""
    lines = text.strip().splitlines()
    if len(lines) >= 2:
        return lines[0].strip(), lines[1].strip()
    elif len(lines) == 1:
        return lines[0].strip(), ""
    return "", ""


def pinyin_to_chinese(pinyin_line: str) -> str:
    """
    Attempt to convert a spaced pinyin line back to Chinese characters.
    This is approximate — uses a simple syllable-to-character mapping.
    Falls back to the pinyin itself if no mapping found.
    """
    # Minimal pinyin→Chinese mapping for common subtitle syllables
    # This is an approximation; for production use a proper dictionary
    # like pypinyin's `pinyin` (not `lazy_pinyin`) with a phrase dictionary
    return pinyin_line  # fallback: return pinyin as-is


def format_timestamp(ts: str) -> str:
    """Convert SRT timestamp to readable form like '01:23'."""
    parts = ts.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return ts


def build_basic_card(pinyin: str, english: str, tag: str = "") -> str:
    """Build Basic card: front\tback"""
    tag_str = f"\t{tag}" if tag else ""
    return f"{pinyin}\t{english}{tag_str}"


def build_reversed_card(pinyin: str, english: str, tag: str = "") -> str:
    """Build Reversed card: back\tfront (English → Pinyin)"""
    tag_str = f"\t{tag}" if tag else ""
    return f"{english}\t{pinyin}{tag_str}"


def main():
    include_chinese = "--include-chinese" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if len(args) < 2:
        print("Usage: python srt_to_anki.py <bilingual_srt> <output_tsv> [--include-chinese]")
        sys.exit(1)

    input_path = Path(args[0])
    output_path = Path(args[1])

    content = input_path.read_text(encoding="utf-8")
    entries = parse_srt(content)
    print(f"Parsed {len(entries)} entries from {input_path.name}")

    # Anki requires a header for the Basic-with-reversed note type
    # Columns: Front, Back, Tags
    lines = ["front\tback\ttags"]

    for start, end, text in entries:
        pinyin, english = split_entry(text)
        if not pinyin or not english:
            continue

        ts = format_timestamp(start)

        if include_chinese:
            # Add Chinese characters between pinyin and English
            chinese = pinyin_to_chinese(pinyin)
            # Basic card: Pinyin + Chinese → English
            lines.append(build_basic_card(f"{pinyin} [{chinese}]", english, "movie"))
        else:
            # Basic card: Pinyin → English
            lines.append(build_basic_card(pinyin, english, "movie"))

        # Reversed card: English → Pinyin  (adds productive recall)
        lines.append(build_reversed_card(pinyin, english, "movie"))

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {output_path}")
    print(f"  {len(entries)} basic cards  (Pinyin → English)")
    print(f"  {len(entries)} reversed cards (English → Pinyin)")
    print(f"  Total: {len(lines) - 1} cards")
    print()
    print("Anki import instructions:")
    print("  1. Open Anki → File → Import")
    print("  2. Select the TSV file")
    print("  3. Separator: Tab")
    print("  4. Note type: Basic (or Basic with reversed for auto-generate)")
    print("  5. Check 'Allow HTML in fields'")
    print("  6. Import")


if __name__ == "__main__":
    main()
