# CLAUDE.md - Trio Tracker Project Guide

## Project Overview

**Trio Tracker** is a self-hosted web application for tracking card game (Trio) wins among coworkers. It runs on a local workstation and is accessible via LAN.

### Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Server** | Uvicorn | ASGI server, handles HTTP connections |
| **Backend** | FastAPI (Python 3.12) | Web framework, routing, request handling |
| **Database** | SQLite | Persistent storage, single file (`data/trio.db`) |
| **Templating** | Jinja2 | Server-side HTML rendering |
| **Frontend** | HTMX | Dynamic updates without JavaScript |
| **Styling** | Tailwind CSS + DaisyUI | Utility-first CSS with components |
| **Deployment** | Docker + Docker Compose | Containerized deployment |

---

## Project Structure

```
trio-tracker/
├── app/
│   ├── __init__.py          # Package marker
│   ├── main.py              # FastAPI routes and application
│   ├── database.py          # SQLite operations
│   └── templates/
│       ├── base.html        # Master layout (header, footer, styles, scripts)
│       ├── index.html       # Main page content
│       └── partials/        # HTMX-swappable fragments
│           ├── leaderboard.html
│           ├── most_active.html
│           ├── recent.html
│           ├── match_form.html
│           ├── player_management.html
│           ├── player_update.html
│           ├── win_streaks.html
│           └── all_stats.html    # Combined OOB response
├── data/
│   └── trio.db              # SQLite database (auto-created)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── CLAUDE.md                # This file
```

---

## Architecture Flow

### Request/Response Cycle

```
Browser → Uvicorn (port 8080) → FastAPI → Route Handler → Database
                                              ↓
Browser ← HTML Response ← Jinja2 Template ←──┘
```

### HTMX Dynamic Updates

```
User Action → HTMX intercepts → AJAX request → FastAPI partial route
                                                      ↓
Page section updates ← HTMX swaps HTML ← Partial template
```

### Out-of-Band (OOB) Swaps

When recording a match, multiple sections update simultaneously:
- Main response goes to `#match-form`
- OOB responses update `#leaderboard`, `#most-active`, `#recent-matches`, `#win-streaks`

---

## Database Schema

```sql
-- Players table
CREATE TABLE players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Matches table
CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    winner_id INTEGER NOT NULL,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (winner_id) REFERENCES players(id)
);

-- Match participants (junction table)
CREATE TABLE match_players (
    match_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    PRIMARY KEY (match_id, player_id),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id)
);
```

---

## Key Files Explained

### `app/main.py`

FastAPI application with routes:

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Main page |
| `/partials/leaderboard` | GET | Leaderboard fragment (HTMX) |
| `/partials/most-active` | GET | Most active fragment (HTMX) |
| `/partials/recent` | GET | Recent matches fragment (HTMX) |
| `/partials/win-streaks` | GET | Win streaks fragment (HTMX) |
| `/players` | POST | Add new player |
| `/players/{id}` | DELETE | Remove player |
| `/matches` | POST | Record match result |

### `app/database.py`

Database operations:

| Function | Purpose |
|----------|---------|
| `init_db()` | Create tables if not exist |
| `get_all_players()` | List all players |
| `add_player(name)` | Insert new player |
| `delete_player(id)` | Remove player |
| `record_match(winner_id, participants)` | Record match with participants |
| `get_leaderboard()` | Player stats (wins, win rate) |
| `get_most_active()` | Players ranked by participation |
| `get_recent_matches(limit)` | Recent match history |
| `get_win_streaks()` | Current consecutive win streaks |

### `app/templates/base.html`

Master template containing:
- CSS imports (Tailwind, DaisyUI)
- HTMX import
- Custom styles and animations
- Header with logo and card suit animations
- Footer with mascot
- JavaScript for participant selection and celebrations

### `app/templates/partials/all_stats.html`

Special template for HTMX OOB swaps. Returns multiple sections at once after recording a match.

---

## Common Development Tasks

### Adding a New Statistic

1. **Database**: Add query function in `database.py`
2. **Route**: Add to context in `main.py` (`index()` and `record_match()`)
3. **Partial Route**: Create `/partials/xxx` route in `main.py`
4. **Template**: Create `partials/xxx.html`
5. **Display**: Add card in `index.html` with `{% include %}` and `hx-get`
6. **Live Update**: Add OOB swap in `all_stats.html`

### Adding a New Page

1. Create route in `main.py` with `@app.get("/newpage")`
2. Create template `templates/newpage.html` extending `base.html`
3. Use `{% block content %}...{% endblock %}` for page content

### Modifying Styles

- **Global styles**: Edit `<style>` section in `base.html`
- **Component styles**: Use Tailwind classes directly in HTML
- **Animations**: Add `@keyframes` in `base.html` `<style>` section

