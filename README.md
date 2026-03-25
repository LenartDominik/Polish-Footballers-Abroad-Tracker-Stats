# Polish Footballers Abroad Tracker

Komercyjna aplikacja freemium do śledzenia około 60 polskich piłkarzy grających za granicą z bogatymi statystykami.

## Funkcje

- **Wyszukiwarka** - szukaj piłkarzy po nazwisku, klubie, lidze
- **Dashboard** - top tygodnia, wykresy xG/90
- **Detailed Stats** - statystyki z podziałem na rozgrywki (League | European | Domestic | Total)
- **Porównywarka** - porównuj piłkarzy (FW vs FW, GK vs GK)
- **Position-specific stats** - inne statystyki dla bramkarzy i graczy z pola

## Tech Stack

| Komponent | Technologia |
|-----------|-------------|
| Backend | FastAPI async + SQLAlchemy asyncpg |
| Frontend | Streamlit |
| Database | Supabase PostgreSQL |
| API zewnętrzne | RapidAPI Football |
| Deployment | Render (backend) + Streamlit Cloud (frontend) |

## Struktura projektu

```
polish-trackers-app/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # endpoints: players, leagues, health
│   │   ├── core/            # config.py (Pydantic Settings)
│   │   ├── db/              # models.py, session.py
│   │   ├── schemas/         # Pydantic schemas
│   │   └── services/        # RapidAPI client
│   ├── sync_full.py         # sync script z CLI
│   └── pyproject.toml
├── frontend/
│   ├── app.py               # main Streamlit app
│   └── requirements.txt
├── .claude/                 # Claude Code skills
├── PLAN_*.md                # dokumentacja planów
└── README.md
```

## Szybki start

### 1. Klonowanie i setup

```bash
git clone https://github.com/USERNAME/polish-footballers-tracker.git
cd polish-footballers-tracker
```

### 2. Konfiguracja środowiska

Utwórz `.env` w folderze `backend/`:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
RAPIDAPI_KEY=your_rapidapi_key
SECRET_KEY=your-secret-key
```

### 3. Uruchomienie backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

API dostępne pod: `http://localhost:8000/docs`

### 4. Uruchomienie frontend

```bash
cd frontend
uv sync
uv run streamlit run app.py
```

Aplikacja dostępna pod: `http://localhost:8501`

## API Endpoints

### Players

| Metoda | Endpoint | Opis |
|--------|----------|------|
| GET | `/api/v1/players/` | Lista wszystkich piłkarzy |
| GET | `/api/v1/players/search` | Szukaj po nazwie/klubie/lidze |
| GET | `/api/v1/players/{id}` | Dane podstawowe |
| GET | `/api/v1/players/{id}/stats` | Statystyki sezonowe (Season Total) |
| GET | `/api/v1/players/{id}/detailed-stats` | Stats z podziałem na rozgrywki |

### Leagues

| Metoda | Endpoint | Opis |
|--------|----------|------|
| GET | `/api/v1/leagues/` | Lista lig |

## Sync Script

Synchronizacja danych z RapidAPI do bazy:

```bash
cd backend

# Incremental sync (tylko nowe mecze)
uv run python sync_full.py

# Pełny sync (wszystkie mecze)
uv run python sync_full.py --full

# Podgląd bez zapisu
uv run python sync_full.py --dry-run

# Tylko konkretny gracz
uv run python sync_full.py --player 1647807

# Tylko bramkarze
uv run python sync_full.py --gk-only

# Wymuś sync mimo cache
uv run python sync_full.py --force
```

### Opcje CLI

| Argument | Opis |
|----------|------|
| `--full` | Pełny sync, ignoruj cache |
| `--dry-run` | Podgląd bez zapisu do bazy |
| `--player ID` | Sync tylko konkretnego gracza (automatycznie full) |
| `--gk-only` | Sync tylko bramkarzy |
| `--force` | Ignoruj timing cache |

## Baza danych

### Tabele

| Tabela | Opis |
|--------|------|
| `players` | Dane podstawowe piłkarzy |
| `player_stats` | Statystyki sezonowe (Season Total - agregacja) |
| `player_stats_by_competition` | Stats per rozgrywka (La Liga, CL, Copa del Rey) |
| `leagues` | Lista lig |
| `sync_state` | Stan incremental sync per zespół/rozgrywka |
| `synced_matches` | Deduplikacja zsyncowanych meczów |

### Schema

```sql
-- Główne tabele
players (id, rapidapi_id, name, position, team, league)
player_stats (player_id, season, goals, assists, minutes_played, ...)
player_stats_by_competition (player_id, season, competition_type, competition_name, ...)

-- Sync tracking
sync_state (team_id, competition_id, last_sync_at, last_match_id, ...)
synced_matches (match_id, team_id, synced_at)
```

## Dodawanie nowego piłkarza (MVP)

Obecnie lista piłkarzy jest hardcoded w `sync_full.py`:

```python
POLISH_PLAYERS = {
    93447: "Robert Lewandowski",
    169718: "Wojciech Szczęsny",
    # Dodaj tutaj nowego piłkarza
}
```

**Kroki:**
1. Znajdź `rapidapi_id` piłkarza (przez RapidAPI lub w meczu)
2. Dodaj do `POLISH_PLAYERS` w `sync_full.py`
3. Dodaj `team_id` do `PLAYER_TEAMS` mapping
4. Jeśli nowy zespół - dodaj do `TEAMS`
5. Uruchom `python sync_full.py --player RAPIDAPI_ID`

> **Uwaga:** Po MVP zostanie zaimplementowane automatyczne wykrywanie Polaków. Zobacz `PLAN_AUTO_DETECT_PLAYERS.md`.

## Deployment

### Backend (Render)

1. Połącz repo z Render
2. Ustaw build command: `pip install -e .`
3. Ustaw start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Dodaj environment variables

### Frontend (Streamlit Cloud)

1. Połącz repo ze Streamlit Cloud
2. Ustaw main file: `frontend/app.py`
3. Dodaj secrets w Streamlit Cloud settings

## Koszty

| Usługa | Koszt |
|--------|-------|
| RapidAPI Football | ~$10/mc (20k requests) |
| Supabase | Free (500MB) |
| Render | Free tier |
| Streamlit Cloud | Free |
| **Total** | **~$11/mc** |

## Dokumentacja

| Plik | Opis |
|------|------|
| `PLAN_POLISH_TRACKER.md` | Pełny plan MVP |
| `PLAN_ADVANCED_STATS_V2.md` | Plan detailed stats per competition |
| `PLAN_AUTO_DETECT_PLAYERS.md` | Plan automatycznego wykrywania (po MVP) |

## Development

### TODO po MVP

- [ ] Automatyczne wykrywanie Polaków
- [ ] Admin panel do zarządzania zespołami
- [ ] Stripe payments (freemium)
- [ ] Landing page z waitlist
- [ ] Powiadomienia o golach
- [ ] Export CSV/PDF (premium)

### Testy

```bash
cd backend
uv run pytest
```

## Licencja

Private / Commercial

---

**Autor:** [Your Name]
**Ostatnia aktualizacja:** Marzec 2026
