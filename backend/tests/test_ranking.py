"""Unit tests for the offense/defense power-rating model (app/ranking.py)."""

import itertools

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app import database
from app.ranking import compute_power_ratings, expected_margin

# Ground truth for a small synthetic league. `OFF` is points a team's offense is
# worth; `DEF` is points its defense takes away from opponents (bigger = better).
OFF = {"Aces": 12.0, "Bulls": 5.0, "Cats": 0.0, "Dogs": -4.0, "Elks": -8.0, "Foxes": 3.0}
DEF = {"Aces": 4.0, "Bulls": 9.0, "Cats": 0.0, "Dogs": -3.0, "Elks": 6.0, "Foxes": -7.0}
BASE_SCORE = 28.0
HOME_EDGE = 2.0


def _league() -> pd.DataFrame:
    """Every ordered pair plays once with the first team at home. Scores follow the
    additive model exactly, so a correct fit must recover OFF/DEF (up to the
    league-average centering)."""
    rows = []
    for home, away in itertools.permutations(OFF, 2):
        rows.append(
            {
                "team": home,
                "opponent": away,
                "team_score": BASE_SCORE + HOME_EDGE + OFF[home] - DEF[away],
                "opponent_score": BASE_SCORE - HOME_EDGE + OFF[away] - DEF[home],
                "Location": 1,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture()
def ratings() -> pd.DataFrame:
    return compute_power_ratings(_league()).set_index("team")


def test_recovers_known_offense_and_defense_relative_to_league_average(ratings):
    off_mean, def_mean = np.mean(list(OFF.values())), np.mean(list(DEF.values()))
    for team in OFF:
        assert ratings.loc[team, "offense"] == pytest.approx(OFF[team] - off_mean)
        assert ratings.loc[team, "defense"] == pytest.approx(DEF[team] - def_mean)


def test_positive_defense_means_good_defense(ratings):
    assert ratings["defense"].idxmax() == "Bulls"  # best defense in the truth table
    assert ratings["defense"].idxmin() == "Foxes"  # worst defense
    assert ratings.loc["Bulls", "defense"] > 0 > ratings.loc["Foxes", "defense"]


def test_offense_and_defense_are_centered_on_zero(ratings):
    assert ratings["offense"].mean() == pytest.approx(0.0, abs=1e-9)
    assert ratings["defense"].mean() == pytest.approx(0.0, abs=1e-9)
    assert ratings["rating"].mean() == pytest.approx(0.0, abs=1e-9)


def test_overall_rating_is_offense_plus_defense(ratings):
    assert (ratings["rating"] - (ratings["offense"] + ratings["defense"])).abs().max() < 1e-9


def test_output_shape_is_ranked_best_to_worst_by_overall():
    out = compute_power_ratings(_league())

    assert list(out.columns) == ["rank", "team", "offense", "defense", "rating"]
    assert list(out["rank"]) == list(range(1, len(OFF) + 1))
    assert out["rating"].is_monotonic_decreasing

    overall = {team: OFF[team] + DEF[team] for team in OFF}
    assert list(out["team"]) == sorted(overall, key=overall.get, reverse=True)


def test_overall_difference_is_expected_neutral_site_margin(ratings):
    # Aces vs Dogs on a neutral field. Aces score OFF[Aces] - DEF[Dogs]; Dogs score
    # OFF[Dogs] - DEF[Aces]. The margin is the difference of the two.
    true_margin = (OFF["Aces"] - DEF["Dogs"]) - (OFF["Dogs"] - DEF["Aces"])
    assert true_margin == 23.0
    modeled = expected_margin(
        ratings.loc["Aces", "rating"], ratings.loc["Dogs", "rating"], home_field_advantage=0
    )
    assert modeled == pytest.approx(true_margin)


def test_home_field_is_not_baked_into_team_ratings():
    # Same league replayed at neutral sites (Location=0, no home edge in the scores):
    # the ratings must come out the same as when the home edge was present and modeled.
    neutral = _league().assign(Location=0)
    neutral["team_score"] -= HOME_EDGE
    neutral["opponent_score"] += HOME_EDGE

    home_version = compute_power_ratings(_league()).set_index("team")
    neutral_version = compute_power_ratings(neutral).set_index("team")

    for column in ("offense", "defense", "rating"):
        assert neutral_version[column].to_dict() == pytest.approx(home_version[column].to_dict())


def test_empty_input_returns_correctly_shaped_frame():
    empty = _league().iloc[0:0]
    out = compute_power_ratings(empty)
    assert out.empty
    assert list(out.columns) == ["rank", "team", "offense", "defense", "rating"]


def test_rows_with_missing_values_are_ignored():
    games = _league()
    games.loc[0, "team_score"] = None
    out = compute_power_ratings(games)
    assert len(out) == len(OFF)


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="Location"):
        compute_power_ratings(_league().drop(columns=["Location"]))


def test_margin_column_is_no_longer_required():
    assert "margin" not in _league().columns
    compute_power_ratings(_league())  # does not raise


def test_add_missing_columns_upgrades_a_pre_split_database(monkeypatch):
    """An existing cfbrank.db has power_ratings without the new columns; init_db must add them."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE power_ratings (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, "
                "season INTEGER NOT NULL, week INTEGER NOT NULL, rating FLOAT NOT NULL, rank INTEGER, "
                "wins INTEGER NOT NULL, losses INTEGER NOT NULL, computed_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO power_ratings (team_id, season, week, rating, rank, wins, losses, computed_at) "
                "VALUES (1, 2026, 5, 12.5, 1, 5, 0, '2026-10-05 00:00:00')"
            )
        )
    monkeypatch.setattr(database, "engine", engine)

    database._add_missing_columns()
    database._add_missing_columns()  # idempotent: a second run must not raise

    columns = {c["name"] for c in inspect(engine).get_columns("power_ratings")}
    assert {"offense_rating", "defense_rating"} <= columns
    with engine.connect() as conn:
        row = conn.execute(text("SELECT rating, offense_rating, defense_rating FROM power_ratings")).one()
    assert row == (12.5, None, None)  # old snapshot survives, new fields empty until recomputed
