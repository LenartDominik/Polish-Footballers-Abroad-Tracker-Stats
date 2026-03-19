# Polish Footballers Abroad Tracker

Komercyjna aplikacja freemium do trackowania polskich piłkarzy za granicą.

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL (Supabase)
- **Frontend**: Streamlit + Plotly
- **API**: RapidAPI Football
- **Payments**: Stripe
- **Deployment**: Render (backend) + Streamlit Cloud (frontend)

## Project Structure

```
polish-trackers-app/
├── backend/                 # FastAPI async API
│   ├── app/
│   │   ├── api/v1/         # REST endpoints
│   │   ├── core/           # Config, deps
│   │   ├── db/             # Models, session
│   │   ├── schemas/        # Pydantic models
│   │   └── services/       # External APIs
│   ├── sync_full.py        # Sync script for player stats
│   └── pyproject.toml
├── frontend/               # Streamlit UI
│   ├── app.py
│   ├── pages/
│   └── pyproject.toml
└── docker-compose.yml
```

## Quick Start

### 1. Setup Environment

```bash
# Copy environment template
cp .env.example .env
# Edit .env with your credentials
```

### 2. Backend

```bash
cd backend

# Using uv (recommended)
uv sync

# Run
uv run uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend

uv sync
uv run streamlit run app.py
```

---

## Synchronizacja Piłkarzy

### Komendy sync

```bash
cd backend

# Synchronizuj konkretnego piłkarza (najszybsze)
uv run python sync_full.py --player RAPIDAPI_ID

# Synchronizuj tylko bramkarzy
uv run python sync_full.py --gk-only --force

# Synchronizuj wszystkich piłkarzy
uv run python sync_full.py --full --force

# Podgląd bez zapisu (dry-run)
uv run python sync_full.py --player RAPIDAPI_ID --dry-run
```

### Aktualni piłkarze

| Piłkarz | rapidapi_id | team_id | Komenda |
|---------|-------------|---------|---------|
| Robert Lewandowski | 93447 | 8634 | `--player 93447` |
| Wojciech Szczęsny | 169718 | 8634 | `--player 169718` |
| Krzysztof Piątek | 543298 | 203826 | `--player 543298` |
| Piotr Zieliński | 362212 | 8636 | `--player 362212` |
| Oskar Pietuszewski | 1647807 | 9773 | `--player 1647807` |
| Jakub Kiwior | 490868 | 9773 | `--player 490868` |
| Jan Bednarek | 1021834 | 9773 | `--player 1021834` |
| Kamil Grabara | 760722 | 8721 | `--player 760722` |

### Jak dodać nowego piłkarza

1. **Zdobądź dane z RapidAPI:**
   - `rapidapi_id` - ID piłkarza
   - `team_id` - ID drużyny
   - `league_id` - ID ligi (dla każdej rozgrywki)

2. **Edytuj `sync_full.py`:**

```python
# Dodaj do POLISH_PLAYERS (z pozycją: GK, DF, MF, FW)
POLISH_PLAYERS = {
    ...
    1234567: {"name": "Jan Kowalski", "position": "FW"},  # rapidapi_id: {name, position}
}

# Dodaj do PLAYER_TEAMS
PLAYER_TEAMS = {
    ...
    1234567: 9999,  # rapidapi_id: team_id
}

# Jeśli drużyna jest NOWA, dodaj do TEAMS
TEAMS = {
    ...
    9999: {  # team_id
        "name": "Nowa Drużyna",
        "competitions": [
            {"name": "Liga", "league_id": 123},      # league_id z API!
            {"name": "Puchar", "league_id": 456},
            {"name": "Champions League", "league_id": 42},
        ],
    },
}
```

3. **Uruchom sync:**

```bash
uv run python sync_full.py --player 1234567 --force
```

4. **Jeśli API nie zwraca meczów (0 matches), dodaj ręcznie:**

```bash
uv run python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.db.models import Player, PlayerStats

async def add_player():
    async with AsyncSessionLocal() as session:
        player = Player(
            rapidapi_id=1234567,
            name='Jan Kowalski',
            position='FW',  # FW, MF, DF, GK
            team='Nowa Drużyna',
            league='Liga',
            nationality='Poland'
        )
        session.add(player)
        await session.flush()
        stats = PlayerStats(
            player_id=player.id,
            season='2025/26',
            matches_total=0, minutes_played=0, goals=0, assists=0
        )
        session.add(stats)
        await session.commit()
        print(f'Added: {player.name}')

asyncio.run(add_player())
"
```

### Kategoryzacja rozgrywek

| Typ | Przykłady | Wyświetlanie |
|-----|-----------|--------------|
| `league` | La Liga, Serie A, Qatar Stars League | Kolumna "League" |
| `european` | Champions League, Europa League, AFC Champions League | Kolumna "European" |
| `domestic` | Copa del Rey, Coppa Italia, Qatar Cup, Taça de Portugal | Kolumna "Domestic Cups" |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/players/search` | Search players |
| GET | `/api/v1/players/{id}` | Get player info |
| GET | `/api/v1/players/{id}/stats` | Get player stats |
| GET | `/api/v1/players/{id}/detailed-stats` | Stats per competition |
| GET | `/api/v1/players/top` | Top players by season |
| GET | `/api/v1/players/top_week` | Top players this week |
| GET | `/api/v1/leagues` | List leagues |

## Environment Variables

See `.env.example` for required variables.

## License

Proprietary - All rights reserved.
