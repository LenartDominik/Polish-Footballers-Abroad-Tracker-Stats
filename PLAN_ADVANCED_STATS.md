# Plan: Advanced Stats Display - Breakdown by Competition

## Cel
Wyświetlanie statystyk piłkarzy z podziałem na rozgrywki:
- **League Stats** (La Liga)
- **European Cups** (Champions League, Europa League)
- **Domestic Cups** (Copa del Rey, Supercopa)
- **Season Total** (suma wszystkich rozgrywek klubowych)

## Architektura zmian

### 1. Database Schema Changes

#### Nowa tabela: `player_stats_by_competition`
Zamiast agregować wszystko w jedną tabelę, przechowujemy stats per competition:

```sql
CREATE TABLE player_stats_by_competition (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT REFERENCES players(id) ON DELETE CASCADE,
    season VARCHAR(10) NOT NULL,              -- "2025/26"
    competition_type VARCHAR(20) NOT NULL,    -- "league", "european", "domestic"
    competition_name VARCHAR(50) NOT NULL,    -- "La Liga", "Champions League", "Copa del Rey"

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

    -- Rating
    rating NUMERIC(4,2) DEFAULT 0,

    -- Goalkeeper stats (nullable, only for GK)
    clean_sheets INT DEFAULT NULL,
    saves INT DEFAULT NULL,
    save_percentage NUMERIC(5,3) DEFAULT NULL,
    goals_against INT DEFAULT NULL,
    goals_against_per90 NUMERIC(5,3) DEFAULT NULL,

    -- Cache
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,

    UNIQUE(player_id, season, competition_type, competition_name)
);

CREATE INDEX idx_stats_comp_player ON player_stats_by_competition(player_id);
CREATE INDEX idx_stats_comp_season ON player_stats_by_competition(season);
```

#### Tabela `player_stats` - zachowujemy jako Season Total (agregacja)
- Pozostaje bez zmian, będzie przechowywać sumę wszystkich rozgrywek

### 2. SQLAlchemy Model Changes

**Plik:** `backend/app/db/models.py`

```python
class PlayerStatsByCompetition(Base):
    """Player statistics per competition per season."""

    __tablename__ = "player_stats_by_competition"
    __table_args__ = (
        UniqueConstraint("player_id", "season", "competition_type", "competition_name",
                        name="uq_player_season_competition"),
        Index("idx_stats_comp_player", "player_id"),
        Index("idx_stats_comp_season", "season"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"))
    season: Mapped[str] = mapped_column(String(10))
    competition_type: Mapped[str] = mapped_column(String(20))  # league, european, domestic
    competition_name: Mapped[str] = mapped_column(String(50))  # La Liga, Champions League

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

    # Per 90 stats
    g_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    a_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    # Rating
    rating: Mapped[float] = mapped_column(Numeric(4, 2), default=0)

    # Goalkeeper stats (nullable)
    clean_sheets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    saves: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    save_percentage: Mapped[Optional[float]] = mapped_column(Numeric(5, 3), nullable=True)
    goals_against: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    goals_against_per90: Mapped[Optional[float]] = mapped_column(Numeric(5, 3), nullable=True)

    # Cache
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="stats_by_competition")
```

### 3. Pydantic Schema Changes

**Plik:** `backend/app/schemas/player.py`

```python
class CompetitionStatsOut(BaseModel):
    """Stats for a single competition."""

    competition_type: str  # league, european, domestic
    competition_name: str  # La Liga, Champions League, Copa del Rey

    matches_total: int = 0
    matches_started: int = 0
    minutes_played: int = 0
    goals: int = 0
    assists: int = 0
    g_per90: float = 0.0
    a_per90: float = 0.0
    rating: float = 0.0

    # Goalkeeper stats (None for field players)
    clean_sheets: Optional[int] = None
    saves: Optional[int] = None
    save_percentage: Optional[float] = None
    goals_against: Optional[int] = None
    goals_against_per90: Optional[float] = None

    model_config = {"from_attributes": True}


class PlayerDetailedStatsOut(BaseModel):
    """Detailed player stats with competition breakdown."""

    player_id: int
    player_name: str
    player_position: str
    player_team: str
    season: str

    # Competition breakdown
    league_stats: Optional[CompetitionStatsOut] = None
    european_stats: List[CompetitionStatsOut] = []  # CL, EL could be multiple
    domestic_stats: List[CompetitionStatsOut] = []  # Copa del Rey, Supercopa

    # Season total (aggregated)
    total: CompetitionStatsOut

    model_config = {"from_attributes": True}
```

