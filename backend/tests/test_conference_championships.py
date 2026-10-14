"""Conference championship games: finalist selection, tiebreakers, sites, and the season simulation."""

import random

import pandas as pd
import pytest

from app.conference_championships import (
    CHAMPIONSHIP_WEEK,
    CONFERENCE_RULES,
    ConferenceModel,
    ConferenceRules,
)
from app.season_simulation import (
    PlayedGame,
    SimGame,
    SimTeam,
    _build_conference_models,
    simulate_season,
)

STRONG = dict(offense=200.0, defense=200.0)  # always beats WEAK (see test_season_simulation.py)
WEAK = dict(offense=-200.0, defense=-200.0)


# ---- helpers: ConferenceModel on its own -----------------------------------

def make_model(conference, members, played=(), schedule=None, divisions=None, ratings=None):
    """`played` is a list of (winner, loser); `schedule` (who plays whom) defaults to the same pairs."""
    played = list(played)
    return ConferenceModel(
        name=conference,
        rules=CONFERENCE_RULES[conference],
        members=list(members),
        schedule=list(schedule) if schedule is not None else played,
        played=played,
        division_of=divisions or {},
        rating=ratings or {},
    )


def records(model):
    size = max(model.members) + 1
    return ([model.base_wins.get(i, 0) for i in range(size)], [model.base_losses.get(i, 0) for i in range(size)])


def finalists(model, wins=None, losses=None, seed=0):
    """Pick finalists. By default the records come from the games played; pass wins/losses to set them directly."""
    if wins is None:
        wins, losses = records(model)
    return model.pick_finalists(wins, losses, model.base_results, random.Random(seed))


# ---- the rules table matches the spec --------------------------------------

def test_every_conference_and_its_tiebreakers_are_as_specified():
    assert set(CONFERENCE_RULES) == {
        "SEC", "Big Ten", "Big 12", "ACC", "Pac-12", "American Athletic",
        "Conference USA", "Sun Belt", "Mountain West", "Mid-American",
    }
    h2h = "head_to_head"
    expected = {
        "SEC": (h2h, "common_opponents"),
        "Big Ten": (h2h, "common_opponents"),
        "Big 12": (h2h, "common_opponents"),
        "ACC": (h2h, "random"),
        "Pac-12": (h2h, "common_opponent_standing"),
        "American Athletic": (h2h, "model_rating"),
        "Conference USA": (h2h, "common_opponents"),
        "Sun Belt": (h2h, "division_pct"),
        "Mountain West": (h2h, "model_rating"),
        "Mid-American": (h2h, "common_opponents"),
    }
    assert {name: rules.tiebreakers for name, rules in CONFERENCE_RULES.items()} == expected


def test_only_the_four_power_conferences_play_at_a_neutral_site():
    neutral = {name for name, rules in CONFERENCE_RULES.items() if rules.neutral_site}
    assert neutral == {"SEC", "Big Ten", "Big 12", "ACC"}


def test_only_the_sun_belt_uses_divisions():
    assert {name for name, rules in CONFERENCE_RULES.items() if rules.divisions} == {"Sun Belt"}


def test_bad_rules_are_rejected():
    with pytest.raises(ValueError, match="Unknown tiebreaker"):
        ConferenceRules(neutral_site=True, tiebreakers=("head_to_head", "coin_flip"))
    with pytest.raises(ValueError, match="divisions"):
        ConferenceRules(neutral_site=True, tiebreakers=("division_pct",))


# ---- finalists: winning percentage, then tiebreakers -----------------------

def test_finalists_are_chosen_by_winning_percentage_not_total_wins():
    model = make_model("SEC", range(5))
    # Team 2 has the most wins (8) but the third-best percentage; 0 and 1 played fewer games.
    wins, losses = [6, 7, 8, 3, 2], [0, 1, 2, 5, 6]  # .1000, .875, .800, .375, .250
    assert finalists(model, wins, losses) == (0, 1)


def test_a_clear_top_two_needs_no_tiebreaker():
    model = make_model("ACC", range(4))  # ACC's 2nd tiebreaker is random; it must not be reached
    seen = {finalists(model, [3, 2, 1, 0], [0, 1, 2, 3], seed=s) for s in range(20)}
    assert seen == {(0, 1)}


