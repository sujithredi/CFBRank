"""College Football Playoff selection: the network, the field rules, and the season simulation wiring."""

import warnings

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app.conference_championships import CHAMPIONSHIP_WEEK, CONFERENCE_RULES
from app.database import Base
from app.models import Conference, Game, PowerRating, Team
from app.playoff import (
    AUTO_BID_CONFERENCES,
    FIELD_SIZE,
    GROUP_OF_6,
    PLAYOFF_DATA_PATH,
    RANKED_AUTO_BID_TEAMS,
    get_playoff_model,
    select_playoff_field,
    train_playoff_model,
)
from app.playoff_bracket import BracketResult
from app.season_simulation import PlayedScore, SimGame, SimTeam, load_season_inputs, simulate_season

STRONG = dict(offense=200.0, defense=200.0)  # always beats WEAK (see test_season_simulation.py)
WEAK = dict(offense=-200.0, defense=-200.0)


class Recorder:
    """Stands in for the network: remembers what it was asked and scores teams with `score`."""

    def __init__(self, score=lambda sos, wins, losses: wins):
        self.calls = []
        self.score = score

    def probability(self, sos, wins, losses):
        sos, wins, losses = (np.asarray(values, dtype=float) for values in (sos, wins, losses))
        self.calls.append((sos, wins, losses))
        return self.score(sos, wins, losses)


# ---- the network -------------------------------------------------------------

def test_the_network_trains_on_the_repository_data_and_generalizes():
    model = get_playoff_model()
    assert model.test_accuracy >= 0.85
    assert get_playoff_model() is model  # trained once per process


def test_probabilities_are_valid_and_rise_with_a_better_record_and_schedule():
    model = get_playoff_model()
    records = [(12, 0), (10, 2), (8, 4)]
    p = model.probability([22.0] * 3, [w for w, _ in records], [l for _, l in records])
    assert ((p >= 0) & (p <= 1)).all()
    assert p[0] > p[1] > p[2]

    easy, hard = model.probability([12.0, 24.0], [10, 10], [2, 2])
    assert hard > easy  # same record, tougher schedule


def test_training_is_deterministic_and_raises_no_convergence_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the deliberate 21-iteration limit must not leak a warning
        first = train_playoff_model()
        second = train_playoff_model()
    probe = ([5.0, 18.0, 25.0], [4, 9, 11], [8, 3, 1])
    np.testing.assert_array_equal(first.probability(*probe), second.probability(*probe))


def test_csv_columns_are_read_by_name_not_position(tmp_path):
    shuffled = pd.read_csv(PLAYOFF_DATA_PATH)[["loses", "wins", "playoffs", "sos"]]
    path = tmp_path / "shuffled.csv"
    shuffled.to_csv(path, index=False)
    probe = ([5.0, 18.0, 25.0], [4, 9, 11], [8, 3, 1])
    np.testing.assert_allclose(
        train_playoff_model(path).probability(*probe), get_playoff_model().probability(*probe)
    )


def test_training_data_problems_are_reported_clearly(tmp_path):
    missing = tmp_path / "missing.csv"
    pd.DataFrame({"playoffs": [0, 1], "sos": [1.0, 2.0], "wins": [3, 4]}).to_csv(missing, index=False)
    with pytest.raises(ValueError, match="loses"):
        train_playoff_model(missing)

    one_class = tmp_path / "one_class.csv"
    pd.DataFrame({"playoffs": [0, 0], "sos": [1.0, 2.0], "wins": [3, 4], "loses": [9, 8]}).to_csv(
        one_class, index=False
    )
    with pytest.raises(ValueError, match="both"):
        train_playoff_model(one_class)


# ---- who is in the field -----------------------------------------------------

