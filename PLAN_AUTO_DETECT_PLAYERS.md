# Plan: Automatyczne Wykrywanie Polskich Piłkarzy

**Status:** Po MVP
**Priorytet:** Średni
**Szacowany czas:** ~3h

---

## Cel

Zastąpienie hardcoded listy `POLISH_PLAYERS` automatycznym wykrywaniem Polaków podczas sync.

---

## Obecny problem

```python
# sync_full.py - hardcoded, nie skaluje się
POLISH_PLAYERS = {
    93447: "Robert Lewandowski",
    169718: "Wojciech Szczęsny",
}
```

**Wady:**
- Ręczne dodawanie każdego piłkarza
- Trzeba znać `rapidapi_id` z góry
- Nie skaluje się do 50-100+ piłkarzy

---

## Nowa architektura

### 1. Nowa tabela: `tracked_teams`

```sql
CREATE TABLE tracked_teams (
    id SERIAL PRIMARY KEY,
    rapidapi_id INT UNIQUE NOT NULL,
    name VARCHAR(100),
    league VARCHAR(50),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tracked_teams_active ON tracked_teams(is_active);
```

### 2. Modyfikacja sync_full.py

```python
# Zamiast hardcoded TEAMS i POLISH_PLAYERS:

async def get_tracked_teams(session) -> list[dict]:
    """Pobierz aktywne zespoły z bazy."""
    result = await session.execute(
        select(TrackedTeam).where(TrackedTeam.is_active == True)
    )
    return result.scalars().all()


async def detect_polish_players(lineup: dict) -> list[dict]:
    """Wykryj Polaków w lineup na podstawie nationality."""
    polish_players = []

    for player in lineup.get("starters", []) + lineup.get("subs", []):
        nationality = player.get("nationality", "")
        if nationality and "poland" in nationality.lower():
            polish_players.append(player)

    return polish_players


async def upsert_player(session, player_data: dict) -> Player:
    """Dodaj lub zaktualizuj piłkarza."""
    rapidapi_id = player_data.get("id")

    result = await session.execute(
        select(Player).where(Player.rapidapi_id == rapidapi_id)
    )
    player = result.scalar_one_or_none()

    if not player:
        player = Player(
            rapidapi_id=rapidapi_id,
            name=player_data.get("name"),
            position=map_position(player_data.get("positionId")),
            team=player_data.get("teamName"),
            league="Multiple",
        )
        session.add(player)
        await session.flush()
    else:
        # Aktualizuj dane
        player.name = player_data.get("name", player.name)
        player.team = player_data.get("teamName", player.team)

    return player
```

### 3. Admin API endpoints

**Plik:** `backend/app/api/v1/admin.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/teams")
async def add_tracked_team(
    rapidapi_id: int,
    name: str,
    league: str,
    db: AsyncSession = Depends(get_db),
):
    """Dodaj zespół do śledzenia."""
    # Implementacja
    pass


@router.delete("/teams/{team_id}")
async def remove_tracked_team(
    team_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Przestań śledzić zespół."""
    # Implementacja
    pass


@router.get("/players")
async def list_all_players(
    db: AsyncSession = Depends(get_db),
):
    """Lista wszystkich wykrytych Polaków."""
    # Implementacja
    pass


@router.post("/sync")
async def trigger_sync(
    full: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Ręcznie triggeruj sync."""
    # Implementacja
    pass
```

### 4. Frontend Admin (Streamlit)

**Plik:** `frontend/pages/4_Admin.py`

```python
import streamlit as st

st.title("⚙️ Admin Panel")

# Dodawanie zespołu
st.subheader("Dodaj zespół do śledzenia")
with st.form("add_team"):
    team_name = st.text_input("Nazwa zespołu")
    league = st.selectbox("Liga", ["La Liga", "Premier League", "Serie A", "Bundesliga", "Ligue 1"])
    submitted = st.form_submit_button("Dodaj")
    if submitted:
        # API call
        st.success(f"Dodano {team_name}")

# Lista śledzonych zespołów
st.subheader("Śledzone zespoły")
# API call to get teams
st.dataframe([])

# Przycisk sync
if st.button("🔄 Uruchom sync"):
    # API call to trigger sync
    st.info("Sync uruchomiony...")
```

---

## Kolejność implementacji

### Faza 1: Database (~30 min)
- [ ] Stworzyć tabelę `tracked_teams`
- [ ] Dodać model SQLAlchemy
- [ ] Zmigrować dane z hardcoded TEAMS

### Faza 2: Sync refactor (~1h)
- [ ] `get_tracked_teams()` - pobieranie z bazy
- [ ] `detect_polish_players()` - wykrywanie po nationality
- [ ] `upsert_player()` - dodawanie/aktualizacja
- [ ] Usunąć hardcoded POLISH_PLAYERS

### Faza 3: Admin API (~45 min)
- [ ] `POST /admin/teams`
- [ ] `DELETE /admin/teams/{id}`
- [ ] `GET /admin/players`
- [ ] `POST /admin/sync`

### Faza 4: Frontend Admin (~45 min)
- [ ] Strona `4_Admin.py`
- [ ] Formularz dodawania zespołów
- [ ] Lista śledzonych zespołów
- [ ] Przycisk trigger sync

---

## Korzyści

| Aspekt | Przed | Po |
|--------|-------|-----|
| Dodawanie piłkarza | Ręcznie w kodzie | Automatycznie |
| Skalowalność | 2-5 piłkarzy | 50-200+ piłkarzy |
| Utrzymanie | Edycja kodu | Admin panel |
| Czas dodania | 10-15 min | Automatycznie |

---

## Uwagi

- **Nationality field** - API może nie zawsze zwracać poprawnie, trzeba fallback
- **Deduplikacja** - ten sam piłkarz może być w wielu meczach
- **Historia** - przy usunięciu zespółu, zachować dane historyczne