@pytest.mark.parametrize("flip", [False, True])
def test_head_to_head_breaks_a_two_way_tie_and_decides_who_is_first(flip):
    # 0 and 1 both finish 2-1; 1 beat 0, so 1 is first. 3 is 1-1, 2 is 0-2.
    games = [(1, 0), (0, 2), (0, 3), (1, 2), (3, 1)]
    if flip:  # same story with the team labels swapped
        swap = {0: 1, 1: 0, 2: 2, 3: 3}
        games = [(swap[w], swap[l]) for w, l in games]
    model = make_model("SEC", range(4), games)
    assert finalists(model) == ((0, 1) if flip else (1, 0))


def test_a_tie_for_the_second_spot_is_broken_among_only_the_tied_teams():
    # 4 is 2-1 and clearly first. 0, 1 and 2 are all 2-2 for the other spot.
    # Among themselves: 0 beat 1 and 2, 1 beat 2 -> 0 wins the spot.
    games = [(0, 1), (0, 2), (1, 2), (3, 0), (4, 0), (1, 3), (4, 1), (2, 3), (2, 4)]
    model = make_model("SEC", range(5), games)
    wins, losses = records(model)
    assert [round(w / (w + l), 3) for w, l in zip(wins, losses)] == [0.5, 0.5, 0.5, 0.333, 0.667]
    assert finalists(model) == (4, 0)


def test_a_three_way_tie_split_by_head_to_head_restarts_among_the_rest():
    # 0, 1, 2 tied. 0 beat both 1 and 2, so 0 is first. 1 and 2 didn't play each
    # other, so the common-opponent record decides: vs {0, 3, 4}, 1 went 1-2 and 2 went 2-1.
    games = [(0, 1), (0, 2), (1, 3), (4, 1), (2, 3), (2, 4)]
    model = make_model("SEC", range(5), games)
    wins, losses = [5, 5, 5, 1, 1], [1, 1, 1, 5, 5]  # 0, 1, 2 level on record
    assert finalists(model, wins, losses) == (0, 2)


def test_common_opponents_decide_when_the_tied_teams_did_not_play_each_other():
    # 0 and 1 didn't meet. Both played 2, 3 and 4: 0 went 2-1, 1 went 1-2.
    games = [(0, 2), (0, 3), (4, 0), (1, 2), (3, 1), (4, 1)]
    model = make_model("Conference USA", range(5), games)
    wins, losses = [4, 4, 1, 1, 3], [1, 1, 4, 4, 2]
    assert finalists(model, wins, losses) == (0, 1)
    swap = {0: 1, 1: 0}  # and it isn't just "lower team number wins"
    flipped = make_model("Conference USA", range(5), [(swap.get(w, w), swap.get(l, l)) for w, l in games])
    assert finalists(flipped, wins, losses) == (1, 0)


def test_only_opponents_every_tied_team_played_count_as_common():
    # 0 and 1 share only opponent 2 (both beat it). 0 also beat 3 and 1 lost to 4, but
    # those aren't common, so the records vs common opponents are level -> random.
    games = [(0, 2), (1, 2), (0, 3), (4, 1)]
    model = make_model("SEC", range(5), games)
    wins, losses = [5, 5, 1, 1, 1], [1, 1, 5, 5, 5]
    firsts = {finalists(model, wins, losses, seed=s)[0] for s in range(40)}
    assert firsts == {0, 1}


def test_pac12_compares_the_highest_placed_common_opponent_first():
    # 0 and 1 are level at the top. Common opponents: 2 (placed higher, .800) and 3 (.400).
    # Overall they're 1-1 against the two, but 1 beat the higher-placed one (2); 0 lost to it.
    games = [(0, 3), (2, 0), (1, 2), (3, 1)]
    wins, losses = [5, 5, 4, 2, 1], [1, 1, 1, 3, 5]
    pac12 = make_model("Pac-12", range(5), games)
    assert {finalists(pac12, wins, losses, seed=s) for s in range(30)} == {(1, 0)}

    # Under the plain common-opponent rule that same data is a dead heat -> random.
    sec = make_model("SEC", range(5), games)
    assert {finalists(sec, wins, losses, seed=s)[0] for s in range(40)} == {0, 1}


