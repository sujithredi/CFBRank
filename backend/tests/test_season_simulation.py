"""Tests for app/season_simulation.py (and the home-field option on simulate_game)."""

import random

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app.conference_championships import CHAMPIONSHIP_WEEK
from app.database import Base
from app.models import Conference, Game, PowerRating, Team
from app.season_simulation import (
    RESULT_COLUMNS,
    PlayedGame,
    PlayedScore,
    SimGame,
    SimTeam,
    load_season_inputs,
    simulate_season,
)
from app.simulation import load_sorted_scores, simulate_game

# Ratings this extreme push every simulated score to the very top / bottom of the
# historical scores, so the "strong" team beats the "weak" team every single time.
STRONG = dict(offense=200.0, defense=200.0)
WEAK = dict(offense=-200.0, defense=-200.0)


def team(team_id, name="T", classification="fbs", **kwargs):
    ratings = {**dict(offense=0.0, defense=0.0), **kwargs}
    return SimTeam(team_id=team_id, school=f"{name}{team_id}", conference="Conf",
                   classification=classification, **ratings)


def row(results, team_id):
    return results[results.team_id == team_id].iloc[0]


# ---- home-field option on simulate_game -------------------------------------

def test_default_is_still_a_neutral_site():
    a = simulate_game(10, 5, -3, 2, rng=random.Random(9))
    b = simulate_game(10, 5, -3, 2, rng=random.Random(9), home_field_advantage=0.0)
    assert a == b


def test_home_field_is_split_between_the_two_teams_expected_points():
    neutral = simulate_game(0, 0, 0, 0, rng=random.Random(1))
    home = simulate_game(0, 0, 0, 0, rng=random.Random(1), home_field_advantage=4.0)
    assert home["expected_a"] == pytest.approx(neutral["expected_a"] + 2.0)
    assert home["expected_b"] == pytest.approx(neutral["expected_b"] - 2.0)


def test_home_field_helps_the_home_team_win_between_equal_teams():
    scores, rng = load_sorted_scores(), random.Random(2)
    n = 3000
    wins = sum(
        (g := simulate_game(0, 0, 0, 0, sorted_scores=scores, rng=rng, home_field_advantage=10.0))["score_a"]
        > g["score_b"]
        for _ in range(n)
    )
    assert wins / n > 0.65


# ---- simulate_season -------------------------------------------------------

def test_result_shape_and_columns():
    teams = [team(1), team(2)]
    results = simulate_season(teams, [SimGame(1, 2)], n_simulations=50, seed=1)
    assert list(results.columns) == RESULT_COLUMNS
    assert len(results) == 2


def test_wins_and_losses_add_up_to_games_played_and_to_each_other():
    teams = [team(i) for i in range(1, 5)]
    games = [SimGame(1, 2), SimGame(3, 4), SimGame(1, 3), SimGame(2, 4, neutral_site=True)]
    teams[0] = SimTeam(1, "T1", "Conf", "fbs", 0.0, 0.0, wins=2, losses=1, fbs_wins=2)
    results = simulate_season(teams, games, n_simulations=300, seed=3)

    for r in results.itertuples():
        assert r.avg_wins + r.avg_losses == pytest.approx(r.wins + r.losses + r.games_remaining)
    # every game has exactly one winner and one loser
    assert results.avg_wins.sum() - results.wins.sum() == pytest.approx(len(games))
    assert results.avg_losses.sum() - results.losses.sum() == pytest.approx(len(games))


def test_same_seed_gives_the_same_results_and_different_seeds_differ():
    teams = [team(i) for i in range(1, 5)]
    games = [SimGame(1, 2), SimGame(3, 4), SimGame(1, 3), SimGame(2, 4)]
    a = simulate_season(teams, games, n_simulations=200, seed=11)
    b = simulate_season(teams, games, n_simulations=200, seed=11)
    c = simulate_season(teams, games, n_simulations=200, seed=12)
    assert a.equals(b)
    assert not a.equals(c)


def test_a_dominant_team_wins_everything_and_is_undefeated():
    teams = [team(1, **STRONG), team(2, **WEAK)]
    results = simulate_season(teams, [SimGame(1, 2), SimGame(2, 1)], n_simulations=100, seed=1)
    strong, weak = row(results, 1), row(results, 2)
    assert strong.avg_wins == 2 and strong.avg_losses == 0 and strong.undefeated_pct == 100.0
    assert weak.avg_wins == 0 and weak.avg_losses == 2 and weak.undefeated_pct == 0.0


