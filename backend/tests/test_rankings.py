"""Tests for GET /api/rankings against an in-memory SQLite database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app.database import Base, get_db
from app.main import app
from app.models import Conference, PowerRating, Team

ALABAMA_LOGO = "https://cdn.collegefootballdata.com/logos/500/333.png"


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


@pytest.fixture()
def seeded(db):
    sec = Conference(id=1, cfbd_id=8, name="SEC")
    db.add(sec)
    db.flush()

    alabama = Team(id=10, cfbd_id=333, school="Alabama", logo_url=ALABAMA_LOGO, conference_id=sec.id)
    no_logo = Team(id=20, cfbd_id=999, school="No Logo U", logo_url=None, conference_id=sec.id)
    db.add_all([alabama, no_logo])
    db.flush()

    db.add(PowerRating(team_id=alabama.id, season=2026, week=4, rating=40.0, rank=1, wins=4, losses=0))
    db.add(PowerRating(team_id=no_logo.id, season=2026, week=4, rating=10.0, rank=2, wins=2, losses=2))
    db.commit()


def test_rankings_include_each_teams_logo_url(client, seeded):
    rankings = client.get("/api/rankings").json()["rankings"]

    assert rankings[0]["team"] == "Alabama"
    assert rankings[0]["logo_url"] == ALABAMA_LOGO


def test_team_without_a_logo_gets_null_not_an_error(client, seeded):
    rankings = client.get("/api/rankings").json()["rankings"]

    assert rankings[1]["team"] == "No Logo U"
    assert rankings[1]["logo_url"] is None


def test_fallback_rankings_still_serve_with_null_logos(client):
    # Empty database -> hardcoded fallback rows, which have no logo.
    response = client.get("/api/rankings")

    assert response.status_code == 200
    rankings = response.json()["rankings"]
    assert rankings
    assert all(entry["logo_url"] is None for entry in rankings)
