"""Word-level audio via edge_tts — pre-synthesized on the server.

Why: speechSynthesis needs a French voice on the DEVICE. Windows without a
French voice pack and Chinese Android ROMs (Honor/Huawei: no Google TTS) only
have zh/en voices, so tapping a word read it with an English accent. We
synthesize every speakable string once here, ship the mp3s with the site, and
the page plays the mp3 first — on-device TTS is only a fallback.

    python scripts/gen_audio.py           # generate missing files, refresh manifest
    python scripts/gen_audio.py --site X  # different output dir

Manifest: site/audio/w/index.json maps text → mp3 path. The page fetches it
lazily and looks strings up by exact text.
"""
from __future__ import annotations

import asyncio
import hashlib
import html as html_mod
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VOICE = "fr-FR-DeniseNeural"
RATE = "-10%"  # a touch slower, this is a learning app
OUT_REL = "audio/w"


def _hash(text: str) -> str:
    """Stable filename: change VOICE/RATE and every hash changes (re-gen)."""
    return hashlib.sha1(f"{VOICE}|{RATE}|{text}".encode("utf-8")).hexdigest()[:24]


def collect_texts(site_dir: Path) -> set[str]:
    """Every string any speaker button may ever pronounce."""
    texts: set[str] = set()

    # 1. Everything already rendered into pages (data-say / data-speak attrs).
    pat = re.compile(r'data-(?:say|speak)="([^"]+)"')
    for page in site_dir.glob("*.html"):
        for m in pat.finditer(page.read_text(encoding="utf-8")):
            texts.add(html_mod.unescape(m.group(1)))

    # 2. Dictionary headwords + example sentences (JS renders these at
    #    runtime, so they are NOT in the scraped HTML).
    for name in ("starter", "curated", "gloss"):
        p = ROOT / "dict" / f"{name}.json"
        if not p.exists():
            continue
        for k, v in json.loads(p.read_text(encoding="utf-8")).items():
            if k.startswith("_"):
                continue
            texts.add(k)
            ex = v.get("example")
            if ex:
                texts.add(ex)

    # 3. Conjugation: the infinitive itself + every "person form" row line
    #    (the conj panel renders these client-side from the embedded book).
    from core import conjug

    for inf, v in conjug.BOOK.items():
        texts.add(inf)
        for block in v["tables"].values():
            for row in block:
                texts.add(f"{row[0]} {row[1]}")

    # 4. Number words: NUMBER_TABLE values look like "vingt /vɛ̃t/" — the
    #    spoken part is everything before the transcription.
    from core.html import NUMBER_TABLE

    for val in NUMBER_TABLE.values():
        i = val.find(" /")
        texts.add(val[:i] if i > 0 else val)

    return {t.strip() for t in texts if t.strip()}


async def _generate(texts: set[str], out_dir: Path) -> int:
    import edge_tts

    sem = asyncio.Semaphore(4)
    done = 0

    async def one(text: str, path: Path) -> None:
        nonlocal done
        async with sem:
            for attempt in (1, 2, 3):
                try:
                    com = edge_tts.Communicate(text, VOICE, rate=RATE)
                    await com.save(str(path))
                    done += 1
                    return
                except Exception:
                    if attempt == 3:
                        print(f"  FAILED: {text[:48]!r}", flush=True)
                    else:
                        await asyncio.sleep(1.5)

    tasks = []
    for t in sorted(texts):
        path = out_dir / f"{_hash(t)}.mp3"
        if path.exists() and path.stat().st_size > 0:
            continue
        tasks.append(one(t, path))
    if tasks:
        print(f"gen_audio: {len(tasks)} mp3 to synthesize "
              f"({len(texts)} known strings)...", flush=True)
        await asyncio.gather(*tasks)
    return done


def refresh(site_dir: Path | None = None, quiet: bool = False) -> int:
    """Generate missing mp3s + write the manifest. Returns count generated."""
    site_dir = Path(site_dir) if site_dir else ROOT / "site"
    out_dir = site_dir / OUT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        if not quiet:
            print("gen_audio: edge_tts not installed on this interpreter, skip")
        return 0

    texts = collect_texts(site_dir)
    n = asyncio.run(_generate(texts, out_dir))

    manifest = {t: f"{OUT_REL}/{_hash(t)}.mp3" for t in sorted(texts)}
    ipath = out_dir / "index.json"
    new = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    if not ipath.exists() or ipath.read_text(encoding="utf-8") != new:
        ipath.write_text(new, encoding="utf-8")

    if not quiet:
        print(f"gen_audio: +{n} mp3, manifest {len(manifest)} entries")
    return n


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Generate French word audio")
    ap.add_argument("--site", default="", help="Site dir (default: site/)")
    args = ap.parse_args()
    refresh(Path(args.site) if args.site else None)
