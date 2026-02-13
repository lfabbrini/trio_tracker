import sqlite3
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

# Use environment variable, or fall back to local data directory
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "trio.db")
DATABASE_PATH = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)


def get_db_path():
    """Get database path, creating directory if needed."""
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    return DATABASE_PATH


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database with schema."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Players table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Matches table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_id INTEGER NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (winner_id) REFERENCES players(id)
            )
        """)
        
        # Match participants junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS match_players (
                match_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                PRIMARY KEY (match_id, player_id),
                FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)
        
        conn.commit()


# Player operations
def get_all_players():
    """Get all players ordered by name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM players ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


def add_player(name: str) -> Optional[dict]:
    """Add a new player. Returns the player or None if exists."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO players (name) VALUES (?)", (name.strip(),))
            conn.commit()
            cursor.execute("SELECT * FROM players WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())
        except sqlite3.IntegrityError:
            return None


def delete_player(player_id: int) -> bool:
    """Delete a player by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM players WHERE id = ?", (player_id,))
        conn.commit()
        return cursor.rowcount > 0


# Match operations
def record_match(winner_id: int, participant_ids: list[int]) -> dict:
    """Record a new match with participants."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Insert match
        cursor.execute(
            "INSERT INTO matches (winner_id) VALUES (?)",
            (winner_id,)
        )
        match_id = cursor.lastrowid
        
        # Insert participants
        for player_id in participant_ids:
            cursor.execute(
                "INSERT INTO match_players (match_id, player_id) VALUES (?, ?)",
                (match_id, player_id)
            )
        
        conn.commit()
        return {"id": match_id, "winner_id": winner_id, "participants": participant_ids}


def get_leaderboard():
    """Get player stats for leaderboard."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                p.id,
                p.name,
                COUNT(DISTINCT m.id) as wins,
                COUNT(DISTINCT mp.match_id) as matches_played,
                CASE 
                    WHEN COUNT(DISTINCT mp.match_id) > 0 
                    THEN ROUND(COUNT(DISTINCT m.id) * 100.0 / COUNT(DISTINCT mp.match_id), 1)
                    ELSE 0 
                END as win_rate
            FROM players p
            LEFT JOIN matches m ON p.id = m.winner_id
            LEFT JOIN match_players mp ON p.id = mp.player_id
            GROUP BY p.id
            ORDER BY wins DESC, win_rate DESC, p.name
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_weekly_leaderboard():
    """Get leaderboard stats filtered to the current Mon-Fri work week."""
    from datetime import timedelta

    today = datetime.now().date()
    # Monday = 0, Sunday = 6
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    week_start = datetime(monday.year, monday.month, monday.day, 0, 0, 0).isoformat()
    week_end = datetime(friday.year, friday.month, friday.day, 23, 59, 59).isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                p.id,
                p.name,
                COUNT(DISTINCT m.id) as wins,
                COUNT(DISTINCT mp.match_id) as matches_played,
                CASE
                    WHEN COUNT(DISTINCT mp.match_id) > 0
                    THEN ROUND(COUNT(DISTINCT m.id) * 100.0 / COUNT(DISTINCT mp.match_id), 1)
                    ELSE 0
                END as win_rate
            FROM players p
            LEFT JOIN matches m ON p.id = m.winner_id
                AND m.played_at BETWEEN ? AND ?
            LEFT JOIN match_players mp ON p.id = mp.player_id
                AND mp.match_id IN (SELECT id FROM matches WHERE played_at BETWEEN ? AND ?)
            GROUP BY p.id
            HAVING matches_played > 0
            ORDER BY wins DESC, win_rate DESC, p.name
        """, (week_start, week_end, week_start, week_end))

        players = [dict(row) for row in cursor.fetchall()]

    return {
        "players": players,
        "week_start": monday.strftime("%d/%m"),
        "week_end": friday.strftime("%d/%m"),
    }


def get_recent_matches(limit: int = 10):
    """Get recent matches with participants."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                m.id,
                m.played_at,
                m.winner_id,
                w.name as winner_name
            FROM matches m
            JOIN players w ON m.winner_id = w.id
            ORDER BY m.played_at DESC
            LIMIT ?
        """, (limit,))
        
        matches = []
        for row in cursor.fetchall():
            match = dict(row)
            # Get participants for this match
            cursor.execute("""
                SELECT p.id, p.name 
                FROM match_players mp
                JOIN players p ON mp.player_id = p.id
                WHERE mp.match_id = ? AND p.id != ?
            """, (match['id'], match['winner_id']))
            match['opponents'] = [dict(r) for r in cursor.fetchall()]
            matches.append(match)
        
        return matches

def get_win_streaks():
    """Get current win streak for each player (consecutive wins from most recent match)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Get matches in order (newest first)
        cursor.execute("""
            SELECT m.winner_id, p.name
            FROM matches m
            JOIN players p ON m.winner_id = p.id
            ORDER BY m.played_at DESC
        """)
        
        matches = cursor.fetchall()
        
        if not matches:
            return []
        
        # The current streak holder is whoever won the most recent match
        # Count how many consecutive wins they have
        streaks = {}
        last_winner = None
        
        for match in matches:
            winner_id = match['winner_id']
            winner_name = match['name']
            
            if last_winner is None:
                # First match - start counting
                last_winner = winner_id
                streaks[winner_id] = {'name': winner_name, 'streak': 1}
            elif winner_id == last_winner:
                # Same person won - streak continues!
                streaks[winner_id]['streak'] += 1
            else:
                # Different winner - streak is broken, stop counting
                break
        
        # Return only players with streak >= 2
        result = [
            {'player_id': pid, 'name': data['name'], 'streak': data['streak']}
            for pid, data in streaks.items()
            if data['streak'] >= 2
        ]

        return result


