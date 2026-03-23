# Plan: Automatyczna Synchronizacja (Render Cron)

**Status:** Do implementacji po MVP
**Priorytet:** Wysoki
**Szacowany czas:** ~1h

---

## Cel

Automatyczna synchronizacja danych piłkarzy bez ręcznego uruchamiania skryptu:
- **Top ligi** (La Liga, Serie A, Premier League): 2x w tygodniu
- **Pozostałe ligi**: 1x w tygodniu

---

## Rekomendowane rozwiązanie: Render Cron Jobs

### Dlaczego Render?

| Kryterium | Render Cron | GitHub Actions | Windows Task |
|-----------|-------------|----------------|--------------|
| Koszt | **Free** | Free | Free |
| Wymaga deploy | Tak (ale już planujesz) | Nie | Nie |
| Wymaga włączonego PC | **Nie** | Nie | **Tak** |
| Konfiguracja | **Bardzo prosta** | Średnia | Skomplikowana |
| Logi | W dashboardzie | W GitHub | Lokalne pliki |
| Wszystko w jednym miejscu | **Tak** (backend + cron) | Nie | Nie |

---

## Plan działania

```
FAZA 1 (teraz)          FAZA 2 (po MVP)           FAZA 3 (produkcyjnie)
┌─────────────┐         ┌─────────────┐          ┌─────────────┐
│ Dev lokalnie│   →     │ Deploy na   │    →     │ Render Cron │
│ Ręczny sync │         │ Render      │          │ Auto sync   │
└─────────────┘         └─────────────┘          └─────────────┘
   Tydzień 1-2            Tydzień 3-4              Tydzień 5+
```

---

## Implementacja

### 1. Podział zespołów na grupy

```python
# sync_full.py - dodać na górze pliku

# Top ligi - sync 2x w tygodniu (wtorek, piątek)
# Mecze w weekendy + środku tygodnia (CL/EL)
TOP_LEAGUES_TEAMS = {
    8634,   # Barcelona (La Liga)
    8636,   # Inter (Serie A)
    # TODO: Dodać Premier League, Bundesliga, Ligue 1 gdy pojawią się polscy gracze
}

# Pozostałe ligi - sync 1x w tygodniu (czwartek)
OTHER_TEAMS = {
    203826, # Al-Duhail (Qatar)
    9773,   # Porto (Portugal)
    8721,   # Wolfsburg (2. Bundesliga)
    8188,   # Magdeburg (2. Bundesliga)
    1925,   # Göztepe (Turkey)
    8259,   # Houston (MLS)
    8595,   # Brøndby (Denmark)
    4081,   # Gaziantep (Turkey)
}
```

### 2. Nowa opcja CLI

```python
# sync_full.py - w parse_args()

parser.add_argument("--top-only", action="store_true",
                    help="Sync only top league teams (La Liga, Serie A, etc.)")
parser.add_argument("--other-only", action="store_true",
                    help="Sync only other league teams")
```

### 3. Filtrowanie teams w main()

```python
# sync_full.py - w main()

if args.top_only:
    teams_to_sync = {tid: TEAMS[tid] for tid in TOP_LEAGUES_TEAMS if tid in TEAMS}
elif args.other_only:
    teams_to_sync = {tid: TEAMS[tid] for tid in OTHER_TEAMS if tid in TEAMS}
else:
    teams_to_sync = TEAMS
```

### 4. Konfiguracja Render

**Plik:** `render.yaml`

```yaml
services:
  # Backend API
  - type: web
    name: polish-players-api
    env: python
    region: frankfurt
    plan: free
    buildCommand: "cd backend && uv sync"
    startCommand: "cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: RAPIDAPI_KEY
        sync: false
      - key: SECRET_KEY
        sync: false

  # Cron: Top ligi (wtorek + piątek 6:00 UTC = 7:00 PL)
  - type: cron
    name: sync-top-leagues
    env: python
    region: frankfurt
    plan: free
    schedule: "0 6 * * 2,5"
    buildCommand: "cd backend && uv sync"
    command: "cd backend && uv run python sync_full.py --top-only"
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: RAPIDAPI_KEY
        sync: false

  # Cron: Wszystkie ligi (czwartek 6:00 UTC = 7:00 PL)
  - type: cron
    name: sync-all-leagues
    env: python
    region: frankfurt
    plan: free
    schedule: "0 6 * * 4"
    buildCommand: "cd backend && uv sync"
    command: "cd backend && uv run python sync_full.py"
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: RAPIDAPI_KEY
        sync: false
```

