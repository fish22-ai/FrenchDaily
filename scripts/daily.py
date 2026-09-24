"""Daily driver for FrenchDaily — the thing Task Scheduler actually runs.

Why this exists instead of daily.bat doing the work:
  * it is launched by ``pythonw.exe``, which has no console subsystem at all,
    so the 17:00 run can never flash a window on screen;
  * batch files meant CRLF/codepage/quoting hazards — the old one shipped with
    LF line endings, cmd.exe lost track of its ``goto``, and the self re-exec
    became an infinite loop that spawned a few hundred CLI processes.

What it does, in order:
  1. a lock file so two runs can never overlap (stale locks are reclaimed);
  2. skip if today's content was already produced;
  3. ``scripts/build.py`` (today only — missed days are never backfilled);
  4. commit + push ``data`` and ``site`` to ``origin/main``;
  5. remember the date, drop the lock.

Every child process is started with CREATE_NO_WINDOW: a windowless process
spawning a console app (git.exe) would otherwise create a console window.
Run it by hand with ``python scripts\\daily.py``; ``daily.bat`` does just that.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
LOG = LOGS / "cron.log"
LOCK = LOGS / ".running"
STAMP = LOGS / ".last_success"

STALE_LOCK_SECONDS = 12 * 3600
CREATE_NO_WINDOW = 0x08000000

GIT_CANDIDATES = (
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
)


def say(message: str) -> None:
    """Append one timestamped line to logs/cron.log (and echo to the console)."""
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass  # pythonw has no stdout


def say_block(title: str, text: str) -> None:
    if not text or not text.strip():
        return
    say(title)
    for raw in text.strip().splitlines():
        line = raw.rstrip()
        if line:
            try:
                with LOG.open("a", encoding="utf-8") as fh:
                    fh.write("    " + line + "\n")
            except OSError:
                pass


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"  # never hang on a credential prompt
    return env


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )


def find_git() -> str | None:
    found = shutil.which("git")
    if found:
        return found
    for candidate in GIT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def target_date() -> str:
    """The day build.py will write — it works in UTC, so we do too."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def acquire_lock() -> bool:
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        if age < STALE_LOCK_SECONDS:
            say(f"another run started {age / 60:.0f} min ago, skip")
            return False
        say("reclaiming a stale run lock")
        try:
            LOCK.unlink()
        except OSError:
            pass
    LOCKS = LOGS
    LOCKS.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(f"{os.getpid()} {dt.datetime.now():%Y-%m-%d %H:%M:%S}", encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        LOCK.unlink()
    except OSError:
        pass


def publish(today: str, git: str | None) -> None:
    """Commit data/ + site/ and push. A failed push is not fatal — the next run
    pushes it along with that day's content."""
    if not git:
        say("git not found, skipping publish")
        return

    run([git, "add", "data", "site", "dict"])
    diff = run([git, "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        say("nothing to commit")
        return

    commit = run([git, "commit", "-m", f"frenchdaily: {today}"])
    say_block("git commit:", commit.stdout + commit.stderr)
    if commit.returncode != 0:
        say("git commit failed")
        return

    push = run([git, "push", "origin", "main"])
    if push.returncode != 0:
        say_block("git push failed:", push.stdout + push.stderr)
        say("git push FAILED, commit kept locally, will retry next run")
    else:
        say("pushed data/ and site/ to origin/main")


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    today = target_date()

    if STAMP.exists() and STAMP.read_text(encoding="utf-8").strip() == today:
        say(f"already built for {today}, skip")
        return 0

    if not acquire_lock():
        return 0

    try:
        say(f"===== FrenchDaily start (target {today}) =====")

        build = run([sys.executable, str(ROOT / "scripts" / "build.py")])
        say_block("build.py:", build.stdout + build.stderr)
        if build.returncode != 0:
            say(f"build.py failed with code {build.returncode}")
            return 1

        # Dictionary top-up, then one re-render so the new entries show today.
        # Lookup resolves at render time, so filling dict/auto.json is enough to
        # make every word tappable-to-defined — no content regeneration involved.
        # Best effort: a failure here leaves the dictionary as it was, and the
        # day still publishes.
        topup = run([sys.executable, str(ROOT / "scripts" / "gen_dict.py")])
        say_block("gen_dict.py:", topup.stdout + topup.stderr)
        if topup.returncode == 0:
            rerender = run([sys.executable, str(ROOT / "scripts" / "render.py")])
            say_block("render.py (after dict top-up):", rerender.stdout + rerender.stderr)
        else:
            say("gen_dict.py failed — dictionary left as is")

        publish(today, find_git())

        STAMP.write_text(today, encoding="utf-8")
        say(f"===== FrenchDaily done ({today}) =====")
        return 0
    except Exception as exc:  # never die silently inside Task Scheduler
        say(f"unexpected error: {exc!r}")
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