def test_the_conference_lists_name_real_conferences_once():
    assert len(AUTO_BID_CONFERENCES) == 4 and len(GROUP_OF_6) == 6
    assert "Pac-12" in GROUP_OF_6  # the Pac-12 is a Group of 6 conference now
    assert not set(AUTO_BID_CONFERENCES) & set(GROUP_OF_6)
    assert set(AUTO_BID_CONFERENCES) | set(GROUP_OF_6) <= set(CONFERENCE_RULES)  # each can have a champion
    assert RANKED_AUTO_BID_TEAMS == ("Notre Dame",)
    assert FIELD_SIZE == 12


def probabilities(n=20):
    return [i / n for i in range(n)]  # a higher index is a better team


def test_champions_get_in_the_best_group_of_6_champion_gets_one_spot_and_the_rest_is_at_large():
    champions = {
        "ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3,  # the weakest teams, in anyway
        "American Athletic": 4, "Mountain West": 10, "Sun Belt": 5, "Conference USA": 6, "Mid-American": 7,
        "Pac-12": 8,  # a Group of 6 champion too, but not the best one
    }
    field = select_playoff_field(probabilities(), champions, range(20))
    assert field.conference_champions == [0, 1, 2, 3]
    assert field.group_of_6 == 10
    assert field.at_large == [19, 18, 17, 16, 15, 14, 13]  # best of the rest, best first
    assert 8 not in field.teams  # it lost the Group of 6 spot, so it has to earn one at large
    assert len(field.teams) == len(set(field.teams)) == FIELD_SIZE


def test_a_group_of_6_champion_that_loses_the_spot_can_still_get_in_at_large():
    champions = {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3, "American Athletic": 19, "Mountain West": 18}
    field = select_playoff_field(probabilities(), champions, range(20))
    assert field.group_of_6 == 19
    assert 18 in field.at_large


def test_a_conference_without_a_champion_does_not_leave_a_spot_empty():
    champions = {"ACC": 0, "Big Ten": 1, "Big 12": 3, "Sun Belt": 5}  # no SEC champion
    field = select_playoff_field(probabilities(), champions, range(20))
    assert field.conference_champions == [0, 1, 3] and field.group_of_6 == 5
    assert len(field.at_large) == FIELD_SIZE - 4
    assert len(field.teams) == FIELD_SIZE

    no_group_of_6 = select_playoff_field(probabilities(), {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3}, range(20))
    assert no_group_of_6.group_of_6 is None
    assert len(no_group_of_6.teams) == FIELD_SIZE


def test_the_pac_12_champion_can_take_the_group_of_6_spot():
    champions = {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3, "Mountain West": 10, "Pac-12": 14}
    field = select_playoff_field(probabilities(), champions, range(20))
    assert field.group_of_6 == 14  # the better of the two Group of 6 champions
    assert field.at_large == [19, 18, 17, 16, 15, 13, 12]
    assert 10 not in field.teams  # the Mountain West champion lost the spot and is too weak to get in at large


def test_a_ranked_auto_bid_team_in_the_top_12_gets_in_even_when_the_automatic_bids_crowd_it_out():
    # Probabilities rise with the index, so the top 12 teams overall are 19..8. Four weak conference
    # champions (0-3) and a weak Group of 6 champion (4) take five spots, leaving seven at large.
    champions = {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3, "Sun Belt": 4}
    without = select_playoff_field(probabilities(), champions, range(20))
    assert without.at_large == [19, 18, 17, 16, 15, 14, 13]
    assert 12 not in without.teams  # 12 is the 8th best team overall, but the at-large spots run out

    with_bid = select_playoff_field(probabilities(), champions, range(20), ranked_auto_bid=[12])
    assert with_bid.ranked_auto == [12]
    # Its spot comes out of the at-large pool: the last at-large team (13) is the one bumped.
    assert with_bid.at_large == [19, 18, 17, 16, 15, 14]
    assert len(with_bid.teams) == len(set(with_bid.teams)) == FIELD_SIZE


