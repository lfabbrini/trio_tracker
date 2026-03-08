# Add Text-to-Speech to Trio Tracker

## Goal
Integrate ElevenLabs TTS into the Trio Tracker game. The feature must be **disabled by default** and toggled on/off by the user at runtime. When enabled, key game events are announced with a natural voice.

---

## Configuration (do not change these values)

- **Voice ID:** `QpDQJR3frbDwOhTIo8nW`
- **Model:** `eleven_turbo_v2_5`
- **API Key env var:** `ELEVENLABS_API_KEY`

---

## Step 1 — Install dependency

Add `elevenlabs` to the project dependencies:

```bash
pip install elevenlabs
```

If a `requirements.txt` exists, append:
```
elevenlabs
```

---

## Step 2 — Create `tts_service.py`

Create a new file `tts_service.py` in the same directory as `main.py`.
This module is the single owner of all TTS logic — nothing else should import elevenlabs directly.

```python
"""
tts_service.py — ElevenLabs TTS integration for Trio Tracker
Default state: DISABLED. Call toggle_tts() or set via env var TTS_ENABLED=true to enable.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── State ──────────────────────────────────────────────────────────────────────
_tts_enabled: bool = os.getenv("TTS_ENABLED", "false").lower() == "true"

VOICE_ID  = "QpDQJR3frbDwOhTIo8nW"
MODEL_ID  = "eleven_turbo_v2_5"

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
        audio_gen = client.text_to_speech.convert(
            text=text,
            voice_id=VOICE_ID,
            model_id=MODEL_ID,
            output_format="mp3_44100_128",
        )
        audio_bytes = b"".join(audio_gen)
        return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return None


# ── Game event helpers ─────────────────────────────────────────────────────────
# These are the narration texts. Adjust wording to match your team's style.

def announce_trio_found(player_name: str) -> Optional[str]:
    return generate_audio_b64(f"{player_name} found a Trio! Amazing move!")

def announce_round_start(round_number: int) -> Optional[str]:
    return generate_audio_b64(f"Round {round_number} begins. Good luck!")

def announce_game_over(winner_name: str) -> Optional[str]:
    return generate_audio_b64(f"{winner_name} wins the game! Well played everyone!")

def announce_card_revealed(player_name: str) -> Optional[str]:
    return generate_audio_b64(f"{player_name} revealed a card.")

def announce_new_game() -> Optional[str]:
    return generate_audio_b64("A new game of Trio is starting. Get ready!")

def announce_player_joined(player_name: str) -> Optional[str]:
    return generate_audio_b64(f"{player_name} joined the game.")
```

---

## Step 3 — Add toggle endpoint to `main.py`

In `main.py`, import the service and add a toggle route.

Add import at the top:
```python
from tts_service import toggle_tts, is_tts_enabled
```

Add this FastAPI route (place it near the other game API routes):
```python
@app.post("/api/tts/toggle")
async def api_toggle_tts():
    new_state = toggle_tts()
    return {"tts_enabled": new_state}

@app.get("/api/tts/status")
async def api_tts_status():
    return {"tts_enabled": is_tts_enabled()}
```

---

## Step 4 — Wire TTS into game events (WebSocket handler)

Find the WebSocket handler in `main.py` (the function decorated with `@app.websocket`).

Import the announcement helpers at the top of `main.py`:
```python
from tts_service import (
    announce_trio_found,
    announce_round_start,
    announce_game_over,
    announce_card_revealed,
    announce_new_game,
    announce_player_joined,
)
```

Inside the WebSocket handler, wherever a game event is broadcast to clients,
attach the TTS audio to the payload. Example pattern:

```python
# Example: when a trio is found
audio_b64 = announce_trio_found(player_name)
await manager.broadcast({
    "type": "trio_found",
    "player": player_name,
    # ... other existing fields ...
    "tts_audio": audio_b64,   # None if TTS disabled — frontend handles gracefully
})

# Example: when a round starts
audio_b64 = announce_round_start(round_number)
await manager.broadcast({
    "type": "round_start",
    "round": round_number,
    "tts_audio": audio_b64,
})

# Example: when game ends
audio_b64 = announce_game_over(winner_name)
await manager.broadcast({
    "type": "game_over",
    "winner": winner_name,
    "tts_audio": audio_b64,
})
```

