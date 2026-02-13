from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List
from datetime import datetime, timezone
import os

from . import database as db

app = FastAPI(title="Trio Tracker", description="Track your Trio card game wins!")

# Setup templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def relative_time(dt_str: str) -> str:
    """Convert datetime string to relative time."""
    if isinstance(dt_str, str):
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    else:
        dt = dt_str
    
    # Make dt timezone-aware if it isn't
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    diff = now - dt
    
    seconds = diff.total_seconds()
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        mins = int(seconds / 60)
        return f"{mins} min{'s' if mins != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"


# Add custom filter to templates
templates.env.filters['relative_time'] = relative_time


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    db.init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "players": db.get_all_players(),
        "leaderboard": db.get_leaderboard(),
        "weekly_leaderboard": db.get_weekly_leaderboard(),
        "recent_matches": db.get_recent_matches(),
        "podium_days": db.get_podium_days(),
    })


# === HTMX Partials ===

@app.get("/partials/leaderboard", response_class=HTMLResponse)
async def leaderboard_partial(request: Request):
    """Leaderboard fragment for HTMX."""
    return templates.TemplateResponse("partials/leaderboard.html", {
        "request": request,
        "leaderboard": db.get_leaderboard(),
    })


@app.get("/partials/most-active", response_class=HTMLResponse)
async def weekly_leaderboard_partial(request: Request):
    """Weekly leaderboard fragment for HTMX."""
    return templates.TemplateResponse("partials/weekly_leaderboard.html", {
        "request": request,
        "weekly_leaderboard": db.get_weekly_leaderboard(),
    })


@app.get("/partials/recent", response_class=HTMLResponse)
async def recent_partial(request: Request):
    """Recent matches fragment for HTMX."""
    return templates.TemplateResponse("partials/recent.html", {
        "request": request,
        "recent_matches": db.get_recent_matches(),
    })


@app.get("/partials/player-list", response_class=HTMLResponse)
async def player_list_partial(request: Request):
    """Player list fragment for HTMX."""
    return templates.TemplateResponse("partials/player_list.html", {
        "request": request,
        "players": db.get_all_players(),
    })


@app.get("/partials/match-form", response_class=HTMLResponse)
async def match_form_partial(request: Request):
    """Match form fragment for HTMX."""
    return templates.TemplateResponse("partials/match_form.html", {
        "request": request,
        "players": db.get_all_players(),
    })


# === API Endpoints ===

@app.post("/players", response_class=HTMLResponse)
async def add_player(request: Request, name: str = Form(...)):
    """Add a new player."""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Player name required")
    
    player = db.add_player(name)
    if not player:
        raise HTTPException(status_code=400, detail="Player already exists")
    
    # Return updated player list AND match form (via OOB swap)
    return templates.TemplateResponse("partials/player_update.html", {
        "request": request,
        "players": db.get_all_players(),
    })


@app.delete("/players/{player_id}", response_class=HTMLResponse)
async def delete_player(request: Request, player_id: int):
    """Delete a player."""
    if not db.delete_player(player_id):
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Return updated player list AND match form (via OOB swap)
    return templates.TemplateResponse("partials/player_update.html", {
        "request": request,
        "players": db.get_all_players(),
    })


@app.get("/partials/win-streaks", response_class=HTMLResponse)
async def win_streaks_partial(request: Request):
    """Win streaks fragment for HTMX."""
    return templates.TemplateResponse("partials/win_streaks.html", {
        "request": request,
        "win_streaks": db.get_win_streaks(),
    })

@app.get("/partials/podium-days", response_class=HTMLResponse)
async def podium_days_partial(request: Request):
    """Podium days fragment for HTMX."""
    return templates.TemplateResponse("partials/podium_days.html", {
        "request": request,
        "podium_days": db.get_podium_days(),
    })


@app.post("/matches", response_class=HTMLResponse)
async def record_match(
    request: Request,
    winner_id: int = Form(...),
    participants: List[int] = Form(...),
):
    """Record a match result."""
    if winner_id not in participants:
        raise HTTPException(status_code=400, detail="Winner must be a participant")

    if len(participants) < 2:
        raise HTTPException(status_code=400, detail="At least 2 players required")

    db.record_match(winner_id, participants)

    # Return all updated sections
    return templates.TemplateResponse("partials/all_stats.html", {
        "request": request,
        "players": db.get_all_players(),
        "leaderboard": db.get_leaderboard(),
        "weekly_leaderboard": db.get_weekly_leaderboard(),
        "recent_matches": db.get_recent_matches(),
        "win_streaks": db.get_win_streaks(),
        "podium_days": db.get_podium_days(),
    })
