"""French word dictionary lookup with IPA, numbers 1-100, and Wiktionary fallback."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-zA-ZÀ-ſ]+(?:'[a-zA-ZÀ-ſ]+)?")
# French contraction prefixes to strip for dictionary lookup
_CONTRACT_PREFIX_RE = re.compile(r"^[mtdljscnqu]'")

# Inflection suffixes tried only when a token has no entry of its own, longest
# first. Only ever *strips* — this never invents a form, so a wrong guess can
# at worst fall through to the next candidate. Saves the reader from
# "未收录" on clés / légumes / finies / soupes and friends.
_INFLECT_SUFFIXES = ("es", "s", "x", "e")


def _inflection_candidates(word: str) -> list[str]:
    """Plausible base forms for a word that is not in the dictionary itself."""
    out: list[str] = []
    for suf in _INFLECT_SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            out.append(word[: -len(suf)])
    if word.endswith("aux") and len(word) > 4:
        out.append(word[:-3] + "al")  # locaux → local, journaux → journal
    return out


def segment(text: str) -> list[str]:
    """Tokenize French text into words, preserving original forms (apostrophes etc.).

    Returns original tokens like ["Je", "m'appelle", "Marie", "j'ai", "vingt", "ans"].
    Contraction stripping (m'appelle → appelle) happens at lookup time, not here,
    so that the full token can be matched as a single clickable span in the HTML.
    """
    words = _WORD_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        wl = w.lower()
        if wl not in seen:
            seen.add(wl)
            result.append(w)
    return result


class Dictionary:
    # Overlay files applied on top of starter.json, in order. Later files win.
    # auto.json is machine-filled by scripts/gen_dict.py for words the pages use
    # but nobody has written up yet — it always comes last, and it only ever
    # *adds* words (the generator skips anything already defined elsewhere).
    OVERLAYS = ("curated.json", "gloss.json", "auto.json")

    def __init__(self, starter_path: Path):
        self.local: dict[str, dict] = {}
        self._numbers: dict[str, str] = {}
        self._cache: dict[str, dict] = {}
        self._load_starter(starter_path)
        # Hand-curated overlays. `curated.json` tops up the words that appear in
        # the daily sentences (plus example_ipa / example_zh); `gloss.json` holds
        # the vocabulary and grammar terms used *inside the explanations*, so the
        # prose is clickable too.
        for name in self.OVERLAYS:
            self._load_starter(starter_path.with_name(name))

    def _load_starter(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            added = 0
            for key, val in data.items():
                if key.startswith("_"):
                    if key == "_numbers":
                        self._numbers = val
                    continue
                if key not in self.local:
                    added += 1
                self.local[key] = val
            log.info("Loaded %d new words from %s (%d total)",
                     added, path.name, len(self.local))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("%s 读取失败：%s", path.name, exc)

    def lookup_local(self, word: str) -> Optional[dict]:
        """Dictionary-only lookup: never touches the network.

        Used by the renderer so a build is fast and reproducible; unknown words
        simply render as clickable-but-unknown spans.
        """
        wl = word.lower().strip("'")
        entry = self.local.get(wl)
        if entry:
            return entry
        # Try stripping French contraction prefix (m'appelle → appelle)
        root = _CONTRACT_PREFIX_RE.sub("", wl)
        if root != wl:
            entry = self.local.get(root)
            if entry:
                return entry
        # Still nothing: try the bare stem of a plural / feminine form, so a
        # real word never shows as 未收录 just because the page says "clés".
        for cand in _inflection_candidates(root):
            entry = self.local.get(cand)
            if entry:
                return entry
        num_info = self._numbers.get(wl)
        if num_info:
            return {"pos": "num", "def": num_info, "ipa": "", "example": ""}
        return None

    def lookup(self, word: str) -> Optional[dict]:
        local = self.lookup_local(word)
        if local:
            return local
        wl = word.lower().strip("'")
        if wl in self._cache:
            return self._cache[wl]
        result = self._fetch_wiktionary(wl)
        if result:
            self._cache[wl] = result
        return result

    def lookup_batch(self, words: list[str]) -> dict[str, dict]:
        return {w: r for w in words if (r := self.lookup(w))}

    def _fetch_wiktionary(self, word: str) -> Optional[dict]:
        try:
            url = f"https://fr.wiktionary.org/api/rest_v1/page/definition/{word}"
            resp = requests.get(url, headers={"User-Agent": "FrenchDaily/1.0"}, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            for entry in data.get("fr", []):
                pos = entry.get("partOfSpeech", "")
                for defn in entry.get("definitions", []):
                    def_text = re.sub(r"<[^>]+>", "", defn.get("definition", ""))
                    if def_text:
                        return {"pos": pos, "def": def_text[:120], "example": "", "ipa": ""}
        except Exception as exc:
            log.debug("Wiktionary lookup failed for '%s': %s", word, exc)
        return None
