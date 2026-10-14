"""The weekly refit must equal app.ranking.compute_power_ratings on the same games."""

import random

import numpy as np
import pandas as pd
import pytest

from app.ranking import compute_power_ratings
from app.weekly_ratings import RatingRefitter

TOLERANCE = 1e-8


def random_games(rng, teams, count, locations=(0, 1, 1, 1)):
    games = []
    for _ in range(count):
        home, away = rng.sample(teams, 2)
        games.append((home, away, rng.randint(0, 56), rng.randint(0, 56), rng.choice(locations)))
    return games


def reference(n, games):
    """What the rankings model says for these (home, away, home_pts, away_pts, location) games."""
    frame = pd.DataFrame(
        [(f"T{h}", f"T{a}", hp, ap, loc) for h, a, hp, ap, loc in games],
        columns=["team", "opponent", "team_score", "opponent_score", "Location"],
    )
    table = compute_power_ratings(frame).set_index("team")
    return table


def assert_matches(refitter_ratings, table, n, active_only=None):
    offense, defense = refitter_ratings
    for team in range(n):
        name = f"T{team}"
        if name not in table.index:
            continue
        assert offense[team] == pytest.approx(table.loc[name, "offense"], abs=TOLERANCE), name
        assert defense[team] == pytest.approx(table.loc[name, "defense"], abs=TOLERANCE), name


def run_weeks(n, played, simulated_weeks, base=None):
    """Drive a RatingRefitter like the season simulation does; yield (stage, ratings, all games so far)."""
    base_offense = base[0] if base else [0.0] * n
    base_defense = base[1] if base else [0.0] * n
    refitter = RatingRefitter(
        n,
        played,
        [[(h, a, loc) for h, a, _, _, loc in week] for week in simulated_weeks],
        base_offense,
        base_defense,
    )
    b = refitter.start_vector()
    so_far = list(played)
    for stage, week in enumerate(simulated_weeks):
        for home, away, home_pts, away_pts, loc in week:
            refitter.add_game(b, home, away, loc, home_pts, away_pts)
        so_far = so_far + list(week)
        yield stage, refitter.ratings(stage, b), so_far


def test_ratings_after_each_week_equal_the_rankings_model():
    rng = random.Random(1)
    n, teams = 30, list(range(30))
    played = random_games(rng, teams, 70)
    weeks = [random_games(rng, teams, 12) for _ in range(4)]
    stages = list(run_weeks(n, played, weeks))
    assert len(stages) == 4
    for _, ratings, games_so_far in stages:
        assert_matches(ratings, reference(n, games_so_far), n)


def test_all_neutral_sites_and_all_home_games_both_work():
    for locations in ((0,), (1,)):
        rng = random.Random(2)
        n, teams = 20, list(range(20))
        played = random_games(rng, teams, 50, locations)
        weeks = [random_games(rng, teams, 10, locations) for _ in range(2)]
        for _, ratings, games_so_far in run_weeks(n, played, weeks):
            assert_matches(ratings, reference(n, games_so_far), n)


def test_two_groups_that_never_play_each_other_still_match():
    # Two disconnected leagues: the model has an extra free constant; both solvers use the same minimum-norm answer.
    rng = random.Random(3)
    group_a, group_b = list(range(0, 10)), list(range(10, 20))
    played = random_games(rng, group_a, 25) + random_games(rng, group_b, 25)
    weeks = [random_games(rng, group_a, 4) + random_games(rng, group_b, 4)]
    for _, ratings, games_so_far in run_weeks(20, played, weeks):
        assert_matches(ratings, reference(20, games_so_far), 20)


def test_offense_and_defense_are_each_centered_on_zero():
    rng = random.Random(4)
    n, teams = 25, list(range(25))
    played = random_games(rng, teams, 60)
    for _, (offense, defense), _ in run_weeks(n, played, [random_games(rng, teams, 10)]):
        assert np.mean(offense) == pytest.approx(0.0, abs=1e-9)
        assert np.mean(defense) == pytest.approx(0.0, abs=1e-9)


def test_a_team_with_no_games_yet_keeps_its_starting_rating_until_it_plays():
    rng = random.Random(5)
    n = 12
    played = random_games(rng, list(range(11)), 40)  # team 11 hasn't played
    week1 = random_games(rng, list(range(11)), 6)
    week2 = random_games(rng, list(range(11)), 5) + [(11, 3, 24, 17, 1), (2, 11, 30, 10, 1)]
    base = ([0.0] * 11 + [7.5], [0.0] * 11 + [-2.5])

    stages = list(run_weeks(n, played, [week1, week2], base=base))

    offense, defense = stages[0][1]
    assert (offense[11], defense[11]) == (7.5, -2.5)  # untouched: no games yet
    assert_matches(stages[0][1], reference(n, stages[0][2]), n)  # others as if team 11 didn't exist

    assert_matches(stages[1][1], reference(n, stages[1][2]), n)  # once it plays, it's a normal fit
    assert stages[1][1][0][11] != 7.5


