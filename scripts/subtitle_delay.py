#!/usr/bin/env python3
"""
subtitle_delay.py

Extends each SRT entry's end_time by a fixed delay (ms), keeping start_time
unchanged. This gives subtitles more display time without shifting when they appear.

Usage:
    python subtitle_delay.py <input.srt> <output.srt> [--delay=400]
    python subtitle_delay.py english_pinyin.srt Three-Body.S01E01_pinyin_delayed.srt --delay=400
"""

import re
import sys
from pathlib import Path

SRT_BLOCK = re.compile(
    r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\n(?=\d+\n)|$)",
)


def parse_timestamp(ts: str) -> int:
    """Parse SRT timestamp (HH:MM:SS,mmm) to total milliseconds."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)


def format_timestamp(ms: int) -> str:
    """Format total milliseconds to SRT timestamp (HH:MM:SS,mmm)."""
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def delay_entry(start: str, end: str, text: str, delay_ms: int) -> str:
    """Shift end_time forward by delay_ms."""
    start_ms = parse_timestamp(start)
    end_ms = parse_timestamp(end) + delay_ms
    # Clamp: don't let end go past 99:59:59,999
    max_ms = 359999999
    end_ms = min(end_ms, max_ms)
    return f"{start}\n{format_timestamp(start_ms)} --> {format_timestamp(end_ms)}\n{text}"


def main():
    delay_ms = 400
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    for f in flags:
        if f.startswith("--delay="):
            delay_ms = int(f.split("=")[1])

    if len(args) < 2:
        print("Usage: python subtitle_delay.py <input.srt> <output.srt> [--delay=400]")
        sys.exit(1)

    input_path = Path(args[0])
    output_path = Path(args[1])

    content = input_path.read_text(encoding="utf-8")
    entries = []
    for m in SRT_BLOCK.finditer(content):
        idx = m.group(1)
        start = m.group(2)
        end = m.group(3)
        text = m.group(4).rstrip("\n")
        entries.append((idx, start, end, text))

    print(f"Parsed {len(entries)} entries from {input_path.name}")

    output_lines = []
    for idx, start, end, text in entries:
        # Re-build the block with delayed end time
        new_end = format_timestamp(parse_timestamp(end) + delay_ms)
        output_lines.append(f"{idx}\n{start} --> {new_end}\n{text}\n")

    output_path.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"Written: {output_path}  (+{delay_ms}ms per entry)")
    print(f"  Entries: {len(entries)}")


if __name__ == "__main__":
    main()