def test_a_ranked_auto_bid_team_outside_the_top_12_does_not_get_one():
    champions = {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3}
    field = select_playoff_field(probabilities(), champions, range(20), ranked_auto_bid=[5])  # 15th best of 20
    assert field.ranked_auto == [] and 5 not in field.teams
    assert len(field.teams) == FIELD_SIZE


def test_a_ranked_auto_bid_team_that_would_get_in_anyway_is_not_counted_twice():
    champions = {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3}
    field = select_playoff_field(probabilities(), champions, range(20), ranked_auto_bid=[19])
    assert field.ranked_auto == [19]
    assert field.at_large == [18, 17, 16, 15, 14, 13, 12]
    assert len(field.teams) == len(set(field.teams)) == FIELD_SIZE


def test_a_ranked_auto_bid_team_that_is_not_eligible_is_ignored():
    champions = {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3}
    field = select_playoff_field(probabilities(), champions, [i for i in range(20) if i != 19], ranked_auto_bid=[19])
    assert field.ranked_auto == [] and 19 not in field.teams


def test_ties_go_to_the_lower_index():
    champions = {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3, "Sun Belt": 6, "American Athletic": 5}
    field = select_playoff_field([0.5] * 20, champions, range(20))
    assert field.group_of_6 == 5
    # Not 5 again, and 6 (the Group of 6 champion that lost the tie) is back in the at-large pool.
    assert field.at_large == [4, 6, 7, 8, 9, 10, 11]


def test_a_small_pool_takes_everyone_and_the_field_size_can_change():
    assert sorted(select_playoff_field([0.1, 0.2, 0.3], {}, range(3)).teams) == [0, 1, 2]
    field = select_playoff_field(probabilities(), {"ACC": 0, "Big Ten": 1, "SEC": 2, "Big 12": 3}, range(20), field_size=4)
    assert field.teams == [0, 1, 2, 3] and field.at_large == []


# ---- wired into the season simulation ----------------------------------------

def fbs(team_id, conference="Indie", **kwargs):
    return SimTeam(team_id=team_id, school=f"T{team_id}", conference=conference, classification="fbs",
                   **{**dict(offense=0.0, defense=0.0), **kwargs})


def test_strength_of_schedule_is_the_average_opponent_rating_of_every_regular_season_game():
    teams = [
        fbs(1, offense=10.0, defense=5.0),  # overall 15
        fbs(2, offense=2.0, defense=-4.0),  # overall -2
        SimTeam(3, "FCS3", "Independent", "fcs", offense=-8.0, defense=-10.0),  # overall -18
        fbs(4, offense=20.0, defense=20.0),  # overall 40
    ]
    played = [
        PlayedScore(1, 3, 40, 3),  # team 1 already beat an FCS team: that opponent counts
        PlayedScore(1, 4, 10, 30, title_game=True),  # a real title game is not a regular-season opponent
    ]
    games = [SimGame(1, 2, week=8), SimGame(2, 4, week=9)]
    model = Recorder()
    simulate_season(teams, games, n_simulations=1, seed=1, played_games=played, update_ratings=False,
                    playoff_model=model)

    sos, _, _ = model.calls[0]  # the three FBS teams, in order: 1, 2, 4
    np.testing.assert_allclose(sos, [(-18 + -2) / 2, (15 + 40) / 2, -2])


def test_strength_of_schedule_uses_the_ratings_after_the_last_simulated_week(monkeypatch):
    class FixedRatings:
        """Stands in for the re-fit: the ratings after every week are these, whatever was played."""

        def __init__(self, n_teams, *args):
            self.n = n_teams

        def start_vector(self):
            return [0.0]

        def add_game(self, *args):
            pass

        def ratings(self, stage, b):
            return [0.0, 10.0, 30.0, 70.0][: self.n], [0.0] * self.n

    monkeypatch.setattr("app.season_simulation.RatingRefitter", FixedRatings)
    teams = [fbs(1, offense=10.0, defense=5.0), fbs(2), fbs(3), fbs(4)]
    games = [SimGame(1, 2, week=8), SimGame(2, 4, week=9)]
    model = Recorder()
    simulate_season(teams, games, n_simulations=1, seed=1, played_games=[PlayedScore(1, 3, 20, 10)],
                    playoff_model=model)

    sos, _, _ = model.calls[0]  # teams 1, 2, 3, 4; stored ratings would give very different numbers
    np.testing.assert_allclose(sos, [(30 + 10) / 2, (0 + 70) / 2, 0.0, 10.0])