def test_a_simulated_week_moves_ratings_toward_the_results():
    # Team 0 and team 1 start level. In the simulated week, 0 hammers 2 and 1 loses to 2.
    rng = random.Random(6)
    n, teams = 10, list(range(10))
    played = random_games(rng, teams, 40, locations=(1,))
    before = reference(n, played)
    week = [(0, 2, 70, 0, 1), (1, 2, 0, 70, 1)]
    (_, (offense, defense), _), = run_weeks(n, played, [week])
    rating = [o + d for o, d in zip(offense, defense)]
    old = [before.loc[f"T{t}", "rating"] for t in range(n)]
    assert rating[0] > old[0] + 1.0  # a 70-0 win helps
    assert rating[1] < old[1] - 1.0  # a 0-70 loss hurts


def test_each_simulation_starts_from_its_own_copy_of_the_played_games():
    rng = random.Random(7)
    refitter = RatingRefitter(
        6, random_games(rng, list(range(6)), 20), [[(0, 1, 1)]], [0.0] * 6, [0.0] * 6
    )
    a, b = refitter.start_vector(), refitter.start_vector()
    refitter.add_game(a, 0, 1, 1, 99, 0)
    assert b == refitter.start_vector() and a != b


def test_no_simulated_weeks_means_nothing_to_refit():
    refitter = RatingRefitter(4, [(0, 1, 30, 20, 1)], [], [0.0] * 4, [0.0] * 4)
    assert refitter.start_vector()  # constructed fine; there are no stages to ask for


# ---- wiring into the season simulation -------------------------------------

from app.season_simulation import PlayedScore, SimGame, SimTeam, simulate_season  # noqa: E402


def sim_team(i, conference="Indie", offense=0.0, defense=0.0):
    return SimTeam(team_id=i, school=f"T{i}", conference=conference, classification="fbs",
                   offense=offense, defense=defense)


class ScriptedGames:
    """Stands in for simulate_game: records the ratings each game was played with, returns fixed scores."""

    def __init__(self):
        self.calls = []

    def __call__(self, offense_a, defense_a, offense_b, defense_b, sorted_scores=None, rng=None,
                 home_field_advantage=0.0):
        i = len(self.calls)
        self.calls.append((offense_a, defense_a, offense_b, defense_b))
        return {"score_a": 20 + (i * 7) % 25, "score_b": 14 + (i * 5) % 22, "overtime": False,
                "expected_a": 0.0, "expected_b": 0.0}

    def scores(self, i):
        return 20 + (i * 7) % 25, 14 + (i * 5) % 22


def _ratings_from_model(played_rows, n):
    table = reference(n, played_rows)
    return [table.loc[f"T{t}", "offense"] for t in range(n)], [table.loc[f"T{t}", "defense"] for t in range(n)]


def test_each_simulated_week_is_played_with_ratings_re_fit_on_the_weeks_before(monkeypatch):
    rng = random.Random(10)
    n, ids = 8, list(range(8))
    played = random_games(rng, ids, 24)
    base_offense = [float(i) for i in range(n)]  # deliberately unlike what the games say
    teams = [sim_team(i, offense=base_offense[i], defense=-base_offense[i]) for i in ids]
    weeks = [
        [SimGame(0, 1, week=6), SimGame(2, 3, neutral_site=True, week=6), SimGame(4, 5, week=6), SimGame(6, 7, week=6)],
        [SimGame(1, 2, week=7), SimGame(3, 4, week=7), SimGame(5, 6, neutral_site=True, week=7), SimGame(7, 0, week=7)],
        [SimGame(0, 2, week=8), SimGame(1, 3, neutral_site=True, week=8), SimGame(4, 6, week=8), SimGame(5, 7, week=8)],
    ]
    games = [g for week in weeks for g in week]
    fake = ScriptedGames()
    monkeypatch.setattr("app.season_simulation.simulate_game", fake)

    simulate_season(
        teams, games, n_simulations=1, seed=1,
        played_games=[PlayedScore(h, a, hp, ap, loc == 0) for h, a, hp, ap, loc in played],
    )
    assert len(fake.calls) == 12

    # Week 6 is played with the ratings it was given (the stored snapshot).
    for (off_a, _, off_b, _), game in zip(fake.calls[:4], weeks[0]):
        assert (off_a, off_b) == (base_offense[game.home_id], base_offense[game.away_id])

    # Every later week is played with ratings re-fit on the played games plus all earlier simulated weeks
    # (a neutral-site game is a Location-0 row in the fit).
    rows = list(played)
    offsets = [0, 4, 8]
    for week_number in (1, 2):
        previous = weeks[week_number - 1]
        rows += [
            (g.home_id, g.away_id, *fake.scores(offsets[week_number - 1] + i), 0 if g.neutral_site else 1)
            for i, g in enumerate(previous)
        ]
        expected_offense, expected_defense = _ratings_from_model(rows, n)
        calls = fake.calls[offsets[week_number]: offsets[week_number] + 4]
        for (off_a, def_a, off_b, def_b), game in zip(calls, weeks[week_number]):
            assert off_a == pytest.approx(expected_offense[game.home_id], abs=1e-8)
            assert def_a == pytest.approx(expected_defense[game.home_id], abs=1e-8)
            assert off_b == pytest.approx(expected_offense[game.away_id], abs=1e-8)
            assert def_b == pytest.approx(expected_defense[game.away_id], abs=1e-8)
        assert expected_offense[0] != pytest.approx(base_offense[0], abs=0.5)  # the test would catch "no update"


