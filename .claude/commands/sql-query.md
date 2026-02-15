# SQL Query Command

Help write or debug SQL queries for Trio Tracker.

## Database Schema

```sql
players (id, name, created_at)
matches (id, winner_id, played_at)
match_players (match_id, player_id)
```

## Relationships

- `matches.winner_id` → `players.id` (who won)
- `match_players.match_id` → `matches.id` (which match)
- `match_players.player_id` → `players.id` (who participated)

## Common Query Patterns

### Get player stats (wins + participation)
```sql
SELECT 
    p.id,
    p.name,
    COUNT(DISTINCT m.id) as wins,
    COUNT(DISTINCT mp.match_id) as matches_played
FROM players p
LEFT JOIN matches m ON p.id = m.winner_id
LEFT JOIN match_players mp ON p.id = mp.player_id
GROUP BY p.id
ORDER BY wins DESC;
```

### Get recent matches with winner name
```sql
SELECT m.id, m.played_at, p.name as winner_name
FROM matches m
JOIN players p ON m.winner_id = p.id
ORDER BY m.played_at DESC
LIMIT 10;
```

### Get match participants
```sql
SELECT p.name
FROM match_players mp
JOIN players p ON mp.player_id = p.id
WHERE mp.match_id = ?;
```

## Testing Queries

```bash
docker-compose exec trio-tracker sqlite3 /app/data/trio.db "YOUR QUERY HERE"
```

## Query Request

$ARGUMENTS
