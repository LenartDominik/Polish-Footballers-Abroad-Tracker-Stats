"""Tests for form & match-log endpoints (media-first MVP, Krok 7).

No real DB: minimal FastAPI app + a fake session that answers select()
by entity type. Rows are real ORM objects built in-memory.
"""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import players, rankings
from app.core.config import settings
from app.db.models import Player, PlayerMatchLog
from app.db.session import get_db


def make_player(pid=1, name="Test Player", position="FW", team="Test FC"):
    return Player(id=pid, name=name, position=position, team=team, league="Test League")


def make_log(
    pid=1,
    match_id=100,
    match_date=date(2026, 9, 20),
    minutes=90,
    goals=0,
    assists=0,
    rating=None,
    score="1:1",
    is_home=True,
    appearance="start",
):
    return PlayerMatchLog(
        player_id=pid,
        match_id=match_id,
        season=settings.current_season,
        match_date=match_date,
        competition_name="Test League",
        competition_type="league",
        opponent="Opponent FC",
        is_home=is_home,
        score=score,
        minutes=minutes,
        goals=goals,
        assists=assists,
        yellow_cards=0,
        red_cards=0,
        appearance=appearance,
        rating=rating,
    )


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


class FakeDB:
    """Answers execute() by the first selected entity; tests pre-filter data."""

    def __init__(self, players=(), logs=(), ranking_rows=()):
        self.players = list(players)
        self.logs = list(logs)
        self.ranking_rows = list(ranking_rows)  # list of (PlayerMatchLog, Player)

    async def execute(self, query):
        entities = [d["entity"] for d in query.column_descriptions]
        if entities and entities[0] is PlayerMatchLog and len(entities) > 1:
            return FakeResult(self.ranking_rows)
        if entities and entities[0] is PlayerMatchLog:
            # Mirror the endpoint's order_by(match_date desc, id desc).limit(n)
            logs = sorted(self.logs, key=lambda log: (log.match_date, log.id or 0), reverse=True)
            limit = getattr(query, "_limit", None)
            return FakeResult(logs[:limit] if limit else logs)
        return FakeResult(self.players)


def make_client(db):
    app = FastAPI()
    app.include_router(players.router, prefix="/players")
    app.include_router(rankings.router, prefix="/rankings")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


class TestPlayerMatches:
    def test_returns_logs_newest_first_with_limit(self):
        logs = [
            make_log(match_id=1, match_date=date(2026, 9, 1)),
            make_log(match_id=2, match_date=date(2026, 9, 20), goals=1),
            make_log(match_id=3, match_date=date(2026, 9, 10)),
        ]
        client = make_client(FakeDB(players=[make_player()], logs=logs))

        resp = client.get("/players/1/matches?limit=2")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["match_id"] == 2  # newest first
        assert data[1]["match_id"] == 3
        assert data[0]["goals"] == 1
        assert data[0]["opponent"] == "Opponent FC"

    def test_default_limit_is_10(self):
        logs = [make_log(match_id=i, match_date=date(2026, 9, i + 1)) for i in range(15)]
        client = make_client(FakeDB(players=[make_player()], logs=logs))

        resp = client.get("/players/1/matches")

        assert resp.status_code == 200
        assert len(resp.json()) == 10

    def test_unknown_player_404(self):
        client = make_client(FakeDB(players=[]))
        assert client.get("/players/999/matches").status_code == 404

    def test_season_without_logs_returns_empty_list(self):
        client = make_client(FakeDB(players=[make_player()], logs=[]))

        resp = client.get("/players/1/matches")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_limit_zero_is_422(self):
        client = make_client(FakeDB(players=[make_player()]))
        assert client.get("/players/1/matches?limit=0").status_code == 422

    def test_limit_above_50_is_422(self):
        client = make_client(FakeDB(players=[make_player()]))
        assert client.get("/players/1/matches?limit=51").status_code == 422


class TestPlayerForm:
    def test_returns_form_score(self):
        logs = [make_log(goals=1, rating=7.0)]
        client = make_client(FakeDB(players=[make_player()], logs=logs))

        resp = client.get("/players/1/form")

        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 50.0  # 3 + 1 + 1 = 5 pts → 50/100
        assert data["matches_count"] == 1
        assert data["avg_rating"] == 7.0
        assert data["clean_sheets"] is None  # field player

    def test_no_logs_returns_null_score_with_message(self):
        client = make_client(FakeDB(players=[make_player()], logs=[]))

        resp = client.get("/players/1/form")

        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] is None
        assert "no match data" in data["message"].lower()

    def test_unknown_player_404(self):
        client = make_client(FakeDB(players=[]))
        assert client.get("/players/999/form").status_code == 404

    def test_matches_not_in_allowed_set_is_422(self):
        client = make_client(FakeDB(players=[make_player()]))
        assert client.get("/players/1/form?matches=7").status_code == 422

    def test_gk_gets_clean_sheets(self):
        gk = make_player(position="GK")
        logs = [make_log(score="2:0", is_home=True)]
        client = make_client(FakeDB(players=[gk], logs=logs))

        resp = client.get("/players/1/form")

        data = resp.json()
        assert data["clean_sheets"] == 1
        assert data["goals"] == 0


class TestFormRanking:
    def _ranking_rows(self):
        hot = make_player(pid=1, name="Hot", position="FW")
        cold = make_player(pid=2, name="Cold", position="MF")
        gk = make_player(pid=3, name="Keeper", position="GK")
        rows = [
            (make_log(pid=1, match_id=1, goals=2, rating=8.0), hot),
            (make_log(pid=2, match_id=2, minutes=20, rating=5.0), cold),
            (make_log(pid=3, match_id=3, score="0:0"), gk),
        ]
        return rows, hot, cold, gk

    def test_default_position_field_excludes_gk_and_sorts_desc(self):
        rows, hot, cold, _ = self._ranking_rows()
        client = make_client(FakeDB(ranking_rows=rows))

        resp = client.get("/rankings/form")

        assert resp.status_code == 200
        data = resp.json()
        names = [e["player_name"] for e in data]
        assert names == ["Hot", "Cold"]  # GK excluded, sorted by score desc
        assert data[0]["rank"] == 1
        assert data[0]["score"] >= data[1]["score"]

    def test_position_gk_returns_only_goalkeepers(self):
        rows, _, _, gk = self._ranking_rows()
        client = make_client(FakeDB(ranking_rows=rows))

        resp = client.get("/rankings/form?position=GK")

        data = resp.json()
        assert len(data) == 1
        assert data[0]["player_name"] == "Keeper"
        assert data[0]["clean_sheets"] == 1

    def test_invalid_position_is_422(self):
        client = make_client(FakeDB())
        assert client.get("/rankings/form?position=xyz").status_code == 422

    def test_no_logs_returns_empty_list(self):
        client = make_client(FakeDB(ranking_rows=[]))

        resp = client.get("/rankings/form")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_limit_bounds_ranking(self):
        rows, _, _, _ = self._ranking_rows()
        client = make_client(FakeDB(ranking_rows=rows))

        assert len(client.get("/rankings/form?limit=1").json()) == 1
        assert client.get("/rankings/form?limit=51").status_code == 422

    def test_entry_has_team_and_position(self):
        rows, _, _, _ = self._ranking_rows()
        client = make_client(FakeDB(ranking_rows=rows))

        entry = client.get("/rankings/form").json()[0]

        assert entry["team"] == "Test FC"
        assert entry["position"] == "FW"
