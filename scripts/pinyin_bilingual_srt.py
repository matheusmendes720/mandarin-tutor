#!/usr/bin/env python3
"""
pinyin_bilingual_srt.py

Converts English SRT subtitles to bilingual Pinyin + English format.

Approach: For each English subtitle line, translate to Simplified Chinese,
then romanize the Chinese to Pinyin with tone marks.

    Line 1: Pīnyīn (romanized Simplified Chinese)
    Line 2: English text (original)

Requirements:
    pip install pypinyin deep_translator

Usage:
    python pinyin_bilingual_srt.py <input.srt> [output.srt]
"""

import re
import sys
import time
from pathlib import Path

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
except ImportError:
    sys.stderr.write("Error: deep_translator not installed.\n    pip install deep_translator\n")
    sys.exit(1)

try:
    from pypinyin import lazy_pinyin, Style  # TONE = tone marks (á), TONE3 = tone numbers (a2)
except ImportError:
    sys.stderr.write("Error: pypinyin not installed.\n    pip install pypinyin\n")
    sys.exit(1)


# --- Pinyin conversion ---
TONE_RE = re.compile(r"([a-z]+)(\d)")


def chinese_to_pinyin(chinese_text: str) -> str:
    """
    Convert Chinese text to readable Pinyin with tone marks.
    Adds spaces between syllables for readability.
    Strips Chinese punctuation before conversion.
    """
    # Remove Chinese punctuation (commas, periods, quotes, etc.)
    cleaned = re.sub(r"[　-〿﹐-﻿《》（）""''【】『』]", "", chinese_text)
    if not cleaned.strip():
        return ""

    try:
        syllables = lazy_pinyin(cleaned, style=Style.TONE)  # TONE = à è î etc.
        # syllables is a list like ['suí', 'cháo', 'mò', 'nián']
        # Join with spaces for readability
        spaced = " ".join(syllables)
        return spaced
    except Exception:
        return chinese_text


# --- Google Translate with retry + backoff ---
import time

def translate_batch(texts: list[str]) -> list[str]:
    """Translate English texts to Chinese Simplified via Google Translate.

    Handles rate limiting with retries and exponential backoff.
    Falls back to MyMemory if Google fails persistently.
    """
    results = []
    errors = {}

    # Try Google first, fall back to MyMemory
    google_ok = False
    try:
        translator = GoogleTranslator(source="en", target="zh-CN")
        test = translator.translate("test")
        google_ok = True
    except Exception:
        pass

    for i, text in enumerate(texts):
        raw = None
        attempts = 0
        max_attempts = 5 if google_ok else 3

        while attempts < max_attempts:
            attempts += 1
            try:
                if google_ok:
                    raw = translator.translate(text)
                else:
                    # Fallback to MyMemory
                    mymem = MyMemoryTranslator(source="english", target="chinese simplified")
                    raw = mymem.translate(text)
                break
            except Exception as e:
                err_str = str(e)
                if attempts == 1:
                    errors[i] = err_str
                # Rate limit: wait longer
                wait = min(2 ** attempts + 0.5, 30)
                sys.stderr.write(f"\n  [attempt {attempts}/{max_attempts}] {err_str[:60]} — waiting {wait:.1f}s...")
                sys.stderr.flush()
                time.sleep(wait)

        if raw:
            results.append(raw)
        else:
            results.append(f"[ERR: {errors.get(i, 'translation failed')}]")

        if (i + 1) % 20 == 0:
            err_count = sum(1 for r in results if r.startswith("[ERR"))
            sys.stderr.write(f"\r  Translated {i+1}/{len(texts)}  errors={err_count}")
            sys.stderr.flush()

    err_count = sum(1 for r in results if r.startswith("[ERR"))
    sys.stderr.write(f"\n  Done — {len(texts)} entries, {err_count} errors\n")
    sys.stderr.flush()
    return results


# --- SRT parsing ---
SRT_BLOCK = re.compile(
    r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\n(?=\d+\n)|$)",
)


def parse_srt(content: str) -> list[tuple[str, str, str, str]]:
    """Return list of (index, start, end, text)."""
    results = []
    for m in SRT_BLOCK.finditer(content):
        idx, start, end, text = m.group(1), m.group(2), m.group(3), m.group(4)
        results.append((idx, start, end, text.rstrip("\n")))
    return results


def build_bilingual_entry(
    idx: str, start: str, end: str, english: str, chinese: str
) -> str:
    """Format a single SRT entry as pinyin + English."""
    # Normalize: replace \n with space, strip trailing whitespace
    english_norm = " ".join(english.splitlines()).strip()
    chinese_norm = " ".join(chinese.splitlines()).strip()

    if not english_norm or not re.search(r"[a-zA-Z]", english_norm):
        return f"{idx}\n{start} --> {end}\n{english_norm}\n"

    pinyin = chinese_to_pinyin(chinese_norm)
    return f"{idx}\n{start} --> {end}\n{pinyin}\n{english_norm}\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: python pinyin_bilingual_srt.py <input.srt> [output.srt]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_name(
        input_path.stem + "_pinyin.srt"
    )

    content = input_path.read_text(encoding="utf-8")
    entries = parse_srt(content)
    print(f"Parsed {len(entries)} entries from {input_path.name}", file=sys.stderr)

    english_texts = [entry[3].strip() for entry in entries]

    sys.stderr.write("Translating...\n")
    chinese_texts = translate_batch(english_texts)

    output_lines = []
    for (idx, start, end, english), chinese in zip(entries, chinese_texts):
        output_lines.append(build_bilingual_entry(idx, start, end, english, chinese))

    output_path.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"Written: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