def test_pac12_moves_to_the_next_placed_opponent_when_the_first_is_level():
    # Both lost to 2 (the top-placed common opponent), so it's a wash; 3 is next: 1 beat it, 0 lost to it.
    games = [(2, 0), (2, 1), (3, 0), (1, 3)]
    wins, losses = [5, 5, 4, 2], [1, 1, 1, 3]
    pac12 = make_model("Pac-12", range(4), games)
    assert {finalists(pac12, wins, losses, seed=s) for s in range(30)} == {(1, 0)}


def test_acc_uses_head_to_head_first_then_picks_randomly():
    wins, losses = [3, 3, 1], [1, 1, 3]
    played = make_model("ACC", range(3), [(0, 1)])  # 0 beat 1
    assert {finalists(played, wins, losses, seed=s) for s in range(30)} == {(0, 1)}

    unplayed = make_model("ACC", range(3), schedule=[], played=[])
    results = {finalists(unplayed, wins, losses, seed=s) for s in range(60)}
    assert results == {(0, 1), (1, 0)}  # always the same two teams, in random order


def test_ties_the_listed_tiebreakers_cannot_settle_are_broken_randomly():
    model = make_model("SEC", range(3), played=[], schedule=[])
    wins, losses = [3, 3, 3], [1, 1, 1]
    pairs = {frozenset(finalists(model, wins, losses, seed=s)) for s in range(60)}
    assert pairs == {frozenset({0, 1}), frozenset({0, 2}), frozenset({1, 2})}


@pytest.mark.parametrize("conference", ["American Athletic", "Mountain West"])
def test_american_and_mountain_west_fall_back_to_the_model_rating(conference):
    wins, losses = [3, 3, 1], [1, 1, 3]
    model = make_model(conference, range(3), played=[], schedule=[], ratings={0: 10.0, 1: 20.0, 2: 99.0})
    assert {finalists(model, wins, losses, seed=s) for s in range(20)} == {(1, 0)}  # 2 is out on record

    model = make_model(conference, range(3), played=[], schedule=[], ratings={0: 30.0, 1: 20.0, 2: 0.0})
    assert {finalists(model, wins, losses, seed=s) for s in range(20)} == {(0, 1)}


@pytest.mark.parametrize("conference", ["American Athletic", "Mountain West"])
def test_head_to_head_still_beats_the_model_rating(conference):
    wins, losses = [3, 3, 1], [1, 1, 3]
    model = make_model(conference, range(3), played=[(0, 1)], ratings={0: 1.0, 1: 90.0, 2: 0.0})
    assert finalists(model, wins, losses) == (0, 1)  # 0 is the worse team but beat 1


# ---- Sun Belt: divisions ---------------------------------------------------

DIVISIONS = {0: "East", 1: "East", 2: "East", 3: "West", 4: "West", 5: "West"}


def sun_belt(played=(), schedule=None):
    return make_model("Sun Belt", range(6), played, schedule, divisions=DIVISIONS)


def test_sun_belt_sends_the_best_team_from_each_division_even_if_not_top_two_overall():
    # The three best records are all East, but only one East team can play.
    wins, losses = [7, 6, 6, 3, 5, 1], [1, 2, 2, 5, 3, 7]
    first, second = finalists(sun_belt(), wins, losses)
    assert (first, second) == (0, 4)  # 0 = East winner (.875), 4 = West winner (.625)


def test_sun_belt_better_conference_record_is_the_host():
    wins, losses = [3, 2, 1, 7, 6, 1], [5, 6, 7, 1, 2, 7]
    assert finalists(sun_belt(), wins, losses) == (3, 0)  # West winner (.875) is first; East winner (.375)


def test_sun_belt_division_tie_is_broken_by_head_to_head_first():
    # 0 and 1 are level atop the East; 1 beat 0.
    model = sun_belt(played=[(1, 0)], schedule=[(1, 0)])
    wins, losses = [5, 5, 1, 2, 6, 1], [2, 2, 6, 5, 1, 6]
    assert finalists(model, wins, losses) == (4, 1)  # West winner 4 (.857) hosts East winner 1


def test_sun_belt_division_tie_then_goes_to_division_record():
    # 0 and 1 didn't play each other. Within the East, 0 beat 2 and 1 lost to 2.
    games = [(0, 2), (2, 1), (3, 0), (1, 4)]
    model = sun_belt(played=games)
    wins, losses = [5, 5, 1, 2, 6, 1], [2, 2, 6, 5, 1, 6]
    assert finalists(model, wins, losses)[1] == 0


