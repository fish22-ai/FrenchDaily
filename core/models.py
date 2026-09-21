"""Core data models for FrenchDaily."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Word:
    """A single French word with its lookup data."""
    w: str              # The word text (lowercase)
    pos: str            # Part of speech: nm/nf/v/interj/adj/adv/np
    def_: str           # Chinese definition
    ipa: str = ""       # IPA pronunciation
    example: str = ""   # Example sentence

    def to_dict(self) -> dict:
        return {"w": self.w, "pos": self.pos, "def": self.def_,
                "ipa": self.ipa, "example": self.example}

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        """Inverse of to_dict(). Accepts both "def" (on disk) and "def_"
        (attribute name) so old and new data files both round-trip."""
        return cls(
            w=d.get("w", ""),
            pos=d.get("pos", ""),
            def_=d.get("def_", d.get("def", "")),
            ipa=d.get("ipa", ""),
            example=d.get("example", ""),
        )


@dataclass
class Sentence:
    """A sentence from a French passage with audio."""
    id: str
    text: str                          # French text (with liaison marks)
    translation: str                   # Chinese translation
    difficulty: str = "A2"             # A1 | A2 | B1 | B2
    grammar_note: str = ""             # Chinese grammar explanation (overall)
    grammar_notes: dict[str, str] = field(default_factory=dict)  # word → per-word grammar
    # Teaching cards shown in the 语法解析 section: [{"t": 标题, "b": 正文}, ...]
    grammar_lessons: list[dict] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    audio_file: str = ""               # filename of the per-sentence audio

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "translation": self.translation,
            "difficulty": self.difficulty,
            "grammar_note": self.grammar_note,
            "grammar_notes": self.grammar_notes,
            "grammar_lessons": self.grammar_lessons,
            "words": [w.to_dict() for w in self.words],
            "audio_file": self.audio_file,
        }


@dataclass
class Passage:
    """A French reading passage with per-sentence audio."""
    id: str
    title_fr: str
    title_zh: str
    source: str = ""
    source_url: str = ""
    duration_min: int = 0
    audio_dir: str = ""           # relative path to audio files directory
    sentences: list[Sentence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title_fr": self.title_fr,
            "title_zh": self.title_zh,
            "source": self.source,
            "source_url": self.source_url,
            "duration_min": self.duration_min,
            "audio_dir": self.audio_dir,
            "sentences": [s.to_dict() for s in self.sentences],
        }


@dataclass
class Day:
    """One day's worth of French learning content."""
    date: str                    # YYYY-MM-DD
    passages: list[Passage] = field(default_factory=list)
    mode: str = "llm"            # llm | rules
    theme: str = "voyage"        # passage theme tag

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "mode": self.mode,
            "theme": self.theme,
            "passages": [p.to_dict() for p in self.passages],
        }

    def total_words(self) -> int:
        return sum(
            len(s.words)
            for p in self.passages
            for s in p.sentences
        )

    def total_sentences(self) -> int:
        return sum(len(p.sentences) for p in self.passages)

    @classmethod
    def from_dict(cls, data: dict) -> Day:
        passages = []
        for p in data.get("passages", []):
            sentences = []
            for s in p.get("sentences", []):
                words = [Word.from_dict(w) for w in s.get("words", [])]
                sentences.append(Sentence(
                    id=s["id"],
                    text=s["text"],
                    translation=s.get("translation", ""),
                    difficulty=s.get("difficulty", "A2"),
                    grammar_note=s.get("grammar_note", ""),
                    grammar_notes=s.get("grammar_notes", {}),
                    grammar_lessons=s.get("grammar_lessons", []),
                    words=words,
                    audio_file=s.get("audio_file", ""),
                ))
            passages.append(Passage(
                id=p["id"],
                title_fr=p["title_fr"],
                title_zh=p.get("title_zh", ""),
                source=p.get("source", ""),
                source_url=p.get("source_url", ""),
                duration_min=p.get("duration_min", 0),
                audio_dir=p.get("audio_dir", ""),
                sentences=sentences,
            ))
        return cls(
            date=data["date"],
            passages=passages,
            mode=data.get("mode", "llm"),
            theme=data.get("theme", "voyage"),
        )
