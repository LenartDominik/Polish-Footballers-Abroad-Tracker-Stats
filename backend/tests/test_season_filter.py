"""Tests for the old-season guard in sync (media-first, backfill safety).

Rule (user, 24.09.2026): sync must never process matches from a previous
season — old-season matches leaking into a --full backfill would be
stamped with the current season and corrupt the new season's aggregates.
"""

from datetime import date, datetime

from sync_full import is_in_current_season, season_start_date


class TestSeasonStartDate:
    def test_european_season_starts_august(self):
        # "2026/27" -> Aug 1, 2026 (year = left side of the slash)
        assert season_start_date("2026/27") == date(2026, 8, 1)
        assert season_start_date("2025/26") == date(2025, 8, 1)


class TestIsInCurrentSeason:
    def test_match_after_season_start_is_included(self):
        assert is_in_current_season(datetime(2026, 8, 1), "2026/27") is True
        assert is_in_current_season(datetime(2026, 9, 20), "2026/27") is True

    def test_match_before_season_start_is_excluded(self):
        # end of the previous season, e.g. May 2026
        assert is_in_current_season(datetime(2026, 5, 17), "2026/27") is False
        # day before the season window opens
        assert is_in_current_season(datetime(2026, 7, 31), "2026/27") is False

    def test_date_object_also_supported(self):
        assert is_in_current_season(date(2026, 9, 20), "2026/27") is True
        assert is_in_current_season(date(2026, 5, 17), "2026/27") is False

    def test_missing_date_is_included(self):
        # Unknown date: keep the match + warn in logs (API field name not yet
        # verified — Sekcja 3B; a hard skip could silently drop everything).
        assert is_in_current_season(None, "2026/27") is True
