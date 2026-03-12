# Plan: Advanced Stats Display v2 - Ekonomiczny

## Cel
Wyświetlanie statystyk z podziałem na rozgrywki **z minimalnym zużyciem API i egress**.

---

## Analiza kosztów API

### Docelowa skala: 100 piłkarzy (~20 zespołów)

| Parametr | Wartość |
|----------|---------|
| Piłkarze | 100 |
| Zespoły | ~20 (średnio 5 Polaków/klub) |
| Mecze/zespół/sezon | ~56 (liga + puchary) |
| Częstotliwość sync | 2x w tygodniu (~8-9/mc) |

### Zużycie API z incremental sync

| Tryb | Zapytania/sync | Syncs/mc | **Total/mc** |
|------|----------------|----------|--------------|
| Incremental (domyślny) | ~40-100 | 8 | **320-800** |
| Pełny sync (tylko pierwszy raz) | ~1,120 | 1 | **1,120** |
| **Średnio miesięcznie** | | | **~500-1,000** |

**Limit RapidAPI: 20,000/mc → Użycie: ~3-5%** ✅

---

## Architektura Sync

### Tryby działania

```
┌─────────────────────────────────────────────────────────────────┐
│                      SYNC SCRIPT OPTIONS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  python sync_full.py                      # Incremental (domyślnie)
│  python sync_full.py --incremental        # Incremental (jawny)
│  python sync_full.py --full               # Pełny sync (wszystko)
│  python sync_full.py --dry-run            # Podgląd bez zapisu
│  python sync_full.py --team 8634          # Tylko konkretny zespół
│  python sync_full.py --force              # Pomiń cache check
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Decyzja: Ręczny vs Automatyczny

| Opcja | Zalety | Wady |
|-------|--------|------|
| **Ręczny** (domyślnie) | Pełna kontrola, brak niespodzianek | Trzeba pamiętać |
| **Automatyczny** (opcja) | Zapominalski-friendly | Może zużyć API gdy nie trzeba |

**Rekomendacja:** Domyślnie ręczny, opcjonalnie automatyczny przez GitHub Actions.

---

## Database Schema

### Tabela: `player_stats_by_competition`

```sql
CREATE TABLE player_stats_by_competition (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT REFERENCES players(id) ON DELETE CASCADE,
    season VARCHAR(10) NOT NULL,
    competition_type VARCHAR(20) NOT NULL,  -- league, european, domestic
    competition_name VARCHAR(50) NOT NULL,
    competition_id INT,                     -- league_id z API (do cache)

    -- Match stats
    matches_total INT DEFAULT 0,
    matches_started INT DEFAULT 0,
    matches_subbed INT DEFAULT 0,
    minutes_played INT DEFAULT 0,

    -- Attacking stats
    goals INT DEFAULT 0,
    assists INT DEFAULT 0,
    yellow_cards INT DEFAULT 0,
    red_cards INT DEFAULT 0,

    -- Per 90 stats
    g_per90 NUMERIC(5,2) DEFAULT 0,
    a_per90 NUMERIC(5,2) DEFAULT 0,
    rating NUMERIC(4,2) DEFAULT 0,

    -- Goalkeeper stats (nullable)
    clean_sheets INT DEFAULT NULL,
    saves INT DEFAULT NULL,
    save_percentage NUMERIC(5,3) DEFAULT NULL,
    goals_against INT DEFAULT NULL,

    -- Cache
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,

    UNIQUE(player_id, season, competition_type, competition_name)
);

CREATE INDEX idx_stats_comp_player ON player_stats_by_competition(player_id);
CREATE INDEX idx_stats_comp_expires ON player_stats_by_competition(expires_at);
CREATE INDEX idx_stats_comp_competition ON player_stats_by_competition(competition_id);
```

### Tabela: `sync_state` (incremental sync)

```sql
CREATE TABLE sync_state (
    id SERIAL PRIMARY KEY,
    team_id INT NOT NULL,
    team_name VARCHAR(100),
    competition_id INT NOT NULL,
    competition_name VARCHAR(100),
    season VARCHAR(10) DEFAULT '2025/26',

    -- Incremental tracking
    last_sync_at TIMESTAMP,
    last_match_id INT,
    matches_synced INT DEFAULT 0,

    -- Cache
    next_sync_at TIMESTAMP,  -- Kiedy można nastepny sync

    UNIQUE(team_id, competition_id, season)
);

