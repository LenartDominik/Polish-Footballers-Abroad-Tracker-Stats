"""Tests for season configuration - single source of truth.

Related plan: PLAN_MEDIA_FIRST_MVP.md, Krok 0 / step 1.
"""

import pytest

from app.core.config import Settings

# Minimal required fields so Settings() can be built without real secrets.
REQUIRED = {
    "database_url": "postgresql://test:test@localhost/test",
    "supabase_url": "https://test.supabase.co",
    "supabase_key": "test-key",
    "rapidapi_key": "test-key",
    "secret_key": "test-secret",
}


def _settings(**overrides) -> Settings:
    """Build Settings without reading .env (deterministic in tests)."""
    kwargs = {**REQUIRED, **overrides}
    return Settings(_env_file=None, **kwargs)


def test_current_season_defaults_to_2026_27():
    """Current season is 2026/27 (user decision, 2026-09-20).

    NOTE: deploy of this default requires 2026/27 data backfilled first,
    otherwise the production app would show an empty season.
    """
    assert _settings().current_season == "2026/27"


def test_current_season_overridable_via_env(monkeypatch: pytest.MonkeyPatch):
    """Season must be switchable via CURRENT_SEASON env var (e.g. 2027/28)."""
    monkeypatch.setenv("CURRENT_SEASON", "2027/28")
    assert _settings().current_season == "2027/28"
