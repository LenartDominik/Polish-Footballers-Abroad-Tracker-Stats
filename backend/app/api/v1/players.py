"""Players API endpoints."""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.db.models import Player, PlayerStats, PlayerStatsByCompetition
from app.schemas.player import (
    PlayerOut, PlayerStatsOut, PlayerSearchOut,
    CompetitionStatsOut, PlayerDetailedStatsOut
)
import structlog

router = APIRouter()
logger = structlog.get_logger()


@router.get("/filters")
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """Get unique filter options for search autocomplete."""
    result = await db.execute(select(Player))
    players = result.scalars().all()

    names = sorted(set(p.name for p in players))
    teams = sorted(set(p.team for p in players if p.team))
    leagues = sorted(set(p.league for p in players if p.league))

    return {
        "names": names,
        "teams": teams,
        "leagues": leagues,
    }


@router.get("/", response_model=List[PlayerOut])
async def list_players(
    league: Optional[str] = Query(None, description="Filter by league"),
    team: Optional[str] = Query(None, description="Filter by team"),
    limit: int = Query(50, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """List all Polish players with optional filters."""
    query = select(Player)

    if league:
        query = query.where(Player.league.ilike(f"%{league}%"))
    if team:
        query = query.where(Player.team.ilike(f"%{team}%"))

    query = query.order_by(Player.name).limit(limit)

    result = await db.execute(query)
    players = result.scalars().all()

    return players


@router.get("/search", response_model=List[PlayerSearchOut])
async def search_players(
    name: Optional[str] = Query(None, min_length=2, description="Player name search"),
    team: Optional[str] = Query(None, description="Filter by team"),
    league: Optional[str] = Query(None, description="Filter by league"),
    limit: int = Query(20, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for Polish players abroad.

    All filters work together (AND logic between them).
    At least one filter must be provided.
    """
    if not any([name, team, league]):
        raise HTTPException(
            status_code=400,
            detail="At least one filter (name, team, or league) is required",
        )

    # Build query with AND conditions
    query = select(Player)
    if name:
        query = query.where(Player.name.ilike(f"%{name}%"))
    if team:
        query = query.where(Player.team.ilike(f"%{team}%"))
    if league:
        query = query.where(Player.league.ilike(f"%{league}%"))

    query = query.limit(limit)
    result = await db.execute(query)
    players = result.scalars().all()

    return players


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(
    player_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get player basic info by ID."""
    result = await db.execute(
        select(Player).where(Player.id == player_id)
    )
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    return player


@router.get("/{player_id}/stats", response_model=PlayerStatsOut, response_model_exclude_none=True)
async def get_player_stats(
    player_id: int,
    season: Optional[str] = Query(None, description="Season filter (default: current)"),
    db: AsyncSession = Depends(get_db),
):
    """Get player statistics for a season.

    Aggregates on-the-fly from PlayerStatsByCompetition to ensure data consistency.
    """
    if not season:
        season = "2025/26"  # Default current season

    # Get player first
    result = await db.execute(
        select(Player).where(Player.id == player_id)
    )
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Get stats by competition and aggregate on-the-fly
    result = await db.execute(
        select(PlayerStatsByCompetition).where(
            PlayerStatsByCompetition.player_id == player_id,
            PlayerStatsByCompetition.season == season,
        )
    )
    comp_stats_list = result.scalars().all()

    if not comp_stats_list:
        raise HTTPException(
            status_code=404,
            detail=f"Player stats not found for season {season}",
        )

    # Aggregate totals from all competitions
    total_matches = 0
    total_started = 0
    total_subbed = 0
    total_minutes = 0
    total_goals = 0
    total_assists = 0
    total_yellow = 0
    total_red = 0
    total_ratings = []
    total_clean_sheets = 0
    total_saves = 0
    total_goals_against = 0

    for cs in comp_stats_list:
        total_matches += cs.matches_total
        total_started += cs.matches_started
        total_subbed += cs.matches_subbed
        total_minutes += cs.minutes_played
        total_goals += cs.goals
        total_assists += cs.assists
        total_yellow += cs.yellow_cards
        total_red += cs.red_cards
        if cs.rating:
            total_ratings.append(float(cs.rating))
        if cs.clean_sheets:
            total_clean_sheets += cs.clean_sheets
        if cs.saves:
            total_saves += cs.saves
        if cs.goals_against:
            total_goals_against += cs.goals_against

    # Calculate per-90 stats
    total_g_per90 = round(total_goals * 90 / total_minutes, 2) if total_minutes > 0 else 0.0
    total_a_per90 = round(total_assists * 90 / total_minutes, 2) if total_minutes > 0 else 0.0
    avg_rating = round(sum(total_ratings) / len(total_ratings), 2) if total_ratings else 0.0

    # Goalkeeper stats only for GK position
    is_goalkeeper = player.position == "GK"

    # Calculate save percentage for GK
    save_pct = None
    if is_goalkeeper and (total_saves + total_goals_against) > 0:
        save_pct = round((total_saves / (total_saves + total_goals_against)) * 100, 1)

    # Calculate clean sheets percentage for GK
    cs_pct = None
    if is_goalkeeper and total_matches > 0:
        cs_pct = round((total_clean_sheets / total_matches) * 100, 1)

    # Calculate goals against per 90 for GK
    ga_per90 = None
    if is_goalkeeper and total_minutes > 0:
        ga_per90 = round(total_goals_against * 90 / total_minutes, 2)

    return {
        "id": comp_stats_list[0].id,  # Use first competition stat id as reference
        "player_id": player_id,
        "season": season,
        "matches_total": total_matches,
        "matches_started": total_started,
        "matches_subbed": total_subbed,
        "minutes_played": total_minutes,
        "goals": total_goals,
        "assists": total_assists,
        "yellow_cards": total_yellow,
        "red_cards": total_red,
        "rating": avg_rating,
        "player_name": player.name,
        "player_position": player.position,
        "player_team": player.team,
        "updated_at": datetime.utcnow(),  # Always show current time since we aggregate live
        # Field player stats (None for GK)
        "penalties_scored": None if is_goalkeeper else 0,  # Not tracked per competition
        "penalties_missed": None if is_goalkeeper else 0,  # Not tracked per competition
        "g_per90": None if is_goalkeeper else total_g_per90,
        "a_per90": None if is_goalkeeper else total_a_per90,
        # Goalkeeper stats (None for field players)
        "clean_sheets": total_clean_sheets if is_goalkeeper else None,
        "clean_sheets_percentage": cs_pct,
        "saves": total_saves if is_goalkeeper else None,
        "save_percentage": save_pct,
        "goals_against": total_goals_against if is_goalkeeper else None,
        "goals_against_per90": ga_per90,
        "penalties_saved": None,  # Not tracked per competition
        "penalties_conceded": None,  # Not tracked per competition
    }


@router.get("/{player_id}/detailed-stats", response_model=PlayerDetailedStatsOut, response_model_exclude_none=True)
async def get_player_detailed_stats(
    player_id: int,
    season: Optional[str] = Query(None, description="Season filter (default: current)"),
    db: AsyncSession = Depends(get_db),
):
    """Get player statistics broken down by competition."""
    if not season:
        season = "2025/26"  # Default current season

    # Get player first
    result = await db.execute(
        select(Player).where(Player.id == player_id)
    )
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Get stats by competition
    result = await db.execute(
        select(PlayerStatsByCompetition).where(
            PlayerStatsByCompetition.player_id == player_id,
            PlayerStatsByCompetition.season == season,
        )
    )
    comp_stats_list = result.scalars().all()

    if not comp_stats_list:
        raise HTTPException(
            status_code=404,
            detail=f"Player detailed stats not found for season {season}",
        )

    # Check if goalkeeper
    is_goalkeeper = player.position == "GK"

    # Helper to convert DB model to schema
    def to_comp_stats(cs: PlayerStatsByCompetition) -> CompetitionStatsOut:
        return CompetitionStatsOut(
            competition_type=cs.competition_type,
            competition_name=cs.competition_name,
            matches_total=cs.matches_total,
            matches_started=cs.matches_started,
            minutes_played=cs.minutes_played,
            goals=cs.goals,
            assists=cs.assists,
            rating=float(cs.rating) if cs.rating else 0.0,
            # Field player stats only for non-GK
            g_per90=None if is_goalkeeper else (float(cs.g_per90) if cs.g_per90 else 0.0),
            a_per90=None if is_goalkeeper else (float(cs.a_per90) if cs.a_per90 else 0.0),
            # GK stats only for goalkeepers
            clean_sheets=cs.clean_sheets if is_goalkeeper else None,
            saves=cs.saves if is_goalkeeper else None,
            save_percentage=float(cs.save_percentage) if (is_goalkeeper and cs.save_percentage is not None) else None,
            goals_against=cs.goals_against if is_goalkeeper else None,
        )

    # Categorize stats
    league_stats = None
    european_stats = []
    domestic_stats = []

    # Totals
    total_matches = 0
    total_started = 0
    total_minutes = 0
    total_goals = 0
    total_assists = 0
    total_ratings = []
    total_clean_sheets = 0
    total_saves = 0
    total_goals_against = 0

    for cs in comp_stats_list:
        comp_out = to_comp_stats(cs)

        if cs.competition_type == "league":
            league_stats = comp_out
        elif cs.competition_type == "european":
            european_stats.append(comp_out)
        elif cs.competition_type == "domestic":
            domestic_stats.append(comp_out)

        # Aggregate totals
        total_matches += cs.matches_total
        total_started += cs.matches_started
        total_minutes += cs.minutes_played
        total_goals += cs.goals
        total_assists += cs.assists
        if cs.rating:
            total_ratings.append(float(cs.rating))
        if cs.clean_sheets:
            total_clean_sheets += cs.clean_sheets
        if cs.saves:
            total_saves += cs.saves
        if cs.goals_against:
            total_goals_against += cs.goals_against

    # Calculate per-90 for total
    total_g_per90 = round(total_goals * 90 / total_minutes, 2) if total_minutes > 0 else 0.0
    total_a_per90 = round(total_assists * 90 / total_minutes, 2) if total_minutes > 0 else 0.0
    avg_rating = round(sum(total_ratings) / len(total_ratings), 2) if total_ratings else 0.0

    # Calculate save percentage for GK
    total_save_pct = None
    if is_goalkeeper and (total_saves + total_goals_against) > 0:
        total_save_pct = round((total_saves / (total_saves + total_goals_against)) * 100, 1)

    total_out = CompetitionStatsOut(
        competition_type="total",
        competition_name="Season Total",
        matches_total=total_matches,
        matches_started=total_started,
        minutes_played=total_minutes,
        goals=total_goals,
        assists=total_assists,
        rating=avg_rating,
        # Field player stats only for non-GK
        g_per90=None if is_goalkeeper else total_g_per90,
        a_per90=None if is_goalkeeper else total_a_per90,
        # GK stats only for goalkeepers
        clean_sheets=total_clean_sheets if is_goalkeeper else None,
        saves=total_saves if is_goalkeeper else None,
        save_percentage=total_save_pct,
        goals_against=total_goals_against if is_goalkeeper else None,
    )

    return PlayerDetailedStatsOut(
        player_id=player_id,
        player_name=player.name,
        player_position=player.position,
        player_team=player.team,
        season=season,
        league_stats=league_stats,
        european_stats=european_stats,
        domestic_stats=domestic_stats,
        total=total_out,
    )
