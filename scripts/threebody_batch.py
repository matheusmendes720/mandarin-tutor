#!/usr/bin/env python3
"""
threebody_batch.py

Batch process Three-Body episodes (E01-E30) through the full pipeline:
  1. Copy 2_eng.srt  →  work dir
  2. Generate bilingual SRT (pinyin + English) via pinyin_bilingual_srt.py
  3. Add +400ms display delay via subtitle_delay.py
  4. Convert to styled ASS via srt_to_ass.py
  5. Mux: video (copy) + Chinese audio (0:a:0) + ASS subtitle
  6. Delete all temp files

Disk-space conscious: video is streamed (copy), only final .mkv is kept.
Output is MKV because MP4/mov_text does not support ASS subtitle styling
(yellow pinyin / white English require the ASS format preserved in MKV).

Usage:
    python scripts/threebody_batch.py
    python scripts/threebody_batch.py --episodes E01,E05,E10

Requirements:
    pip install deep_translator pypinyin
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── config ──────────────────────────────────────────────────────────────────
ROOT = Path(r"C:\Users\mathe\Downloads\Three-Body.S01.CHINESE.1080p.WEBRip.x265-KONTRAST")
PYTHON = r"C:\Python314\python.exe"   # has deep_translator + pypinyin
SCRIPT_DIR = Path(__file__).parent

EPISODES = [f"E{i:02d}" for i in range(1, 31)]
DELAY_MS = 400
# ─────────────────────────────────────────────────────────────────────────────

def run(cmd: list[str], desc: str, timeout: int | None = None) -> bool:
    print(f"  {'─'*50}")
    print(f"  {desc}")
    print(f"  {' '.join(str(c) for c in cmd)!r}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"  [FAIL] {result.stderr[:500]}")
        return False
    print(f"  [OK] {result.stdout[:200] if result.stdout else '(no stdout)'}")
    return True


def process_episode(ep: str) -> bool:
    ep_dir = ROOT / f"Three-Body.S01E{ep}.CHINESE.1080p.WEBRip.x265-KONTRAST"
    video = ep_dir.with_name(f"Three-Body.S01E{ep}.CHINESE.1080p.WEBRip.x265-KONTRAST.mp4")
    subs_dir = ROOT / f"Subs/Three-Body.S01E{ep}.CHINESE.1080p.WEBRip.x265-KONTRAST"
    srt_src = subs_dir / "2_eng.srt"
    work_dir = ROOT / "temp_subs"
    work_dir.mkdir(exist_ok=True)

    eng_srt   = work_dir / f"Three-Body.S01E{ep}_eng.srt"
    pinyin_srt= work_dir / f"Three-Body.S01E{ep}_pinyin.srt"
    delayed_srt= work_dir / f"Three-Body.S01E{ep}_delayed.srt"
    ass_file  = work_dir / f"Three-Body.S01E{ep}_bilingual.ass"
    output_mkv= ROOT / f"Three-Body.S01E{ep}.[CMN-PINYIN].mkv"

    print(f"\n{'═'*60}")
    print(f"  Episode {ep}")
    print(f"{'═'*60}")

    # ── step 1: copy SRT ────────────────────────────────────────────────────
    if not srt_src.exists():
        print(f"  [SKIP] SRT not found: {srt_src}")
        return False
    shutil.copy2(srt_src, eng_srt)

    # ── step 2: bilingual pinyin SRT (slow – MyMemory translation) ─────────
    # Check if already generated
    if pinyin_srt.exists():
        print(f"  [SKIP] Bilingual SRT already exists: {pinyin_srt.name}")
    else:
        ok = run(
            [PYTHON, SCRIPT_DIR / "pinyin_bilingual_srt.py", str(eng_srt), str(pinyin_srt)],
            "Generate bilingual pinyin+English SRT"
        )
        if not ok:
            return False

    # ── step 3: add display delay ────────────────────────────────────────────
    if delayed_srt.exists():
        print(f"  [SKIP] Delayed SRT already exists")
    else:
        ok = run(
            [PYTHON, SCRIPT_DIR / "subtitle_delay.py", str(pinyin_srt), str(delayed_srt), f"--delay={DELAY_MS}"],
            f"Add +{DELAY_MS}ms display delay"
        )
        if not ok:
            return False

    # ── step 4: convert to styled ASS ────────────────────────────────────────
    if ass_file.exists():
        print(f"  [SKIP] ASS already exists")
    else:
        ok = run(
            [PYTHON, SCRIPT_DIR / "srt_to_ass.py", str(delayed_srt), str(ass_file)],
            "Convert to styled ASS"
        )
        if not ok:
            return False

    # ── step 5: mux ────────────────────────────────────────────────────────
    # Chinese audio is at 0:a:0 (confirmed by Whisper)
    # Output is MKV because MP4/mov_text strips ASS styling
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(ass_file),
        "-map", "0:v",
        "-map", "0:a:0",
        "-map", "1:s",
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", "ass",
        "-disposition:s:0", "default",
        "-metadata:s:a:0", "language=cmn",
        "-metadata:s:s:0", "language=cmn",
        str(output_mkv),
    ]
    ok = run(cmd, "Mux video + Chinese audio + ASS subtitle")
    if not ok:
        return False

    # ── step 6: clean up temp files ─────────────────────────────────────────
    for f in [eng_srt, pinyin_srt, delayed_srt, ass_file]:
        if f.exists():
            f.unlink()
    # Remove work dir if empty
    if work_dir.exists() and not any(work_dir.iterdir()):
        work_dir.rmdir()

    print(f"  ✓ Output: {output_mkv.name}  ({output_mkv.stat().st_size / 1024**2:.1f} MB)")
    return True


def main():
    episodes_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith("--episodes="):
            episodes_arg = arg.split("=", 1)[1].split(",")

    episodes = episodes_arg if episodes_arg else EPISODES
    print(f"Three-Body batch pipeline")
    print(f"  Root:  {ROOT}")
    print(f"  Python: {PYTHON}")
    print(f"  Episodes: {', '.join(episodes)}")
    print(f"  Delay: +{DELAY_MS}ms per subtitle")

    success, failed = [], []
    for ep in episodes:
        ep_num = ep[-2:]
        ok = process_episode(ep_num)
        if ok:
            success.append(ep_num)
        else:
            failed.append(ep_num)

    print(f"\n{'═'*60}")
    print(f"  DONE  success={len(success)}  failed={len(failed)}  (.mkv output)")
    if failed:
        print(f"  Failed episodes: {', '.join(failed)}")


if __name__ == "__main__":
    main()
