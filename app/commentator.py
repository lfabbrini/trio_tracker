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

SYSTEM_PROMPT = """Sei un commentatore sportivo italiano sarcastico per un gioco di carte chiamato Trio.
Regole:
- Rispondi SEMPRE e SOLO in italiano, senza eccezioni
- Massimo 1-2 frasi
- Sii arguto, sarcastico e prendi bonariamente in giro i giocatori
- Fai riferimento agli eventi specifici o alle statistiche che ti vengono fornite
- Usa esclamazioni italiane tipiche (Mamma mia!, Madonna!, Che disastro!, Incredibile!, Porco cane!)
- Non essere mai offensivo o meschino, mantieni un tono giocoso e divertente
- Se commenti le statistiche, concentrati su rivalità, serie di vittorie e narrazioni drammatiche
- Stai seguendo la partita in diretta, reagisci con energia"""


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
        return "La classifica è vuota — nessuno ha ancora giocato!"

    lines = []
    for i, player in enumerate(players):
        rank = i + 1
        streak = player.get("streak", 0)
        streak_str = f", serie attuale: {streak}" if streak >= 2 else ""
        lines.append(
            f"#{rank} {player['name']}: {player['wins']} vittorie, "
            f"{player['win_rate']}% percentuale vittorie{streak_str}"
        )
    return "Classifica attuale:\n" + "\n".join(lines)


def _build_game_context(event_type: str, details: dict) -> str:
    """Build a context string from a game event."""
    templates = {
        "game_start": "Una nuova partita di Trio sta iniziando! Giocatori: {players}",
        "trio_claimed": "{player} ha appena completato un Trio con le carte: {cards}!",
        "trio_failed": "{player} ha tentato di completare un Trio ma ha FALLITO! Le carte erano: {cards}",
        "game_won": "{player} ha vinto la partita! Punteggi finali: {scores}",
        "win_streak": "{player} è ora in una serie di {count} vittorie consecutive!",
    }
    template = templates.get(event_type, "È successo qualcosa: {event_type}")
    try:
        return template.format(**details, event_type=event_type)
    except KeyError:
        return f"Evento di gioco: {event_type} — {details}"