def test_the_record_given_to_the_network_is_regular_season_wins_and_losses():
    teams = [fbs(1, wins=3, losses=1, **STRONG), fbs(2, **WEAK)]
    model = Recorder()
    simulate_season(teams, [SimGame(1, 2, week=1), SimGame(1, 2, week=2)], n_simulations=1, seed=1,
                    playoff_model=model)
    _, wins, losses = model.calls[0]
    assert wins.tolist() == [5, 0] and losses.tolist() == [1, 2]


def test_a_played_game_with_an_unknown_team_is_rejected():
    with pytest.raises(ValueError, match="isn't in `teams`"):
        simulate_season([fbs(1), fbs(2)], [SimGame(1, 2)], n_simulations=1, update_ratings=False,
                        played_games=[PlayedScore(1, 99, 10, 3)], playoff_model=Recorder())


def field_teams(extra=()):
    """
    Twelve FBS teams in six two-team conferences (the odd id is STRONG, so it always wins its
    conference's title game), four independents, and `extra`. Team k has k wins and the Recorder
    rates a team by its wins, so a higher id is a better team.
    """
    conferences = ["SEC", "Big Ten", "Big 12", "ACC", "Mountain West", "American Athletic"]
    teams = []
    for number, conference in enumerate(conferences):
        strong, weak = 2 * number + 1, 2 * number + 2
        teams.append(fbs(strong, conference, wins=strong, **STRONG))
        teams.append(fbs(weak, conference, wins=weak, **WEAK))
    teams += [fbs(i, "FBS Independents", wins=i) for i in range(13, 17)]
    return teams + list(extra)


def playoff_pct(results):
    return dict(zip(results.team_id, results.playoff_pct))


def test_the_field_is_champions_then_the_best_group_of_6_champion_then_at_large():
    results = simulate_season(field_teams(), [], n_simulations=20, seed=1, playoff_model=Recorder())
    pct = playoff_pct(results)
    in_field = {1, 3, 5, 7, 11, 16, 15, 14, 13, 12, 10, 9}
    # 1, 3, 5, 7: SEC / Big Ten / Big 12 / ACC champions. 11: the better of the two Group of 6 champions
    # (9 and 11); 9 still gets in at large. 16..13, 12, 10: the best of the rest. 2, 4, 6, 8 miss out.
    assert {team for team, value in pct.items() if value == 100.0} == in_field
    assert {team for team, value in pct.items() if value == 0.0} == {2, 4, 6, 8}


def test_an_fcs_team_is_never_selected_however_the_network_rates_it():
    fcs = SimTeam(99, "FCS99", "Independent", "fcs", offense=0.0, defense=0.0, wins=99)
    results = simulate_season(field_teams([fcs]), [], n_simulations=20, seed=1, playoff_model=Recorder())
    assert pd.isna(results[results.team_id == 99].iloc[0].playoff_pct)
    pct = playoff_pct(results)
    assert {team for team, value in pct.items() if value == 100.0} == {1, 3, 5, 7, 11, 16, 15, 14, 13, 12, 10, 9}


