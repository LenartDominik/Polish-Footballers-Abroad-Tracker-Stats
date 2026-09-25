"""Tests for weekly report endpoints (media-first MVP, Krok 7 part 2).

No real DB: fake session answers select() by entity type, applies simple
where-clauses (eq/ge/le) in memory, and captures add() calls.
"""

import operator as op
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import reports
from app.api.v1.dependencies import verify_admin_key
from app.core.config import settings
from app.db.models import Player, PlayerMatchLog, WeeklyReport
from app.db.session import get_db

EQ_GE_LE = {op.eq, op.ge, op.le, op.gt, op.lt}


def make_player(pid=1, name="Test Player", position="FW", team="Test FC"):
    return Player(id=pid, name=name, position=position, team=team, league="Test League")


def make_log(
    pid=1,
    match_id=100,
    match_date=date(2026, 9, 20),
    minutes=90,
    goals=0,
    assists=0,
):
    return PlayerMatchLog(
        player_id=pid,
        match_id=match_id,
        season=settings.current_season,
        match_date=match_date,
        competition_name="Test League",
        competition_type="league",
        opponent="Opponent FC",
        is_home=True,
        score="1:1",
        minutes=minutes,
        goals=goals,
        assists=assists,
        yellow_cards=0,
        red_cards=0,
        appearance="start",
        rating=None,
    )