def get_podium_days():
    """Get how many match days each player held a top-3 leaderboard position.

    For each player, tracks their best (lowest) position and how many
    calendar days with matches they held that position.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get all distinct match days
        cursor.execute("SELECT DISTINCT DATE(played_at) as match_day FROM matches ORDER BY match_day")
        match_days = [row['match_day'] for row in cursor.fetchall()]

        if not match_days:
            return []

        # For each match day, compute cumulative leaderboard up to that day
        # and track who held positions 1-3
        # player_id -> {name, best_position, days_at_best}
        player_podium = {}

        for day in match_days:
            # Cumulative leaderboard up to end of this day
            cursor.execute("""
                SELECT
                    p.id,
                    p.name,
                    COUNT(DISTINCT m.id) as wins,
                    COUNT(DISTINCT mp.match_id) as matches_played,
                    CASE
                        WHEN COUNT(DISTINCT mp.match_id) > 0
                        THEN ROUND(COUNT(DISTINCT m.id) * 100.0 / COUNT(DISTINCT mp.match_id), 1)
                        ELSE 0
                    END as win_rate
                FROM players p
                LEFT JOIN matches m ON p.id = m.winner_id AND DATE(m.played_at) <= ?
                LEFT JOIN match_players mp ON p.id = mp.player_id
                    AND mp.match_id IN (SELECT id FROM matches WHERE DATE(played_at) <= ?)
                GROUP BY p.id
                HAVING matches_played > 0
                ORDER BY wins DESC, win_rate DESC, p.name
            """, (day, day))

            rows = cursor.fetchall()

            # Top 3 positions
            for pos_idx, row in enumerate(rows[:3]):
                position = pos_idx + 1
                pid = row['id']
                name = row['name']

                if pid not in player_podium:
                    player_podium[pid] = {'name': name, 'best_position': position, 'days': 1}
                elif position < player_podium[pid]['best_position']:
                    # Found a better position - reset
                    player_podium[pid] = {'name': name, 'best_position': position, 'days': 1}
                elif position == player_podium[pid]['best_position']:
                    player_podium[pid]['days'] += 1

        result = [
            {'name': data['name'], 'best_position': data['best_position'], 'days': data['days']}
            for data in player_podium.values()
        ]

        # Sort by best_position ASC, then days DESC
        result.sort(key=lambda x: (x['best_position'], -x['days']))

        return result
