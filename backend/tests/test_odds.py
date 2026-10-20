"""GET /api/odds/weekly: every upcoming game is simulated 1,000 times and the results averaged."""

import threading
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables on Base)
from app.database import Base, get_db
from app.main import app
from app.models import Game, Line, PowerRating, Team
from app.ratelimit import RateLimiter
from app.routers import odds
from app.routers.odds import NUM_SIMULATIONS, simulate_matchup
from app.simulation import load_sorted_scores


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
    """Alabama (strong) hosts Auburn in week 8. Ratings are from week 6, going into the week."""
    db.add_all([
        Team(id=10, cfbd_id=1, school="Alabama", classification="fbs", logo_url="http://logos/alabama.png"),
        Team(id=20, cfbd_id=2, school="Auburn", classification="fbs"),  # no logo on file
    ])
    db.flush()
    db.add_all([
        PowerRating(team_id=10, season=2026, week=6, rating=15, rank=1, offense_rating=9.0, defense_rating=6.0),
        PowerRating(team_id=20, season=2026, week=6, rating=3, rank=2, offense_rating=1.0, defense_rating=2.0),
    ])
    db.add(Game(cfbd_id=3, season=2026, week=8, season_type="regular", completed=False,
                start_date=datetime(2026, 10, 24, 19, 0), home_team_id=10, away_team_id=20))
    db.commit()


def _games(client, **params):
    response = client.get("/api/odds/weekly", params=params)
    assert response.status_code == 200
    return response.json()


def _rating(offense, defense):
    return PowerRating(team_id=0, season=2026, week=1, rating=offense + defense,
                       offense_rating=offense, defense_rating=defense)


# ---- how the numbers are made ------------------------------------------------

def test_each_game_is_simulated_1000_times(client, seeded, monkeypatch):
    calls = []
    real = odds.simulate_game
    monkeypatch.setattr(odds, "simulate_game", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))

    body = _games(client)
    assert NUM_SIMULATIONS == 1000
    assert body["num_simulations"] == 1000
    assert len(body["games"]) == 1
    assert len(calls) == 1000


def test_the_model_numbers_are_averages_over_the_simulated_games(monkeypatch):
    # Four scripted games: home wins two of them.
    scripted = iter([(30, 20), (20, 31), (27, 24), (10, 17)])

    def fake_simulate_game(*args, **kwargs):
        score_a, score_b = next(scripted)
        return {"score_a": score_a, "score_b": score_b, "expected_a": 0, "expected_b": 0, "overtime": False}

    monkeypatch.setattr(odds, "simulate_game", fake_simulate_game)
    result = simulate_matchup(_rating(1, 1), _rating(1, 1), neutral_site=False, seed=1,
                              sorted_scores=None, num_simulations=4)
    assert result.home_win_prob == 0.5  # 2 of 4
    assert result.home_points == (30 + 20 + 27 + 10) / 4
    assert result.away_points == (20 + 31 + 24 + 17) / 4


def test_win_probability_is_the_share_of_the_1000_simulations_each_team_won(client, seeded):
    game = _games(client)["games"][0]
    wins = game["model_home_win_prob"] * NUM_SIMULATIONS
    assert wins == pytest.approx(round(wins), abs=1e-6)  # a whole number of the 1000 simulations
    assert 0 < wins < NUM_SIMULATIONS


def test_projected_points_margin_and_total_agree_with_each_other(client, seeded):
    game = _games(client)["games"][0]
    # Each is rounded to one decimal on its own, so they can differ by a rounding step.
    assert game["model_predicted_margin"] == pytest.approx(game["model_home_points"] - game["model_away_points"], abs=0.11)
    assert game["model_total"] == pytest.approx(game["model_home_points"] + game["model_away_points"], abs=0.11)


