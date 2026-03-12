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
