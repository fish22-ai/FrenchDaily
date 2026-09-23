"""Re-render HTML from existing data/*.json — no LLM, no TTS.

Use this after changing the layout in core/html.py:

    python scripts/render.py                # re-render every day
    python scripts/render.py 2026-09-21     # re-render one day
    python scripts/render.py --site DIR     # write somewhere else

index.html is always a copy of the newest day.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import Day
from core.html import render_day

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import apply_lessons_pack, attach_conj_lessons

DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"


def load_streak_info() -> dict:
    path = DATA_DIR / "streak.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "current_streak": raw.get("current_streak", 0),
        "longest_streak": raw.get("longest_streak", 0),
        "total_days": raw.get("total_days", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-render FrenchDaily HTML")
    parser.add_argument("dates", nargs="*", help="Dates to render (default: all)")
    parser.add_argument("--site", default="", help="Output directory (default: site/)")
    args = parser.parse_args()

    site_dir = Path(args.site) if args.site else SITE_DIR
    site_dir.mkdir(parents=True, exist_ok=True)

    all_dates = sorted(
        (p.stem for p in DATA_DIR.glob("20*.json") if p.name != "index.json"),
        reverse=True,
    )
    if not all_dates:
        print("No data files in", DATA_DIR)
        return 1

    dates = args.dates or all_dates
    streak_info = load_streak_info()

    for date_str in dates:
        src = DATA_DIR / f"{date_str}.json"
        if not src.exists():
            print(f"skip {date_str}: no data file")
            continue
        day = Day.from_dict(json.loads(src.read_text(encoding="utf-8")))
        # The curated grammar pack always wins, so a restyle also picks up
        # whatever was added to dict/lessons.json since the day was generated.
        synced = apply_lessons_pack(
            [s for p in day.passages for s in p.sentences]
        )
        # Conjugation tables are a hard requirement: auto-attach one per BOOK
        # verb (no LLM, no content change — same engine as the tap panel).
        attached = attach_conj_lessons(
            [s for p in day.passages for s in p.sentences]
        )
        html = render_day(day, streak_info, all_dates)
        (site_dir / f"{date_str}.html").write_text(html, encoding="utf-8")
        print(f"rendered {date_str}.html  ({len(html):,} bytes, "
              f"{day.total_sentences()} sentences, {synced} lessons from pack, "
              f"{attached} auto tables)")

    latest = all_dates[0]
    latest_file = site_dir / f"{latest}.html"
    if latest_file.exists():
        (site_dir / "index.html").write_text(
            latest_file.read_text(encoding="utf-8"), encoding="utf-8"
        )
        print(f"index.html -> {latest}.html")

    # Word-level mp3s for devices without a French TTS voice. Quiet + guarded:
    # renders must keep working on interpreters without edge_tts.
    try:
        from gen_audio import refresh as gen_audio_refresh
        n = gen_audio_refresh(site_dir, quiet=False)
        if n:
            print(f"gen_audio: synthesized {n} new mp3s")
    except Exception as exc:
        print(f"gen_audio skipped: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
