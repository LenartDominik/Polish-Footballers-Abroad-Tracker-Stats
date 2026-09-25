"""Tests for pure functions in live_poller.py — no DB, no API, just logic."""

from datetime import date, datetime

import pytest

from app.services.live_poller import (
    _extract_events_from_match,
    _find_player_in_lineup,
    _is_team_in_match,
    _map_event_type,
    _match_is_today,
    _name_match_str,
    _parse_live_match,
    _parse_match_status,
)


class TestMapEventType:
    """Simple but critical — wrong mapping = wrong event shown to user."""

    @pytest.mark.parametrize("raw,expected", [
        ("goal", "goal"),
        ("assist", "assist"),
        ("subin", "subin"),
        ("subout", "subout"),
        ("yellowcard", "yellow_card"),
        ("yellow_card", "yellow_card"),
        ("yellow card", "yellow_card"),
        ("redcard", "red_card"),
        ("red_card", "red_card"),
        ("red card", "red_card"),
    ])
    def test_known_types(self, raw, expected):
        assert _map_event_type(raw) == expected

    def test_unknown_type_returns_none(self):
        assert _map_event_type("foul") is None
        assert _map_event_type("") is None
        assert _map_event_type("Goal") is None  # case-sensitive


class TestNameMatchStr:
    """Polish character handling — critical for Szczęsny, Kiwior, etc."""

    def test_exact_match(self):
        assert _name_match_str("Lewandowski", "Lewandowski") is True

    def test_case_insensitive(self):
        assert _name_match_str("lewandowski", "Lewandowski") is True

    def test_polish_chars_normalized(self):
        assert _name_match_str("Szczesny", "Szczęsny") is True
        assert _name_match_str("Kiwior", "Kiwior") is True

    def test_partial_match(self):
        assert _name_match_str("Robert Lewandowski", "Lewandowski") is True
        assert _name_match_str("Lewandowski", "Robert Lewandowski") is True

    def test_no_match(self):
        assert _name_match_str("Messi", "Lewandowski") is False

    def test_empty_strings(self):
        assert _name_match_str("", "Lewandowski") is False
        assert _name_match_str("Lewandowski", "") is False
        assert _name_match_str("", "") is False


class TestParseMatchStatus:
    """Parses live match data — wrong parse = wrong score/minute on frontend."""

    def test_live_match_with_score(self):
        data = {
            "status": {
                "scoreStr": "2 - 1",
                "finished": False,
                "started": True,
                "ongoing": True,
                "liveTime": {"short": "45'"},
            }
        }
        result = _parse_match_status(data)
        assert result["home_score"] == 2
        assert result["away_score"] == 1
        assert result["minute"] == "45"
        assert result["ongoing"] is True
        assert result["finished"] is False
        assert result["started"] is True

    def test_unicode_minute_stripped(self):
        data = {
            "status": {
                "scoreStr": "0 - 0",
                "liveTime": {"short": "72‎'"},
                "ongoing": True,
                "started": True,
                "finished": False,
            }
        }
        result = _parse_match_status(data)
        assert result["minute"] == "72"

    def test_smart_quote_stripped(self):
        data = {
            "status": {
                "scoreStr": "0 - 0",
                "liveTime": {"short": "90+2’"},
                "ongoing": True,
                "started": True,
                "finished": False,
            }
        }
        result = _parse_match_status(data)
        assert "’" not in result["minute"]

    def test_finished_match(self):
        data = {
            "status": {
                "scoreStr": "3 - 0",
                "finished": True,
                "started": False,
                "ongoing": False,
                "liveTime": {},
            }
        }
        result = _parse_match_status(data)
        assert result["finished"] is True
        assert result["home_score"] == 3
        assert result["away_score"] == 0

    def test_none_input(self):
        assert _parse_match_status(None) is None

    def test_empty_dict(self):
        assert _parse_match_status({}) is None

    def test_status_not_dict(self):
        assert _parse_match_status({"status": "finished"}) is None

    def test_missing_score_str(self):
        data = {
            "status": {
                "ongoing": True,
                "started": True,
                "finished": False,
                "liveTime": {"short": "15'"},
            }
        }
        result = _parse_match_status(data)
        assert result["home_score"] == 0
        assert result["away_score"] == 0
        assert result["minute"] == "15"


class TestParseLiveMatch:
    """Parses match data from different API formats."""

    def test_fixture_format(self):
        data = {
            "id": 12345,
            "home": {"name": "Barcelona", "score": 2},
            "away": {"name": "Real Madrid", "score": 1},
            "status": {"ongoing": True, "started": True},
            "tournament": {"name": "La Liga"},
        }
        result = _parse_live_match(data)
        assert result["match_id"] == 12345
        assert result["home_team"] == "Barcelona"
        assert result["away_team"] == "Real Madrid"
        assert result["home_score"] == 2
        assert result["away_score"] == 1
        assert result["status"] == "live"
        assert result["competition"] == "La Liga"

    def test_scores_array_format(self):
        data = {
            "id": 67890,
            "scores": [
                {"name": "Inter", "score": 3},
                {"name": "Roma", "score": 0},
            ],
            "status": {"ongoing": False, "started": False},
        }
        result = _parse_live_match(data)
        assert result["home_team"] == "Inter"
        assert result["away_team"] == "Roma"
        assert result["home_score"] == 3
        assert result["away_score"] == 0

    def test_score_str_fallback(self):
        data = {
            "id": 11111,
            "home": {"name": "Barcelona"},
            "away": {"name": "Sevilla"},
            "status": {"scoreStr": "1 - 0", "ongoing": True, "started": True},
        }
        result = _parse_live_match(data)
        assert result["home_score"] == 1
        assert result["away_score"] == 0

    def test_none_input(self):
        assert _parse_live_match(None) is None

    def test_no_match_id(self):
        assert _parse_live_match({"home": {"name": "A"}}) is None

    def test_event_id_fallback(self):
        data = {
            "eventId": 99999,
            "home": {"name": "A", "score": 0},
            "away": {"name": "B", "score": 0},
        }
        result = _parse_live_match(data)
        assert result["match_id"] == 99999


