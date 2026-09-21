"""Content fetchers for FrenchDaily.

Currently implements RSS-based fetching from French learning sources.
Falls back to built-in corpus when no sources are available.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Default RSS sources for French learning content
DEFAULT_SOURCES = [
    # RFI Savoirs - Journal en français facile (simplified daily news)
    "http://savoirs.rfi.fr/fr/apprendre-enseigner/langue-francais/journal-en-francais-facile/rss",
    # RFI Apprendre le français
    "http://savoirs.rfi.fr/fr/apprendre-enseigner/langue-francais/rss",
]


class FeedItem:
    """A single item from an RSS feed."""
    title: str
    link: str
    summary: str
    source: str
    published: Optional[datetime]

    def __init__(self, title: str, link: str, summary: str, source: str,
                 published: Optional[datetime] = None):
        self.title = title
        self.link = link
        self.summary = summary
        self.source = source
        self.published = published


def fetch_rss(url: str, timeout: int = 30) -> list[FeedItem]:
    """Fetch and parse an RSS feed, returning FeedItems."""
    items = []
    try:
        log.info("Fetching RSS: %s", url)
        feed = feedparser.parse(
            requests.get(url, timeout=timeout, headers={
                "User-Agent": "FrenchDaily/1.0 (language learning)"
            }).content
        )
        source_name = feed.feed.get("title", url)

        for entry in feed.entries[:15]:  # Limit to recent 15
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            # Strip HTML from summary
            summary = re.sub(r"<[^>]+>", "", summary)
            summary = summary.strip()

            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            if title and summary:
                items.append(FeedItem(
                    title=title,
                    link=link,
                    summary=summary,
                    source=source_name,
                    published=published,
                ))
    except Exception as exc:
        log.warning("RSS fetch failed for %s: %s", url, exc)

    return items


def fetch_all_sources(sources: list[str], timeout: int = 30) -> list[FeedItem]:
    """Fetch from all sources and deduplicate by title."""
    all_items: list[FeedItem] = []
    seen_titles: set[str] = set()

    for url in sources:
        items = fetch_rss(url, timeout)
        for item in items:
            # Normalize title for dedup
            norm = re.sub(r"\s+", " ", item.title.lower().strip())
            if norm not in seen_titles:
                seen_titles.add(norm)
                all_items.append(item)

    # Sort by published date (newest first)
    all_items.sort(key=lambda x: x.published or datetime.min, reverse=True)
    return all_items


# ── Built-in Corpus (fallback) ─────────────────────────────────────────

BUILTIN_CORPUS = [
    {
        "title_fr": "Le charme de Paris en automne",
        "title_zh": "巴黎秋天的魅力",
        "text": (
            "Les rues de Paris se parent de leurs habits d'été. "
            "La ville se revêt d'une palette de couleurs dorées et rouges. "
            "Les feuilles des platanes dansent au vent léger. "
            "Les Parisiens reprennent leurs manteaux légers et leurs écharpes. "
            "Les terrasses des cafés restent encore pleines. "
            "On respire un air frais qui sent le bois et la terre humide. "
            "C'est la saison idéale pour se promener le long de la Seine. "
            "Chaque coin de rue semble sorti d'un tableau impressionniste."
        ),
        "source": "FrenchDaily Corpus",
    },
    {
        "title_fr": "Un matin au marché",
        "title_zh": "市场里的一个早晨",
        "text": (
            "Le marché s'éveille avec les premiers rayons du soleil. "
            "Les marchands installent leurs étals avec soin. "
            "Les tomates brillent de rouge éclatant. "
            "Les fromages dégagent des parfums variés. "
            "Une boulangère propose du pain frais encore chaud. "
            "Les clients flânent entre les stands avec plaisir. "
            "Les conversations mélangent le français et les accents du monde. "
            "C'est un spectacle vivant et coloré qui anime le quartier."
        ),
        "source": "FrenchDaily Corpus",
    },
    {
        "title_fr": "L'art de vivre à la française",
        "title_zh": "法式生活艺术",
        "text": (
            "Les Français attachent une grande importance au plaisir de la table. "
            "Un repas n'est jamais seulement une question de nourriture. "
            "C'est un moment de partage et de conversation. "
            "Le petit déjeuner reste simple : café et tartine beurrée. "
            "Le déjeuner peut durer plus d'une heure. "
            "Le dîner est souvent le moment le plus important de la journée. "
            "On accompagne chaque repas d'un bon pain et d'un verre de vin. "
            "Cette philosophie fait le bonheur quotidien de millions de personnes."
        ),
        "source": "FrenchDaily Corpus",
    },
    {
        "title_fr": "Voyage à travers les champs de Provence",
        "title_zh": "穿越普罗旺斯的花田",
        "text": (
            "La Provence déploie ses paysages enchanteurs au printemps. "
            "Les champs de lavande s'étendent à perte de vue. "
            "Les villages perchés dominent la vallée avec élégance. "
            "L'air est embaumé par le parfum des herbes de Provence. "
            "Les oliviers centenaires racontent l'histoire de la région. "
            "Les marchés locaux regorgent de produits authentiques. "
            "Le soleil méditerranéen éclaire chaque instant de sa lumière dorée. "
            "Chaque visiteur repart avec des souvenirs inoubliables au cœur."
        ),
        "source": "FrenchDaily Corpus",
    },
    {
        "title_fr": "La magie des bibliothèques parisiennes",
        "title_zh": "巴黎图书馆的魔力",
        "text": (
            "Paris possède des bibliothèques aux histoires fascinantes. "
            "La Bibliothèque nationale de France conserve des trésors anciens. "
            "Ses escaliers de marbre et ses lustres imposants impressionnent. "
            "Shakespeare and Company attire les amoureux des lettres du monde entier. "
            "Chaque rayonnage contient des milliers d'histoires à découvrir. "
            "Le silence y est respecté comme un art de vivre. "
            "On y croise des étudiants, des écrivains et des rêveurs solitaires. "
            "Ces lieux gardent vivante la flamme de la culture française."
        ),
        "source": "FrenchDaily Corpus",
    },
]


def get_builtin_item(index: int = 0) -> FeedItem:
    """Get a built-in corpus item by index (rounds-robin)."""
    item = BUILTIN_CORPUS[index % len(BUILTIN_CORPUS)]
    return FeedItem(
        title=item["title_fr"],
        link="",
        summary=item["text"],
        source=item["source"],
        published=datetime.now(timezone.utc),
    )


def select_best_content(items: list[FeedItem],
                         min_words: int = 150,
                         max_words: int = 400) -> list[FeedItem]:
    """Select the best items for French learning.

    Filters by word count (A2-B1 range) and prefers sources that are
    designed for learners.
    """
    learner_sources = {"rfisavoirs", "savoirs.rfi.fr", "frenchdaily corpus"}
    selected: list[FeedItem] = []

    # Score each item
    scored = []
    for item in items:
        text = item.summary
        word_count = len(text.split())
        if word_count < min_words or word_count > max_words:
            continue

        score = word_count  # Prefer closer to max_words
        src_lower = item.source.lower()
        if any(ls in src_lower for ls in learner_sources):
            score += 1000  # Boost learner sources

        scored.append((score, item))

    scored.sort(key=lambda x: -x[0])

    # Return top items (up to 2)
    return [item for _, item in scored[:2]]
