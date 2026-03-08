"""
tts_service.py — ElevenLabs TTS integration for Trio Tracker
Default state: DISABLED. Call toggle_tts() or set via env var TTS_ENABLED=true to enable.
"""

import os
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── State ──────────────────────────────────────────────────────────────────────
_tts_enabled: bool = os.getenv("TTS_ENABLED", "true").lower() == "true"

VOICE_ID = "QpDQJR3frbDwOhTIo8nW"
MODEL_ID = "eleven_turbo_v2_5"

# ── Lazy client — only instantiated when TTS is first used ────────────────────
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from elevenlabs.client import ElevenLabs
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            logger.warning("TTS: ELEVENLABS_API_KEY not set — TTS will be disabled")
            return None
        _client = ElevenLabs(api_key=api_key)
        return _client
    except ImportError:
        logger.warning("TTS: elevenlabs package not installed — run: pip install elevenlabs")
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def is_tts_enabled() -> bool:
    return _tts_enabled


def toggle_tts() -> bool:
    """Toggle TTS on/off. Returns the new state."""
    global _tts_enabled
    _tts_enabled = not _tts_enabled
    logger.info(f"TTS {'enabled' if _tts_enabled else 'disabled'}")
    return _tts_enabled


def set_tts(enabled: bool) -> None:
    global _tts_enabled
    _tts_enabled = enabled


def generate_audio_b64(text: str) -> Optional[str]:
    """
    Generate TTS audio and return as base64-encoded MP3 string,
    ready to embed in a data URI for the browser.
    Returns None if TTS is disabled, API key is missing, or generation fails.
    """
    if not _tts_enabled:
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        import base64
        print(f"TTS: generating audio for: {text[:60]}")
        audio_gen = client.text_to_speech.convert(
            text=text,
            voice_id=VOICE_ID,
            model_id=MODEL_ID,
            output_format="mp3_44100_128",
        )
        audio_bytes = b"".join(audio_gen)
        print(f"TTS: generated {len(audio_bytes)} bytes")
        return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        print(f"TTS ERROR: {e}")
        logger.error(f"TTS generation failed: {e}")
        return None


async def async_generate_audio_b64(text: str) -> Optional[str]:
    """Async wrapper — runs blocking generate_audio_b64 in a thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, generate_audio_b64, text)


# ── Game event helpers ─────────────────────────────────────────────────────────

def announce_trio_found(player_name: str) -> Optional[str]:
    return generate_audio_b64(f"{player_name} found a Trio! Amazing move!")


def announce_game_over(winner_name: str) -> Optional[str]:
    return generate_audio_b64(f"{winner_name} wins the game! Well played everyone!")


def announce_card_revealed(player_name: str) -> Optional[str]:
    return generate_audio_b64(f"{player_name} revealed a card.")


def announce_new_game() -> Optional[str]:
    return generate_audio_b64("A new game of Trio is starting. Get ready!")


def announce_player_joined(player_name: str) -> Optional[str]:
    return generate_audio_b64(f"{player_name} joined the game.")


def announce_match_winner(winner_name: str) -> Optional[str]:
    return generate_audio_b64(f"{winner_name} wins this round! Great game!")


# ── Async game event helpers ───────────────────────────────────────────────────

async def async_announce_trio_found(player_name: str) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, announce_trio_found, player_name)


async def async_announce_game_over(winner_name: str) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, announce_game_over, winner_name)


async def async_announce_card_revealed(player_name: str) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, announce_card_revealed, player_name)


async def async_announce_new_game() -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, announce_new_game)


async def async_announce_player_joined(player_name: str) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, announce_player_joined, player_name)


async def async_announce_match_winner(winner_name: str) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, announce_match_winner, winner_name)