def test_a_team_that_already_lost_can_never_be_undefeated():
    teams = [SimTeam(1, "T1", "Conf", "fbs", **STRONG, wins=3, losses=1, fbs_wins=3), team(2, **WEAK)]
    results = simulate_season(teams, [SimGame(1, 2)], n_simulations=100, seed=1)
    r = row(results, 1)
    assert r.undefeated_pct == 0.0
    assert (r.avg_wins, r.avg_losses) == (4, 1)


def test_a_perfect_team_with_no_games_left_is_undefeated():
    teams = [SimTeam(1, "T1", "Conf", "fbs", 0.0, 0.0, wins=12, fbs_wins=12), team(2), team(3)]
    results = simulate_season(teams, [SimGame(2, 3)], n_simulations=20, seed=1)
    assert row(results, 1).undefeated_pct == 100.0


def test_bowl_eligibility_needs_six_wins():
    five = SimTeam(1, "Five", "Conf", "fbs", 0.0, 0.0, wins=5, losses=6, fbs_wins=5)
    six = SimTeam(2, "Six", "Conf", "fbs", 0.0, 0.0, wins=6, losses=6, fbs_wins=6)
    results = simulate_season([five, six, team(3), team(4)], [SimGame(3, 4)], n_simulations=20, seed=1)
    assert row(results, 1).bowl_pct == 0.0
    assert row(results, 2).bowl_pct == 100.0


def test_a_remaining_win_can_carry_a_team_over_the_bowl_line():
    on_the_bubble = SimTeam(1, "Bubble", "Conf", "fbs", **STRONG, wins=5, losses=6, fbs_wins=5)
    results = simulate_season([on_the_bubble, team(2, **WEAK)], [SimGame(1, 2)], n_simulations=50, seed=1)
    assert row(results, 1).bowl_pct == 100.0
    assert row(results, 2).bowl_pct == 0.0


def test_only_one_fcs_win_counts_toward_bowl_eligibility():
    # 4 FBS wins + 2 FCS wins = 6 wins, but only 5 count.
    two_fcs = SimTeam(1, "TwoFCS", "Conf", "fbs", 0.0, 0.0, wins=6, losses=6, fbs_wins=4, fcs_wins=2)
    # 5 FBS wins + 2 FCS wins -> 5 + 1 = 6 counts.
    enough = SimTeam(2, "Enough", "Conf", "fbs", 0.0, 0.0, wins=7, losses=5, fbs_wins=5, fcs_wins=2)
    results = simulate_season([two_fcs, enough, team(3), team(4)], [SimGame(3, 4)], n_simulations=20, seed=1)
    assert row(results, 1).bowl_pct == 0.0
    assert row(results, 2).bowl_pct == 100.0


def test_simulated_fcs_wins_are_capped_too():
    # Starts 4-0 against FBS teams, then plays two FCS opponents it always beats: 4 + min(2, 1) = 5.
    fbs = SimTeam(1, "FBS", "Conf", "fbs", **STRONG, wins=4, losses=7, fbs_wins=4)
    games = [SimGame(1, 2), SimGame(1, 3)]
    teams = [fbs, team(2, "FCS", classification="fcs", **WEAK), team(3, "FCS", classification="fcs", **WEAK)]
    results = simulate_season(teams, games, n_simulations=20, seed=1)
    assert row(results, 1).avg_wins == 6
    assert row(results, 1).bowl_pct == 0.0


def test_bowl_pct_is_none_for_fcs_teams():
    teams = [team(1), team(2, classification="fcs")]
    results = simulate_season(teams, [SimGame(1, 2)], n_simulations=20, seed=1)
    assert pd.isna(row(results, 2).bowl_pct)
    assert not pd.isna(row(results, 1).bowl_pct)


def test_home_field_edge_shows_up_over_a_season():
    # Two equal teams swap hosting duties, so the edge cancels; but a team that only hosts gains.
    teams = [team(1), team(2)]
    hosts_only = simulate_season(teams, [SimGame(1, 2)] * 20, n_simulations=200, seed=4)
    assert row(hosts_only, 1).avg_wins > row(hosts_only, 2).avg_wins + 1

    neutral = simulate_season(teams, [SimGame(1, 2, neutral_site=True)] * 20, n_simulations=200, seed=4)
    assert abs(row(neutral, 1).avg_wins - 10) < 1.0


