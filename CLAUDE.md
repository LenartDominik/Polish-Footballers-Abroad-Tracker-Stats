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
uv run python sync_full.py --player 1647807  # Sync specific player only
uv run python sync_full.py --gk-only       # Sync goalkeepers only
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
4. Add player's team_id to `PLAYER_TEAMS` mapping
5. Run `python sync_full.py --player RAPIDAPI_ID`

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


# CLAUDE.md

## Projekt

Ten projekt składa się z:
- backendu w FastAPI,
- frontendu w Streamlit,
- bazy danych Supabase PostgreSQL,
- deployu na Render.

## Główne zasady pracy

Zawsze pracuj w tej kolejności:
1. Zrozum problem.
2. Zrób plan w małych krokach.
3. Oceń wpływ zmian na backend, frontend, bazę i deploy.
4. Implementuj tylko zakres, o który proszę.
5. Na końcu zrób review i wskaż ryzyka.
6. Nigdy nie czytaj wrażliwych plików i sekretów np. .env i innych

Nie zaczynaj od kodu, jeśli wcześniej nie było analizy problemu i planu.

## Styl pracy

- Pisz jasno, krótko i konkretnie.
- Nie rób dużych, niekontrolowanych refactorów.
- Nie zmieniaj wielu warstw naraz bez wyraźnej potrzeby.
- Najpierw proponuj najmniejszą sensowną zmianę.
- Jeśli problem nie jest jasny, najpierw podaj możliwe przyczyny i sposób diagnozy.
- Gdy czegoś brakuje, napisz czego potrzebujesz zamiast zgadywać.

## Backend FastAPI

Przy zmianach w backendzie:
- zachowuj czytelny podział odpowiedzialności,
- używaj typowania,
- dbaj o walidację wejścia i wyjścia,
- nie mieszaj logiki biznesowej z warstwą endpointów,
- pokazuj, które pliki zmieniasz i dlaczego.

Zawsze sprawdź:
- wpływ na request/response,
- wpływ na modele danych,
- wpływ na obsługę błędów,
- wpływ na auth, jeśli dotyczy.

## Frontend Streamlit

Przy zmianach w Streamlit:
- dbaj o prosty flow użytkownika,
- pokazuj czytelne komunikaty błędów,
- nie komplikuj UI bez potrzeby,
- nie zmieniaj backendu, jeśli proszę tylko o frontend,
- uwzględniaj stany: loading, brak danych, błąd.

## Baza danych Supabase / PostgreSQL

Przy zmianach w bazie:
- najpierw oceń wpływ na obecny schemat,
- wskaż ryzyko migracji,
- sprawdź wpływ na endpointy FastAPI,
- sprawdź wpływ na Streamlit,
- zwróć uwagę na relacje, indeksy i uprawnienia.

Nie proponuj zmian w bazie bez oceny skutków.

## Render / deploy

Przy zmianach sprawdzaj też:
- zmienne środowiskowe,
- zależności i wersje pakietów,
- komendy startowe,
- wpływ zmian na deploy,
- możliwe różnice między local a production.

## Debugowanie

Gdy analizujesz błąd:
1. Najpierw wypisz możliwe przyczyny.
2. Wskaż najbardziej prawdopodobną.
3. Zaproponuj minimalny sposób potwierdzenia diagnozy.
4. Dopiero potem zaproponuj poprawkę.

Nie zgaduj bez analizy.

## Review zmian

Po każdej większej zmianie zrób krótkie review:
- poprawność logiki,
- czytelność,
- nazewnictwo,
- ryzyko regresji,
- bezpieczeństwo,
- wpływ na bazę, API i frontend.

Pisz krótko i konkretnie.

## Security

Zawsze zwracaj uwagę na:
- sekrety i env,
- auth i autoryzację,
- walidację danych,
- zapytania do bazy,
- nadmiarowe ujawnianie błędów,
- dostęp do danych użytkowników.

Jeśli widzisz ryzyko, nazwij je wprost.

## Sposób odpowiedzi

Domyślnie odpowiadaj w formacie:
1. Krótki opis problemu.
2. Założenia.
3. Ryzyka.
4. Plan.
5. Implementacja albo rekomendacja.
6. Krótkie review po zmianie.

Jeśli proszę tylko o analizę, nie generuj kodu.
Jeśli proszę tylko o kod, najpierw daj krótki plan, potem kod.


## Ważne dla mnie

Jestem początkujący.
Chcę krótkich wyjaśnień.
Nie chcę zbyt skomplikowanych rozwiązań.
Jeśli da się zrobić coś prościej, zaproponuj prostszą wersję.