def make_report(
    rid=1,
    period_start=date(2026, 9, 14),
    period_end=date(2026, 9, 20),
    status="draft",
    title="Raport tygodnia 2026-09-14 - 2026-09-20",
    editorial_comment=None,
):
    return WeeklyReport(
        id=rid,
        season=settings.current_season,
        period_start=period_start,
        period_end=period_end,
        title=title,
        editorial_comment=editorial_comment,
        status=status,
        generated_at=datetime(2026, 9, 21, 10, 0, 0),
        published_at=datetime(2026, 9, 21, 12, 0, 0) if status == "published" else None,
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
    def __init__(self, players=(), joined_rows=(), reports=()):
        self.players = list(players)
        self.joined_rows = list(joined_rows)  # list of (PlayerMatchLog, Player)
        self.reports = list(reports)
        self.added = []
        self._next_id = 100

    async def execute(self, query):
        entities = [d["entity"] for d in query.column_descriptions]
        if entities and entities[0] is WeeklyReport:
            items = self._apply_where(self.reports, query)
            limit = getattr(query, "_limit", None)
            if limit == 1:
                # /latest: newest published by period_end
                items = sorted(items, key=lambda r: r.period_end, reverse=True)
            else:
                # /archive: ascending by period_start
                items = sorted(items, key=lambda r: r.period_start)
            return FakeResult(items[:limit] if limit else items)
        if entities and entities[0] is PlayerMatchLog:
            rows = self.joined_rows
            if len(entities) > 1:  # select(PlayerMatchLog, Player) — keep tuples
                logs = self._apply_where([log for log, _ in rows], query)
                kept = {id(log) for log in logs}
                return FakeResult([row for row in rows if id(row[0]) in kept])
            items = self._apply_where([log for log, _ in rows], query)
            return FakeResult(items)
        return FakeResult(self.players)

    @staticmethod
    def _apply_where(items, query):
        clause = query.whereclause
        if clause is None:
            return items
        for c in getattr(clause, "clauses", [clause]):
            if c.operator not in EQ_GE_LE:
                continue  # fake supports simple comparisons only
            col = c.left.name
            val = getattr(c.right, "value", c.right)
            items = [i for i in items if c.operator(getattr(i, col), val)]
        return items

    def add(self, obj):
        self.added.append(obj)
        if obj.id is None:
            obj.id = self._next_id
            self._next_id += 1

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def make_client(db, admin=False):
    app = FastAPI()
    app.include_router(reports.router, prefix="/reports")
    app.dependency_overrides[get_db] = lambda: db
    if admin:
        app.dependency_overrides[verify_admin_key] = lambda: None
    return TestClient(app)


PERIOD = {"start": "2026-09-14", "end": "2026-09-20"}


class TestGenerate:
    def test_creates_draft_with_summary(self):
        rows = [
            (make_log(pid=1, match_id=1, goals=2), make_player(pid=1, name="Striker")),
            (make_log(pid=2, match_id=2, assists=1), make_player(pid=2, name="Midfielder")),
        ]
        db = FakeDB(joined_rows=rows)
        client = make_client(db, admin=True)

        resp = client.post("/reports/generate", params=PERIOD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["season"] == settings.current_season
        assert data["period_start"] == PERIOD["start"]
        assert "2026-09-14" in data["title"]
        assert data["summary"] == {
            "matches_count": 2, "players_count": 2, "goals": 2, "assists": 1,
        }
        assert len(db.added) == 1  # draft persisted

    def test_no_matches_in_period_is_400(self):
        client = make_client(FakeDB(), admin=True)

        resp = client.post("/reports/generate", params=PERIOD)

        assert resp.status_code == 400
        assert "no match data" in resp.json()["detail"].lower()

    def test_invalid_range_is_422(self):
        client = make_client(FakeDB(), admin=True)

        resp = client.post(
            "/reports/generate",
            params={"start": "2026-09-20", "end": "2026-09-14"},
        )

        assert resp.status_code == 422

    def test_regenerate_upserts_without_duplicate(self):
        existing = make_report(
            rid=5, editorial_comment="Mój komentarz", status="draft"
        )
        rows = [(make_log(pid=1, match_id=1, goals=1), make_player(pid=1))]
        db = FakeDB(joined_rows=rows, reports=[existing])
        client = make_client(db, admin=True)

        resp = client.post("/reports/generate", params=PERIOD)

        assert resp.status_code == 200
        assert resp.json()["id"] == 5  # same report, no duplicate
        assert resp.json()["editorial_comment"] == "Mój komentarz"  # preserved
        assert db.added == []  # update path, no insert

    def test_requires_admin_key(self):
        client = make_client(FakeDB(joined_rows=[]), admin=False)

        resp = client.post(
            "/reports/generate", params=PERIOD, headers={"X-Secret-Key": "wrong"}
        )

        assert resp.status_code == 401


class TestPatch:
    def test_publishes_report(self):
        draft = make_report(rid=7, status="draft")
        client = make_client(FakeDB(reports=[draft]), admin=True)

        resp = client.patch("/reports/7", json={"publish": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    def test_saves_editorial_comment(self):
        draft = make_report(rid=7, status="draft")
        client = make_client(FakeDB(reports=[draft]), admin=True)

        resp = client.patch("/reports/7", json={"editorial_comment": "Świetny tydzień"})

        assert resp.status_code == 200
        assert resp.json()["editorial_comment"] == "Świetny tydzień"
        assert resp.json()["status"] == "draft"  # not auto-published

    def test_unknown_report_404(self):
        client = make_client(FakeDB(), admin=True)
        assert client.patch("/reports/99", json={"publish": True}).status_code == 404

    def test_requires_admin_key(self):
        draft = make_report(rid=7)
        client = make_client(FakeDB(reports=[draft]), admin=False)

        resp = client.patch(
            "/reports/7", json={"publish": True}, headers={"X-Secret-Key": "wrong"}
        )

        assert resp.status_code == 401


class TestLatest:
    def test_returns_newest_published_with_matches(self):
        published = make_report(
            rid=1,
            period_start=date(2026, 9, 14),
            period_end=date(2026, 9, 20),
            status="published",
            editorial_comment="Komentarz tygodnia",
        )
        older_published = make_report(
            rid=2,
            period_start=date(2026, 9, 7),
            period_end=date(2026, 9, 13),
            status="published",
        )
        draft = make_report(rid=3, status="draft")
        rows = [
            (make_log(pid=1, match_id=1, match_date=date(2026, 9, 15), goals=1),
             make_player(pid=1, name="Striker")),
            (make_log(pid=1, match_id=2, match_date=date(2026, 9, 18)),
             make_player(pid=1, name="Striker")),
            # outside the report period — must not leak into it
            (make_log(pid=2, match_id=3, match_date=date(2026, 9, 25)),
             make_player(pid=2, name="Other")),
        ]
        client = make_client(FakeDB(joined_rows=rows, reports=[published, older_published, draft]))

        resp = client.get("/reports/latest")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["editorial_comment"] == "Komentarz tygodnia"
        assert len(data["matches"]) == 2  # only logs within the period
        assert data["matches"][0]["player_name"] == "Striker"
        assert data["matches"][0]["goals"] == 1

    def test_no_published_reports_is_404_with_message(self):
        client = make_client(FakeDB(reports=[make_report(rid=1, status="draft")]))

        resp = client.get("/reports/latest")

        assert resp.status_code == 404
        assert "no published" in resp.json()["detail"].lower()


class TestArchive:
    def test_lists_published_ascending_drafts_excluded(self):
        r1 = make_report(
            rid=2, period_start=date(2026, 9, 7),
            period_end=date(2026, 9, 13), status="published",
        )
        r2 = make_report(
            rid=1, period_start=date(2026, 9, 14),
            period_end=date(2026, 9, 20), status="published",
        )
        draft = make_report(rid=3, status="draft")
        client = make_client(FakeDB(reports=[r2, r1, draft]))

        resp = client.get("/reports/archive")

        assert resp.status_code == 200
        data = resp.json()
        assert [r["id"] for r in data] == [2, 1]  # ascending by period_start
        assert all(r["status"] == "published" for r in data)

    def test_empty_archive_returns_empty_list(self):
        client = make_client(FakeDB())

        resp = client.get("/reports/archive")

        assert resp.status_code == 200
        assert resp.json() == []
