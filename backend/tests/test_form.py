"""Tests for form score calculation (media-first MVP, Krok 6).

Pure functions on duck-typed match log rows — no DB. Rows mimic
PlayerMatchLog columns (minutes, goals, assists, rating, score, is_home,
match_date). The DB query itself is Krok 7 (endpoints).
"""

from datetime import date

from app.services.form import FormScore, calculate_form_score, form_sort_key


def make_log(
    match_date: date,
    minutes: int = 90,
    goals: int = 0,
    assists: int = 0,
    rating: float | None = None,
    score: str | None = "1:1",
    is_home: bool = True,
    appearance: str = "start",
):
    """Build a minimal PlayerMatchLog-like row for tests."""
    return {
        "match_date": match_date,
        "minutes": minutes,
        "goals": goals,
        "assists": assists,
        "rating": rating,
        "score": score,
        "is_home": is_home,
        "appearance": appearance,
    }


class TestFieldPlayerScore:
    """Field: goals×3 + assists×2 + minutes/90 + (rating−6), normalized 0–100."""

    def test_goal_and_assist_weights(self):
        # points = 1×3 (goal) + 0×2 + 90/90 + (7.0−6.0) = 5.0 → 5/10 = 50
        log = make_log(date(2026, 9, 20), goals=1, rating=7.0)
        result = calculate_form_score([log], position="field")
        assert result.score == 50.0
        assert result.goals == 1

    def test_assist_worth_two_thirds_of_goal(self):
        # 1 assist: 0 + 2 + 1 + 0 = 3.0 → 30
        log = make_log(date(2026, 9, 20), assists=1)
        result = calculate_form_score([log], position="field")
        assert result.score == 30.0

    def test_no_goal_no_assist_no_rating_is_low(self):
        # 0 + 0 + 1 + 0 = 1.0 → 10
        log = make_log(date(2026, 9, 20), rating=None)
        result = calculate_form_score([log], position="field")
        assert result.score == 10.0

    def test_rating_below_six_subtracts(self):
        # 0 + 0 + 1 + (4.0−6.0) = −1.0 → clamped to 0
        log = make_log(date(2026, 9, 20), rating=4.0)
        result = calculate_form_score([log], position="field")
        assert result.score == 0.0

    def test_score_capped_at_100(self):
        # 2 goals + 1 assist + 90' + rating 9: 6+2+1+3 = 12 → 120 → 100
        log = make_log(date(2026, 9, 20), goals=2, assists=1, rating=9.0)
        result = calculate_form_score([log], position="field")
        assert result.score == 100.0

    def test_minutes_capped_at_90_per_match(self):
        # 120' (extra time) counts as 1.0, same as 90'
        log = make_log(date(2026, 9, 20), minutes=120, rating=None)
        result = calculate_form_score([log], position="field")
        assert result.score == 10.0

    def test_averages_over_multiple_matches(self):
        # match A: 3+2+1+0 = 6.0; match B: 0+0+1+0 = 1.0 → avg 3.5 → 35
        logs = [
            make_log(date(2026, 9, 20), goals=1, assists=1),
            make_log(date(2026, 9, 13), rating=None),
        ]
        result = calculate_form_score(logs, position="field")
        assert result.score == 35.0
        assert result.matches_count == 2
        assert result.minutes == 180


class TestLastNMatches:
    """Form window = last N matches by match_date desc."""

    def test_older_matches_excluded_from_window(self):
        # 6 matches: oldest has 3 goals — must not count with matches=5
        old = make_log(date(2026, 8, 1), goals=3, rating=9.5)
        recent = [make_log(date(2026, 9, d), rating=None) for d in range(15, 20)]
        result = calculate_form_score(recent + [old], position="field", matches=5)
        assert result.matches_count == 5
        assert result.goals == 0

    def test_bench_row_counts_as_zero_point_appearance(self):
        # bench = 0 points but stays in the window (matches_count, dilution)
        logs = [
            make_log(date(2026, 9, 20), goals=1, rating=7.0),  # 5.0
            make_log(date(2026, 9, 13), minutes=0, appearance="bench"),
        ]
        result = calculate_form_score(logs, position="field")
        assert result.matches_count == 2
        assert result.score == 25.0  # avg(5.0, 0.0) = 2.5 → 25

    def test_input_order_does_not_matter(self):
        # same two matches as test_averages_over_multiple_matches but goal-only:
        # 5.0 + 1.0 = avg 3.0 → 30 — order of input must not change it
        shuffled = [
            make_log(date(2026, 9, 13), rating=None),
            make_log(date(2026, 9, 20), goals=1, rating=7.0),
        ]
        result = calculate_form_score(shuffled, position="field")
        assert result.score == 30.0


