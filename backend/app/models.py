"""
ORM models for the five data entities in the proposal:
Team, Game, PowerRating, Line/Odds, Conference.

Kept intentionally simple for the MVP -- this is meant to be easy to query
from both the ingestion script and the ranking job without extra joins.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conference(Base):
    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    cfbd_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    abbreviation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(20), nullable=True)  # fbs / fcs / etc.

    teams: Mapped[list["Team"]] = relationship(back_populates="conference")

    def __repr__(self) -> str:
        return f"<Conference {self.name}>"


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    cfbd_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    school: Mapped[str] = mapped_column(String(100), index=True)
    mascot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    abbreviation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    division: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. "East"/"West", null for most
    logo_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    alternate_color: Mapped[str | None] = mapped_column(String(10), nullable=True)

    school_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    school_state: Mapped[str | None] = mapped_column(String(5), nullable=True)

    stadium_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    stadium_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    stadium_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    stadium_elevation: Mapped[float | None] = mapped_column(Float, nullable=True)
    stadium_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stadium_grass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stadium_dome: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    conference_id: Mapped[int | None] = mapped_column(ForeignKey("conferences.cfbd_id"), nullable=True)
    conference: Mapped["Conference | None"] = relationship(back_populates="teams")

    power_ratings: Mapped[list["PowerRating"]] = relationship(back_populates="team")
    home_games: Mapped[list["Game"]] = relationship(
        back_populates="home_team", foreign_keys="Game.home_team_id"
    )
    away_games: Mapped[list["Game"]] = relationship(
        back_populates="away_team", foreign_keys="Game.away_team_id"
    )

    def __repr__(self) -> str:
        return f"<Team {self.school}>"


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (UniqueConstraint("cfbd_id", name="uq_games_cfbd_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cfbd_id: Mapped[int] = mapped_column(Integer, index=True)

    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    season_type: Mapped[str] = mapped_column(String(20), default="regular")
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    neutral_site: Mapped[bool] = mapped_column(Boolean, default=False)
    conference_game: Mapped[bool] = mapped_column(Boolean, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    venue: Mapped[str | None] = mapped_column(String(150), nullable=True)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_points: Mapped[int | None] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    home_team: Mapped["Team"] = relationship(back_populates="home_games", foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(back_populates="away_games", foreign_keys=[away_team_id])
    lines: Mapped[list["Line"]] = relationship(back_populates="game", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Game {self.season} wk{self.week} {self.away_team_id}@{self.home_team_id}>"


class Line(Base):
    """One provider's betting line for one game (CFBD returns several per game)."""

    __tablename__ = "lines"
    __table_args__ = (UniqueConstraint("game_id", "provider", name="uq_lines_game_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    provider: Mapped[str] = mapped_column(String(50))  # e.g. "DraftKings", "Bovada", "consensus"

    spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    over_under: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_moneyline: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_moneyline: Mapped[int | None] = mapped_column(Integer, nullable=True)

    game: Mapped["Game"] = relationship(back_populates="lines")

    def __repr__(self) -> str:
        return f"<Line {self.provider} game={self.game_id} spread={self.spread}>"


class PowerRating(Base):
    """Weekly snapshot of a team's computed power score -- written by the ranking job, not CFBD."""

    __tablename__ = "power_ratings"
    __table_args__ = (UniqueConstraint("team_id", "season", "week", name="uq_rating_team_season_week"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)

    rating: Mapped[float] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)

    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    team: Mapped["Team"] = relationship(back_populates="power_ratings")

    def __repr__(self) -> str:
        return f"<PowerRating team={self.team_id} wk{self.week} rating={self.rating}>"