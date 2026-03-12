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
│   └── pyproject.toml
├── frontend/               # Streamlit UI
│   ├── app.py
│   ├── pages/
│   └── requirements.txt
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
uv pip install -e ".[dev]"

# Run
uvicorn app.main:app --reload
```

### 3. Frontend

```bash
cd frontend

pip install -r requirements.txt

streamlit run app.py
```

### 4. Docker

```bash
docker-compose up
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/players/search` | Search players |
| GET | `/api/v1/players/{id}` | Get player info |
| GET | `/api/v1/players/{id}/stats` | Get player stats |
| GET | `/api/v1/players/top` | Top players by season |
| GET | `/api/v1/players/top_week` | Top players this week |
| GET | `/api/v1/leagues` | List leagues |

## Environment Variables

See `.env.example` for required variables.

## License

Proprietary - All rights reserved.