Apply this pattern to ALL game event broadcasts. The exact event names and
existing fields must be preserved — only `"tts_audio"` is added.

---

## Step 5 — Frontend: play audio on WebSocket events

Find the main JavaScript file or `<script>` block that handles WebSocket messages
(the `ws.onmessage` handler).

Add this TTS playback utility function **once**, near the top of the script block:

```javascript
function playTTSAudio(base64Audio) {
    if (!base64Audio) return;  // TTS disabled or failed — silent
    try {
        const audio = new Audio("data:audio/mp3;base64," + base64Audio);
        audio.play().catch(e => console.warn("TTS playback blocked:", e));
    } catch (e) {
        console.warn("TTS error:", e);
    }
}
```

Then inside the `ws.onmessage` handler, call `playTTSAudio` for each event type:

```javascript
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);

    // ... existing handling logic (keep it all) ...

    // Add TTS playback at the end of each case:
    if (data.type === "trio_found") {
        // ... existing UI updates ...
        playTTSAudio(data.tts_audio);
    }
    if (data.type === "round_start") {
        // ... existing UI updates ...
        playTTSAudio(data.tts_audio);
    }
    if (data.type === "game_over") {
        // ... existing UI updates ...
        playTTSAudio(data.tts_audio);
    }
    // Add playTTSAudio(data.tts_audio) to every event type that carries tts_audio
};
```

---

## Step 6 — Add toggle button to the UI

Find the game UI template (likely a Jinja2 `.html` file).

Add a toggle button in a sensible location (near game controls or header):

```html
<!-- TTS Toggle Button -->
<button
    id="tts-toggle-btn"
    onclick="toggleTTS()"
    title="Toggle voice announcements"
    style="opacity: 0.5;">
    🔇 Voice Off
</button>
```

Add this script (in the template's `<script>` block or JS file):

```javascript
// ── TTS Toggle ────────────────────────────────────────────────────────────────
async function toggleTTS() {
    const res  = await fetch("/api/tts/toggle", { method: "POST" });
    const data = await res.json();
    updateTTSButton(data.tts_enabled);
}

function updateTTSButton(enabled) {
    const btn = document.getElementById("tts-toggle-btn");
    if (!btn) return;
    btn.textContent = enabled ? "🔊 Voice On" : "🔇 Voice Off";
    btn.style.opacity = enabled ? "1" : "0.5";
}

// Sync button state with server on page load
fetch("/api/tts/status")
    .then(r => r.json())
    .then(d => updateTTSButton(d.tts_enabled));
```

---

## Step 7 — Environment variable

Ensure `ELEVENLABS_API_KEY` is available at runtime. If the project uses a `.env` file,
check whether `python-dotenv` is already used. If it is, simply add:

```
ELEVENLABS_API_KEY=your_key_here
```

If `python-dotenv` is NOT already used, add it:
```bash
pip install python-dotenv
```
And add at the very top of `main.py` (before other imports):
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## Checklist before finishing

- [ ] `tts_service.py` created with all functions
- [ ] `/api/tts/toggle` and `/api/tts/status` endpoints added to `main.py`
- [ ] TTS announcement helpers imported in `main.py`
- [ ] `tts_audio` field added to ALL game event broadcasts
- [ ] `playTTSAudio()` called in `ws.onmessage` for every event type
- [ ] Toggle button added to the HTML template
- [ ] `toggleTTS()` and `updateTTSButton()` JS functions added
- [ ] `ELEVENLABS_API_KEY` present in `.env`
- [ ] `elevenlabs` added to `requirements.txt`
- [ ] Server restart tested — TTS disabled by default, toggle works

---

## Notes for Claude Code

- Do NOT remove or rewrite any existing game logic — only add TTS on top
- The `tts_audio` field in WebSocket messages is always optional — `None` is valid and the frontend handles it silently
- All existing WebSocket message fields must be preserved exactly
- If the project uses a connection manager class (e.g. `ConnectionManager`), use its existing `broadcast` method
- If game events are handled in separate functions rather than inline, add the TTS call at the point where the broadcast happens
- The toggle is **server-side state** — all connected players share the same TTS on/off state