def test_ratings_stay_fixed_without_played_games_or_when_updates_are_turned_off(monkeypatch):
    rng = random.Random(11)
    played = [PlayedScore(h, a, hp, ap, False) for h, a, hp, ap, _ in random_games(rng, list(range(6)), 20)]
    teams = [sim_team(i, offense=float(i), defense=0.0) for i in range(6)]
    games = [SimGame(0, 1, week=1), SimGame(2, 3, week=1), SimGame(4, 5, week=2), SimGame(1, 2, week=2)]

    for kwargs in ({}, {"played_games": played, "update_ratings": False}):
        fake = ScriptedGames()
        monkeypatch.setattr("app.season_simulation.simulate_game", fake)
        simulate_season(teams, games, n_simulations=2, seed=1, **kwargs)
        for off_a, _, off_b, _ in fake.calls:
            assert off_a == pytest.approx(round(off_a)) and off_b == pytest.approx(round(off_b))  # the original 0..5
        assert {c[0] for c in fake.calls} <= {0.0, 1.0, 2.0, 3.0, 4.0, 5.0}


def test_title_games_use_the_ratings_from_after_the_last_week_before_them(monkeypatch):
    rng = random.Random(12)
    n = 6
    played = [PlayedScore(h, a, hp, ap, False) for h, a, hp, ap, _ in random_games(rng, list(range(n)), 24)]
    teams = [sim_team(0, "Pac-12"), sim_team(1, "Pac-12")] + [sim_team(i, offense=float(i)) for i in range(2, n)]
    games = [
        SimGame(0, 1, conference_game=True, week=6),  # the only Pac-12 game: its two teams play the title game
        SimGame(2, 3, week=15),  # after title week
    ]
    fake = ScriptedGames()
    monkeypatch.setattr("app.season_simulation.simulate_game", fake)
    simulate_season(teams, games, n_simulations=1, seed=1, played_games=played)

    assert len(fake.calls) == 3  # week 6, then the title game, then week 15

    # Ratings after week 6: re-fit on everything played plus week 6's simulated score.
    rows = [(p.home_id, p.away_id, p.home_points, p.away_points, 1) for p in played]
    rows.append((0, 1, *fake.scores(0), 1))
    expected_offense, _ = _ratings_from_model(rows, n)

    (title_off_a, _, title_off_b, _), (late_off_a, _, _, _) = fake.calls[1], fake.calls[2]
    assert sorted([title_off_a, title_off_b]) == pytest.approx(
        sorted([expected_offense[0], expected_offense[1]]), abs=1e-8
    )
    assert late_off_a == pytest.approx(expected_offense[2], abs=1e-8)  # title scores aren't fed back


def test_a_team_the_games_so_far_say_is_dominant_is_trusted_more_once_the_ratings_update():
    # The stored ratings are stale (all zero), but every game played says team 1 is far better than the rest.
    others = [2, 3, 4, 5, 6]
    played = [PlayedScore(1, o, 60, 0, False) for o in others]
    played += [PlayedScore(a, b, 24, 20, i % 2 == 0) for i, (a, b) in enumerate(
        (a, b) for k, a in enumerate(others) for b in others[k + 1:])]
    teams = [sim_team(i) for i in range(1, 7)]
    games = [SimGame(1, 2, neutral_site=True, week=1), SimGame(1, 3, neutral_site=True, week=2)]

    def team_one_wins(update):
        results = simulate_season(teams, games, n_simulations=1500, seed=3, played_games=played,
                                  update_ratings=update)
        return results[results.team_id == 1].iloc[0].avg_wins

    frozen = team_one_wins(False)
    updated = team_one_wins(True)
    assert 0.9 < frozen < 1.1  # two coin flips
    assert updated > frozen + 0.3  # week 1 is still a coin flip, week 2 is not
