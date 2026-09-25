"""Tests for match log building + date/score parsers (media-first MVP, Krok 5).

Pure functions only — the DB upsert itself is verified at backfill gates
(plan Sekcja 5), not in unit tests (no test database).
"""

from datetime import UTC, datetime

from sync_full import (
    _extract_match_date,
    _extract_match_score,
    build_match_log_values,
)


class TestBuildMatchLogValues:
    """build_match_log_values: appearance determination (start/sub/bench)."""

    def test_starter_with_minutes_is_start(self):
        parsed = {
            "minutes": 90, "goals": 2, "assists": 0,
            "yellow_cards": 1, "red_cards": 0, "started": True,
        }
        values = build_match_log_values(parsed, {})
        assert values["appearance"] == "start"
        assert values["minutes"] == 90
        assert values["goals"] == 2
        assert values["yellow_cards"] == 1

    def test_sub_with_minutes_is_sub(self):
        parsed = {
            "minutes": 25, "goals": 0, "assists": 1,
            "yellow_cards": 0, "red_cards": 0, "started": False,
        }
        values = build_match_log_values(parsed, {})
        assert values["appearance"] == "sub"
        assert values["minutes"] == 25
        assert values["assists"] == 1

    def test_none_parsed_is_bench(self):
        """Parser returns None for a player without minutes and events."""
        values = build_match_log_values(None, {})
        assert values["appearance"] == "bench"
        assert values["minutes"] == 0
        assert values["goals"] == 0
        assert values["red_cards"] == 0

    def test_zero_minutes_is_bench(self):
        parsed = {
            "minutes": 0, "goals": 0, "assists": 0,
            "yellow_cards": 0, "red_cards": 0, "started": False,
        }
        values = build_match_log_values(parsed, {})
        assert values["appearance"] == "bench"
        assert values["minutes"] == 0

    def test_rating_taken_from_lineup(self):
        lineup = {"performance": {"rating": 7.4}}
        values = build_match_log_values(None, lineup)
        assert values["rating"] == 7.4

    def test_rating_string_is_converted(self):
        lineup = {"performance": {"rating": "6.8"}}
        values = build_match_log_values(None, lineup)
        assert values["rating"] == 6.8

    def test_rating_none_stays_none(self):
        values = build_match_log_values(None, {"performance": {}})
        assert values["rating"] is None

    def test_rating_garbage_is_none(self):
        lineup = {"performance": {"rating": "N/A"}}
        values = build_match_log_values(None, lineup)
        assert values["rating"] is None


class TestExtractMatchDate:
    """_extract_match_date: field names to verify at 1st real sync."""

    def test_start_timestamp_unix(self):
        expected = datetime(2026, 8, 15, 19, 0)
        ts = int(expected.replace(tzinfo=UTC).timestamp())
        assert _extract_match_date({"startTimestamp": ts}) == expected

    def test_iso_string(self):
        assert _extract_match_date({"date": "2026-08-15T19:00:00Z"}) == datetime(2026, 8, 15, 19, 0)

    def test_iso_date_only(self):
        assert _extract_match_date({"date": "2026-08-15"}) == datetime(2026, 8, 15)

    def test_no_date_returns_none(self):
        assert _extract_match_date({"id": 123}) is None

    def test_garbage_returns_none(self):
        assert _extract_match_date({"startTimestamp": "not-a-date"}) is None


class TestExtractMatchScore:
    """_extract_match_score: SofaScore-style nested + flat fallbacks."""

    def test_nested_sofascore(self):
        match = {"homeScore": {"current": 2}, "awayScore": {"current": 1}}
        assert _extract_match_score(match) == "2:1"

    def test_flat_fields(self):
        match = {"home_score": 0, "away_score": 3}
        assert _extract_match_score(match) == "0:3"

    def test_no_score_returns_none(self):
        assert _extract_match_score({"id": 123}) is None

    def test_partial_score_returns_none(self):
        match = {"homeScore": {"current": 2}, "awayScore": {}}
        assert _extract_match_score(match) is None

    def test_bool_score_ignored(self):
        """bool is a subclass of int — must not be treated as a score."""
        match = {"home_score": True, "away_score": 1}
        assert _extract_match_score(match) is None
