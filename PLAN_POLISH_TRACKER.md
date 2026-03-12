
# 📋 Kompletny Plan Budowy Aplikacji: Polish Footballers Abroad Tracker

**Data utworzenia:** 07.03.2026  
**Wersja:** 2.0 (z UX/UI improvements)  
**MVP Timeline:** 1-2 tygodnie (~40h pracy)  
**Koszt miesięczny:** ~10 USD (API) + domain (~1 USD)

---

## 🎯 Cel projektu

Komercyjna aplikacja freemium do trackowania polskich piłkarzy za granicą z bogatymi statystykami (gole, xG, clean sheets, save%, etc.), cachingiem ekonomicznym, pełną responsywnością i intuicyjnym UX.

**Stack:** FastAPI (backend) + Streamlit (frontend) + Supabase PostgreSQL + RapidAPI Football (~10 USD/mc) + Render/Streamlit Cloud

---

## 📋 Spis treści

1. [Setup projektu](#1-setup-projektu)
2. [Baza Supabase PostgreSQL](#2-baza-supabase-postgresql)
3. [Backend FastAPI](#3-backend-fastapi)
4. [Frontend Streamlit](#4-frontend-streamlit)
5. [Payments Freemium](#5-payments-freemium)
6. [Deployment](#6-deployment)
7. [Landing Page + Marketing](#7-landing-page--marketing)
8. [Testy i utrzymanie](#8-testy-i-utrzymanie)
9. [Timeline MVP](#9-timeline-mvp)

---

## 1. Setup projektu (Dzień 1, 2-4h)

### Narzędzia

```bash
# uv (szybsze niż pip/poetry)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Struktura repo (monorepo)

```
polish-trackers-app/
├── backend/                    # FastAPI async
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── core/             # config, deps, security
│   │   ├── api/v1/           # endpoints: players, stats, search
│   │   ├── db/               # models, session, migrations
│   │   ├── cache/            # TTL logic
│   │   └── services/         # RapidAPI client
│   ├── Dockerfile
│   ├── requirements.txt      # uv export
│   └── pyproject.toml
├── frontend/                   # Streamlit
│   ├── app.py
│   ├── pages/
│   │   ├── 1_dashboard.py
│   │   ├── 2_search.py
│   │   └── 3_compare.py
│   └── requirements.txt
├── landing/                    # Waitlist page
├── docker-compose.yml
├── .github/workflows/ci-cd.yml
├── .env.example
└── README.md
```

### Inicjalizacja

```bash
mkdir polish-trackers-app && cd polish-trackers-app
uv init backend --app
uv init frontend --app
uv add "fastapi[standard] sqlalchemy[asyncio] asyncpg pydantic-settings httpx alembic supabase python-dotenv structlog slowapi" backend/
uv add "streamlit requests plotly pandas" frontend/
```

### Environment variables (.env)

```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
RAPIDAPI_KEY=your_rapidapi_key
STRIPE_SECRET=sk_test_...
SECRET_KEY=super-secret-key-change-in-production
```

---

## 2. Baza Supabase PostgreSQL (Dni 1-2, 4-6h)

### Schemat tabel

```sql
-- players (podstawowe dane)
CREATE TABLE players (
    id BIGSERIAL PRIMARY KEY,
    rapidapi_id INTEGER UNIQUE,        -- ID z API
    name VARCHAR(100) NOT NULL,
    position VARCHAR(10),              -- FW, MF, DF, GK
    team VARCHAR(100),
    league VARCHAR(50),
    nationality VARCHAR(30) DEFAULT 'Poland',
    photo_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- player_stats (statystyki per sezon)
CREATE TABLE player_stats (
    id BIGSERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES players(id) ON DELETE CASCADE,
    season VARCHAR(10),                -- "2025/26"
    matches_total INTEGER DEFAULT 0,
    matches_started INTEGER DEFAULT 0,
    minutes_played INTEGER DEFAULT 0,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    red_cards INTEGER DEFAULT 0,
    penalties_scored INTEGER DEFAULT 0,
    penalties_missed INTEGER DEFAULT 0,
    xg DECIMAL(5,3) DEFAULT 0,
    xa DECIMAL(5,3) DEFAULT 0,
    xg_per90 DECIMAL(5,3) DEFAULT 0,
    xa_per90 DECIMAL(5,3) DEFAULT 0,

    -- Bramkarze
    clean_sheets INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    save_percentage DECIMAL(5,3) DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goals_against_per90 DECIMAL(5,3) DEFAULT 0,
    penalties_saved INTEGER DEFAULT 0,
    penalties_conceded INTEGER DEFAULT 0,

    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,              -- TTL cache
    UNIQUE(player_id, season)
);

-- leagues (ligi z Polakami)
CREATE TABLE leagues (
    id BIGSERIAL PRIMARY KEY,
    rapidapi_id INTEGER UNIQUE,
    name VARCHAR(100),
    country VARCHAR(50),
    logo_url TEXT
);

-- Cache indexy
CREATE INDEX idx_player_stats_updated ON player_stats(updated_at);
CREATE INDEX idx_player_stats_expires ON player_stats(expires_at);
CREATE INDEX idx_players_name ON players(name);
CREATE INDEX idx_players_team ON players(team);
```

### Migracja starych danych

```bash
# 1. Export CSV z Supabase dashboard
# 2. Python script: pandas.read_csv → bulk_insert SQLAlchemy
# 3. Filtruj Polaków (nazwisko + nationality=Poland)
```

---

## 3. Backend FastAPI (Dni 2-4, 10-15h)

### Kluczowe endpoints

```
GET  /api/v1/players/search?name=szczęsny&team=&league=   # Niezależne filtry
GET  /api/v1/players/{id}/stats?season=2025/26             # Pełne stats
GET  /api/v1/players/top?season=2025/26&limit=10           # Top gracze
GET  /api/v1/players/top_week?limit=5                      # Top tydzień
GET  /api/v1/leagues                                       # Lista lig
```

### Szkielet kodu

```python
# backend/app/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.db.session import engine, init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await engine.dispose()

app = FastAPI(title="Polish Football Tracker", lifespan=lifespan)

# backend/app/api/v1/players.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.rapidapi import RapidAPIClient
from app.schemas.player import PlayerOut, PlayerStatsOut

router = APIRouter(prefix="/players", tags=["players"])

@router.get("/search")
async def search_players(
    name: str = Query(None, min_length=2),
    team: str = Query(None),
    league: str = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    # 1. Szukaj w cache (OR logika między filtrami)
    # 2. Jeśli brak/niedawno: RapidAPI /players?search=...
    # 3. Zapisz/aktualizuj DB z TTL 24h
    pass
```

### Best practices wdrożone

- ✅ Async/await + SQLAlchemy asyncpg
- ✅ Pydantic v2 models (walidacja API↔DB)
- ✅ Dependency injection (get_db)
- ✅ Rate limiting (slowapi)
- ✅ Structured logging (structlog)
- ✅ Config z Pydantic Settings
- ✅ CORS dla Streamlit
- ✅ Lifespan events (DB init/cleanup)

---

## 4. Frontend Streamlit (Dni 4-6, 12-16h)

### Layout z UX improvements

```
[🔍 SEARCH BAR (sticky)] [Klub ▼] [Liga ▼]    ← Global, niezależne

🏆 DASHBOARD (pierwsza wizyta)
│   📊 Top tygodnia: Lewandowski (FW) – 3 gole
│   📈 Wykresy xG/90, gole, asysty (Plotly)

🔍 SEARCH
│   • Autocomplete nazwisko (min 2 litery)
│   • Lista z pozycją (FW), klubem, ligą

⚖️ COMPARE (tylko pole vs pole, GK vs GK)
│   • Player 1 vs Player 2: radar chart
│   • Tabela statystyk obok siebie

📊 Legenda statystyk (expander z tooltipami)
```

### Szkielet app.py

```python
import streamlit as st
import requests
import plotly.express as px
import pandas as pd

st.set_page_config(layout="wide", page_icon="⚽")

# Custom CSS: sticky search
st.markdown("""
<style>
.search-bar { position: sticky; top: 0; z-index: 100; background: white; padding: 1rem; }
</style>
""", unsafe_allow_html=True)

# GLOBAL SEARCH BAR (priorytet #1 UX)
col1, col2, col3 = st.columns([3,2,2])
with col1: player_query = st.text_input("🔍 Wyszukaj piłkarza", key="search")
with col2: team_filter = st.selectbox("Klub", ["All"] + teams)
with col3: league_filter = st.selectbox("Liga", ["All"] + leagues)

# ONBOARDING: Top tydzień (pokazuje jak działa)
if not st.session_state.get("visited"):
    st.session_state.visited = True
    top_week = requests.get("https://api.polish-tracker.com/players/top_week").json()
    st.metric(f"🏆 Top tygodnia: {top_week[0]['name']}",
              f"{top_week[0]['goals']} goli, {top_week[0]['xg_per90']:.2f} xG/90")

# Tabs
tab1, tab2, tab3 = st.tabs(["🏆 Dashboard", "🔍 Wyszukiwarka", "⚖️ Porównaj"])

with tab1:
    # Top gracze sezonu + wykresy
    pass

with tab2:
    if player_query or team_filter != "All":
        data = fetch_search(player_query, team_filter, league_filter)
        st.dataframe(data)

with tab3:
    # Player 1 vs Player 2 (walidacja GK vs GK)
    pass

# Legenda (zawsze dostępna)
with st.expander("📊 Legenda statystyk"):
    st.markdown("""
    - **xG**: Expected Goals – szansa na gola (0-1)
    - **npxG**: xG bez karnych
    - **Save%**: % obronionych strzałów na bramkę
    """)
```

---

## 5. Payments Freemium (Dzień 6, 2-4h)

### Model

```
FREE:     Dashboard, search, podstawowe stats
PREMIUM:  Compare, powiadomienia, historyczne dane, eksport CSV
```

### Stripe (ekonomicznie)

```python
# Backend: /stripe/create-checkout
@router.post("/stripe/create-checkout")
async def create_checkout():
    stripe.api_key = settings.STRIPE_SECRET
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': 'Premium Polish Tracker'},
                'unit_amount': 990,  # 9.99 USD/mc
            }
        }],
        mode='subscription'
    )
```

> Frontend: Stripe.js via `st.components.v1.html`  
> **Alternatywa:** Lemon Squeezy (no-code payments, EU VAT included)

---

## 6. Deployment (Dni 7-8, 4-6h)

| Komponent | Platforma | Konfiguracja | Koszt |
|-----------|-----------|--------------|-------|
| Backend | Render | Docker + Uvicorn workers | Free tier → $7/mc |
| Frontend | Streamlit Cloud | GitHub direct | Free |
| Database | Supabase | PostgreSQL Pro | Free → $25/mc |
| Domain | Namecheap + Cloudflare | polish-trackers.com | ~$12/rok |

### GitHub Actions CI/CD

```yaml
name: CI/CD
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/uv@v0
      - run: uv sync --locked
      - run: uv run pytest
      - run: uv run black --check .
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Render
        run: curl https://api.render.com/deploy/srv-xxx?key=yyy
```

---

## 7. Landing Page + Marketing (Dzień 8+, 4h+)

### Strona waitlist (Streamlit Cloud)

```
[Hero: "Śledź polskich piłkarzy za granicą 👉"]
[Demo video 30s + live stats Lewandowskiego]
[Funkcje: search, compare, alerts ✓]
[Email signup: "Otrzymaj powiadomienia o golach!"]
[Waitlist: 125 osób już czeka...]
```

### Marketing automation

```python
# Cron job (Render): Wysyłaj personalizowane maile
# "Cześć! Lewandowski strzelił gola w PL – sprawdź stats!"
```

> **Tools:** Resend (1000 emaili free/mc) + Supabase table `waitlist`

---

## 8. Testy i utrzymanie

### Testy (pytest)

```python
# test_api.py
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_search():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/players/search?name=lewandowski")
        assert resp.status_code == 200
```

### Monitoring

- **Sentry:** Error tracking (free tier)
- **Supabase Dashboard:** DB usage
- **Render Metrics:** API requests

---

## 9. Timeline MVP (1-2 tygodnie)

| Dzień | Zadanie | Godziny | Status |
|-------|---------|---------|--------|
| 1 | Setup repo + Supabase schema | 4h | 🔧 |
| 2-3 | Backend core (search + cache) | 12h | 🔧 |
| 4-5 | Backend stats endpoints | 8h | 🔧 |
| 6-8 | Frontend + UX (search, dashboard) | 16h | 🔧 |
| 9 | Deployment + Stripe | 4h | 🔧 |
| 10 | Landing page + testy | 4h | ✅ |

> **Pierwsze 3 dni → działający search z cache!**

---

## 💰 Koszty startowe

| Usługa | Koszt |
|--------|-------|
| API RapidAPI | $10/mc (20000 req/month) |
| Supabase | Free (500MB) |
| Render | Free tier |
| Streamlit Cloud | Free |
| Domain | $12/rok |
| **RAZEM** | **~$12/mc start** |

---

## 🚀 Next steps po MVP

- Powiadomienia (Firebase free)
- Mobile PWA
- Admin panel (stats usage)
- Export CSV/PDF premium
