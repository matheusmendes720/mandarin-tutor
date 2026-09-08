#!/usr/bin/env python3
"""
srt_to_ass.py

Converts a bilingual pinyin+English SRT into a styled ASS subtitle file.

Line 1 (pinyin):  yellow text  (&H00FFFF&)
Line 2 (english):  white text   (&H00FFFFFF&)

Output is proper ASS v4+ with bottom-aligned bilingual display.

Usage:
    python srt_to_ass.py <input.srt> <output.ass>
    python srt_to_ass.py Three-Body.S01E01_pinyin_delayed.srt Three-Body.S01E01_bilingual.ass
"""

import re
import sys
from pathlib import Path

SRT_BLOCK = re.compile(
    r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\n(?=\d+\n)|$)",
)

ASS_HEADER = """[Script Info]
Title: Bilingual Pinyin/English
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Pinyin,Arial,54,&H00FFFF&,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,2,0,2,30,30,20,1
Style: English,Arial,46,&H00FFFFFF,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,2,0,2,30,30,56,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def srt_to_ass_time(ts: str) -> str:
    """Convert SRT timestamp (HH:MM:SS,mmm) to ASS timestamp (H:MM:SS.cc)."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    cs = int(ms) // 10  # SRT ms → ASS centiseconds (round down)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"


def split_entry(text: str):
    """Split SRT entry text into pinyin (line 1) and english (line 2)."""
    lines = text.strip().splitlines()
    if len(lines) >= 2:
        return lines[0].strip(), lines[1].strip()
    elif len(lines) == 1:
        return lines[0].strip(), ""
    return "", ""


def escape_ass(text: str) -> str:
    """Escape special ASS override characters."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def make_dialogue(start: str, end: str, style: str, text: str) -> str:
    """Build a single ASS Dialogue line."""
    a_start = srt_to_ass_time(start)
    a_end = srt_to_ass_time(end)
    color = "\\c&H00FFFF&" if style == "Pinyin" else "\\c&H00FFFFFF&"
    # Strip existing override tags from text and wrap with our color
    clean = re.sub(r"\{[^}]*\}", "", text)
    # Re-apply our color override at the start
    styled = f"{{{color}}}{escape_ass(clean)}"
    return f"Dialogue: 0,{a_start},{a_end},{style},*,0,0,0,,{styled}"


def main():
    if len(sys.argv) < 3:
        print("Usage: python srt_to_ass.py <input.srt> <output.ass>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    content = input_path.read_text(encoding="utf-8")
    entries = []
    for m in SRT_BLOCK.finditer(content):
        idx = m.group(1)
        start = m.group(2)
        end = m.group(3)
        text = m.group(4).rstrip("\n")
        entries.append((idx, start, end, text))

    print(f"Parsed {len(entries)} entries from {input_path.name}")

    lines = [ASS_HEADER]
    for idx, start, end, text in entries:
        pinyin, english = split_entry(text)
        if not pinyin and not english:
            continue
        if pinyin:
            lines.append(make_dialogue(start, end, "Pinyin", pinyin))
        if english:
            lines.append(make_dialogue(start, end, "English", english))

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {output_path}")
    print(f"  Pinyin lines: {sum(1 for _,_,_,t in entries if split_entry(t)[0])}")
    print(f"  English lines: {sum(1 for _,_,_,t in entries if split_entry(t)[1])}")


if __name__ == "__main__":
    main()