def test_better_team_has_more_wins_than_a_worse_one():
    teams = [team(1, offense=8.0, defense=8.0), team(2), team(3, offense=-8.0, defense=-8.0)]
    games = [SimGame(1, 2), SimGame(2, 3), SimGame(3, 1), SimGame(2, 1), SimGame(3, 2), SimGame(1, 3)]
    results = simulate_season(teams, games, n_simulations=500, seed=6)
    assert row(results, 1).avg_wins > row(results, 2).avg_wins > row(results, 3).avg_wins


def test_results_are_sorted_by_average_wins():
    teams = [team(1, **WEAK), team(2, **STRONG), team(3)]
    results = simulate_season(teams, [SimGame(1, 2), SimGame(2, 3)], n_simulations=20, seed=1)
    assert results.avg_wins.is_monotonic_decreasing


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        simulate_season([team(1), team(2)], [SimGame(1, 2)], n_simulations=0)
    with pytest.raises(ValueError, match="isn't in `teams`"):
        simulate_season([team(1)], [SimGame(1, 99)], n_simulations=5)


def test_no_remaining_games_just_reports_current_records():
    teams = [SimTeam(1, "T1", "Conf", "fbs", 0.0, 0.0, wins=7, losses=5, fbs_wins=7)]
    r = row(simulate_season(teams, [], n_simulations=10, seed=1), 1)
    assert (r.avg_wins, r.avg_losses, r.games_remaining) == (7, 5, 0)
    assert r.bowl_pct == 100.0 and r.undefeated_pct == 0.0


# ---- load_season_inputs ----------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


def _game(game_id, home, away, completed, home_pts=None, away_pts=None, **kwargs):
    fields = dict(cfbd_id=game_id, season=2026, week=1, season_type="regular", neutral_site=False,
                  conference_game=False, completed=completed, home_team_id=home, away_team_id=away,
                  home_points=home_pts, away_points=away_pts)
    fields.update(kwargs)
    return Game(**fields)


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
        # An older snapshot that must be ignored in favor of week 6.
        PowerRating(team_id=10, season=2026, week=5, rating=0, offense_rating=-50.0, defense_rating=-50.0),
        PowerRating(team_id=10, season=2026, week=6, rating=15, offense_rating=9.0, defense_rating=6.0, wins=2, losses=0),
        PowerRating(team_id=20, season=2026, week=6, rating=3, offense_rating=1.0, defense_rating=2.0, wins=0, losses=1),
        PowerRating(team_id=30, season=2026, week=6, rating=-9, offense_rating=-5.0, defense_rating=-4.0, wins=0, losses=1),
    ])
    db.add_all([
        _game(1, 10, 30, True, 56, 3, week=1),                       # Alabama beats an FCS team
        _game(2, 20, 10, True, 17, 24, week=2),                      # Alabama beats Auburn
        _game(3, 10, 20, False, week=8, neutral_site=True),          # remaining, neutral
        _game(4, 20, 30, False, week=9),                             # remaining
        _game(5, 10, 20, False, week=15, season_type="postseason"),  # bowl game: not simulated
        _game(6, 10, 20, False, season=2025, week=9),                # another season: not simulated
    ])
    db.commit()


def test_loader_reads_ratings_records_and_remaining_schedule(db, seeded):
    season, week, teams, games, played_conference_games, played_games = load_season_inputs(db)
    assert (season, week) == (2026, 6)

    by_name = {t.school: t for t in teams}
    alabama = by_name["Alabama"]
    assert (alabama.offense, alabama.defense) == (9.0, 6.0)  # latest snapshot, not week 5
    assert (alabama.wins, alabama.losses) == (2, 0)
    assert (alabama.fbs_wins, alabama.fcs_wins) == (1, 1)  # beat Auburn (FBS) and Idaho State (FCS)
    assert alabama.conference == "SEC" and alabama.is_fbs

    auburn, idaho = by_name["Auburn"], by_name["Idaho State"]
    assert (auburn.wins, auburn.losses) == (0, 1)
    assert (idaho.wins, idaho.losses) == (0, 1)
    assert idaho.classification == "fcs" and idaho.conference == "Independent"

    assert games == [SimGame(10, 20, True, False, 8), SimGame(20, 30, False, False, 9)]
    assert played_conference_games == []  # none of the played games in this fixture is a conference game
    # Every completed game, with its score, is what the rating model is fit on.
    assert played_games == [PlayedScore(10, 30, 56, 3, False), PlayedScore(20, 10, 17, 24, False)]


