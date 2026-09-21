"""Streak tracking for daily check-ins.

Analogous to dailybrief's seen.py — tracks which dates the user has
completed a reading session.  Supports both the JSON on disk (source of
truth) and an in-memory cache.

The on-disk format (data/streak.json):
{
    "records": {
        "2026-09-20": {"done": true},
        "2026-09-21": {"done": true}
    },
    "current_streak": 4,
    "longest_streak": 7,
    "total_days": 15
}
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


class StreakStore:
    """Persistent streak record with computed counters."""

    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, dict] = {}
        self.current_streak: int = 0
        self.longest_streak: int = 0
        self.total_days: int = 0
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.records = data.get("records", {})
                self.current_streak = data.get("current_streak", 0)
                self.longest_streak = data.get("longest_streak", 0)
                self.total_days = data.get("total_days", 0)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("streak.json 读取失败，按空档案处理：%s", exc)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "records": self.records,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "total_days": self.total_days,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── streak logic ─────────────────────────────────────────────────────

    def mark_done(self, day_str: str) -> None:
        """Mark a date as completed and update streak counters."""
        if self.records.get(day_str, {}).get("done"):
            return  # already marked

        self.records[day_str] = {"done": True}
        self.total_days += 1
        self._recalc_streak()
        self.save()

    def _recalc_streak(self) -> None:
        """Recalculate current_streak from records."""
        today = date.today()
        streak = 0
        d = today

        # Walk backwards day by day
        while True:
            ds = d.isoformat()
            if self.records.get(ds, {}).get("done"):
                streak += 1
                d -= timedelta(days=1)
            else:
                # If it's today and not done yet, that's fine — skip to yesterday
                if d == today:
                    d -= timedelta(days=1)
                    continue
                break

        self.current_streak = streak
        if streak > self.longest_streak:
            self.longest_streak = streak

    def is_done(self, day_str: str) -> bool:
        return self.records.get(day_str, {}).get("done", False)

    def get_streak_info(self) -> dict:
        """Return current streak info for embedding in HTML."""
        return {
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "total_days": self.total_days,
        }
