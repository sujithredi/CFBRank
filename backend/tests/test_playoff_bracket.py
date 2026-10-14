"""College Football Playoff bracket: seeding, the bracket's shape, and playing it."""

import random

import numpy as np
import pytest

from app import playoff_bracket
from app.playoff_bracket import (
    FINAL,
    FIRST_ROUND,
    QUARTERFINAL,
    SEMIFINAL,
    TWELVE_TEAM_BRACKET,
    BracketGame,
    Seed,
    Winner,
    bracket_size,
    bye_seeds,
    seed_field,
    simulate_bracket,
    validate_bracket,
)
from app.ranking import DEFAULT_HOME_FIELD_ADVANTAGE


def chalk(n=12, step=100.0):
    """
    Ratings where team k (seed k + 1 when seeded in index order) beats every team after it, every
    time: each step in index is worth `step` points on offense and on defense.
    """
    ratings = [-step * k for k in range(n)]
    return ratings, list(ratings)


def play(seeds=None, ratings=None, seed=1, **kwargs):
    off, dfn = ratings or chalk()
    seeds = list(range(12)) if seeds is None else seeds
    return simulate_bracket(seeds, off, dfn, random.Random(seed), **kwargs)


def matchups(result):
    """{game id: (seed of team A, seed of team B)}, for teams where seed = index + 1."""
    return {g.game: (g.team_a + 1, g.team_b + 1) for g in result.games}


# ---- the bracket's shape ----------------------------------------------------

def test_the_twelve_team_bracket_has_twelve_seeds_four_byes_and_eleven_games():
    validate_bracket(TWELVE_TEAM_BRACKET)
    assert bracket_size() == 12
    assert bye_seeds() == [1, 2, 3, 4]
    rounds = [game.round for game in TWELVE_TEAM_BRACKET]
    assert [rounds.count(r) for r in (FIRST_ROUND, QUARTERFINAL, SEMIFINAL, FINAL)] == [4, 4, 2, 1]


def test_only_round_one_is_hosted():
    hosted = {game.id for game in TWELVE_TEAM_BRACKET if game.hosted}
    assert hosted == {"R1-5v12", "R1-6v11", "R1-7v10", "R1-8v9"}


def test_a_bracket_that_plays_a_game_before_the_games_feeding_it_is_rejected():
    with pytest.raises(ValueError, match="isn't played before"):
        validate_bracket([BracketGame("F", FINAL, Winner("SF"), Seed(1)), BracketGame("SF", SEMIFINAL, Seed(2), Seed(3))])


def test_a_bracket_must_use_each_seed_once():
    with pytest.raises(ValueError, match="Seeds must be 1..n"):
        validate_bracket([BracketGame("A", FIRST_ROUND, Seed(1), Seed(1))])
    with pytest.raises(ValueError, match="Seeds must be 1..n"):
        validate_bracket([BracketGame("A", FIRST_ROUND, Seed(1), Seed(3))])
    with pytest.raises(ValueError, match="Duplicate game id"):
        validate_bracket([BracketGame("A", FIRST_ROUND, Seed(1), Seed(2)), BracketGame("A", FIRST_ROUND, Seed(3), Seed(4))])


# ---- seeding -----------------------------------------------------------------

def test_the_field_is_seeded_best_rating_first_and_only_includes_the_teams_given():
    rating = [5.0, 40.0, -3.0, 22.0, 99.0, 10.0]  # index = team
    assert seed_field([0, 1, 2, 3, 5], rating) == [1, 3, 5, 0, 2]  # team 4 isn't in the field


def test_rating_ties_go_to_the_lower_index():
    assert seed_field([3, 1, 2, 0], np.array([7.0, 7.0, 7.0, 7.0])) == [0, 1, 2, 3]


def test_seeding_accepts_a_numpy_array_of_ratings():
    assert seed_field(range(3), np.array([1.0, 3.0, 2.0])) == [1, 2, 0]


# ---- playing the bracket ------------------------------------------------------

def test_with_no_upsets_the_bracket_goes_1_2_3_4_5_6_7_8_with_no_reseeding():
    result = play()
    assert matchups(result) == {
        "R1-5v12": (5, 12), "R1-6v11": (6, 11), "R1-7v10": (7, 10), "R1-8v9": (8, 9),
        "QF-1": (1, 8), "QF-4": (4, 5), "QF-2": (2, 7), "QF-3": (3, 6),
        "SF-1/4": (1, 4), "SF-2/3": (2, 3),
        "FINAL": (1, 2),
    }
    assert result.champion == 0  # the 1 seed
    assert [g.game for g in result.games][-1] == "FINAL"


def test_an_upset_team_keeps_its_slot_in_the_bracket_rather_than_being_reseeded():
    # The 12 seed is far better than everybody else: it must beat 5, then 4, then the 1 seed's
    # side of the bracket, then the other side -- never a "lowest remaining seed" matchup.
    off, dfn = chalk()
    off[11] = dfn[11] = 1000.0
    result = play(ratings=(off, dfn))
    twelve = 11
    opponents = {
        g.game: (g.team_b if g.team_a == twelve else g.team_a) + 1
        for g in result.games
        if twelve in (g.team_a, g.team_b)
    }
    assert opponents == {"R1-5v12": 5, "QF-4": 4, "SF-1/4": 1, "FINAL": 2}
    assert result.champion == twelve