class TestGoalkeeperScore:
    """GK: clean_sheet×3 + minutes/90 + (rating−6)."""

    def test_home_clean_sheet(self):
        # home "2:0" → conceded 0: 3 + 1 + (7.0−6.0) = 5.0 → 50
        log = make_log(date(2026, 9, 20), rating=7.0, score="2:0", is_home=True)
        result = calculate_form_score([log], position="GK")
        assert result.score == 50.0
        assert result.clean_sheets == 1

    def test_away_clean_sheet(self):
        # away "0:0" → conceded 0
        log = make_log(date(2026, 9, 20), rating=6.0, score="0:0", is_home=False)
        result = calculate_form_score([log], position="GK")
        assert result.score == 40.0  # 3 + 1 + 0

    def test_goals_conceded_is_not_clean_sheet(self):
        # home "2:1" → conceded 1: 0 + 1 + (7.0−6.0) = 2.0 → 20
        log = make_log(date(2026, 9, 20), rating=7.0, score="2:1", is_home=True)
        result = calculate_form_score([log], position="GK")
        assert result.score == 20.0
        assert result.clean_sheets == 0

    def test_missing_score_is_not_clean_sheet(self):
        log = make_log(date(2026, 9, 20), rating=None, score=None)
        result = calculate_form_score([log], position="GK")
        assert result.score == 10.0  # 0 + 1 + 0

    def test_gk_goals_not_counted(self):
        # GK scoring a goal does not inflate form (field weighting skipped)
        log = make_log(date(2026, 9, 20), goals=1, rating=6.0, score="1:0")
        result = calculate_form_score([log], position="GK")
        assert result.score == 40.0  # 3 (CS) + 1 + 0 — not 3+3+1


class TestEmptyAndEdge:
    def test_no_matches_returns_none(self):
        assert calculate_form_score([], position="field") is None
        assert calculate_form_score([], position="GK") is None


class TestInvalidWindow:
    """matches < 1 is an endpoint bug — must fail loudly, not 500 or lie."""

    def test_matches_zero_raises(self):
        import pytest

        log = make_log(date(2026, 9, 20))
        with pytest.raises(ValueError):
            calculate_form_score([log], position="field", matches=0)

    def test_negative_matches_raises(self):
        import pytest

        log = make_log(date(2026, 9, 20))
        with pytest.raises(ValueError):
            calculate_form_score([log], position="field", matches=-1)


class TestAverageRating:
    def test_avg_rating_is_minutes_weighted(self):
        # (8.0×90 + 6.0×30) / 120 = 7.5
        logs = [
            make_log(date(2026, 9, 20), minutes=90, rating=8.0),
            make_log(date(2026, 9, 13), minutes=30, rating=6.0),
        ]
        result = calculate_form_score(logs, position="field")
        assert result.avg_rating == 7.5

    def test_avg_rating_none_when_no_rated_match(self):
        logs = [make_log(date(2026, 9, 20), rating=None)]
        result = calculate_form_score(logs, position="field")
        assert result.avg_rating is None


class TestSortKey:
    """Ranking: score desc; tie-break avg_rating, then minutes."""

    def test_higher_score_sorts_first(self):
        weaker = FormScore(score=30.0, matches_count=5, goals=0, assists=0,
                           minutes=450, avg_rating=6.5, clean_sheets=None)
        stronger = FormScore(score=50.0, matches_count=5, goals=1, assists=0,
                             minutes=450, avg_rating=7.0, clean_sheets=None)
        ranked = sorted([weaker, stronger], key=form_sort_key, reverse=True)
        assert ranked[0] is stronger

    def test_tie_broken_by_avg_rating(self):
        low_rating = FormScore(score=40.0, matches_count=5, goals=0, assists=0,
                               minutes=450, avg_rating=6.2, clean_sheets=None)
        high_rating = FormScore(score=40.0, matches_count=5, goals=0, assists=0,
                                minutes=450, avg_rating=7.4, clean_sheets=None)
        ranked = sorted([low_rating, high_rating], key=form_sort_key, reverse=True)
        assert ranked[0] is high_rating

    def test_double_tie_broken_by_minutes(self):
        starter = FormScore(score=40.0, matches_count=5, goals=0, assists=0,
                            minutes=450, avg_rating=7.0, clean_sheets=None)
        super_sub = FormScore(score=40.0, matches_count=5, goals=0, assists=0,
                              minutes=200, avg_rating=7.0, clean_sheets=None)
        ranked = sorted([super_sub, starter], key=form_sort_key, reverse=True)
        assert ranked[0] is starter

    def test_avg_rating_none_sorts_last_on_tie(self):
        rated = FormScore(score=40.0, matches_count=5, goals=0, assists=0,
                          minutes=450, avg_rating=6.0, clean_sheets=None)
        unrated = FormScore(score=40.0, matches_count=5, goals=0, assists=0,
                            minutes=450, avg_rating=None, clean_sheets=None)
        ranked = sorted([unrated, rated], key=form_sort_key, reverse=True)
        assert ranked[0] is rated