def test_sun_belt_division_winners_level_on_record_use_head_to_head_for_the_host():
    # East winner 0 and West winner 3 are both .750; 3 beat 0 in the regular season.
    model = sun_belt(played=[(3, 0)], schedule=[(3, 0)])
    wins, losses = [6, 2, 1, 6, 2, 1], [2, 6, 7, 2, 6, 7]
    assert {finalists(model, wins, losses, seed=s) for s in range(20)} == {(3, 0)}


def test_sun_belt_needs_complete_divisions():
    no_division = {k: v for k, v in DIVISIONS.items() if k != 5}
    with pytest.raises(ValueError, match="have none"):
        make_model("Sun Belt", range(6), divisions=no_division)
    three = {**DIVISIONS, 5: "North"}
    with pytest.raises(ValueError, match="exactly two divisions"):
        make_model("Sun Belt", range(6), divisions=three)


def test_a_conference_needs_two_teams():
    with pytest.raises(ValueError, match="at least two"):
        make_model("SEC", [0])


# ---- the season simulation -------------------------------------------------

def team(team_id, conference, classification="fbs", **kwargs):
    ratings = {**dict(offense=0.0, defense=0.0), **kwargs}
    return SimTeam(team_id=team_id, school=f"T{team_id}", conference=conference,
                   classification=classification, **ratings)


def row(results, team_id):
    return results[results.team_id == team_id].iloc[0]


def round_robin(ids, week=6):
    return [SimGame(a, b, conference_game=True, week=week) for i, a in enumerate(ids) for b in ids[i + 1:]]


def test_every_conference_sends_exactly_two_teams_and_crowns_one():
    teams = [team(i, "Pac-12", **STRONG if i == 1 else {}) for i in range(1, 7)]
    results = simulate_season(teams, round_robin(list(range(1, 7))), n_simulations=300, seed=1)
    assert results.title_game_pct.sum() == pytest.approx(200.0)
    assert results.conf_champ_pct.sum() == pytest.approx(100.0)
    assert row(results, 1).title_game_pct == 100.0  # a team that wins everything always gets there


def test_a_dominant_team_wins_its_conference_and_its_title_game():
    teams = [team(1, "SEC", **STRONG), team(2, "SEC", **WEAK), team(3, "SEC", offense=3.0, defense=3.0)]
    results = simulate_season(teams, round_robin([1, 2, 3]), n_simulations=100, seed=2)
    assert row(results, 1).title_game_pct == 100.0 and row(results, 1).conf_champ_pct == 100.0
    assert row(results, 2).title_game_pct == 0.0 and row(results, 2).conf_champ_pct == 0.0


def test_title_game_is_never_part_of_wins_losses_bowl_or_undefeated():
    # Weak team 2 beat strong team 1 earlier, so 2 is 1-0 and 1 is 0-1: they play the title game.
    # 1 wins it every time -- yet 2 stays 1-0, 'undefeated' and with a loss-free projection.
    teams = [
        SimTeam(1, "T1", "Pac-12", "fbs", **STRONG, wins=0, losses=1),
        SimTeam(2, "T2", "Pac-12", "fbs", **WEAK, wins=1, losses=0, fbs_wins=1),
    ]
    results = simulate_season(teams, [], n_simulations=200, seed=3,
                              played_conference_games=[PlayedGame(winner_id=2, loser_id=1)])
    strong, weak = row(results, 1), row(results, 2)
    assert (strong.title_game_pct, weak.title_game_pct) == (100.0, 100.0)
    assert strong.conf_champ_pct == 100.0 and weak.conf_champ_pct == 0.0
    assert (strong.avg_wins, strong.avg_losses) == (0, 1)  # the title-game win isn't counted
    assert (weak.avg_wins, weak.avg_losses) == (1, 0)  # the title-game loss isn't counted
    assert weak.undefeated_pct == 100.0 and strong.undefeated_pct == 0.0
    assert weak.bowl_pct == 0.0 and strong.bowl_pct == 0.0


def test_the_standings_so_far_decide_the_finalists():
    teams = [team(i, "SEC") for i in (1, 2, 3)]
    played = [PlayedGame(1, 2), PlayedGame(1, 3), PlayedGame(2, 3)]  # 1: 2-0, 2: 1-1, 3: 0-2
    results = simulate_season(teams, [], n_simulations=100, seed=4, played_conference_games=played)
    assert [row(results, i).title_game_pct for i in (1, 2, 3)] == [100.0, 100.0, 0.0]
    assert row(results, 1).title_game_pct + row(results, 2).title_game_pct == 200.0


