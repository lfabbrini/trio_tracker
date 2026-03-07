"""
AI Commentator for Trio Tracker.

Generates sarcastic Italian sports commentary via Gemini (cloud) or Ollama (local).
All calls are fire-and-forget safe — failures return empty string, never break the app.
"""

import httpx
import os
import logging

logger = logging.getLogger(__name__)

COMMENTATOR_MODE = os.getenv("COMMENTATOR_MODE", "cloud")  # "cloud" or "local"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")

SYSTEM_PROMPT = """You are a sarcastic Italian sports commentator for a card game called Trio.
Rules:
- Keep it to 1-2 sentences MAX
- Be witty, sarcastic, and slightly roast the players
- Reference the specific game events or stats you're given
- Use occasional Italian exclamations (Mamma mia!, Madonna!, Che disastro!, Incredibile!)
- Never be mean-spirited or offensive, keep it fun and playful
- If commenting on stats, focus on rivalries, streaks, and dramatic narratives
- You are watching this unfold live, react with energy"""


async def get_commentary(context: str) -> str:
    """Get commentary from configured provider. Returns empty string on failure."""
    if COMMENTATOR_MODE == "local":
        return await _call_ollama(context)
    return await _call_gemini(context)


async def _call_gemini(context: str) -> str:
    """Call Gemini API for commentary."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set, commentator disabled")
        return ""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [{"text": f"{SYSTEM_PROMPT}\n\nHere is what just happened:\n{context}"}]
        }],
        "generationConfig": {
            "maxOutputTokens": 100,
            "temperature": 0.9
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Commentator (Gemini) error: {e}")
        return ""


async def _call_ollama(context: str) -> str:
    """Call local Ollama instance for commentary."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Here is what just happened:\n{context}"}
                    ],
                    "stream": False
                },
                timeout=15.0
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Commentator (Ollama) error: {e}")
        return ""


async def comment_on_stats(db_stats: dict) -> str:
    """Generate commentary for the main page based on leaderboard stats."""
    context = _build_stats_context(db_stats)
    return await get_commentary(context)


async def comment_on_game_event(event_type: str, details: dict) -> str:
    """Generate commentary for a live game event."""
    context = _build_game_context(event_type, details)
    return await get_commentary(context)


def _build_stats_context(stats: dict) -> str:
    """Build a context string from leaderboard data."""
    players = stats.get("players", [])
    if not players:
        return "The leaderboard is empty — nobody has played yet!"

    lines = []
    for i, player in enumerate(players):
        rank = i + 1
        streak = player.get("streak", 0)
        streak_str = f", current streak: {streak}" if streak >= 2 else ""
        lines.append(
            f"#{rank} {player['name']}: {player['wins']} wins, "
            f"{player['win_rate']}% win rate{streak_str}"
        )
    return "Current leaderboard:\n" + "\n".join(lines)


def _build_game_context(event_type: str, details: dict) -> str:
    """Build a context string from a game event."""
    templates = {
        "game_start": "A new game of Trio is starting! Players: {players}",
        "trio_claimed": "{player} just claimed a Trio with cards: {cards}!",
        "trio_failed": "{player} tried to claim a Trio but FAILED! The cards were: {cards}",
        "game_won": "{player} won the game! Final scores: {scores}",
        "win_streak": "{player} is now on a {count}-game win streak!",
    }
    template = templates.get(event_type, "Something happened: {event_type}")
    try:
        return template.format(**details, event_type=event_type)
    except KeyError:
        return f"Game event: {event_type} — {details}"
