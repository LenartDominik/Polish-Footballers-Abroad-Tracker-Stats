"""Form score calculation from player match logs (media-first MVP).

Pure functions — no DB access. The endpoint layer (Krok 7) queries the
last N match logs and feeds them here.

Scoring (per match, then averaged over the window and normalized 0–100):
- Field player: goals×3 + assists×2 + min(minutes, 90)/90 + (rating − 6.0)
- Goalkeeper:   clean_sheet×3 + min(minutes, 90)/90 + (rating − 6.0)
  Clean sheet is derived from the match score string ("2:0") + is_home —
  there is no clean_sheets column in player_match_logs.
A bench appearance (minutes=0) stays in the window as a 0-point match.
Rating is SofaScore-style (~1–10, 6 = neutral).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

GOAL_POINTS = 3
ASSIST_POINTS = 2
CLEAN_SHEET_POINTS = 3
MINUTES_WEIGHT = 1.0  # points for a full 90 minutes
RATING_BASELINE = 6.0
MAX_POINTS_PER_MATCH = 10.0  # normalization cap: avg 10 pts/match = 100


@dataclass(frozen=True)
class FormScore:
    """Normalized form score + raw components for display."""

    score: float  # 0–100
    matches_count: int
    goals: int
    assists: int
    minutes: int  # total in window
    avg_rating: float | None  # minutes-weighted; None when no rated match
    clean_sheets: int | None  # GK only; None for field players


def _get(row: Any, key: str) -> Any:
    """Read a field from an ORM object or a dict (tests, API mocks)."""
    return getattr(row, key, None) if not isinstance(row, dict) else row.get(key)


def _rating_of(row: Any) -> float | None:
    rating = _get(row, "rating")
    return float(rating) if rating is not None else None


def _is_clean_sheet(row: Any) -> bool:
    """True when the player's team conceded 0. Score format: 'H:A'."""
    score = _get(row, "score")
    if not score or ":" not in score:
        return False
    home_s, away_s = score.split(":", 1)
    if not home_s.strip().isdigit() or not away_s.strip().isdigit():
        return False
    conceded = int(away_s) if _get(row, "is_home") else int(home_s)
    return conceded == 0


def _minutes_weighted_rating(rows: Sequence[Any]) -> float | None:
    rated = [(r, _rating_of(r)) for r in rows]
    rated = [(r, rating) for r, rating in rated if rating is not None]
    if not rated:
        return None
    total_minutes = sum(_get(r, "minutes") or 0 for r, _ in rated)
    if total_minutes > 0:
        return sum(rating * (_get(r, "minutes") or 0) for r, rating in rated) / total_minutes
    return sum(rating for _, rating in rated) / len(rated)


def calculate_form_score(
    logs: Sequence[Any],
    position: str = "field",
    matches: int = 5,
) -> FormScore | None:
    """Calculate form over the last `matches` appearances (by match_date desc).

    Rows are duck-typed (PlayerMatchLog ORM objects or dicts with the same
    keys). Returns None when there are no logs (endpoint shows "no data").
    """
    if not logs:
        return None

    if matches < 1:
        raise ValueError(f"matches must be >= 1, got {matches}")

    is_gk = position == "GK"
    window = sorted(logs, key=lambda r: _get(r, "match_date"), reverse=True)[:matches]

    total_points = 0.0
    for row in window:
        minutes_part = min(_get(row, "minutes") or 0, 90) / 90 * MINUTES_WEIGHT
        rating = _rating_of(row)
        rating_part = (rating - RATING_BASELINE) if rating is not None else 0.0

        if is_gk:
            clean = CLEAN_SHEET_POINTS if _is_clean_sheet(row) else 0
            match_points = clean + minutes_part + rating_part
        else:
            match_points = (
                (_get(row, "goals") or 0) * GOAL_POINTS
                + (_get(row, "assists") or 0) * ASSIST_POINTS
                + minutes_part
                + rating_part
            )
        total_points += match_points

    avg_points = total_points / len(window)
    score = round(max(0.0, min(100.0, 100.0 * avg_points / MAX_POINTS_PER_MATCH)), 1)

    return FormScore(
        score=score,
        matches_count=len(window),
        goals=sum(_get(r, "goals") or 0 for r in window),
        assists=sum(_get(r, "assists") or 0 for r in window),
        minutes=sum(_get(r, "minutes") or 0 for r in window),
        avg_rating=_minutes_weighted_rating(window),
        clean_sheets=sum(1 for r in window if _is_clean_sheet(r)) if is_gk else None,
    )


def form_sort_key(form: FormScore) -> tuple:
    """Ranking key: score desc, tie-break avg_rating desc, then minutes desc.

    Usage: sorted(scores, key=form_sort_key, reverse=True).
    """
    return (form.score, form.avg_rating if form.avg_rating is not None else -1.0, form.minutes)
