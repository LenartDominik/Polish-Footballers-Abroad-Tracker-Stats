"""Tests for empty cache handling (bug fix: [] treated as 'no cache').

Before fix: empty list [] and empty dict {} were falsy, causing:
- _load_cache_json: row[0] check failed for [] → returned None
- get_upcoming_matches: self._upcoming_cache check failed for [] → re-fetched from API
- Result: 13 RapidAPI calls + DB writes every time /live/upcoming was called

After fix: is not None checks allow empty containers to be cached properly.
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.live_poller import LivePoller


@pytest.fixture
def poller():
    p = LivePoller()
    p._player_db_ids = {1053714: 19}
    return p


@pytest.fixture(autouse=True)
def mock_season_active():
    with patch("app.services.live_poller._is_off_season", return_value=False):
        yield


class TestUpcomingInMemoryCacheEmptyList:
    """In-memory cache should work for empty results."""

    @pytest.mark.asyncio
    async def test_empty_list_is_cached_in_memory(self, poller):
        """[] in memory cache should prevent API/DB calls."""
        poller._upcoming_cache = []
        poller._upcoming_cache_time = datetime.utcnow()
        poller._upcoming_cache_ttl = 3600

        with patch.object(poller, "_load_cache_json", AsyncMock()) as mock_db:
            result = await poller.get_upcoming_matches(limit=5)

        assert result == []
        mock_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_populated_list_is_cached_in_memory(self, poller):
        """Non-empty list in memory cache should work too (regression)."""
        poller._upcoming_cache = [{"match_id": 1, "_hours_until": 5}]
        poller._upcoming_cache_time = datetime.utcnow()
        poller._upcoming_cache_ttl = 3600

        with patch.object(poller, "_load_cache_json", AsyncMock()) as mock_db:
            result = await poller.get_upcoming_matches(limit=5)

        assert len(result) == 1
        mock_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_memory_cache_hits_db(self, poller):
        """None (initial state) should fall through to DB cache."""
        poller._upcoming_cache = None
        poller._upcoming_cache_time = None

        mock_db_data = [{"match_id": 1, "_hours_until": 5}]
        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=mock_db_data)):
            with patch.object(poller, "_save_cache_json", AsyncMock()):
                with patch("app.services.live_poller.rapidapi_client") as mock_api:
                    result = await poller.get_upcoming_matches(limit=5)

        assert len(result) == 1


class TestUpcomingDBCacheEmptyList:
    """DB cache should work for empty results."""

    @pytest.mark.asyncio
    async def test_empty_list_from_db_is_used(self, poller):
        """[] from DB cache should be returned without API calls."""
        poller._upcoming_cache = None  # Force DB cache check

        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=[])):
            with patch("app.services.live_poller.rapidapi_client") as mock_api:
                result = await poller.get_upcoming_matches(limit=5)

        assert result == []
        mock_api.get_matches_by_league.assert_not_called()

    @pytest.mark.asyncio
    async def test_populated_list_from_db_is_used(self, poller):
        """Non-empty list from DB cache should work (regression)."""
        poller._upcoming_cache = None

        db_data = [{"match_id": 1, "_hours_until": 5, "home_team": "A", "away_team": "B"}]
        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=db_data)):
            result = await poller.get_upcoming_matches(limit=5)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_none_from_db_triggers_api_fetch(self, poller):
        """None from DB (no cache) should trigger API fetch."""
        poller._upcoming_cache = None

        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=None)):
            with patch.object(poller, "_save_cache_json", AsyncMock()):
                with patch("app.services.live_poller.rapidapi_client") as mock_api:
                    mock_api.get_matches_by_league = AsyncMock(return_value=[])
                    result = await poller.get_upcoming_matches(limit=5)

        assert result == []
        mock_api.get_matches_by_league.assert_called()


class TestUpcomingSavesEmptyResult:
    """When API returns no matches, empty result should be saved to cache."""

    @pytest.mark.asyncio
    async def test_empty_result_saved_to_db(self, poller):
        """After API returns no matches, [] should be persisted to DB cache."""
        poller._upcoming_cache = None

        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=None)):
            with patch.object(poller, "_save_cache_json", AsyncMock()) as mock_save:
                with patch("app.services.live_poller.rapidapi_client") as mock_api:
                    mock_api.get_matches_by_league = AsyncMock(return_value=[])
                    result = await poller.get_upcoming_matches(limit=5)

        assert result == []
        assert poller._upcoming_cache == []
        mock_save.assert_called_once_with("upcoming_matches", [])

    @pytest.mark.asyncio
    async def test_empty_result_has_6h_ttl(self, poller):
        """Empty result should set long TTL to avoid re-fetching."""
        poller._upcoming_cache = None

        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=None)):
            with patch.object(poller, "_save_cache_json", AsyncMock()):
                with patch("app.services.live_poller.rapidapi_client") as mock_api:
                    mock_api.get_matches_by_league = AsyncMock(return_value=[])
                    await poller.get_upcoming_matches(limit=5)

        assert poller._upcoming_cache_ttl == 6 * 3600  # 6 hours


class TestLoadCacheJsonEmptyValues:
    """Test _load_cache_json handles empty containers correctly.

    Tested via mocking _load_cache_json on the poller instance
    (see TestUpcomingDBCacheEmptyList for behavior-level tests).
    Direct DB mocking of AsyncSessionLocal async context manager is fragile,
    so we test the contract: given mock return values, does the caller behave correctly?
    """

    @pytest.mark.asyncio
    async def test_empty_list_treated_as_valid_cache(self, poller):
        """Verifies the fix: [] from _load_cache_json prevents API calls."""
        poller._upcoming_cache = None

        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=[])):
            with patch("app.services.live_poller.rapidapi_client") as mock_api:
                result = await poller.get_upcoming_matches(limit=5)

        assert result == []
        mock_api.get_matches_by_league.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_treated_as_no_cache(self, poller):
        """Verifies: None from _load_cache_json triggers API fetch."""
        poller._upcoming_cache = None

        with patch.object(poller, "_load_cache_json", AsyncMock(return_value=None)):
            with patch.object(poller, "_save_cache_json", AsyncMock()):
                with patch("app.services.live_poller.rapidapi_client") as mock_api:
                    mock_api.get_matches_by_league = AsyncMock(return_value=[])
                    result = await poller.get_upcoming_matches(limit=5)

        assert result == []
        mock_api.get_matches_by_league.assert_called()