def test_loader_end_to_end_through_simulate_season(db, seeded):
    inputs = load_season_inputs(db)
    results = simulate_season(inputs.teams, inputs.games, n_simulations=100, seed=1,
                              played_conference_games=inputs.played_conference_games)
    assert set(results.team) == {"Alabama", "Auburn", "Idaho State"}
    assert row(results, 10).games_remaining == 1 and row(results, 30).games_remaining == 1


def test_loader_can_pick_a_season(db, seeded):
    with pytest.raises(ValueError, match="No power ratings"):
        load_season_inputs(db, season=2025)
    assert load_season_inputs(db, season=2026)[0] == 2026


def test_loader_without_any_ratings_raises(db):
    with pytest.raises(ValueError, match="No power ratings"):
        load_season_inputs(db)


def test_loader_rejects_a_team_with_games_left_but_no_offense_defense_split(db, seeded):
    db.query(PowerRating).filter_by(team_id=20, week=6).update({"offense_rating": None})
    db.commit()
    with pytest.raises(ValueError, match="Auburn"):
        load_season_inputs(db)


# ---- load_season_inputs: conference-championship inputs ---------------------

def test_loader_reads_divisions_ratings_and_played_conference_games(db):
    db.add_all([Conference(id=1, cfbd_id=1, name="Sun Belt"), Conference(id=2, cfbd_id=2, name="SEC")])
    db.flush()
    db.add_all([
        Team(id=1, cfbd_id=1, school="Troy", classification="fbs", conference_id=1, division="West"),
        Team(id=2, cfbd_id=2, school="Marshall", classification="fbs", conference_id=1, division="East"),
        Team(id=3, cfbd_id=3, school="Alabama", classification="fbs", conference_id=2),
    ])
    db.flush()
    for team_id, rating in ((1, 5.0), (2, 8.0), (3, 20.0)):
        db.add(PowerRating(team_id=team_id, season=2026, week=6, rating=rating,
                           offense_rating=rating / 2, defense_rating=rating / 2))
    db.add_all([
        _game(1, 1, 2, True, 30, 20, week=3, conference_game=True),    # Sun Belt game: Troy beat Marshall
        _game(2, 3, 1, True, 40, 10, week=4),                          # non-conference: ignored for standings
        _game(3, 2, 1, True, 24, 21, week=CHAMPIONSHIP_WEEK, conference_game=True),  # a real title game
        _game(4, 1, 2, False, week=8, conference_game=True),           # remaining conference game
        _game(5, 2, 1, False, week=CHAMPIONSHIP_WEEK, conference_game=True),         # a real title game, unplayed
        _game(6, 1, 2, False, week=CHAMPIONSHIP_WEEK + 1, conference_game=True),     # after title week: kept
    ])
    db.commit()

    season, week, teams, games, played, played_games = load_season_inputs(db)
    by_name = {t.school: t for t in teams}
    assert (by_name["Troy"].division, by_name["Marshall"].division) == ("West", "East")
    assert by_name["Alabama"].division is None
    assert by_name["Alabama"].rating == 20.0 and by_name["Troy"].rating == 5.0

    # Only the Sun Belt game before title week feeds the standings.
    assert played == [PlayedGame(winner_id=1, loser_id=2)]
    # ...but the rating model is fit on every completed game, as compute_rankings does (title game included).
    assert {(g.home_id, g.away_id, g.neutral_site) for g in played_games} == {(1, 2, False), (3, 1, False), (2, 1, False)}

    # The real title-game rows are neither simulated nor counted in the record; the late game is kept.
    assert games == [SimGame(1, 2, False, True, 8), SimGame(1, 2, False, True, CHAMPIONSHIP_WEEK + 1)]
    assert (by_name["Troy"].wins, by_name["Troy"].losses) == (1, 1)  # beat Marshall, lost to Alabama; not the title game
    assert (by_name["Marshall"].wins, by_name["Marshall"].losses) == (0, 1)
