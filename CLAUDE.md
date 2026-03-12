# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Polish Footballers Abroad Tracker - komercyjna aplikacja freemium do śledzenia polskich piłkarzy grających za granicą. Monorepo z FastAPI backend i Streamlit frontend.

## Commands

### Backend
```bash
cd backend
uv sync                                    # Install dependencies
uv run uvicorn app.main:app --reload --port 8000   # Start dev server
uv run pytest                              # Run tests
uv run ruff check .                        # Lint
uv run mypy app                            # Type check
```

### Frontend
```bash
cd frontend
uv sync                                    # Install dependencies
uv run streamlit run app.py                # Start Streamlit
```

### Sync Script (critical)
```bash
cd backend
uv run python sync_full.py                 # Incremental sync (default)
uv run python sync_full.py --dry-run       # Preview without saving
uv run python sync_full.py --full          # Full sync (all matches)
uv run python sync_full.py --team 8634     # Sync specific team only
uv run python sync_full.py --force         # Ignore cache timing
```

**IMPORTANT:** Always run `--dry-run` first before actual sync to preview changes.

## Architecture

### Data Flow
```
RapidAPI → sync_full.py → Supabase (player_stats_by_competition) → aggregate → player_stats (Season Total)
                                    ↓
                              FastAPI endpoints → Streamlit frontend
```

### Key Architectural Decisions

1. **Two stats tables:**
   - `player_stats` = Season Total (aggregated from all competitions)
   - `player_stats_by_competition` = Stats per competition (La Liga, CL, Copa del Rey)

2. **Position-specific stats:**
   - Field players: `g_per90`, `a_per90`, `penalties_scored`, `penalties_missed`
   - Goalkeepers: `clean_sheets`, `saves`, `save_percentage`, `goals_against`
   - API uses `response_model_exclude_none=True` to hide irrelevant stats

3. **Incremental sync:**
   - `sync_state` table tracks last synced match per team/competition
   - `synced_matches` table prevents duplicate processing
   - Default mode syncs only new matches since last run

4. **Hardcoded players (MVP):**
   - `POLISH_PLAYERS` dict in `sync_full.py` defines tracked players
   - `TEAMS` dict defines teams with their competitions
   - See `PLAN_AUTO_DETECT_PLAYERS.md` for post-MVP automation

### Backend Structure
```
backend/app/
├── api/v1/players.py    # All player endpoints including /detailed-stats
├── db/models.py         # Player, PlayerStats, PlayerStatsByCompetition, SyncState, SyncedMatch
├── schemas/player.py    # Pydantic schemas with Optional fields for position-specific stats
└── services/rapidapi.py # API client + calculate_per_90 helper
```

## Important Patterns

### Adding a new player (MVP)
1. Find `rapidapi_id` via RapidAPI
2. Add to `POLISH_PLAYERS` dict in `sync_full.py`
3. Add team to `TEAMS` if new
4. Run `python sync_full.py --full --team TEAM_ID`

### Position-specific stats in API
Check `player.position == "GK"` before returning stats:
```python
# Field player stats - None for GK
"g_per90": None if is_goalkeeper else float(stats.g_per90),
# Goalkeeper stats - None for field players
"clean_sheets": stats.clean_sheets if is_goalkeeper else None,
```

### Competition type mapping
```python
"league"     # La Liga, Premier League, etc.
"european"   # Champions League, Europa League
"domestic"   # Copa del Rey, Supercopa, domestic cups
```

## Environment Variables

Required in `backend/.env`:
```
SUPABASE_URL=
SUPABASE_KEY=
RAPIDAPI_KEY=
SECRET_KEY=
```

## Documentation Files

- `PLAN_POLISH_TRACKER.md` - Full MVP plan with SQL schema
- `PLAN_ADVANCED_STATS_V2.md` - Detailed stats per competition implementation
- `PLAN_AUTO_DETECT_PLAYERS.md` - Post-MVP automatic player detection