CREATE INDEX idx_sync_state_team ON sync_state(team_id);
CREATE INDEX idx_sync_state_next ON sync_state(next_sync_at);
```

### Tabela: `synced_matches` (deduplikacja)

```sql
-- Śledzi które mecze już zostały zsyncowane (żeby nie dublować)
CREATE TABLE synced_matches (
    id SERIAL PRIMARY KEY,
    match_id INT NOT NULL,
    team_id INT NOT NULL,
    competition_id INT NOT NULL,
    synced_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(match_id, team_id)
);

CREATE INDEX idx_synced_matches_match ON synced_matches(match_id);
```

### Tabela `player_stats` - Season Total (agregacja)
**Pozostaje bez zmian** - będzie update'owana z sumy `player_stats_by_competition`

---

## SQLAlchemy Models

**Plik:** `backend/app/db/models.py`

```python
class PlayerStatsByCompetition(Base):
    """Player statistics per competition per season."""

    __tablename__ = "player_stats_by_competition"
    __table_args__ = (
        UniqueConstraint("player_id", "season", "competition_type", "competition_name",
                        name="uq_player_season_competition"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"))
    season: Mapped[str] = mapped_column(String(10))
    competition_type: Mapped[str] = mapped_column(String(20))  # league, european, domestic
    competition_name: Mapped[str] = mapped_column(String(50))
    competition_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Match stats
    matches_total: Mapped[int] = mapped_column(Integer, default=0)
    matches_started: Mapped[int] = mapped_column(Integer, default=0)
    matches_subbed: Mapped[int] = mapped_column(Integer, default=0)
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)

    # Attacking stats
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)

    # Per 90 & Rating
    g_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    a_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    rating: Mapped[float] = mapped_column(Numeric(4, 2), default=0)

    # Goalkeeper stats (nullable)
    clean_sheets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    saves: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    save_percentage: Mapped[Optional[float]] = mapped_column(Numeric(5, 3), nullable=True)
    goals_against: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Cache
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="stats_by_competition")