def test_round_one_gives_the_higher_seed_the_home_edge_and_every_later_round_is_neutral(monkeypatch):
    calls = []

    def fake_simulate_game(off_a, def_a, off_b, def_b, **kwargs):
        calls.append(kwargs["home_field_advantage"])
        return {"score_a": 30, "score_b": 20, "overtime": False}

    monkeypatch.setattr(playoff_bracket, "simulate_game", fake_simulate_game)
    play()
    assert calls == [DEFAULT_HOME_FIELD_ADVANTAGE] * 4 + [0.0] * 7

    calls.clear()
    play(home_field_advantage=6.0)
    assert calls == [6.0] * 4 + [0.0] * 7


def test_the_top_four_seeds_get_byes_and_the_rest_play_in_round_one():
    result = play()
    assert result.bye_teams == [0, 1, 2, 3]
    first_round_teams = {t for g in result.games if g.round == FIRST_ROUND for t in (g.team_a, g.team_b)}
    assert first_round_teams == set(range(4, 12))


def test_furthest_round_records_how_deep_each_team_got():
    result = play()
    expected = {0: FINAL, 1: FINAL, 2: SEMIFINAL, 3: SEMIFINAL}
    expected |= {team: QUARTERFINAL for team in range(4, 8)}
    expected |= {team: FIRST_ROUND for team in range(8, 12)}
    assert result.furthest_round == expected


def test_every_game_has_a_winner_who_is_one_of_its_teams_and_the_title_game_decides_the_champion():
    result = play(ratings=([0.0] * 12, [0.0] * 12), seed=9)  # evenly matched: plenty of upsets
    assert len(result.games) == 11
    for game in result.games:
        assert game.winner in (game.team_a, game.team_b)
        assert game.score_a != game.score_b  # no ties: overtime breaks them
        assert (game.winner == game.team_a) == (game.score_a > game.score_b)
    assert result.champion == result.games[-1].winner


def test_the_same_random_seed_gives_the_same_bracket_and_different_seeds_can_differ():
    even = ([0.0] * 12, [0.0] * 12)
    assert play(ratings=even, seed=4) == play(ratings=even, seed=4)
    champions = {play(ratings=even, seed=s).champion for s in range(40)}
    assert len(champions) > 3


def test_better_seeds_win_the_title_more_often():
    # A realistic spread: each seed is 4 points of overall rating worse than the one before.
    ratings = ([-2.0 * k for k in range(12)], [-2.0 * k for k in range(12)])
    rng = random.Random(21)
    titles = [0] * 12
    for _ in range(600):
        off, dfn = ratings
        titles[simulate_bracket(list(range(12)), off, dfn, rng).champion] += 1
    assert titles[0] > titles[11]
    assert sum(titles[:4]) > sum(titles[8:])  # the byes are worth a lot
    assert sum(titles) == 600


def test_seeds_can_be_any_team_indexes_not_just_0_to_11():
    off, dfn = chalk(20)
    seeds = [19, 17, 15, 13, 11, 9, 7, 5, 3, 1, 18, 16]  # arbitrary teams, best seed first (index 19 = weakest rated)
    result = simulate_bracket(seeds, off, dfn, random.Random(1))
    assert set(result.furthest_round) == set(seeds)
    assert result.champion in seeds


# ---- fields that aren't full --------------------------------------------------

def test_a_short_field_plays_on_with_walkovers_for_the_empty_slots():
    result = play(seeds=[0, 1, 2])  # seeds 4-12 are empty
    assert result.champion == 0
    assert result.bye_teams == [0, 1, 2]
    # Only the 2 vs 3 semifinal and the final have two real teams, so only those are played.
    assert {g.game for g in result.games if g.score_a is not None} == {"SF-2/3", "FINAL"}
    assert all(g.score_b is None for g in result.games if g.score_a is None)
    assert len(result.games) == 11  # a walkover still gets a row, so the log always has every game


def test_a_walkover_team_is_credited_with_reaching_the_next_round():
    # Seeds 10-12 are empty, so seeds 7, 6 and 5 (indexes 6, 5, 4) advance without playing; seed 9
    # (index 8) does play, against seed 8, and loses.
    result = play(seeds=list(range(9)))
    unplayed = {g.game for g in result.games if g.score_a is None and g.round == FIRST_ROUND}
    assert unplayed == {"R1-5v12", "R1-6v11", "R1-7v10"}
    assert [result.furthest_round[team] for team in (4, 5, 6)] == [QUARTERFINAL] * 3
    assert result.furthest_round[8] == FIRST_ROUND


def test_an_empty_field_has_no_champion_and_a_single_team_wins_by_default():
    assert play(seeds=[]).champion is None
    assert play(seeds=[7]).champion == 7


def test_too_many_teams_or_a_repeated_team_is_rejected():
    with pytest.raises(ValueError, match="holds 12"):
        play(seeds=list(range(13)), ratings=chalk(13))
    with pytest.raises(ValueError, match="only be in the field once"):
        play(seeds=[0, 1, 1])
