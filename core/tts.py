"""TTS audio generation using edge-tts."""
from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Default French voice — clear, friendly, good for learning
VOICE = "fr-FR-DeniseNeural"

# Rate adjustments for normal and slow playback
RATE_NORMAL = "+0%"
RATE_SLOW = "-20%"


async def _generate_async(text: str, rate: str = RATE_NORMAL) -> bytes:
    """Generate MP3 audio bytes from text using edge-tts."""
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE, rate=rate)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


def generate_audio(text: str, rate: str = RATE_NORMAL) -> bytes:
    """Generate MP3 audio bytes (sync wrapper)."""
    try:
        return asyncio.run(_generate_async(text, rate))
    except Exception as exc:
        log.error("TTS generation failed: %s", exc)
        return b""


def audio_to_base64(mp3_bytes: bytes) -> str:
    """Convert MP3 bytes to base64 string (without data URI prefix)."""
    return base64.b64encode(mp3_bytes).decode("ascii")


def generate_passage_audio(text: str) -> tuple[str, str]:
    """Generate both normal and slow audio for a passage.
    Returns (normal_b64, slow_b64) — empty strings on failure.
    """
    log.info("Generating normal-speed audio (%d chars)...", len(text))
    normal = generate_audio(text, RATE_NORMAL)
    normal_b64 = audio_to_base64(normal) if normal else ""

    log.info("Generating slow-speed audio (%d chars)...", len(text))
    slow = generate_audio(text, RATE_SLOW)
    slow_b64 = audio_to_base64(slow) if slow else ""

    return normal_b64, slow_b64