def _first_place_champ_pct(conference):
    # Two equal teams; team 1 finishes first (it beat team 2), so it hosts if the conference plays on campus.
    teams = [team(1, conference), team(2, conference)]
    results = simulate_season(teams, [], n_simulations=6000, seed=11,
                              played_conference_games=[PlayedGame(1, 2)])
    return row(results, 1).conf_champ_pct


def test_the_first_place_team_hosts_unless_the_conference_plays_at_a_neutral_site():
    campus = _first_place_champ_pct("Pac-12")
    assert campus > 53.0  # a ~2.5-point home edge between equal teams is worth about 6 points of win%
    for neutral in ("SEC", "Big Ten", "Big 12", "ACC"):
        assert 46.5 < _first_place_champ_pct(neutral) < 53.5


def test_games_in_or_after_championship_week_do_not_count_toward_the_standings():
    teams = [team(i, "Pac-12") for i in (1, 2, 3)]
    games = [
        SimGame(1, 2, conference_game=True, week=6),
        SimGame(1, 3, conference_game=True, week=CHAMPIONSHIP_WEEK + 1),  # played after the title game
        SimGame(2, 3, neutral_site=False, conference_game=False, week=7),  # not a conference game
    ]
    index = {t.team_id: i for i, t in enumerate(teams)}
    models, conference_of_game = _build_conference_models(teams, games, [], index)
    assert len(models) == 1
    assert models[0].schedule == [(0, 1)]
    assert conference_of_game == [0, -1, -1]


def test_a_late_conference_game_still_counts_in_the_regular_season_record():
    teams = [team(1, "American Athletic", **STRONG), team(2, "American Athletic", **WEAK)]
    games = [SimGame(1, 2, conference_game=True, week=CHAMPIONSHIP_WEEK + 1)]  # e.g. Army-Navy
    results = simulate_season(teams, games, n_simulations=50, seed=5)
    assert (row(results, 1).avg_wins, row(results, 2).avg_losses) == (1, 1)


def test_non_title_teams_have_no_title_game_numbers():
    teams = [
        team(1, "SEC"), team(2, "SEC"),
        team(3, "FBS Independents"), team(4, "Big Sky", classification="fcs"),
        team(5, "SEC", classification="fcs"),  # an FCS team never plays in the FBS title game
    ]
    results = simulate_season(teams, [SimGame(3, 4)], n_simulations=20, seed=1)
    for team_id in (3, 4, 5):
        assert pd.isna(row(results, team_id).title_game_pct)
        assert pd.isna(row(results, team_id).conf_champ_pct)
    assert not pd.isna(row(results, 1).title_game_pct)


def test_sun_belt_title_game_has_one_team_from_each_division():
    east, west = [1, 2, 3], [4, 5, 6]
    teams = (
        [team(i, "Sun Belt", division="East", offense=float(i), defense=0.0) for i in east]
        + [team(i, "Sun Belt", division="West", offense=float(i), defense=0.0) for i in west]
    )
    results = simulate_season(teams, round_robin(east + west), n_simulations=400, seed=6)
    in_east = results[results.team_id.isin(east)].title_game_pct.sum()
    in_west = results[results.team_id.isin(west)].title_game_pct.sum()
    assert in_east == pytest.approx(100.0) and in_west == pytest.approx(100.0)
    assert results.conf_champ_pct.sum() == pytest.approx(100.0)


def test_a_sun_belt_team_without_a_division_is_an_error():
    teams = [team(1, "Sun Belt", division="East"), team(2, "Sun Belt")]
    with pytest.raises(ValueError, match="divisions"):
        simulate_season(teams, [], n_simulations=5, seed=1)


def test_conference_runs_are_reproducible_with_a_seed():
    teams = [team(i, "ACC") for i in range(1, 7)]  # ACC ties are random, so this exercises the rng
    games = round_robin(list(range(1, 7)))
    a = simulate_season(teams, games, n_simulations=200, seed=9)
    b = simulate_season(teams, games, n_simulations=200, seed=9)
    assert a.equals(b)
