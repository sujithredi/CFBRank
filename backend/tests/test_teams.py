"""Tests for GET /api/teams/{team_id} against an in-memory SQLite database."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app.database import Base, get_db
from app.main import app
from app.models import Conference, Game, PowerRating, Team

OHIO_LOGO = "https://cdn.collegefootballdata.com/logos/500/194.png"


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)  # no `with`: skips the lifespan, so the real DB is never touched
    app.dependency_overrides.clear()


def _game(cfbd_id, week, home, away, home_pts, away_pts, completed=True, season=2026):
    return Game(
        cfbd_id=cfbd_id, season=season, week=week, completed=completed,
        home_team_id=home.id, away_team_id=away.id,
        home_points=home_pts, away_points=away_pts,
        start_date=datetime(season, 9, week, 18, 0),
    )


@pytest.fixture()
def seeded(db):
    # Mirrors seed_teams.py: teams.conference_id holds conferences.id (the PK),
    # and the two conferences' ids deliberately differ from their cfbd_ids.
    big_ten = Conference(id=1, cfbd_id=5, name="Big Ten")
    sec = Conference(id=2, cfbd_id=8, name="SEC")
    db.add_all([big_ten, sec])
    db.flush()

    alabama = Team(id=10, cfbd_id=333, school="Alabama", conference_id=sec.id)
    ohio = Team(id=20, cfbd_id=194, school="Ohio State", logo_url=OHIO_LOGO, conference_id=big_ten.id)
    idle = Team(id=30, cfbd_id=999, school="No Ratings U", conference_id=sec.id)
    db.add_all([alabama, ohio, idle])
    db.flush()

    # Alabama: 7 finished games (limit is 5), one upcoming, one from a prior season.
    for week in range(1, 8):
        home, away = (alabama, ohio) if week % 2 else (ohio, alabama)
        # Alabama wins odd weeks 30-10, loses even weeks 17-24.
        pts = (30, 10) if week % 2 else (24, 17)
        db.add(_game(1000 + week, week, home, away, *pts))
    db.add(_game(2000, 8, alabama, ohio, None, None, completed=False))
    db.add(_game(3000, 12, alabama, ohio, 50, 0, season=2025))

    for week, rating in [(2, 20.0), (3, 25.5), (4, 31.256)]:
        # Only the latest snapshot has the offense/defense split (older ones predate it).
        split = {"offense_rating": 18.123, "defense_rating": 13.133} if week == 4 else {}
        db.add(PowerRating(team_id=alabama.id, season=2026, week=week, rating=rating,
                           rank=3, wins=week, losses=0, **split))
    db.add(PowerRating(team_id=alabama.id, season=2025, week=15, rating=5.0, rank=40, wins=6, losses=6))
    db.add(PowerRating(team_id=ohio.id, season=2026, week=4, rating=40.0, rank=1, wins=4, losses=0))
    db.commit()
    return {"alabama": alabama, "ohio": ohio, "idle": idle}


def test_returns_the_requested_team_not_a_fixed_one(client, seeded):
    alabama = client.get("/api/teams/10").json()
    ohio = client.get("/api/teams/20").json()

    assert (alabama["team"], alabama["rank"], alabama["power_score"]) == ("Alabama", 3, 31.26)
    assert (ohio["team"], ohio["rank"], ohio["power_score"]) == ("Ohio State", 1, 40.0)


def test_conference_uses_conferences_id_not_cfbd_id(client, seeded):
    assert client.get("/api/teams/10").json()["conference"] == "SEC"
    assert client.get("/api/teams/20").json()["conference"] == "Big Ten"


def test_uses_latest_snapshot_for_record(client, seeded):
    body = client.get("/api/teams/10").json()
    assert (body["wins"], body["losses"]) == (4, 0)  # week-4 row, not the 2025 one


def test_recent_results_are_last_five_finished_games_oldest_first(client, seeded):
    results = client.get("/api/teams/10").json()["recent_results"]

    assert [r["week"] for r in results] == [3, 4, 5, 6, 7]  # no upcoming, no 2025
    assert all(r["opponent"] == "Ohio State" for r in results)
    # Alabama is home on odd weeks (wins 30-10) and away on even weeks (loses 17-24).
    assert [r["result"] for r in results] == ["W 30-10", "L 17-24", "W 30-10", "L 17-24", "W 30-10"]


def test_rating_trend_is_ascending_and_limited_to_latest_season(client, seeded):
    trend = client.get("/api/teams/10").json()["rating_trend"]
    assert trend == [
        {"week": 2, "rating": 20.0},
        {"week": 3, "rating": 25.5},
        {"week": 4, "rating": 31.26},
    ]


def test_team_with_no_games_has_empty_results(client, seeded, db):
    db.add(PowerRating(team_id=seeded["idle"].id, season=2026, week=4, rating=-3.0, rank=99, wins=0, losses=0))
    db.commit()
    body = client.get("/api/teams/30").json()
    assert body["recent_results"] == []
    assert len(body["rating_trend"]) == 1


def test_unknown_team_is_404(client, seeded):
    assert client.get("/api/teams/999999").status_code == 404


def test_team_without_a_rating_is_404(client, seeded):
    response = client.get("/api/teams/30")
    assert response.status_code == 404
    assert "No Ratings U" in response.json()["detail"]


@pytest.mark.parametrize("bad_id", ["0", "-5", str(10**30), "abc"])
def test_invalid_ids_are_rejected_not_500(client, seeded, bad_id):
    assert client.get(f"/api/teams/{bad_id}").status_code == 422


def test_team_detail_includes_offense_and_defense(client, seeded):
    body = client.get("/api/teams/10").json()
    assert (body["power_score"], body["offense_rating"], body["defense_rating"]) == (31.26, 18.12, 13.13)


def test_team_detail_offense_defense_null_when_snapshot_predates_split(client, seeded):
    body = client.get("/api/teams/20").json()  # Ohio State's only snapshot has no split
    assert body["power_score"] == 40.0
    assert body["offense_rating"] is None and body["defense_rating"] is None


def test_schedule_lists_every_game_this_season_in_date_order(client, seeded):
    schedule = client.get("/api/teams/10").json()["schedule"]

    # Weeks 1-7 finished plus the week-8 game still to play; the 2025 game is left out.
    assert [g["week"] for g in schedule] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert all(g["opponent"] == "Ohio State" for g in schedule)
    assert all(g["opponent_logo_url"] == OHIO_LOGO for g in schedule)


def test_schedule_marks_home_and_away_and_the_result(client, seeded):
    schedule = client.get("/api/teams/10").json()["schedule"]
    finished = schedule[:7]

    # Alabama is home on odd weeks (wins 30-10) and away on even weeks (loses 17-24).
    assert [g["location"] for g in finished] == ["home", "away"] * 3 + ["home"]
    assert [g["outcome"] for g in finished] == ["W", "L"] * 3 + ["W"]
    assert [g["score"] for g in finished] == ["30-10", "17-24"] * 3 + ["30-10"]
    assert all(g["completed"] for g in finished)


def test_upcoming_game_has_a_date_but_no_result(client, seeded):
    upcoming = client.get("/api/teams/10").json()["schedule"][-1]

    assert upcoming["completed"] is False
    assert upcoming["outcome"] is None
    assert upcoming["score"] is None
    assert upcoming["location"] == "home"
    assert upcoming["start_date"].startswith("2026-09-08T18:00:00")
    assert upcoming["start_date"].endswith(("Z", "+00:00"))  # UTC, so the browser can localize it


def test_schedule_is_from_the_other_teams_point_of_view(client, seeded):
    schedule = client.get("/api/teams/20").json()["schedule"]

    assert schedule[0]["opponent"] == "Alabama"
    assert schedule[0]["location"] == "away"  # week 1: Alabama is home
    assert (schedule[0]["outcome"], schedule[0]["score"]) == ("L", "10-30")


def test_neutral_site_game_is_neither_home_nor_away(client, seeded, db):
    game = _game(4000, 9, seeded["alabama"], seeded["ohio"], None, None, completed=False)
    game.neutral_site = True
    db.add(game)
    db.commit()

    assert client.get("/api/teams/10").json()["schedule"][-1]["location"] == "neutral"


def test_team_with_no_games_has_an_empty_schedule(client, seeded, db):
    db.add(PowerRating(team_id=seeded["idle"].id, season=2026, week=4, rating=-3.0, rank=99, wins=0, losses=0))
    db.commit()

    assert client.get("/api/teams/30").json()["schedule"] == []