def test_the_better_home_team_is_favored_and_scores_more(client, seeded):
    game = _games(client)["games"][0]
    assert game["home_team"] == "Alabama" and game["away_team"] == "Auburn"
    assert game["model_home_win_prob"] > 0.7
    assert game["model_home_points"] > game["model_away_points"]
    assert game["model_predicted_margin"] > 0
    assert 30 < game["model_total"] < 80  # a real football total, not a rating gap


def test_a_game_shows_the_same_numbers_every_time_until_the_ratings_change(client, seeded):
    assert _games(client) == _games(client)


def test_changing_a_teams_rating_changes_the_numbers(client, seeded, db):
    before = _games(client)["games"][0]
    db.query(PowerRating).filter_by(team_id=20).update({"offense_rating": 11.0, "rating": 13.0})
    db.commit()
    after = _games(client)["games"][0]
    assert after["model_home_win_prob"] < before["model_home_win_prob"]
    assert after["model_away_points"] > before["model_away_points"]


# ---- where the game is played ------------------------------------------------

def test_the_home_team_gets_the_home_edge_unless_the_game_is_at_a_neutral_site():
    scores = load_sorted_scores()
    home, away = _rating(5, 5), _rating(5, 5)  # evenly matched, so any edge is the site
    at_home = simulate_matchup(home, away, neutral_site=False, seed=7, sorted_scores=scores)
    neutral = simulate_matchup(home, away, neutral_site=True, seed=7, sorted_scores=scores)

    # Same random draws, so the gap between them is the home-field edge (2.5 points of margin).
    assert 1.5 < (at_home.home_points - at_home.away_points) - (neutral.home_points - neutral.away_points) < 3.5
    assert at_home.home_win_prob > neutral.home_win_prob
    assert neutral.home_win_prob == pytest.approx(0.5, abs=0.06)


def test_a_neutral_site_game_is_simulated_without_the_home_edge(client, seeded, db):
    db.query(Game).filter_by(cfbd_id=3).update({"neutral_site": True})
    db.commit()
    game = _games(client)["games"][0]

    expected = simulate_matchup(_rating(9, 6), _rating(1, 2), neutral_site=True, seed=3, sorted_scores=load_sorted_scores())
    assert game["model_home_win_prob"] == round(expected.home_win_prob, 4)
    assert game["model_home_points"] == round(expected.home_points, 1)


# ---- logos, lines, ratings -----------------------------------------------------

def test_each_teams_logo_is_included_and_is_null_when_there_isnt_one(client, seeded):
    game = _games(client)["games"][0]
    assert game["home_logo_url"] == "http://logos/alabama.png"
    assert game["away_logo_url"] is None


def test_market_lines_come_through_and_the_delta_uses_the_simulated_win_probability(client, seeded, db):
    game_row_id = db.query(Game).filter_by(cfbd_id=3).one().id
    db.add(Line(game_id=game_row_id, provider="consensus", spread=-14.5, over_under=55.5,
                home_moneyline=-200, away_moneyline=170))
    db.commit()
    game = _games(client)["games"][0]

    assert game["market_spread"] == -14.5
    assert game["market_home_moneyline"] == -200 and game["market_away_moneyline"] == 170
    assert game["delta"] == pytest.approx(round(game["model_home_win_prob"] - 200 / 300, 4))


def test_a_game_without_a_line_has_no_market_numbers_or_delta(client, seeded):
    game = _games(client)["games"][0]
    assert game["market_spread"] is None and game["market_home_moneyline"] is None and game["delta"] is None


def test_only_ratings_from_before_the_week_are_used(client, seeded, db):
    before = _games(client, season=2026, week=8)["games"][0]
    # A rating computed *after* this week's games must not leak into this week's odds.
    db.add_all([
        PowerRating(team_id=10, season=2026, week=8, rating=-30, offense_rating=-15.0, defense_rating=-15.0),
        PowerRating(team_id=20, season=2026, week=8, rating=30, offense_rating=15.0, defense_rating=15.0),
    ])
    db.commit()
    assert _games(client, season=2026, week=8)["games"][0] == before