---

## Harmonogram sync

| Dzień | Czas (UTC) | Czas (PL) | Co syncuje |
|-------|------------|-----------|------------|
| Wtorek | 6:00 | 7:00 | Top ligi (La Liga, Serie A) |
| Czwartek | 6:00 | 7:00 | **Wszystkie ligi** |
| Piątek | 6:00 | 7:00 | Top ligi (przed weekendem) |

### Dlaczego te godziny?

- **Wtorek** - po weekendowych meczach ligowych
- **Czwartek** - przed meczami CL/EL (środa/czwartek wieczór)
- **Piątek** - przed weekendem (ostatnie dane)

---

## Zużycie API (szacunkowe)

| Typ sync | Częstotliwość | API calls/tydzień |
|----------|---------------|-------------------|
| Top ligi | 2x | ~70 calls |
| Wszystkie | 1x | ~50 calls |
| **Total** | - | **~120 calls/tydzień** |

**Limit miesięczny:** 20,000 calls
**Zużycie:** ~480 calls/miesiąc = **2.4% limitu** ✅

---

## Monitoring

### Render Dashboard
- Logi każdego cron job
- Powiadomienia o błędach
- Historia wykonań

### Opcjonalnie: Discord/Slack webhook
```python
# sync_full.py - na końcu main()

import httpx

async def send_notification(success: bool, matches: int):
    webhook_url = os.getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        return

    status = "✅" if success else "❌"
    message = f"{status} Sync complete: {matches} matches processed"

    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json={"content": message})
```

---

## Kolejność implementacji

### Faza 1: Kod (~30 min)
- [ ] Dodać `TOP_LEAGUES_TEAMS` i `OTHER_TEAMS` do sync_full.py
- [ ] Dodać opcje `--top-only` i `--other-only`
- [ ] Przetestować lokalnie

### Faza 2: Deploy (~20 min)
- [ ] Utworzyć konto na Render
- [ ] Skonfigurować environment variables
- [ ] Zdeployować backend

### Faza 3: Cron jobs (~10 min)
- [ ] Dodać `render.yaml` do repo
- [ ] Skonfigurować cron jobs w dashboardzie
- [ ] Przetestować ręczne triggerowanie

---

## Alternatywa: GitHub Actions

Jeśli Render Cron nie zadziała, fallback:

```yaml
# .github/workflows/sync.yml
name: Sync Players

on:
  schedule:
    - cron: '0 6 * * 2,5'  # Top ligi
    - cron: '0 6 * * 4'    # Wszystkie
  workflow_dispatch:        # Ręczne triggerowanie

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: cd backend && uv sync
      - run: cd backend && uv run python sync_full.py ${{ github.event.schedule == '0 6 * * 4' && '' || '--top-only' }}
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          RAPIDAPI_KEY: ${{ secrets.RAPIDAPI_KEY }}
```

---

## Koszty

| Usługa | Plan | Koszt/miesiąc |
|--------|------|---------------|
| Render Web | Free | $0 |
| Render Cron (2 jobs) | Free | $0 |
| RapidAPI | Basic | ~$10 |
| **Total** | - | **~$10/miesiąc** |

---

## Uwagi

- **Free tier limitations** - Render free tier "spindown" po 15 min nieaktywności (pierwszy request wolniejszy)
- **Timezone** - UTC w cron, PL = UTC+1 (zima) / UTC+2 (lato)
- **Retry logic** - dodać w sync_full.py jeśli API timeout
- **Graceful degradation** - jeśli sync fails, zachować ostatnie dane
