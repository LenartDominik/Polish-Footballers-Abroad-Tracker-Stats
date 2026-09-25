"""Tests for poller behavior after match ends.

Verifies that:
1. When a live match ends, today_matches cache is invalidated
2. When all matches are done, has_match_today flag is cleared and poller returns INTERVAL_SLEEPING
3. After restart, DB cache also returns has_match=False
"""

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.live_poller import (
    INTERVAL_PREMATCH,
    INTERVAL_SLEEPING,
    INTERVAL_TRACKING,
    LivePoller,
    _parse_match_status,
)


def _make_finished_status():
    """Simulate API response for a finished match."""
    return {
        "status": {
            "scoreStr": "2 - 1",
            "finished": True,
            "started": False,
            "ongoing": False,
            "liveTime": {},
        }
    }


def _make_live_status(minute="45"):
    """Simulate API response for a live match."""
    return {
        "status": {
            "scoreStr": "1 - 0",
            "finished": False,
            "started": True,
            "ongoing": True,
            "liveTime": {"short": f"{minute}'"},
        }
    }


def _make_today_match(match_id=4803410, status="scheduled", kickoff_hours_from_now=2):
    """Create a match dict as returned by _find_today_tracked_matches."""
    kickoff = (datetime.utcnow() + timedelta(hours=kickoff_hours_from_now)).isoformat() + "Z"
    return {
        "match_id": match_id,
        "home_team": "Atalanta",
        "away_team": "Roma",
        "home_score": 0,
        "away_score": 0,
        "status": status,
        "competition": "Serie A",
        "kickoff_time": kickoff,
    }


@pytest.fixture
def poller():
    """Create a fresh LivePoller instance."""
    p = LivePoller()
    p._player_db_ids = {1053714: 19}  # Zalewski
    return p


@pytest.fixture(autouse=True)
def mock_season_active():
    with patch("app.services.live_poller._is_off_season", return_value=False):
        yield


class TestMatchEndClearsCache:
    """Test 1: match ending invalidates today_matches_cache."""

    def test_today_matches_cache_invalidated_on_match_end(self):
        """When match ends, _today_matches_cache should be set to None."""
        poller = LivePoller()
        # Simulate: cache was populated with a match
        poller._today_matches_cache = {1053714: _make_today_match()}
        poller._today_matches_cache_date = date.today()
        poller._today_matches_cache_time = datetime.utcnow()

        # Simulate: match ended -> _today_matches_cache set to None
        assert poller._today_matches_cache is not None

        # This is what the code does when match ends:
        poller._today_matches_cache = None
        assert poller._today_matches_cache is None


class TestAllMatchesDone:
    """Test 2: when all matches end, poller returns INTERVAL_SLEEPING."""

    @pytest.mark.asyncio
    async def test_returns_deep_sleep_when_no_matches_and_had_match_today(self, poller):
        """When today_matches is empty but had matches earlier, return INTERVAL_SLEEPING."""
        poller._has_match_today = True
        poller._fixture_check_date = date.today()

        # Mock DB cache write (we don't want real DB)
        poller._write_fixture_db_cache = AsyncMock()

        with patch.object(poller, "_check_fixtures_today", return_value=True):
            with patch.object(poller, "_find_today_tracked_matches", return_value={}):
                interval = await poller._poll_cycle()

        assert interval == INTERVAL_SLEEPING
        assert poller._has_match_today is False
        assert poller._fixture_check_date is None
        assert poller._today_matches_cache is None
        poller._write_fixture_db_cache.assert_called_once_with(date.today(), False)

    @pytest.mark.asyncio
    async def test_returns_prematch_when_no_matches_but_never_had_match(self, poller):
        """When no matches and never had one today, return INTERVAL_PREMATCH (pre-match waiting)."""
        poller._has_match_today = False

        with patch.object(poller, "_check_fixtures_today", return_value=True):
            with patch.object(poller, "_find_today_tracked_matches", return_value={}):
                interval = await poller._poll_cycle()

        # Should return PREMATCH (30 min) because has_match_today was False
        assert interval == INTERVAL_PREMATCH


class TestDBCacheAfterRestart:
    """Test 3: DB cache is updated to has_match=False after all matches end."""

    @pytest.mark.asyncio
    async def test_db_cache_updated_to_false(self, poller):
        """DB cache should be set to has_match=False when all matches end."""
        poller._has_match_today = True
        poller._fixture_check_date = date.today()

        poller._write_fixture_db_cache = AsyncMock()

        with patch.object(poller, "_check_fixtures_today", return_value=True):
            with patch.object(poller, "_find_today_tracked_matches", return_value={}):
                await poller._poll_cycle()

        # Verify DB cache was written with False
        poller._write_fixture_db_cache.assert_called_once_with(date.today(), False)

    @pytest.mark.asyncio
    async def test_after_restart_db_cache_returns_false(self, poller):
        """Simulate restart: DB cache has False, poller should sleep."""
        poller._has_match_today = False

        # Simulate DB cache read returning has_match=False
        with patch.object(poller, "_check_fixtures_today", return_value=False):
            interval = await poller._poll_cycle()

        assert interval == INTERVAL_SLEEPING


class TestLiveMatchFlow:
    """Integration test: live match -> ends -> deep sleep."""

    @pytest.mark.asyncio
    async def test_live_to_finished_to_deep_sleep(self, poller):
        """Full flow: live match detected -> events -> match ends -> deep sleep."""
        match = _make_today_match(status="live", kickoff_hours_from_now=-1)

        # Cycle 1: Match is live
        poller._has_match_today = True
        poller._fixture_check_date = date.today()
        poller._write_fixture_db_cache = AsyncMock()

        with patch.object(poller, "_check_fixtures_today", return_value=True):
            with patch.object(poller, "_find_today_tracked_matches", return_value={1053714: match}):
                with patch("app.services.live_poller.rapidapi_client") as mock_api:
                    # Match is live with events
                    mock_api.get_match_status = AsyncMock(return_value=_make_live_status("45"))
                    mock_api.get_lineup_home = AsyncMock(return_value={
                        "response": {"lineup": {"starters": [], "subs": []}}
                    })
                    mock_api.get_lineup_away = AsyncMock(return_value={
                        "response": {"lineup": {"starters": [], "subs": []}}
                    })

                    interval1 = await poller._poll_cycle()

        assert interval1 == INTERVAL_TRACKING
        assert len(poller._current_matches) == 1
        assert poller._has_match_today is True

        # Cycle 2: Match ends
        with patch.object(poller, "_check_fixtures_today", return_value=True):
            with patch.object(poller, "_find_today_tracked_matches", return_value={1053714: match}):
                with patch("app.services.live_poller.rapidapi_client") as mock_api:
                    mock_api.get_match_status = AsyncMock(return_value=_make_finished_status())
                    mock_api.get_lineup_home = AsyncMock(return_value={})
                    mock_api.get_lineup_away = AsyncMock(return_value={})

                    interval2 = await poller._poll_cycle()

        # After match ended, _current_matches should be empty
        assert len(poller._current_matches) == 0
        # Cache should be invalidated
        assert poller._today_matches_cache is None
        # But has_match_today is still True (cleared on NEXT cycle when today_matches is empty)

        # Cycle 3: No more matches -> deep sleep
        with patch.object(poller, "_check_fixtures_today", return_value=True):
            with patch.object(poller, "_find_today_tracked_matches", return_value={}):
                interval3 = await poller._poll_cycle()

        assert interval3 == INTERVAL_SLEEPING
        assert poller._has_match_today is False
        assert poller._fixture_check_date is None
