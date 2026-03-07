# 🃏 Trio Tracker

A beautiful, self-hosted leaderboard for tracking your Trio card game wins at work!

![Made with love for break time fun](https://img.shields.io/badge/Made%20with-♠️%20♥️%20♣️%20♦️-red)

## Features

- 🏆 **Live Leaderboard** — Ranked by wins with win rate percentages
- 📊 **Most Active** — See who plays the most
- 🎯 **Quick Match Recording** — Log a game in seconds
- 👥 **Player Management** — Add/remove players easily
- 📜 **Match History** — Recent games with timestamps
- 🌙 **Beautiful Dark Theme** — Easy on the eyes during break time
- 🔄 **Auto-refresh** — Stats update every 30 seconds

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Clone or download this folder
cd trio-tracker

# Start the app
docker-compose up -d

# Open in browser
open http://localhost:8080
```

### Option 2: Docker Run

```bash
# Build the image
docker build -t trio-tracker .

# Run with persistent data
docker run -d \
  --name trio-tracker \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  trio-tracker
```

### Option 3: Run Locally (Development)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
DATABASE_PATH=./data/trio.db uvicorn app.main:app --reload --port 8080
```

## Access from Other Computers

Once running, anyone on your LAN can access the tracker:

1. Find your workstation's IP address:
   ```bash
   # Linux/Mac
   hostname -I
   
   # Windows
   ipconfig
   ```

2. Share the URL with teammates:
   ```
   http://YOUR_IP_ADDRESS:8080
   ```

## Usage

### Adding Players
1. Go to "Manage Players" section
2. Type a name and click "+ Add"

### Recording a Match
1. Select all players who participated (checkboxes)
2. Select who won (radio buttons appear after selecting 2+ players)
3. Click "🏆 Record Match"

### Understanding Stats
- **Wins**: Total number of matches won
- **Win Rate**: Percentage of matches won (wins ÷ matches played × 100)
- **Most Active**: Ranked by total matches played

## Data Persistence

Your data is stored in `./data/trio.db` (SQLite database).

- **Backup**: Simply copy the `data/trio.db` file
- **Reset**: Delete the `data/trio.db` file and restart

## Stopping the App

```bash
# Stop and keep data
docker-compose down

# Stop and remove everything (including data volume)
docker-compose down -v
```

## Rebuild After modifications

```bash
#re-build 
docker-compose build 

#re-build everithing from scratch
docker-compose build --no-cache

# Start the app
docker-compose up -d

```

## Tech Stack

- **Backend**: Python 3.12 + FastAPI
- **Frontend**: HTMX + DaisyUI + Tailwind CSS
- **Database**: SQLite
- **Deployment**: Docker

## Customization

### Change the Port

Edit `docker-compose.yml`:
```yaml
ports:
  - "3000:8080"  # Change 3000 to your preferred port
```

### Change the Theme

Edit `app/templates/base.html` and change `data-theme="night"` to another DaisyUI theme:
- `dark`, `light`, `cupcake`, `cyberpunk`, `retro`, `valentine`, etc.

---

Made with ♠️ ♥️ ♣️ ♦️ for break time fun