def test_choosing_the_field_never_changes_the_rest_of_the_simulation():
    games = [SimGame(a, b, conference_game=True, week=6) for a, b in ((1, 2), (3, 4), (5, 6), (7, 8))]
    games += [SimGame(13, 14, week=6), SimGame(15, 16, week=7)]
    runs = [
        simulate_season(field_teams(), games, n_simulations=60, seed=5, playoff_model=model)
        for model in (Recorder(), Recorder(lambda sos, wins, losses: -wins))
    ]
    field_columns = ["playoff_pct", "cfp_bye_pct", "cfp_quarterfinal_pct", "cfp_semifinal_pct",
                     "cfp_final_pct", "cfp_champion_pct"]  # who is in the field, and so who plays
    other_columns = [c for c in runs[0].columns if c not in field_columns]
    pd.testing.assert_frame_equal(runs[0][other_columns], runs[1][other_columns])
    assert not runs[0].playoff_pct.equals(runs[1].playoff_pct)  # ...while the field itself does change


def test_with_the_real_network_every_season_has_a_full_field_and_the_champions_are_in():
    results = simulate_season(field_teams(), [], n_simulations=40, seed=2)  # default model: the trained network
    assert results.playoff_pct.sum() == pytest.approx(100.0 * FIELD_SIZE)
    pct = playoff_pct(results)
    assert all(pct[champion] == 100.0 for champion in (1, 3, 5, 7))


CFP_COLUMNS = ["cfp_bye_pct", "cfp_quarterfinal_pct", "cfp_semifinal_pct", "cfp_final_pct", "cfp_champion_pct"]


def test_notre_dame_is_found_by_name_and_takes_the_automatic_bid_it_has_earned():
    # With the Recorder a team's strength is its wins, so a higher id is a better team, and the field
    # is champions 1, 3, 5, 7, 11 plus the seven at-large teams 16, 15, 14, 13, 12, 10 and 9.
    # Notre Dame (9 wins, so 9th in the top 12) is the 8th-best team left, and just misses at large
    # (it ties team 9, and the lower index wins the tie). As Notre Dame it takes team 9's spot.
    def run(school):
        irish = SimTeam(17, school, "FBS Independents", "fbs", offense=0.0, defense=0.0, wins=9)
        results = simulate_season(field_teams([irish]), [], n_simulations=20, seed=1, playoff_model=Recorder())
        return playoff_pct(results)

    other = run("Boston College")
    assert other[17] == 0.0 and other[9] == 100.0

    notre_dame = run("Notre Dame")
    assert notre_dame[17] == 100.0 and notre_dame[9] == 0.0
    assert {team for team, value in notre_dame.items() if value == 100.0} == {1, 3, 5, 7, 11, 16, 15, 14, 13, 12, 10, 17}


def test_the_playoff_game_odds_add_up_to_the_bracket_totals_and_nest():
    results = simulate_season(field_teams(), [], n_simulations=60, seed=2)  # the real network
    totals = {column: results[column].sum() for column in CFP_COLUMNS}
    # 12 teams in the field, 4 byes, 8 teams in the quarterfinals, 4 in the semifinals, 2 in the final, 1 champion.
    assert results.playoff_pct.sum() == pytest.approx(1200.0)
    assert totals == pytest.approx(
        {"cfp_bye_pct": 400.0, "cfp_quarterfinal_pct": 800.0, "cfp_semifinal_pct": 400.0,
         "cfp_final_pct": 200.0, "cfp_champion_pct": 100.0}
    )
    for row in results.itertuples():
        # Each stage is a subset of the one before it (a bye team is also a quarterfinalist).
        assert (row.cfp_champion_pct <= row.cfp_final_pct <= row.cfp_semifinal_pct
                <= row.cfp_quarterfinal_pct <= row.playoff_pct)
        assert row.cfp_bye_pct <= row.cfp_quarterfinal_pct
        if row.playoff_pct == 0.0:
            assert all(getattr(row, column) == 0.0 for column in CFP_COLUMNS)  # missing the field is a 0, not null