def test_a_game_is_skipped_when_a_team_has_no_offense_and_defense_rating(client, seeded, db):
    db.add_all([
        Team(id=30, cfbd_id=4, school="Old Snapshot", classification="fbs"),
        Team(id=40, cfbd_id=5, school="No Ratings", classification="fbs"),
    ])
    db.flush()
    db.add(PowerRating(team_id=30, season=2026, week=6, rating=4))  # from before the offense/defense split
    db.add_all([
        Game(cfbd_id=6, season=2026, week=8, season_type="regular", completed=False, home_team_id=30, away_team_id=10),
        Game(cfbd_id=7, season=2026, week=8, season_type="regular", completed=False, home_team_id=40, away_team_id=20),
    ])
    db.commit()

    games = _games(client)["games"]
    assert [(g["home_team"], g["away_team"]) for g in games] == [("Alabama", "Auburn")]


def test_completed_games_are_not_included(client, seeded, db):
    db.query(Game).filter_by(cfbd_id=3).update({"completed": True, "home_points": 31, "away_points": 10})
    db.add(Game(cfbd_id=8, season=2026, week=8, season_type="regular", completed=False, home_team_id=20, away_team_id=10))
    db.commit()
    games = _games(client, season=2026, week=8)["games"]
    assert [(g["home_team"], g["away_team"]) for g in games] == [("Auburn", "Alabama")]


def test_a_week_with_no_upcoming_games_gets_the_placeholder_rows(client, seeded, db):
    db.query(Game).filter_by(cfbd_id=3).update({"completed": True, "home_points": 31, "away_points": 10})
    db.commit()
    games = _games(client, season=2026, week=8)["games"]
    assert [g["away_team"] for g in games] == ["Wisconsin", "Kentucky"]


# ---- the placeholder rows ------------------------------------------------------

def test_with_no_games_on_file_the_placeholder_rows_have_every_field(client):
    body = _games(client)
    assert body["num_simulations"] == NUM_SIMULATIONS
    assert len(body["games"]) == 2
    for game in body["games"]:
        for field in ("model_home_points", "model_away_points", "model_predicted_margin", "model_total",
                      "model_home_win_prob", "home_logo_url", "away_logo_url"):
            assert field in game
        assert game["model_predicted_margin"] == pytest.approx(game["model_home_points"] - game["model_away_points"], abs=0.11)
        assert game["model_total"] == pytest.approx(game["model_home_points"] + game["model_away_points"], abs=0.11)


# ---- the simulation cache ------------------------------------------------------

def _count_simulated_games(monkeypatch):
    """Wrap odds.simulate_game so a test can see how many games were really simulated."""
    calls = []
    real = odds.simulate_game
    monkeypatch.setattr(odds, "simulate_game", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))
    return calls


def test_a_repeat_request_reuses_the_simulations_instead_of_running_them_again(client, seeded, monkeypatch):
    calls = _count_simulated_games(monkeypatch)

    first = _games(client)
    assert len(calls) == NUM_SIMULATIONS

    second = _games(client)
    assert len(calls) == NUM_SIMULATIONS  # nothing new was simulated
    assert second == first  # and the answer is exactly the same


def test_cached_numbers_equal_freshly_simulated_numbers(client, seeded):
    body = _games(client)["games"][0]
    fresh = simulate_matchup(_rating(9, 6), _rating(1, 2), neutral_site=False, seed=3, sorted_scores=load_sorted_scores())
    assert body["model_home_win_prob"] == round(fresh.home_win_prob, 4)
    assert body["model_home_points"] == round(fresh.home_points, 1)
    assert body["model_away_points"] == round(fresh.away_points, 1)


def test_a_changed_rating_is_not_served_from_the_cache(client, seeded, db, monkeypatch):
    calls = _count_simulated_games(monkeypatch)
    before = _games(client)["games"][0]
    assert len(calls) == NUM_SIMULATIONS

    db.query(PowerRating).filter_by(team_id=20).update({"offense_rating": 15.0, "defense_rating": 12.0, "rating": 27})
    db.commit()

    after = _games(client)["games"][0]
    assert len(calls) == 2 * NUM_SIMULATIONS  # simulated again, not remembered
    assert after["model_home_win_prob"] != before["model_home_win_prob"]


