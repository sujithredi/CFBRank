"""Season projections in GET /api/rankings, and saving them (save_season_projections)."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app.database import Base, get_db
from app.main import app
from app.models import Conference, Game, PowerRating, SeasonProjection, Team
from app.season_simulation import (
    RESULT_COLUMNS,
    load_season_inputs,
    save_season_projections,
    simulate_season,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    db.add(Conference(id=1, cfbd_id=8, name="SEC"))
    db.flush()
    db.add_all([
        Team(id=10, cfbd_id=1, school="Alabama", classification="fbs", conference_id=1),
        Team(id=20, cfbd_id=2, school="Auburn", classification="fbs", conference_id=1),
        Team(id=30, cfbd_id=3, school="Idaho State", classification="fcs"),
    ])
    db.flush()
    db.add_all([
        PowerRating(team_id=10, season=2026, week=6, rating=15, rank=1, wins=2, losses=0,
                    offense_rating=9.0, defense_rating=6.0),
        PowerRating(team_id=20, season=2026, week=6, rating=3, rank=2, wins=0, losses=1,
                    offense_rating=1.0, defense_rating=2.0),
        PowerRating(team_id=30, season=2026, week=6, rating=-9, rank=3, wins=0, losses=1,
                    offense_rating=-5.0, defense_rating=-4.0),
    ])
    db.add_all([
        Game(cfbd_id=1, season=2026, week=1, season_type="regular", completed=True,
             home_team_id=10, away_team_id=30, home_points=56, away_points=3),
        Game(cfbd_id=2, season=2026, week=2, season_type="regular", completed=True,
             home_team_id=20, away_team_id=10, home_points=17, away_points=24),
        Game(cfbd_id=3, season=2026, week=8, season_type="regular", completed=False,
             home_team_id=10, away_team_id=20),
    ])
    db.commit()


CFP_FIELDS = ["cfp_bye_pct", "cfp_quarterfinal_pct", "cfp_semifinal_pct", "cfp_final_pct", "cfp_champion_pct"]


def _entries(client, **params):
    body = client.get("/api/rankings", params=params).json()
    return body, {entry["team"]: entry for entry in body["rankings"]}


# ---- the endpoint ----------------------------------------------------------

def test_rankings_have_no_projection_fields_until_the_simulation_has_run(client, seeded):
    body, entries = _entries(client)
    assert body["simulations"] is None
    for entry in entries.values():
        assert entry["projected_wins"] is None
        assert entry["projected_losses"] is None
        assert entry["bowl_pct"] is None
        assert entry["undefeated_pct"] is None
        assert entry["title_game_pct"] is None
        assert entry["conf_champ_pct"] is None
        assert entry["playoff_pct"] is None
        for field in CFP_FIELDS:
            assert entry[field] is None


def test_rankings_include_each_teams_projection(client, db, seeded):
    db.add_all([
        SeasonProjection(team_id=10, season=2026, week=6, n_simulations=10000,
                         avg_wins=10.456, avg_losses=1.544, bowl_pct=99.987, undefeated_pct=31.234,
                         title_game_pct=88.888, conf_champ_pct=61.111, playoff_pct=71.234,
                         cfp_bye_pct=20.049, cfp_quarterfinal_pct=55.557, cfp_semifinal_pct=33.333,
                         cfp_final_pct=19.999, cfp_champion_pct=11.111),
        SeasonProjection(team_id=30, season=2026, week=6, n_simulations=10000,
                         avg_wins=1.2, avg_losses=9.8, bowl_pct=None, undefeated_pct=0.0),
    ])
    db.commit()

    body, entries = _entries(client)
    assert body["simulations"] == 10000

    alabama = entries["Alabama"]
    assert alabama["projected_wins"] == 10.46
    assert alabama["projected_losses"] == 1.54
    assert alabama["bowl_pct"] == 99.99
    assert alabama["undefeated_pct"] == 31.23
    assert alabama["title_game_pct"] == 88.89
    assert alabama["conf_champ_pct"] == 61.11
    assert alabama["playoff_pct"] == 71.23
    assert [alabama[field] for field in CFP_FIELDS] == [20.05, 55.56, 33.33, 20.0, 11.11]

    # FCS team: has a projection but no Bowl%.
    idaho = entries["Idaho State"]
    assert idaho["projected_wins"] == 1.2
    assert idaho["bowl_pct"] is None
    assert idaho["title_game_pct"] is None and idaho["conf_champ_pct"] is None  # FCS: no FBS title game
    assert idaho["playoff_pct"] is None  # FCS: not eligible for the playoff field
    assert all(idaho[field] is None for field in CFP_FIELDS)

    # A team the simulation never saw just has no projection.
    assert entries["Auburn"]["projected_wins"] is None

    # The existing ranking fields are untouched.
    assert [e["rank"] for e in body["rankings"]] == [1, 2, 3]
    assert alabama["power_score"] == 15.0 and alabama["conference"] == "SEC"


def test_a_projection_from_another_ratings_week_is_not_shown(client, db, seeded):
    db.add(SeasonProjection(team_id=10, season=2026, week=5, n_simulations=10000,
                            avg_wins=9.0, avg_losses=3.0, bowl_pct=90.0, undefeated_pct=1.0))
    db.commit()

    body, entries = _entries(client)  # latest snapshot is week 6
    assert body["simulations"] is None
    assert entries["Alabama"]["projected_wins"] is None


def test_the_hardcoded_fallback_has_no_projections(client):
    body, entries = _entries(client)  # empty database -> fallback rows
    assert body["simulations"] is None
    assert all(e["projected_wins"] is None and e["bowl_pct"] is None for e in entries.values())


# ---- save_season_projections -----------------------------------------------

def _results(**overrides):
    row = dict(team_id=10, team="Alabama", conference="SEC", classification="fbs", wins=2, losses=0,
               games_remaining=1, avg_wins=2.7, avg_losses=0.3, bowl_pct=100.0, undefeated_pct=70.0,
               title_game_pct=80.0, conf_champ_pct=45.0, playoff_pct=70.0,
               cfp_bye_pct=25.0, cfp_quarterfinal_pct=50.0, cfp_semifinal_pct=35.0, cfp_final_pct=20.0,
               cfp_champion_pct=10.0)
    row.update(overrides)
    return pd.DataFrame([row], columns=RESULT_COLUMNS)


def test_save_writes_one_row_per_team(db, seeded):
    results = pd.concat(
        [_results(), _results(team_id=30, bowl_pct=float("nan"), title_game_pct=float("nan"), conf_champ_pct=float("nan"),
                  playoff_pct=float("nan"), **{field: float("nan") for field in CFP_FIELDS})],
        ignore_index=True,
    )
    assert save_season_projections(db, 2026, 6, results, 5000) == 2
    db.commit()

    saved = {p.team_id: p for p in db.query(SeasonProjection)}
    assert saved[10].avg_wins == 2.7 and saved[10].bowl_pct == 100.0 and saved[10].n_simulations == 5000
    assert (saved[10].season, saved[10].week) == (2026, 6)
    assert (saved[10].title_game_pct, saved[10].conf_champ_pct) == (80.0, 45.0)
    assert saved[10].playoff_pct == 70.0
    assert [getattr(saved[10], field) for field in CFP_FIELDS] == [25.0, 50.0, 35.0, 20.0, 10.0]
    assert saved[30].bowl_pct is None  # NaN from the DataFrame becomes NULL, not NaN
    assert saved[30].title_game_pct is None and saved[30].conf_champ_pct is None
    assert saved[30].playoff_pct is None
    assert all(getattr(saved[30], field) is None for field in CFP_FIELDS)  # NaN -> NULL


def test_saving_again_replaces_rather_than_duplicates(db, seeded):
    save_season_projections(db, 2026, 6, _results(avg_wins=2.7), 5000)
    db.commit()
    save_season_projections(db, 2026, 6, _results(avg_wins=3.0, bowl_pct=50.0), 10000)
    db.commit()

    rows = db.query(SeasonProjection).all()
    assert len(rows) == 1
    assert rows[0].avg_wins == 3.0 and rows[0].bowl_pct == 50.0 and rows[0].n_simulations == 10000


def test_a_new_ratings_week_adds_rows_alongside_the_old_ones(db, seeded):
    save_season_projections(db, 2026, 6, _results(), 5000)
    save_season_projections(db, 2026, 7, _results(), 5000)
    db.commit()
    assert db.query(SeasonProjection).count() == 2


def test_simulate_save_and_serve_end_to_end(client, db, seeded):
    inputs = load_season_inputs(db)
    results = simulate_season(inputs.teams, inputs.games, n_simulations=200, seed=1,
                              played_conference_games=inputs.played_conference_games,
                              played_games=inputs.played_games)
    save_season_projections(db, inputs.season, inputs.week, results, 200)
    db.commit()

    body, entries = _entries(client)
    assert body["simulations"] == 200
    assert entries["Alabama"]["projected_wins"] + entries["Alabama"]["projected_losses"] == pytest.approx(3.0, abs=0.02)
    assert entries["Idaho State"]["bowl_pct"] is None
    assert entries["Alabama"]["bowl_pct"] is not None
    # Both FBS teams are in the (tiny) field, so each has a playoff chance; the FCS team has none.
    assert entries["Alabama"]["playoff_pct"] == 100.0 and entries["Auburn"]["playoff_pct"] == 100.0
    assert entries["Idaho State"]["playoff_pct"] is None
    # With only two teams in the field, both get byes, reach the semifinals unopposed and meet in the
    # final, so exactly one of them wins it in each simulated season.
    alabama, auburn, idaho = entries["Alabama"], entries["Auburn"], entries["Idaho State"]
    for field in ("cfp_bye_pct", "cfp_quarterfinal_pct", "cfp_semifinal_pct", "cfp_final_pct"):
        assert alabama[field] == 100.0 and auburn[field] == 100.0
    assert alabama["cfp_champion_pct"] + auburn["cfp_champion_pct"] == pytest.approx(100.0, abs=0.02)
    assert all(idaho[field] is None for field in CFP_FIELDS)