def test_the_best_rated_teams_get_the_byes_and_a_weak_field_team_cannot_win_it_all():
    results = simulate_season(field_teams(), [], n_simulations=30, seed=3, playoff_model=Recorder())
    by_team = results.set_index("team_id")
    # STRONG teams (odd ids 1-11, overall 400) are seeded first, ties by order: 1, 3, 5, 7 are seeds 1-4.
    assert {team for team, pct in by_team.cfp_bye_pct.items() if pct == 100.0} == {1, 3, 5, 7}
    assert by_team.cfp_bye_pct.drop([1, 3, 5, 7]).eq(0.0).all()
    # The independents (overall 0) and the weak teams (overall -400) can't beat a STRONG team.
    strong = {1, 3, 5, 7, 9, 11}
    assert by_team.cfp_champion_pct.drop(list(strong)).eq(0.0).all()
    assert by_team.cfp_champion_pct.loc[list(strong)].sum() == pytest.approx(100.0)
    assert by_team.cfp_semifinal_pct.drop(list(strong)).eq(0.0).all()


def test_fcs_teams_have_no_playoff_game_odds():
    fcs = SimTeam(99, "FCS99", "Independent", "fcs", offense=0.0, defense=0.0, wins=99)
    results = simulate_season(field_teams([fcs]), [], n_simulations=10, seed=1, playoff_model=Recorder())
    row = results[results.team_id == 99].iloc[0]
    assert all(pd.isna(row[column]) for column in CFP_COLUMNS)


def test_playing_the_bracket_never_changes_any_other_column(monkeypatch):
    games = [SimGame(a, b, conference_game=True, week=6) for a, b in ((1, 2), (3, 4), (5, 6), (7, 8))]
    games += [SimGame(13, 14, week=6), SimGame(15, 16, week=7)]
    with_bracket = simulate_season(field_teams(), games, n_simulations=60, seed=5, playoff_model=Recorder())

    def no_games(seeds, *args, **kwargs):  # a bracket that plays nothing, and so draws nothing
        return BracketResult(list(seeds), [], None, {}, [])

    monkeypatch.setattr("app.season_simulation.simulate_bracket", no_games)
    without = simulate_season(field_teams(), games, n_simulations=60, seed=5, playoff_model=Recorder())

    other = [c for c in with_bracket.columns if c not in CFP_COLUMNS]
    pd.testing.assert_frame_equal(with_bracket[other], without[other])
    assert not with_bracket.cfp_champion_pct.equals(without.cfp_champion_pct)


def test_a_seeded_run_repeats_its_playoff_game_odds_exactly():
    run = lambda seed: simulate_season(field_teams(), [], n_simulations=40, seed=seed, playoff_model=Recorder())
    pd.testing.assert_frame_equal(run(8), run(8))


# ---- the loader marks real title games ---------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


def test_the_loader_flags_a_real_conference_title_game(db):
    db.add(Conference(id=1, cfbd_id=1, name="Sun Belt"))
    db.flush()
    db.add_all([
        Team(id=1, cfbd_id=1, school="Troy", classification="fbs", conference_id=1, division="West"),
        Team(id=2, cfbd_id=2, school="Marshall", classification="fbs", conference_id=1, division="East"),
    ])
    db.flush()
    for team_id in (1, 2):
        db.add(PowerRating(team_id=team_id, season=2026, week=6, rating=0.0, offense_rating=0.0, defense_rating=0.0))
    fields = dict(season=2026, season_type="regular", neutral_site=False, completed=True,
                  home_team_id=1, away_team_id=2, home_points=30, away_points=20)
    db.add_all([
        Game(cfbd_id=1, week=3, conference_game=True, **fields),
        Game(cfbd_id=2, week=CHAMPIONSHIP_WEEK, conference_game=True, **fields),
        Game(cfbd_id=3, week=CHAMPIONSHIP_WEEK, conference_game=False, **fields),  # same week, not a conference game
    ])
    db.commit()

    played = load_season_inputs(db).played_games
    assert sorted(g.title_game for g in played) == [False, False, True]
