"""Main build script: generate → process → render → output.

Pipeline:
  1. Parse config (difficulty mix, theme)
  2. Call LLM to generate French sentences (A1/A2/B1/B1 mix)
  3. Look up words in dictionary
  4. Generate TTS audio
  5. Build Day model and save to data/
  6. Render self-contained HTML
  7. Update streak

Usage:
    python scripts/build.py              # Normal build (today)
    python scripts/build.py --date X     # Build specific date
    python scripts/build.py --force      # Force rebuild
    python scripts/build.py --dry-run    # Show config only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import Day, Passage, Sentence, Word
from core.streak import StreakStore
from core.dict_lookup import Dictionary, segment
from core.tts import generate_audio
from core.html import render_day
from core.llm import generate_sentences, get_fallback_sentences, LEVEL_DESCRIPTIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"


# ── Config Parser ─────────────────────────────────────────────────────────

def parse_difficulty_mix(raw: str) -> dict[str, int]:
    """Parse 'A1:1,A2:2,B1:2' → {'A1': 1, 'A2': 2, 'B1': 2}."""
    mix: dict[str, int] = {}
    if not raw:
        return {"A2": 2, "B1": 2}  # sensible default
    for part in raw.split(","):
        part = part.strip()
        if ":" in part:
            level, count = part.split(":", 1)
            level = level.strip().upper()
            count = int(count.strip())
            if level in LEVEL_DESCRIPTIONS and count > 0:
                mix[level] = count
    return mix if mix else {"A2": 2, "B1": 2}


def get_config() -> dict:
    """Load config.toml (simple parser, no external deps)."""
    config_path = ROOT / "config.toml"
    config: dict[str, dict] = {}
    current_section = None
    _array_buf: str | None = None
    _array_key: str | None = None

    if not config_path.exists():
        return config

    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue

        if _array_buf is not None:
            _array_buf += " " + line
            if "]" in line:
                full = _array_buf.strip()
                arr_str = full[full.index("["): full.rindex("]") + 1]
                items = arr_str[1:-1].split(",")
                config[current_section][_array_key] = [
                    it.strip().strip('"').strip("'") for it in items if it.strip()
                ]
                _array_buf = None
                _array_key = None
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            config.setdefault(current_section, {})
            continue

        if "=" in line and current_section is not None:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if "#" in value and not value.startswith('"'):
                value = value[: value.index("#")].strip()

            if value.startswith("[") and not value.endswith("]"):
                _array_buf = value
                _array_key = key
                continue

            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                value = [it.strip().strip('"').strip("'") for it in items if it.strip()]
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            elif value == "true":
                value = True
            elif value == "false":
                value = False
            else:
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass

            config[current_section][key] = value

    return config


# ── Lessons pack ──────────────────────────────────────────────────────────

def _norm_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def load_lessons_pack() -> dict[str, dict]:
    """dict/lessons.json: 句子原文 → {"notes": {...}, "lessons": [...]}.

    Hand-written grammar courses. The pack is *curated*, so it wins over
    generated content: a sentence that appears in the pack always renders the
    hand-authored course (conjugation tables and all), and only sentences the
    pack does not know about fall back to whatever the model produced.
    """
    path = ROOT / "dict" / "lessons.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("lessons.json 读取失败：%s", exc)
        return {}
    return {_norm_sentence(k): v for k, v in raw.items() if not k.startswith("_")}


def apply_lessons_pack(sentences: list[Sentence]) -> int:
    """Overlay grammar_lessons / grammar_notes from the curated pack."""
    pack = load_lessons_pack()
    if not pack:
        return 0
    filled = 0
    for s in sentences:
        hit = pack.get(_norm_sentence(s.text))
        if not hit:
            continue
        s.grammar_lessons = hit.get("lessons", [])
        notes = dict(s.grammar_notes or {})
        notes.update(hit.get("notes") or {})
        s.grammar_notes = notes
        filled += 1
    return filled


# ── Content Generation ────────────────────────────────────────────────────

def recent_sentence_texts(days: int = 14) -> list[str]:
    """Sentences shown in the last `days` built days — the do-not-repeat list.

    Read straight off data/*.json so it works for both the LLM prompt and the
    fallback corpus, and never depends on a run having happened yesterday.
    """
    files = sorted(
        (p for p in DATA_DIR.glob("20*.json") if p.name != "index.json"),
        key=lambda p: p.stem,
        reverse=True,
    )[:days]
    out: list[str] = []
    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for passage in raw.get("passages") or []:
            for sentence in passage.get("sentences") or []:
                text = (sentence.get("text") or "").strip()
                if text:
                    out.append(text)
    return out


def generate_day_content(config: dict, date_str: str = "") -> tuple[str, str, list[dict]]:
    """Generate today's French sentences via LLM or fallback.

    Returns (title_fr, title_zh, sentences_list_of_dicts)
    """
    content_cfg = config.get("content", {})
    raw_mix = content_cfg.get("difficulty_mix", "A2:2,B1:2")
    difficulty_mix = parse_difficulty_mix(raw_mix)
    theme = content_cfg.get("theme", "")

    # Log the difficulty mix
    parts = [f"{k}:{v}句" for k, v in sorted(difficulty_mix.items())]
    log.info("Difficulty mix: %s", ", ".join(parts))
    if theme:
        log.info("Theme: %s", theme)

    # Sentences from the past two weeks: never show them again. Without this the
    # LLM happily re-emits a favourite sentence and yesterday's page comes back.
    avoid = recent_sentence_texts()
    if avoid:
        log.info("Avoiding %d sentences already used recently", len(avoid))

    # Try LLM first
    result = generate_sentences(difficulty_mix, theme, avoid)
    if result and result.get("sentences"):
        result["sentences"] = _drop_repeats(result["sentences"], avoid)

    if result and result.get("sentences"):
        # Validate and normalize
        sentences = []
        for i, s in enumerate(result["sentences"]):
            sentences.append({
                "id": f"s{i + 1}",
                "difficulty": s.get("difficulty", "A2").upper(),
                "text": s.get("text", "").strip(),
                "translation": s.get("translation", "").strip(),
                "grammar_note": s.get("grammar_note", ""),
                "grammar_notes": s.get("grammar_notes", {}),
                "grammar_lessons": s.get("grammar_lessons", []),
                "words": s.get("words", []),
            })
        return result["title_fr"], result["title_zh"], sentences

    # Fallback
    log.warning("LLM unavailable, using built-in corpus")
    result = get_fallback_sentences(difficulty_mix, avoid=avoid, seed=date_str or None)
    sentences = []
    for i, s in enumerate(result["sentences"]):
        sentences.append({
            "id": f"s{i + 1}",
            "difficulty": s.get("difficulty", "A2"),
            "text": s.get("text", "").strip(),
            "translation": s.get("translation", "").strip(),
            "grammar_note": s.get("grammar_note", ""),
            "grammar_notes": s.get("grammar_notes", {}),
            "grammar_lessons": s.get("grammar_lessons", []),
            "words": s.get("words", []),
        })
    return result["title_fr"], result["title_zh"], sentences


def _drop_repeats(sentences: list[dict], avoid: list[str]) -> list[dict]:
    """Strip sentences the last two weeks already showed (LLM path guard)."""
    seen = {_norm_sentence(t).lower() for t in avoid}
    kept = [s for s in sentences if _norm_sentence(s.get("text", "")).lower() not in seen]
    dropped = len(sentences) - len(kept)
    if dropped:
        log.warning("Dropped %d sentence(s) the model repeated from recent days", dropped)
    return kept


# ── Day Building ──────────────────────────────────────────────────────────

def build_day(date_str: str, config: dict, force: bool = False) -> Day:
    """Build content for a specific date."""
    data_file = DATA_DIR / f"{date_str}.json"

    # Skip if already built (unless force)
    if data_file.exists() and not force:
        log.info("%s already exists, skipping (--force to rebuild)", data_file.name)
        return Day.from_dict(json.loads(data_file.read_text(encoding="utf-8")))

    log.info("Building content for %s", date_str)

    # 1. Generate sentences via LLM
    title_fr, title_zh, sentences_data = generate_day_content(config, date_str)

    if not sentences_data:
        log.error("No sentences generated for %s", date_str)
        return Day(date=date_str, passages=[], mode="rules")

    # 2. Look up words in the dictionary (local only — no network in the build)
    dict_path = ROOT / "dict" / "starter.json"
    dictionary = Dictionary(dict_path)

    processed_sentences = []
    for s_data in sentences_data:
        words_raw = segment(s_data["text"])
        word_objects = []
        for w in words_raw:
            lookup = dictionary.lookup_local(w)
            if lookup:
                word_objects.append(Word(
                    w=w,
                    pos=lookup.get("pos", ""),
                    def_=lookup.get("def", ""),
                    ipa=lookup.get("ipa", ""),
                    example=lookup.get("example", ""),
                ))

        processed_sentences.append(Sentence(
            id=s_data["id"],
            text=s_data["text"],
            translation=s_data["translation"],
            difficulty=s_data.get("difficulty", "A2"),
            grammar_note=s_data.get("grammar_note", ""),
            grammar_notes=s_data.get("grammar_notes", {}),
            grammar_lessons=s_data.get("grammar_lessons", []),
            words=word_objects,
        ))

    # 2b. Top up grammar courses from the curated pack where the model skipped them
    filled = apply_lessons_pack(processed_sentences)
    if filled:
        log.info("Filled grammar lessons from dict/lessons.json for %d sentence(s)", filled)

    # 3. Generate per-sentence TTS audio files
    audio_dir = SITE_DIR / "audio" / date_str
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_rel = f"audio/{date_str}"

    log.info("Generating per-sentence TTS audio (%d sentences)...", len(processed_sentences))
    total_chars = 0
    for s in processed_sentences:
        fname = f"{s.id}.mp3"
        fpath = audio_dir / fname
        if not fpath.exists() or force:
            mp3 = generate_audio(s.text)
            if mp3:
                fpath.write_bytes(mp3)
                total_chars += len(s.text)
        s.audio_file = f"{audio_rel}/{fname}"

    # Slow audio (one combined file for all sentences, slower speed)
    all_text = " ".join(s.text for s in processed_sentences)
    slow_path = audio_dir / "all_slow.mp3"
    if not slow_path.exists() or force:
        slow_mp3 = generate_audio(all_text, rate="-20%")
        if slow_mp3:
            slow_path.write_bytes(slow_mp3)

    # Estimate duration
    word_count = len(all_text.split())
    duration = max(1, round(word_count / 150))

    # 4. Build passage
    passage = Passage(
        id="p1",
        title_fr=title_fr,
        title_zh=title_zh,
        source="AI Generated",
        duration_min=duration,
        audio_dir=audio_rel,
        sentences=processed_sentences,
    )

    mode = "llm" if processed_sentences else "rules"
    return Day(date=date_str, passages=[passage], mode=mode)


# ── Save & Render ─────────────────────────────────────────────────────────

def save_day(day: Day) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_file = DATA_DIR / f"{day.date}.json"
    data_file.write_text(
        json.dumps(day.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved %s", data_file)

    # Update index
    (DATA_DIR / "index.json").write_text(
        json.dumps({"latest": day.date}, ensure_ascii=False),
        encoding="utf-8",
    )


def render_site(day: Day, streak_info: dict) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    data_files = sorted(
        (p for p in DATA_DIR.glob("20*.json") if p.name != "index.json"),
        key=lambda p: p.stem,
        reverse=True,
    )
    archive_dates = [p.stem for p in data_files]

    html = render_day(day, streak_info, archive_dates)

    (SITE_DIR / f"{day.date}.html").write_text(html, encoding="utf-8")
    log.info("Rendered %s.html", day.date)

    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    log.info("Updated index.html")

    # Word-level mp3s for devices without a French TTS voice (Chinese Android
    # ROMs etc.). Quiet: skips itself when edge_tts is not on this interpreter.
    try:
        from gen_audio import refresh as gen_audio_refresh
        gen_audio_refresh(SITE_DIR, quiet=True)
    except Exception as exc:  # audio is an enhancement, never fail the build
        log.warning("gen_audio skipped: %s", exc)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="FrenchDaily build")
    parser.add_argument("--date", default="", help="Build specific date (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Force rebuild")
    parser.add_argument("--dry-run", action="store_true", help="Show config only")
    args = parser.parse_args()

    config = get_config()

    if args.dry_run:
        mix = config.get("content", {}).get("difficulty_mix", "(default)")
        print(f"Difficulty mix: {mix}")
        print(f"Theme: {config.get('content', {}).get('theme', '(any)')}")
        print(f"LLM model: {config.get('content', {}).get('llm_model', 'deepseek-v4-flash')}")
        print(f"Schedule: {config.get('schedule', {}).get('cron', '0 17 * * *')}")
        return 0

    # Determine date
    if args.date:
        date_str = args.date
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Load streak
    streak_store = StreakStore(DATA_DIR / "streak.json")
    streak_info = streak_store.get_streak_info()

    # Build
    day = build_day(date_str, config, force=args.force)

    if not day.passages or not day.passages[0].sentences:
        log.error("Build failed: no content generated")
        return 1

    # Save
    save_day(day)

    # Mark streak (server-side mirror)
    streak_store.mark_done(date_str)

    # Render
    render_site(day, streak_info)

    # Summary
    total_s = day.total_sentences()
    total_w = day.total_words()
    levels = {}
    for p in day.passages:
        for s in p.sentences:
            levels[s.difficulty] = levels.get(s.difficulty, 0) + 1
    level_str = ", ".join(f"{k}:{v}句" for k, v in sorted(levels.items()))

    log.info(
        "Done: %s — %d sentences (%s), %d words with definitions",
        date_str, total_s, level_str, total_w,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