### 4. API Endpoint Changes

**Plik:** `backend/app/api/v1/players.py`

Nowy endpoint:
```python
@router.get("/{player_id}/detailed-stats", response_model=PlayerDetailedStatsOut)
async def get_player_detailed_stats(
    player_id: int,
    season: Optional[str] = Query(None, description="Season filter"),
    db: AsyncSession = Depends(get_db),
):
    """Get player statistics broken down by competition."""
    ...
```

### 5. Sync Script Changes

**Plik:** `backend/sync_full.py`

Główne zmiany:
- Zapisuj stats per competition do `player_stats_by_competition`
- Agreguj do `player_stats` jako Season Total
- Mapowanie competition → type:
  - La Liga → `league`
  - Champions League → `european`
  - Copa del Rey → `domestic`
  - Supercopa → `domestic`

```python
# Przykład struktury danych do zapisu
for match in matches:
    competition_type = map_competition_type(competition_name)
    # Zapisz do player_stats_by_competition
    # ...

# Po przetworzeniu wszystkich meczów
# Agreguj do player_stats (Season Total)
```

### 6. Frontend Changes

**Plik:** `frontend/app.py`

Nowa funkcja `display_player_stats()`:

```python
def display_player_stats(player_id: int, season: str = "2025/26"):
    """Display detailed stats with competition breakdown."""

    # Fetch data from API
    stats = fetch_detailed_stats(player_id, season)

    # Player header
    st.markdown(f"### {stats['player_name']} - {stats['player_team']}")

    # Create 4 columns: League | European | Domestic | Total
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**League Stats**")
        display_compact_stats(stats['league_stats'], is_gk)

    with col2:
        st.markdown("**European Cups**")
        for comp in stats['european_stats']:
            display_compact_stats(comp, is_gk)

    with col3:
        st.markdown("**Domestic Cups**")
        for comp in stats['domestic_stats']:
            st.markdown(f"*{comp['competition_name']}*")
            display_compact_stats(comp, is_gk)

    with col4:
        st.markdown("**Season Total**")
        display_compact_stats(stats['total'], is_gk)

    # Expandable details section
    with st.expander("📊 Details"):
        display_detailed_stats_table(stats)
```

---

## Kolejność implementacji

### Faza 1: Database & Models (backend)
1. [ ] Dodać model `PlayerStatsByCompetition` do `models.py`
2. [ ] Uruchomić migrację Alembic / SQL ręcznie w Supabase
3. [ ] Dodać relację w modelu `Player`

### Faza 2: Sync Script
4. [ ] Zmodyfikować `sync_full.py` aby zapisywał per competition
5. [ ] Dodać funkcję agregującą do Season Total
6. [ ] Przetestować sync lokalnie

### Faza 3: API
7. [ ] Dodać schema `CompetitionStatsOut`, `PlayerDetailedStatsOut`
8. [ ] Zaimplementować endpoint `/detailed-stats`
9. [ ] Przetestować w /docs

### Faza 4: Frontend
10. [ ] Dodać funkcję `fetch_detailed_stats()`
11. [ ] Zaimplementować `display_player_stats()` z 4 kolumnami
12. [ ] Dodać expandable details section
13. [ ] Różnicować stats dla GK vs field players

---

## Szacowany czas
- Faza 1: ~30 min
- Faza 2: ~1h
- Faza 3: ~45 min
- Faza 4: ~1.5h

**Total: ~4h**

---

## Decyzje do podjęcia
2. **Czy zachować starą tabelę `player_stats`?** - TAK, jako Season Total (agregacja)
3. **Format dat w frontend** - Uproszczony (bez dokładnej daty meczu)