def test_the_cache_keeps_home_and_neutral_games_apart():
    scores = load_sorted_scores()
    home, away = _rating(9, 6), _rating(1, 2)

    at_home = odds.cached_simulate_matchup(home, away, False, 7, scores)
    neutral = odds.cached_simulate_matchup(home, away, True, 7, scores)

    assert at_home == simulate_matchup(home, away, neutral_site=False, seed=7, sorted_scores=scores)
    assert neutral == simulate_matchup(home, away, neutral_site=True, seed=7, sorted_scores=scores)
    assert at_home != neutral


def test_simultaneous_requests_for_the_same_game_simulate_it_only_once(monkeypatch):
    calls = []

    def slow_simulation(home, away, neutral_site, seed, sorted_scores, num_simulations=NUM_SIMULATIONS):
        calls.append(seed)
        time.sleep(0.05)  # long enough for every other thread to arrive while this one is working
        return odds.SimulatedGame(0.5, 20.0, 20.0)

    monkeypatch.setattr(odds, "simulate_matchup", slow_simulation)

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(odds.cached_simulate_matchup(_rating(1, 1), _rating(2, 2), False, 7, None)))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == [7]
    assert len(results) == 8
    assert all(result == results[0] for result in results)


def test_the_cache_is_bounded_and_drops_the_least_recently_used_game(monkeypatch):
    calls = []

    def quick_simulation(home, away, neutral_site, seed, sorted_scores, num_simulations=NUM_SIMULATIONS):
        calls.append(seed)
        return odds.SimulatedGame(0.5, 20.0, 20.0)

    monkeypatch.setattr(odds, "simulate_matchup", quick_simulation)
    monkeypatch.setattr(odds, "SIMULATION_CACHE_MAX_ENTRIES", 3)

    def play(seed):
        return odds.cached_simulate_matchup(_rating(1, 1), _rating(2, 2), False, seed, None)

    play(1), play(2), play(3)
    play(1)  # a hit: game 1 is now the most recently used, so game 2 is the oldest
    play(4)  # over the limit: game 2 goes
    assert len(odds._simulation_cache) == 3
    assert calls == [1, 2, 3, 4]

    play(1), play(3), play(4)  # all still cached
    assert calls == [1, 2, 3, 4]
    play(2)  # was evicted, so it is simulated again
    assert calls == [1, 2, 3, 4, 2]


# ---- database work per request ---------------------------------------------------

def _select_statements(db, request):
    """Run `request()` and return the SQL statements it sent to the database."""
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        request()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return statements


def _add_extra_games(db, n_games):
    """`n_games` more week-8 games, each between two brand new teams that have ratings."""
    for i in range(n_games):
        home_id, away_id = 100 + 2 * i, 101 + 2 * i
        db.add_all([
            Team(id=home_id, cfbd_id=1000 + home_id, school=f"Home {i}", classification="fbs"),
            Team(id=away_id, cfbd_id=1000 + away_id, school=f"Away {i}", classification="fbs"),
        ])
        db.flush()
        db.add_all([
            PowerRating(team_id=home_id, season=2026, week=6, rating=4, offense_rating=2.0, defense_rating=2.0),
            PowerRating(team_id=away_id, season=2026, week=6, rating=-2, offense_rating=-1.0, defense_rating=-1.0),
            Game(cfbd_id=5000 + i, season=2026, week=8, season_type="regular", completed=False,
                 start_date=datetime(2026, 10, 24, 19, 0), home_team_id=home_id, away_team_id=away_id),
        ])
    db.commit()