### Database Queries

Access SQLite directly for debugging:
```bash
docker-compose exec trio-tracker sqlite3 /app/data/trio.db
```

Common SQL:
```sql
.tables                          -- List tables
.schema players                  -- Show table structure
SELECT * FROM players;           -- All players
SELECT * FROM matches ORDER BY played_at DESC LIMIT 5;  -- Recent matches
```

---

## Development Workflow

### With Docker (Production-like)

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Restart (after Python changes)
docker-compose restart

# Rebuild (after requirements.txt or Dockerfile changes)
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Stop
docker-compose down
```

### Live Template Editing

With current `docker-compose.yml` volume mount (`./app:/app/app`):
- Edit templates → Refresh browser → See changes
- Edit Python files → Must restart container

### Local Development (without Docker)

```bash
cd trio-tracker
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
DATABASE_PATH=./data/trio.db uvicorn app.main:app --reload --port 8080
```

The `--reload` flag enables auto-restart on Python file changes.

---

## Jinja2 Template Syntax

| Syntax | Purpose | Example |
|--------|---------|---------|
| `{{ var }}` | Print variable | `{{ player.name }}` |
| `{% if %}` | Conditional | `{% if wins > 0 %}...{% endif %}` |
| `{% for %}` | Loop | `{% for p in players %}...{% endfor %}` |
| `{% extends %}` | Inherit template | `{% extends "base.html" %}` |
| `{% block %}` | Define/fill block | `{% block content %}...{% endblock %}` |
| `{% include %}` | Insert template | `{% include "partials/x.html" %}` |
| `{{ x \| filter }}` | Apply filter | `{{ time \| relative_time }}` |

---

## HTMX Attributes

| Attribute | Purpose | Example |
|-----------|---------|---------|
| `hx-get` | GET request | `hx-get="/partials/leaderboard"` |
| `hx-post` | POST request | `hx-post="/matches"` |
| `hx-delete` | DELETE request | `hx-delete="/players/5"` |
| `hx-target` | Where to put response | `hx-target="#leaderboard"` |
| `hx-swap` | How to insert | `hx-swap="innerHTML"` |
| `hx-trigger` | When to trigger | `hx-trigger="every 30s"` |
| `hx-swap-oob` | Out-of-band swap | `hx-swap-oob="true"` |
| `hx-confirm` | Confirmation dialog | `hx-confirm="Are you sure?"` |

---

## Tailwind CSS Patterns

### Common Classes Used

| Class | CSS Equivalent |
|-------|----------------|
| `p-4` | `padding: 1rem` |
| `m-4` | `margin: 1rem` |
| `px-4` | `padding-left/right: 1rem` |
| `mt-4` | `margin-top: 1rem` |
| `text-white` | `color: white` |
| `bg-slate-800` | `background-color: #1e293b` |
| `rounded-xl` | `border-radius: 0.75rem` |
| `flex` | `display: flex` |
| `gap-4` | `gap: 1rem` |
| `grid` | `display: grid` |
| `grid-cols-3` | `grid-template-columns: repeat(3, 1fr)` |
| `hidden` | `display: none` |

### Responsive Prefixes

| Prefix | Breakpoint |
|--------|------------|
| `sm:` | 640px+ |
| `md:` | 768px+ |
| `lg:` | 1024px+ |
| `xl:` | 1280px+ |

Example: `class="grid-cols-1 lg:grid-cols-3"` = 1 column on mobile, 3 on large screens.

---

## Troubleshooting

### "Internal Server Error"

1. Check container logs: `docker-compose logs -f`
2. Look for Python tracebacks
3. Common causes:
   - Jinja2 template syntax error
   - Missing variable in template context
   - Database query error

### Changes Not Appearing

1. **Template changes**: Just refresh browser
2. **Python changes**: `docker-compose restart`
3. **Still not working**: Rebuild with `docker-compose build --no-cache`

### Database Issues

Reset database:
```bash
rm data/trio.db
docker-compose restart
```

### HTMX Not Updating

1. Check browser DevTools Network tab for failed requests
2. Verify `hx-target` matches element ID
3. Check `hx-swap-oob="true"` (not `"innerHTML"`)

---

## Future Enhancement Ideas

- [ ] Head-to-head statistics
- [ ] Match history with filters
- [ ] Player avatars
- [ ] Sound effects on win
- [ ] Export data to CSV
- [ ] Multiple game types support
- [ ] Dark/light theme toggle
- [ ] Player achievements/badges

---

## Contact & Ownership

**Maintained by**: SAI-Team  
**Created**: 2026  
**Purpose**: Break time fun! 🃏