class SyncState(Base):
    """Track sync progress per team/competition for incremental sync."""

    __tablename__ = "sync_state"
    __table_args__ = (
        UniqueConstraint("team_id", "competition_id", "season", name="uq_team_comp_season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(Integer)
    team_name: Mapped[Optional[str]] = mapped_column(String(100))
    competition_id: Mapped[int] = mapped_column(Integer)
    competition_name: Mapped[Optional[str]] = mapped_column(String(100))
    season: Mapped[str] = mapped_column(String(10), default="2025/26")

    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_match_id: Mapped[Optional[int]] = mapped_column(Integer)
    matches_synced: Mapped[int] = mapped_column(Integer, default=0)
    next_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class SyncedMatch(Base):
    """Track which matches have been synced to prevent duplicates."""

    __tablename__ = "synced_matches"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_match_team"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int] = mapped_column(Integer)
    competition_id: Mapped[int] = mapped_column(Integer)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

---

## Sync Script - Implementacja

**Plik:** `backend/sync_full.py`

### CLI Arguments

```python
import argparse

parser = argparse.ArgumentParser(description="Sync Polish players stats")
parser.add_argument("--full", action="store_true", help="Full sync (all matches)")
parser.add_argument("--incremental", action="store_true", help="Incremental sync (only new)")
parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
parser.add_argument("--team", type=int, help="Sync only specific team by ID")
parser.add_argument("--force", action="store_true", help="Force sync, ignore cache")
args = parser.parse_args()

# Default: incremental
sync_mode = "full" if args.full else "incremental"
```

### Główna logika incremental sync

```python
async def sync_team_incremental(team_id: int, team_info: dict, session, force: bool = False):
    """Sync only new matches since last sync."""

    stats_to_save = []
    matches_processed = 0

    for competition in team_info.get("competitions", []):
        comp_id = competition["league_id"]
        comp_name = competition["name"]

        # 1. Check sync_state
        sync_state = await get_sync_state(session, team_id, comp_id)

        if not force and sync_state and sync_state.next_sync_at:
            if datetime.utcnow() < sync_state.next_sync_at:
                print(f"  ⏭️ {comp_name}: Cache valid, skipping")
                continue

        # 2. Get last synced match_id
        last_match_id = sync_state.last_match_id if sync_state else 0

        # 3. Fetch matches from API
        matches = await get_matches_by_league(comp_id, client)

        # 4. Filter: only finished + team matches + new
        new_matches = [
            m for m in matches
            if is_team_match(m, team_id)
            and is_finished(m)
            and m["id"] > last_match_id
        ]

        if not new_matches:
            print(f"  ✅ {comp_name}: No new matches")
            continue

        print(f"  📥 {comp_name}: {len(new_matches)} new matches")

        # 5. Process each new match
        for match in new_matches:
            # Check if already synced (dedup)
            if await is_match_synced(session, match["id"], team_id):
                continue

            lineup = await get_lineup(match["id"], is_home(match, team_id), client)
            parsed = parse_polish_players(lineup)

            if parsed:
                stats_to_save.append({
                    "match_id": match["id"],
                    "competition": competition,
                    "stats": parsed
                })

            matches_processed += 1
            last_match_id = max(last_match_id, match["id"])

        # 6. Update sync_state
        await update_sync_state(session, team_id, comp_id, last_match_id, len(new_matches))

    # 7. Save to database (batch)
    if stats_to_save and not args.dry_run:
        await save_stats_batch(session, stats_to_save)
        await aggregate_to_season_total(session, player_ids)
        await session.commit()

    return matches_processed
```

### Komenda: dry-run

```python
async def dry_run_sync():
    """Preview what would be synced without making changes."""
    print("🔍 DRY RUN MODE - No changes will be made")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        for team_id, team_info in TEAMS.items():
            print(f"\n{team_info['name']}:")
            for comp in team_info["competitions"]:
                sync_state = await get_sync_state(session, team_id, comp["league_id"])
                matches = await get_matches_by_league(comp["league_id"], client)
                new_matches = filter_new_matches(matches, sync_state)

                print(f"  {comp['name']}: {len(new_matches)} new matches to sync")
                print(f"    Last sync: {sync_state.last_sync_at if sync_state else 'Never'}")
```

---

## Automatyzacja (opcjonalnie)

### GitHub Actions - 2x w tygodniu

**Plik:** `.github/workflows/sync-players.yml`

```yaml
name: Sync Players Stats

on:
  # Wtorek i piątek o 6:00 UTC
  schedule:
    - cron: '0 6 * * 2,5'

  # Ręczne triggerowanie
  workflow_dispatch:
    inputs:
      mode:
        description: 'Sync mode'
        required: true
        default: 'incremental'
        type: choice
        options:
          - incremental
          - full
      team_id:
        description: 'Team ID (optional)'
        required: false
        type: string

jobs:
  sync:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd backend
          pip install -e .

      - name: Run sync
        env:
          RAPIDAPI_KEY: ${{ secrets.RAPIDAPI_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          cd backend
          if [ "${{ github.event.inputs.team_id }}" != "" ]; then
            python sync_full.py --team ${{ github.event.inputs.team_id }}
          else
            python sync_full.py --${{ github.event.inputs.mode || 'incremental' }}
          fi

      - name: Notify on failure
        if: failure()
        run: |
          echo "Sync failed! Check logs."
          # Opcjonalnie: Slack/Discord webhook
```

### Ręczne triggerowanie przez GitHub UI

1. Wejdź na Actions → Sync Players Stats
2. Click "Run workflow"
3. Wybierz mode: `incremental` lub `full`
4. Opcjonalnie podaj `team_id`

---

## Egress Optimization (Supabase)

| Strategia | Oszczędność | Implementacja |
|-----------|-------------|---------------|
| Gzip compression | ~70% | FastAPI middleware |
| `exclude_none=True` | ~20% | Pydantic schemas |
| `@st.cache_data` | ~50% | Streamlit client cache |

**Szacunkowy egress:** ~50-100 MB/mc (limit: 5 GB) ✅

---

## Implementacja - Fazy

### Faza 1: Database & Models (~30 min)

**Zadania:**
- [ ] Dodać model `PlayerStatsByCompetition` do `models.py`
- [ ] Dodać model `SyncState` do `models.py`
- [ ] Dodać model `SyncedMatch` do `models.py`
- [ ] Dodać relację `Player.stats_by_competition`
- [ ] Uruchomić SQL w Supabase (3 nowe tabele)

**SQL do wykonania w Supabase:**
```sql
-- Patrz sekcja "Database Schema" wyżej
```

### Faza 2: Sync Script (~1.5h)

**Zadania:**
- [ ] Dodać CLI arguments (`--full`, `--dry-run`, `--team`, `--force`)
- [ ] Implementacja `get_sync_state()`, `update_sync_state()`
- [ ] Implementacja `is_match_synced()` (deduplikacja)
- [ ] Implementacja `sync_team_incremental()`
- [ ] Implementacja `dry_run_sync()`
- [ ] Zapis per competition do `player_stats_by_competition`
- [ ] Agregacja do `player_stats` (Season Total)
- [ ] Batch operations (`session.add_all`)

### Faza 3: API Endpoint (~45 min)

**Zadania:**
- [ ] Dodać schema `CompetitionStatsOut`, `PlayerDetailedStatsOut`
- [ ] Zaimplementować endpoint `GET /players/{id}/detailed-stats`
- [ ] Dodać `response_model_exclude_none=True`
- [ ] Przetestować w /docs

### Faza 4: Frontend (~1.5h)

**Zadania:**
- [ ] Funkcja `fetch_detailed_stats(player_id)` z `@st.cache_data`
- [ ] UI: 4 kolumny (League | European | Domestic | Total)
- [ ] Expandable details section
- [ ] Position-specific display (GK vs field)

### Faza 5: Automatyzacja (~30 min) - OPCJONALNIE

**Zadania:**
- [ ] Stworzyć `.github/workflows/sync-players.yml`
- [ ] Dodać secrets do GitHub (RAPIDAPI_KEY, DATABASE_URL)
- [ ] Przetestować ręczne triggerowanie

---

## Pliki do zmiany

| Plik | Zmiany |
|------|--------|
| `backend/app/db/models.py` | +3 modele |
| `backend/sync_full.py` | Incremental sync, CLI args |
| `backend/app/api/v1/players.py` | +1 endpoint |
| `backend/app/schemas/player.py` | +2 schemas |
| `frontend/app.py` | +UI detailed stats |
| `.github/workflows/sync-players.yml` | Nowy plik (opcjonalnie) |

---

## Podsumowanie kosztów

### API Requests (RapidAPI)

| Scenariusz | Req/mc | % limitu |
|------------|--------|----------|
| 100 piłkarzy, 2x/tydzień, incremental | ~500-1,000 | **~3-5%** ✅ |
| Pełny sync (pierwszy raz) | ~1,100 | ~5.5% |
| Limit planu | 20,000 | 100% |

### Egress (Supabase)

| Scenariusz | Transfer/mc | % limitu |
|------------|-------------|----------|
| Dashboard + Search + Details | ~50-100 MB | **~1-2%** ✅ |
| Limit free tier | 5 GB | 100% |

---

## Backup & Rollback

### Co jeśli coś pójdzie nie tak?

1. **`player_stats` pozostaje** - Season Total działa niezależnie
2. **Można wyłączyć per-competition display** - wrócić do agregatu
3. **`sync_state` można zresetować** - zrobić pełny sync od nowa
4. **`synced_matches` można wyczyścić** - resync wszystkiego

### SQL Rollback (jeśli trzeba)

```sql
-- Usunąć nowe tabele (OSTROŻNIE!)
DROP TABLE IF EXISTS synced_matches;
DROP TABLE IF EXISTS sync_state;
DROP TABLE IF EXISTS player_stats_by_competition;
```

---

## Kolejność implementacji

1. **Faza 1:** Database (bezpieczne, nie rozwala nic)
2. **Faza 2:** Sync Script (najważniejsze dla ekonomii)
3. **Faza 3:** API (endpoint)
4. **Faza 4:** Frontend (UI)
5. **Faza 5:** Automatyzacja (opcjonalnie)

**Szacowany czas: ~4.5h**
