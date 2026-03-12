"""SQLAlchemy database models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Integer,
    String,
    Text,
    Numeric,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Player(Base):
    """Player model - basic player information."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rapidapi_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    position: Mapped[Optional[str]] = mapped_column(String(10))  # FW, MF, DF, GK
    team: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    league: Mapped[Optional[str]] = mapped_column(String(50))
    nationality: Mapped[str] = mapped_column(String(30), default="Poland")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    stats: Mapped[list["PlayerStats"]] = relationship(
        "PlayerStats", back_populates="player", cascade="all, delete-orphan"
    )
    stats_by_competition: Mapped[list["PlayerStatsByCompetition"]] = relationship(
        "PlayerStatsByCompetition", back_populates="player", cascade="all, delete-orphan"
    )


class PlayerStats(Base):
    """Player statistics per season with TTL cache."""

    __tablename__ = "player_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "season", name="uq_player_season"),
        Index("idx_player_stats_updated", "updated_at"),
        Index("idx_player_stats_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"))
    season: Mapped[str] = mapped_column(String(10))  # "2025/26"

    # Match stats
    matches_total: Mapped[int] = mapped_column(Integer, default=0)
    matches_started: Mapped[int] = mapped_column(Integer, default=0)
    matches_subbed: Mapped[int] = mapped_column(Integer, default=0)  # wejścia z ławki
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)

    # Attacking stats
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)
    penalties_scored: Mapped[int] = mapped_column(Integer, default=0)
    penalties_missed: Mapped[int] = mapped_column(Integer, default=0)

    # Per 90 stats (calculated)
    g_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    a_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    # Rating
    rating: Mapped[float] = mapped_column(Numeric(4, 2), default=0)

    # Goalkeeper stats
    clean_sheets: Mapped[int] = mapped_column(Integer, default=0)
    clean_sheets_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    save_percentage: Mapped[float] = mapped_column(Numeric(5, 3), default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    goals_against_per90: Mapped[float] = mapped_column(Numeric(5, 3), default=0)
    penalties_saved: Mapped[int] = mapped_column(Integer, default=0)
    penalties_conceded: Mapped[int] = mapped_column(Integer, default=0)

    # Cache
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="stats")


class League(Base):
    """League model - leagues with Polish players."""

    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rapidapi_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(50))


class PlayerStatsByCompetition(Base):
    """Player statistics per competition per season."""

    __tablename__ = "player_stats_by_competition"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "season", "competition_type", "competition_name",
            name="uq_player_season_competition"
        ),
        Index("idx_stats_comp_player", "player_id"),
        Index("idx_stats_comp_expires", "expires_at"),
        Index("idx_stats_comp_competition", "competition_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.id", ondelete="CASCADE"))
    season: Mapped[str] = mapped_column(String(10))
    competition_type: Mapped[str] = mapped_column(String(20))  # league, european, domestic
    competition_name: Mapped[str] = mapped_column(String(50))
    competition_id: Mapped[Optional[int]] = mapped_column(Integer)

    # Match stats
    matches_total: Mapped[int] = mapped_column(Integer, default=0)
    matches_started: Mapped[int] = mapped_column(Integer, default=0)
    matches_subbed: Mapped[int] = mapped_column(Integer, default=0)
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)

    # Attacking stats
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    yellow_cards: Mapped[int] = mapped_column(Integer, default=0)
    red_cards: Mapped[int] = mapped_column(Integer, default=0)

    # Per 90 & Rating
    g_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    a_per90: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    rating: Mapped[float] = mapped_column(Numeric(4, 2), default=0)

    # Goalkeeper stats (nullable)
    clean_sheets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    saves: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    save_percentage: Mapped[Optional[float]] = mapped_column(Numeric(5, 3), nullable=True)
    goals_against: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Cache
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="stats_by_competition")


class SyncState(Base):
    """Track sync progress per team/competition for incremental sync."""

    __tablename__ = "sync_state"
    __table_args__ = (
        UniqueConstraint("team_id", "competition_id", "season", name="uq_team_comp_season"),
        Index("idx_sync_state_team", "team_id"),
        Index("idx_sync_state_next", "next_sync_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(Integer)
    team_name: Mapped[Optional[str]] = mapped_column(String(100))
    competition_id: Mapped[int] = mapped_column(Integer)
    competition_name: Mapped[Optional[str]] = mapped_column(String(100))
    season: Mapped[str] = mapped_column(String(10), default="2025/26")

    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_match_id: Mapped[Optional[int]] = mapped_column(Integer)
    matches_synced: Mapped[int] = mapped_column(Integer, default=0)
    next_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class SyncedMatch(Base):
    """Track which matches have been synced to prevent duplicates."""

    __tablename__ = "synced_matches"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_match_team"),
        Index("idx_synced_matches_match", "match_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int] = mapped_column(Integer)
    competition_id: Mapped[int] = mapped_column(Integer)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