class TestFindPlayerInLineup:
    """Determines starting/bench/absent — wrong = wrong status on frontend."""

    def test_empty_data(self):
        assert _find_player_in_lineup(None, 123, "Test") == "absent"
        assert _find_player_in_lineup({}, 123, "Test") == "absent"

    def test_player_in_starters_by_id(self):
        data = {
            "response": {
                "lineup": {
                    "starters": [{"id": 93447, "name": "Robert Lewandowski"}],
                    "subs": [],
                }
            }
        }
        assert _find_player_in_lineup(data, 93447, "Lewandowski") == "starting"

    def test_player_in_subs_by_id(self):
        data = {
            "response": {
                "lineup": {
                    "starters": [],
                    "subs": [{"id": 93447, "name": "Robert Lewandowski"}],
                }
            }
        }
        assert _find_player_in_lineup(data, 93447, "Lewandowski") == "bench"

    def test_player_found_by_name_fallback(self):
        data = {
            "response": {
                "list": {
                    "starters": [{"name": "R. Lewandowski"}],
                    "subs": [],
                }
            }
        }
        assert _find_player_in_lineup(data, 99999, "Lewandowski") == "starting"

    def test_player_absent(self):
        data = {
            "response": {
                "lineup": {
                    "starters": [{"id": 111, "name": "Player A"}],
                    "subs": [{"id": 222, "name": "Player B"}],
                }
            }
        }
        assert _find_player_in_lineup(data, 93447, "Lewandowski") == "absent"

    def test_flat_list_format(self):
        data = {
            "response": [
                {"id": 93447, "name": "Lewandowski", "type": "sub"},
                {"id": 111, "name": "Player A"},
            ]
        }
        assert _find_player_in_lineup(data, 93447, "Lewandowski") == "bench"

    def test_flat_list_starter(self):
        data = {
            "response": [
                {"id": 93447, "name": "Lewandowski"},
            ]
        }
        assert _find_player_in_lineup(data, 93447, "Lewandowski") == "starting"


class TestMatchIsToday:
    """Date matching — wrong = missed match or false tracking."""

    def test_utc_time_today(self):
        today = date(2026, 5, 25)
        data = {"status": {"utcTime": "2026-05-25T15:00:00Z"}}
        assert _match_is_today(data, today) is True

    def test_utc_time_not_today(self):
        today = date(2026, 5, 25)
        data = {"status": {"utcTime": "2026-05-26T15:00:00Z"}}
        assert _match_is_today(data, today) is False

    def test_match_date_fallback(self):
        today = date(2026, 5, 25)
        data = {"matchDate": "2026-05-25"}
        assert _match_is_today(data, today) is True

    def test_date_with_time(self):
        today = date(2026, 5, 25)
        data = {"date": "2026-05-25T20:00:00"}
        assert _match_is_today(data, today) is True

    def test_no_date_field(self):
        assert _match_is_today({}, date.today()) is False

    def test_invalid_date(self):
        data = {"status": {"utcTime": "not-a-date"}}
        assert _match_is_today(data, date.today()) is False


class TestIsTeamInMatch:
    """Team matching — case insensitive."""

    def test_home_team(self):
        assert _is_team_in_match({"home_team": "FC Barcelona", "away_team": "Roma"}, "barcelona") is True

    def test_away_team(self):
        assert _is_team_in_match({"home_team": "Roma", "away_team": "FC Porto"}, "porto") is True

    def test_not_in_match(self):
        assert _is_team_in_match({"home_team": "Roma", "away_team": "Napoli"}, "Barcelona") is False


class TestExtractEventsFromMatch:
    """Event extraction — filters events for tracked player."""

    def test_goal_event(self):
        data = {
            "events": [
                {"type": "goal", "playerName": "Robert Lewandowski", "minute": 45, "score": "1 - 0"},
                {"type": "goal", "playerName": "Other Player", "minute": 60},
            ]
        }
        result = _extract_events_from_match(data, "Lewandowski")
        assert len(result) == 1
        assert result[0]["event_type"] == "goal"
        assert result[0]["minute"] == 45

    def test_no_events_for_player(self):
        data = {"events": [{"type": "goal", "playerName": "Other", "minute": 10}]}
        result = _extract_events_from_match(data, "Lewandowski")
        assert result == []

    def test_penalty_mapped_to_goal(self):
        data = {"events": [{"type": "penalty", "playerName": "Lewandowski", "minute": 80}]}
        result = _extract_events_from_match(data, "Lewandowski")
        assert len(result) == 1
        assert result[0]["event_type"] == "goal"

    def test_incidents_key_fallback(self):
        data = {"incidents": [{"type": "goal", "playerName": "Lewandowski", "minute": 30}]}
        result = _extract_events_from_match(data, "Lewandowski")
        assert len(result) == 1

    def test_empty_data(self):
        assert _extract_events_from_match({}, "Lewandowski") == []
        assert _extract_events_from_match({"events": []}, "Lewandowski") == []

    def test_multiple_event_types(self):
        data = {
            "events": [
                {"type": "goal", "playerName": "Lewandowski", "minute": 20},
                {"type": "yellowcard", "playerName": "Lewandowski", "minute": 55},
            ]
        }
        result = _extract_events_from_match(data, "Lewandowski")
        assert len(result) == 2
        assert result[0]["event_type"] == "goal"
        assert result[1]["event_type"] == "yellow_card"