def test_the_number_of_database_queries_does_not_grow_with_the_number_of_games(client, seeded, db):
    one_game = _select_statements(db, lambda: _games(client))

    _add_extra_games(db, 30)
    assert len(_games(client)["games"]) == 31
    many_games = _select_statements(db, lambda: _games(client))

    assert len(many_games) == len(one_game)
    assert len(many_games) <= 6


# ---- which market line is shown --------------------------------------------------

def _game_id(db):
    return db.query(Game).filter_by(cfbd_id=3).one().id


def test_the_consensus_line_is_the_one_shown_when_there_are_several(client, seeded, db):
    game_id = _game_id(db)
    db.add_all([
        Line(game_id=game_id, provider="Bovada", spread=-4.0, home_moneyline=-200, away_moneyline=170),
        Line(game_id=game_id, provider="consensus", spread=-5.5, home_moneyline=-250, away_moneyline=210),
        Line(game_id=game_id, provider="DraftKings", spread=-6.0, home_moneyline=-300, away_moneyline=250),
    ])
    db.commit()

    game = _games(client)["games"][0]
    assert (game["market_spread"], game["market_home_moneyline"]) == (-5.5, -250)


def test_without_a_consensus_line_the_first_provider_by_name_is_shown(client, seeded, db):
    game_id = _game_id(db)
    # Stored in the opposite order to their names, so a pick by insertion order would differ.
    db.add_all([
        Line(game_id=game_id, provider="DraftKings", spread=-6.0, home_moneyline=-300, away_moneyline=250),
        Line(game_id=game_id, provider="Bovada", spread=-4.0, home_moneyline=-200, away_moneyline=170),
    ])
    db.commit()

    game = _games(client)["games"][0]
    assert (game["market_spread"], game["market_home_moneyline"]) == (-4.0, -200)


def test_each_game_gets_its_own_line_when_a_week_has_several_games(client, seeded, db):
    _add_extra_games(db, 2)
    lines = {game.cfbd_id: game.id for game in db.query(Game).all()}
    db.add_all([
        Line(game_id=lines[3], provider="consensus", spread=-7.0),
        Line(game_id=lines[5000], provider="consensus", spread=-1.5),
    ])  # the third game (cfbd 5001) has no line at all
    db.commit()

    by_home = {game["home_team"]: game for game in _games(client)["games"]}
    assert by_home["Alabama"]["market_spread"] == -7.0
    assert by_home["Home 0"]["market_spread"] == -1.5
    assert by_home["Home 1"]["market_spread"] is None


# ---- rate limit and cache headers --------------------------------------------------

def test_a_client_over_the_limit_gets_429_with_retry_after_and_the_other_endpoints_still_work(client, seeded, monkeypatch):
    monkeypatch.setattr(odds, "_odds_limiter", RateLimiter(max_requests=3, window_seconds=60))

    assert [client.get("/api/odds/weekly").status_code for _ in range(3)] == [200, 200, 200]

    blocked = client.get("/api/odds/weekly")
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    assert "detail" in blocked.json()

    assert client.get("/health").status_code == 200
    assert client.get("/api/rankings").status_code == 200


def test_a_limit_of_zero_turns_the_rate_limit_off(client, seeded, monkeypatch):
    monkeypatch.setattr(odds, "_odds_limiter", RateLimiter(max_requests=0))
    assert all(client.get("/api/odds/weekly").status_code == 200 for _ in range(10))


def test_real_odds_can_be_cached_by_browsers_and_cdns(client, seeded):
    response = client.get("/api/odds/weekly")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == odds.ODDS_CACHE_CONTROL
    assert "max-age=300" in response.headers["Cache-Control"]


def test_the_placeholder_rows_for_a_week_with_no_games_are_never_cached(client, seeded):
    response = client.get("/api/odds/weekly", params={"season": 2026, "week": 99})
    assert response.status_code == 200
    assert response.json()["games"][0]["game_id"] == 401520123  # the placeholder rows
    assert response.headers["Cache-Control"] == "no-store"


def test_the_placeholder_rows_for_an_empty_database_are_never_cached(client):
    response = client.get("/api/odds/weekly")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
