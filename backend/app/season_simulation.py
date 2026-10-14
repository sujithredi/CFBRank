"""
Monte Carlo simulation the regular season, plus conference
championship games.

Every game that has not been played yet is simulated with
app.simulation.simulate_game, the
whole remaining schedule is replayed N_SIMULATIONS times, and tracks:

    avg_wins         mean regular-season wins (games already played + simulated)
    avg_losses       mean regular-season losses
    bowl_pct         % of simulations where the team finishes bowl eligible
    undefeated_pct   % of simulations where the team finishes with 0 losses
    title_game_pct   % of simulations where the team plays in its conference
                     championship game
    conf_champ_pct   % of simulations where the team wins that game
    playoff_pct      % of simulations where the team is selected for the College
                     Football Playoff field (FBS teams only)
    cfp_bye_pct          % of simulations where it is a top-4 seed, with a first-round bye
    cfp_quarterfinal_pct % where it plays in the quarterfinals (a bye, or a first-round win)
    cfp_semifinal_pct    % where it plays in a semifinal
    cfp_final_pct        % where it plays in the national championship game
    cfp_champion_pct     % where it wins the national championship
                     (all five are FBS teams only; each is out of every simulation, so
                     a team that misses the field counts as a miss, not as missing data)

After each simulated regular season, the finalists of every conference title
game are picked from the simulated conference standings and the title game is played.

Ratings update as the simulated season goes. The games are played one week at a time, and after each week
ratings are re-fit with that week's simulated scores. The next week is then simulated with the updated ratings, so a team
that piles up wins in a given simulation is rated higher for what follows.

Playoff selection. After the conference title games, once every regular-season
game is played, the 12-team playoff field is chosen (app/playoff.py): the
champions of the ACC, Big Ten, SEC and Big 12, the best Group of 6 champion, Notre
Dame if it is a top-12 team, and the remaining spots at large. Teams other than the
conference champions are picked by the neural network in playoff_data.csv from each
team's strength of schedule (the average overall rating of its opponents, using the
ratings as they stand after the last simulated week) and its regular-season record.

Playoff games. The field is then seeded 1-12 by overall rating and the bracket is
played out (app/playoff_bracket.py): byes for the top four seeds, first-round games
on the higher seed's campus, neutral sites after that, no re-seeding. The ratings
used are the ones after the last regular-season week, and the playoff results are
not fed back into them. The bracket draws from its own random stream (derived from
`seed`), so it never changes any other column: a seeded run gives the same bowl,
title-game and playoff_pct numbers it would give without the bracket.

Inputs
    * Ratings -- the latest PowerRating snapshot (the one /api/rankings serves).
      Teams need an offense and a defense rating, so run
      `python -m scripts.compute_rankings` first if those are missing.
    * Schedule -- Game rows with completed = False for that season, regular season.
    * Current record -- counted from the completed Game rows (not from the
      snapshot's wins/losses columns, which can lag behind the games on file).
    * Conference standings -- completed conference games, plus the simulated ones.
    * Sun Belt divisions -- Team.division.

Assumptions
    * Home-field advantage is app.ranking.DEFAULT_HOME_FIELD_ADVANTAGE (a margin,
      in points) for the home team, and zero at neutral sites. A title game gets
      it for the first-place team when the conference plays it on campus (see
      conference_championships.py for which do).
    * Bowl eligible = at least BOWL_WINS_REQUIRED wins, FBS teams only, and at most
      MAX_FCS_WINS_COUNTED win over an FCS opponent counts toward that total.
      This is *eligibility*; it does not model which eligible teams actually
      get a bowl slot. bowl_pct is None for FCS teams.
    * Football has no ties (simulate_game sends a tied score to overtime), so
      wins + losses always equals games played.
    * Real conference-championship rows in the schedule (a conference game in
      CHAMPIONSHIP_WEEK) are ignored, because the simulation plays its own.
    * Week 1 of the simulation uses the stored ratings (what the app shows).
      A title game is played with the ratings from after the last regular
      week before it, and its score is not fed back into the ratings (only
      one game, Army-Navy, is played after it).
    * Home-field advantage in the simulated games stays at the fixed value
      above; the refit's own Location term only keeps it out of the ratings.
    * Strength of schedule counts every regular-season opponent, FCS teams
      included, played or simulated -- never a conference title game, which is
      also left out of wins and losses. It is built from `played_games` plus
      the schedule, so a caller that doesn't pass `played_games` gets a
      schedule strength based on the unplayed games only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session, aliased

from app.conference_championships import CHAMPIONSHIP_WEEK, CONFERENCE_RULES, ConferenceModel
from app.models import Conference, Game, PowerRating, SeasonProjection, Team
from app.playoff import FIELD_SIZE, RANKED_AUTO_BID_TEAMS, PlayoffModel, get_playoff_model, select_playoff_field
from app.playoff_bracket import FINAL, QUARTERFINAL, SEMIFINAL, seed_field, simulate_bracket
from app.ranking import DEFAULT_HOME_FIELD_ADVANTAGE
from app.simulation import load_sorted_scores, simulate_game
from app.weekly_ratings import RatingRefitter

N_SIMULATIONS = 10_000
BOWL_WINS_REQUIRED = 6
MAX_FCS_WINS_COUNTED = 1 #counts for bowl eliabilty

RESULT_COLUMNS = [
    "team_id",
    "team",
    "conference",
    "classification",
    "wins",
    "losses",
    "games_remaining",
    "avg_wins",
    "avg_losses",
    "bowl_pct",
    "undefeated_pct",
    "title_game_pct",
    "conf_champ_pct",
    "playoff_pct",
    "cfp_bye_pct",
    "cfp_quarterfinal_pct",
    "cfp_semifinal_pct",
    "cfp_final_pct",
    "cfp_champion_pct",
]


@dataclass(frozen=True)
class SimTeam:
    """A team's ratings and its record so far this season."""

    team_id: int
    school: str
    conference: str
    classification: str | None
    offense: float
    defense: float
    wins: int = 0
    losses: int = 0
    fbs_wins: int = 0  # wins so far over non-FCS opponents
    fcs_wins: int = 0  # wins so far over FCS opponents
    division: str | None = None  # Sun Belt only
    rating: float = 0.0  # overall power rating (breaks ties for the American and Mountain West)

    @property
    def is_fbs(self) -> bool:
        return self.classification == "fbs"


@dataclass(frozen=True)
class SimGame:
    """
    One unplayed game. The home team is `home_id`; neutral sites get no home edge.
    `conference_game` games before CHAMPIONSHIP_WEEK count toward the conference
    standings that decide the title-game finalists.
    """

    home_id: int
    away_id: int
    neutral_site: bool = False
    conference_game: bool = False
    week: int = 0


class PlayedGame(NamedTuple):
    """A conference game already played this season (for the conference standings)."""

    winner_id: int
    loser_id: int


class PlayedScore(NamedTuple):
    """
    A game already played this season, with its score: what the rating model is fit on.
    `title_game` marks a real conference championship game: it is fit like any other
    game, but is not a regular-season opponent for strength of schedule.
    """

    home_id: int
    away_id: int
    home_points: float
    away_points: float
    neutral_site: bool = False
    title_game: bool = False


class SeasonInputs(NamedTuple):
    season: int
    week: int  # the ratings snapshot's week
    teams: list[SimTeam]
    games: list[SimGame]  # unplayed regular-season games
    played_conference_games: list[PlayedGame]
    played_games: list[PlayedScore]  # every completed regular-season

def load_season_inputs(db: Session, season: int | None = None) -> SeasonInputs:
    """
    Read what the simulation needs: (season, ratings_week, teams, remaining_games,
    played_conference_games, played_games).

    `season` defaults to the latest one with power ratings. Raises ValueError if
    there are no ratings, or if a team with games left has no offense/defense rating.
    """
    latest = db.query(PowerRating.season, PowerRating.week)
    if season is not None:
        latest = latest.filter(PowerRating.season == season)
    latest = latest.order_by(PowerRating.season.desc(), PowerRating.week.desc()).first()
    if latest is None:
        raise ValueError("No power ratings have been computed yet -- run scripts.compute_rankings first")
    season, week = latest

    rating_rows = (
        db.query(Team.id, Team.school, Team.classification, Conference.name,
                 PowerRating.offense_rating, PowerRating.defense_rating,
                 Team.division, PowerRating.rating)
        .join(PowerRating, PowerRating.team_id == Team.id)
        .outerjoin(Conference, Team.conference_id == Conference.id)
        .filter(PowerRating.season == season, PowerRating.week == week)
        .all()
    )
    info = {row[0]: row for row in rating_rows}

    HomeTeam, AwayTeam = aliased(Team), aliased(Team)
    played = (
        db.query(Game.home_team_id, Game.away_team_id, Game.home_points, Game.away_points,
                 HomeTeam.classification, AwayTeam.classification, Game.conference_game, Game.week,
                 Game.neutral_site)
        .join(HomeTeam, Game.home_team_id == HomeTeam.id)
        .join(AwayTeam, Game.away_team_id == AwayTeam.id)
        .filter(
            Game.season == season,
            Game.season_type == "regular",
            Game.completed.is_(True),
            Game.home_points.isnot(None),
            Game.away_points.isnot(None),
        )
        .all()
    )
    record = {team_id: {"w": 0, "l": 0, "fbs_w": 0, "fcs_w": 0} for team_id in info}
    played_conference_games: list[PlayedGame] = []
    played_games: list[PlayedScore] = []
    for (home_id, away_id, home_pts, away_pts, home_class, away_class,
         conference_game, game_week, neutral_site) in played:
        is_title_game = bool(conference_game and game_week == CHAMPIONSHIP_WEEK)
        # The rating model is fit on every completed game
        if home_id in info and away_id in info:
            played_games.append(
                PlayedScore(home_id, away_id, home_pts, away_pts, bool(neutral_site), title_game=is_title_game)
            )
        if is_title_game:
            continue  # a real title game: the simulation plays its own, and it isn't regular-season record
        if home_pts == away_pts:
            continue  # a tie counts as neither
        winner, loser, loser_class = (
            (home_id, away_id, away_class) if home_pts > away_pts else (away_id, home_id, home_class)
        )
        if winner in record:
            record[winner]["w"] += 1
            record[winner]["fcs_w" if loser_class == "fcs" else "fbs_w"] += 1
        if loser in record:
            record[loser]["l"] += 1
        if (
            conference_game
            and game_week < CHAMPIONSHIP_WEEK
            and winner in info and loser in info
            and info[winner][3] == info[loser][3]
        ):
            played_conference_games.append(PlayedGame(winner, loser))

    remaining = (
        db.query(Game.home_team_id, Game.away_team_id, Game.neutral_site, Game.conference_game, Game.week)
        .filter(Game.season == season, Game.season_type == "regular", Game.completed.is_(False))
        .order_by(Game.week, Game.id)
        .all()
    )
    games = [
        SimGame(home, away, bool(neutral), bool(conference_game), game_week)
        for home, away, neutral, conference_game, game_week in remaining
        if not (conference_game and game_week == CHAMPIONSHIP_WEEK)
    ]

    unrated = sorted(
        {
            info[t][1] if t in info else f"team id {t}"
            for g in games for t in (g.home_id, g.away_id)
            if t not in info or info[t][4] is None or info[t][5] is None
        }
    )
    if unrated:
        raise ValueError(
            f"{len(unrated)} team(s) with games left have no offense/defense rating "
            f"(re-run scripts.compute_rankings): {unrated[:10]}"
        )

    teams = [
        SimTeam(
            team_id=team_id,
            school=school,
            conference=conference or "Independent",
            classification=classification,
            offense=offense if offense is not None else 0.0,
            defense=defense if defense is not None else 0.0,
            wins=record[team_id]["w"],
            losses=record[team_id]["l"],
            fbs_wins=record[team_id]["fbs_w"],
            fcs_wins=record[team_id]["fcs_w"],
            division=division,
            rating=rating if rating is not None else 0.0,
        )
        for team_id, school, classification, conference, offense, defense, division, rating in rating_rows
    ]
    return SeasonInputs(season, week, teams, games, played_conference_games, played_games)


#conference championship setup

def _build_conference_models(
    teams: list[SimTeam],
    games: list[SimGame],
    played: list[PlayedGame],
    index: dict[int, int],
) -> tuple[list[ConferenceModel], list[int]]:
    members_by_conference: dict[str, list[int]] = {}
    for i, team in enumerate(teams):
        if team.is_fbs and team.conference in CONFERENCE_RULES:
            members_by_conference.setdefault(team.conference, []).append(i)

    conference_of: dict[int, str] = {i: name for name, members in members_by_conference.items() for i in members}

    def same_conference(a: int, b: int) -> str | None:
        name = conference_of.get(a)
        return name if name is not None and name == conference_of.get(b) else None

    schedule: dict[str, list[tuple[int, int]]] = {name: [] for name in members_by_conference}
    results: dict[str, list[tuple[int, int]]] = {name: [] for name in members_by_conference}

    game_conference: list[str | None] = []
    for game in games:
        a, b = index[game.home_id], index[game.away_id]
        name = same_conference(a, b) if game.conference_game and game.week < CHAMPIONSHIP_WEEK else None
        game_conference.append(name)
        if name:
            schedule[name].append((a, b))

    for winner_id, loser_id in played:
        if winner_id in index and loser_id in index:
            winner, loser = index[winner_id], index[loser_id]
            name = same_conference(winner, loser)
            if name:
                schedule[name].append((winner, loser))
                results[name].append((winner, loser))

    models = []
    position = {}
    for name, members in members_by_conference.items():
        if len(members) < 2:
            continue
        position[name] = len(models)
        models.append(
            ConferenceModel(
                name=name,
                rules=CONFERENCE_RULES[name],
                members=members,
                schedule=schedule[name],
                played=results[name],
                division_of={i: teams[i].division for i in members if teams[i].division},
                rating={i: teams[i].rating for i in members},
            )
        )
    return models, [position.get(name, -1) if name else -1 for name in game_conference]

# main simulation
def simulate_season(
    teams: list[SimTeam],
    games: list[SimGame],
    n_simulations: int = N_SIMULATIONS,
    seed: int | None = None,
    home_field_advantage: float = DEFAULT_HOME_FIELD_ADVANTAGE,
    played_conference_games: list[PlayedGame] | tuple = (),
    played_games: list[PlayedScore] | tuple | None = None,
    update_ratings: bool = True,
    playoff_model: PlayoffModel | None = None,
) -> pd.DataFrame:
    if n_simulations < 1:
        raise ValueError("n_simulations must be at least 1")

    index = {team.team_id: i for i, team in enumerate(teams)}
    for game in games:
        for team_id in (game.home_id, game.away_id):
            if team_id not in index:
                raise ValueError(f"Game references team id {team_id}, which isn't in `teams`")

    n_teams = len(teams)
    offense = [t.offense for t in teams]
    defense = [t.defense for t in teams]
    is_fbs = [t.is_fbs for t in teams]
    games_left = [0] * n_teams

    # Resolve the schedule to list indexes once, so the hot loop is only list lookups.
    # location is the rating model's Location term: 1 for a home game, 0 for neutral site.
    schedule = []
    for game in games:
        home, away = index[game.home_id], index[game.away_id]
        schedule.append(
            (home, away, 0.0 if game.neutral_site else home_field_advantage, 0 if game.neutral_site else 1)
        )
        games_left[home] += 1
        games_left[away] += 1

    # The schedule in weeks, earliest first (games keep their order within a week).
    weeks = sorted({game.week for game in games})
    games_in_week = {week: [] for week in weeks}
    for k, game in enumerate(games):
        games_in_week[game.week].append(k)
    stages = [games_in_week[week] for week in weeks]
    # Title games are played after the last week before CHAMPIONSHIP_WEEK.
    first_late_stage = next((i for i, week in enumerate(weeks) if week >= CHAMPIONSHIP_WEEK), len(weeks))

    refitter = None
    if update_ratings and played_games:
        scored = []
        for played in played_games:
            if played.home_id not in index or played.away_id not in index:
                raise ValueError("A played game references a team id that isn't in `teams`")
            scored.append(
                (index[played.home_id], index[played.away_id], played.home_points, played.away_points,
                 0 if played.neutral_site else 1)
            )
        refitter = RatingRefitter(
            n_teams,
            scored,
            [[(schedule[k][0], schedule[k][1], schedule[k][3]) for k in ks] for ks in stages],
            offense,
            defense,
        )

    models, conference_of_game = _build_conference_models(teams, games, list(played_conference_games), index)
    has_title_game = [False] * n_teams
    base_conf_wins = [0] * n_teams
    base_conf_losses = [0] * n_teams
    for model in models:
        for team in model.members:
            has_title_game[team] = True
            base_conf_wins[team] = model.base_wins[team]
            base_conf_losses[team] = model.base_losses[team]

    sorted_scores = load_sorted_scores()
    rng = random.Random(seed)

    base_wins = [t.wins for t in teams]
    base_losses = [t.losses for t in teams]
    base_fbs_wins = [t.fbs_wins for t in teams]
    base_fcs_wins = [t.fcs_wins for t in teams]
    away_is_fcs = [teams[away].classification == "fcs" for _, away, _, _ in schedule]
    home_is_fcs = [teams[home].classification == "fcs" for home, _, _, _ in schedule]

    #playoff field: who is eligible, and each team's strength-of-schedule row
    playoff_model = playoff_model or get_playoff_model()
    fbs_teams = [i for i in range(n_teams) if is_fbs[i]]
    ranked_auto_bid = [i for i in fbs_teams if teams[i].school in RANKED_AUTO_BID_TEAMS]
    # The bracket gets its own random stream, so playing it never shifts the draws behind
    # every other column. (A string seed is hashed the same way on every run.)
    playoff_rng = random.Random(None if seed is None else f"cfp-bracket-{seed}")
    opponents: list[list[int]] = [[] for _ in range(n_teams)]
    for home, away, _, _ in schedule:
        opponents[home].append(away)
        opponents[away].append(home)
    for played in played_games or ():
        if played.home_id not in index or played.away_id not in index:
            raise ValueError("A played game references a team id that isn't in `teams`")
        if not played.title_game:
            home, away = index[played.home_id], index[played.away_id]
            opponents[home].append(away)
            opponents[away].append(home)
    # schedule_strength @ overall_ratings = each FBS team's average opponent rating
    schedule_strength = np.zeros((len(fbs_teams), n_teams))
    for row_number, team_index in enumerate(fbs_teams):
        for opponent in opponents[team_index]:
            schedule_strength[row_number, opponent] += 1.0 / len(opponents[team_index])
    fbs_rows = np.array(fbs_teams, dtype=int)
    base_wins_array = np.array(base_wins)
    base_losses_array = np.array(base_losses)
    games_left_array = np.array(games_left)

    total_wins = [0] * n_teams
    bowl_count = [0] * n_teams
    undefeated_count = [0] * n_teams
    title_game_count = [0] * n_teams
    champion_count = [0] * n_teams
    playoff_count = [0] * n_teams
    cfp_bye_count = [0] * n_teams
    cfp_quarterfinal_count = [0] * n_teams
    cfp_semifinal_count = [0] * n_teams
    cfp_final_count = [0] * n_teams
    cfp_champion_count = [0] * n_teams

    def play_title_games(off, dfn, conf_wins, conf_losses, conf_results):
        # Conference championship games. These touch only the title-game columns
        champions = {}
        for position, model in enumerate(models):
            first, second = model.pick_finalists(conf_wins, conf_losses, conf_results[position], rng)
            title_game_count[first] += 1
            title_game_count[second] += 1
            title = simulate_game(
                off[first], dfn[first], off[second], dfn[second],
                sorted_scores=sorted_scores, rng=rng,
                home_field_advantage=0.0 if model.rules.neutral_site else home_field_advantage,
            )
            champion = first if title["score_a"] > title["score_b"] else second
            champion_count[champion] += 1
            champions[model.name] = champion
        return champions

    def select_playoff_teams(off, dfn, sim_wins, champions):
        if not fbs_teams:
            return
        overall = np.asarray(off) + np.asarray(dfn)
        wins = base_wins_array[fbs_rows] + np.asarray(sim_wins)[fbs_rows]
        losses = base_losses_array[fbs_rows] + games_left_array[fbs_rows] - np.asarray(sim_wins)[fbs_rows]
        probability = [0.0] * n_teams
        for team_index, value in zip(
            fbs_teams, playoff_model.probability(schedule_strength @ overall, wins, losses).tolist()
        ):
            probability[team_index] = value
        field = select_playoff_field(
            probability, champions, fbs_teams, FIELD_SIZE, ranked_auto_bid=ranked_auto_bid
        )
        for team_index in field.teams:
            playoff_count[team_index] += 1

        # Seed the field by overall rating, then play the bracket with the same ratings.
        playoff = simulate_bracket(
            seed_field(field.teams, overall), off, dfn, playoff_rng,
            sorted_scores=sorted_scores, home_field_advantage=home_field_advantage,
        )
        for team_index in playoff.bye_teams:
            cfp_bye_count[team_index] += 1
        for team_index, furthest_round in playoff.furthest_round.items():
            if furthest_round >= QUARTERFINAL:
                cfp_quarterfinal_count[team_index] += 1
            if furthest_round >= SEMIFINAL:
                cfp_semifinal_count[team_index] += 1
            if furthest_round >= FINAL:
                cfp_final_count[team_index] += 1
        if playoff.champion is not None:
            cfp_champion_count[playoff.champion] += 1

    for _ in range(n_simulations):
        sim_wins = [0] * n_teams
        sim_fbs_wins = base_fbs_wins[:]
        sim_fcs_wins = base_fcs_wins[:]
        conf_wins = base_conf_wins[:]
        conf_losses = base_conf_losses[:]
        conf_results = [model.base_results.copy() for model in models]

        off, dfn = offense, defense  # this week's ratings; replaced by a re-fit after each week
        b = refitter.start_vector() if refitter else None  # running X'y for the re-fit
        titles_played = not models
        champions = {}

        for stage, game_ids in enumerate(stages):
            if not titles_played and stage >= first_late_stage:
                champions = play_title_games(off, dfn, conf_wins, conf_losses, conf_results)
                titles_played = True

            for k in game_ids:
                home, away, hfa, location = schedule[k]
                game = simulate_game(
                    off[home], dfn[home], off[away], dfn[away],
                    sorted_scores=sorted_scores, rng=rng, home_field_advantage=hfa,
                )
                # simulate_game never returns a tie, so exactly one team wins.
                if game["score_a"] > game["score_b"]:
                    winner, loser, loser_is_fcs = home, away, away_is_fcs[k]
                else:
                    winner, loser, loser_is_fcs = away, home, home_is_fcs[k]

                sim_wins[winner] += 1
                if loser_is_fcs:
                    sim_fcs_wins[winner] += 1
                else:
                    sim_fbs_wins[winner] += 1

                model_position = conference_of_game[k]
                if model_position >= 0:
                    conf_wins[winner] += 1
                    conf_losses[loser] += 1
                    results = conf_results[model_position]
                    results[(winner, loser)] = results.get((winner, loser), 0) + 1

                if b is not None:
                    refitter.add_game(b, home, away, location, game["score_a"], game["score_b"])

            if refitter is not None:
                off, dfn = refitter.ratings(stage, b)

        if not titles_played:
            champions = play_title_games(off, dfn, conf_wins, conf_losses, conf_results)

        select_playoff_teams(off, dfn, sim_wins, champions)

        for i in range(n_teams):
            total_wins[i] += sim_wins[i]
            if base_losses[i] + (games_left[i] - sim_wins[i]) == 0:
                undefeated_count[i] += 1
            if is_fbs[i] and sim_fbs_wins[i] + min(sim_fcs_wins[i], MAX_FCS_WINS_COUNTED) >= BOWL_WINS_REQUIRED:
                bowl_count[i] += 1

    rows = []
    for i, team in enumerate(teams):
        avg_sim_wins = total_wins[i] / n_simulations
        rows.append(
            {
                "team_id": team.team_id,
                "team": team.school,
                "conference": team.conference,
                "classification": team.classification,
                "wins": base_wins[i],
                "losses": base_losses[i],
                "games_remaining": games_left[i],
                "avg_wins": base_wins[i] + avg_sim_wins,
                "avg_losses": base_losses[i] + (games_left[i] - avg_sim_wins),
                "bowl_pct": 100.0 * bowl_count[i] / n_simulations if is_fbs[i] else None,
                "undefeated_pct": 100.0 * undefeated_count[i] / n_simulations,
                "title_game_pct": 100.0 * title_game_count[i] / n_simulations if has_title_game[i] else None,
                "conf_champ_pct": 100.0 * champion_count[i] / n_simulations if has_title_game[i] else None,
                "playoff_pct": 100.0 * playoff_count[i] / n_simulations if is_fbs[i] else None,
                "cfp_bye_pct": 100.0 * cfp_bye_count[i] / n_simulations if is_fbs[i] else None,
                "cfp_quarterfinal_pct": 100.0 * cfp_quarterfinal_count[i] / n_simulations if is_fbs[i] else None,
                "cfp_semifinal_pct": 100.0 * cfp_semifinal_count[i] / n_simulations if is_fbs[i] else None,
                "cfp_final_pct": 100.0 * cfp_final_count[i] / n_simulations if is_fbs[i] else None,
                "cfp_champion_pct": 100.0 * cfp_champion_count[i] / n_simulations if is_fbs[i] else None,
            }
        )
    result = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    return result.sort_values(["avg_wins", "team"], ascending=[False, True]).reset_index(drop=True)


def run_season_simulation(
    db: Session,
    season: int | None = None,
    n_simulations: int = N_SIMULATIONS,
    seed: int | None = None,
    update_ratings: bool = True,
) -> tuple[int, int, pd.DataFrame]:
    """Load the latest ratings and schedule from the DB and simulate. Returns (season, week, results)."""
    inputs = load_season_inputs(db, season)
    results = simulate_season(
        inputs.teams,
        inputs.games,
        n_simulations=n_simulations,
        seed=seed,
        played_conference_games=inputs.played_conference_games,
        played_games=inputs.played_games,
        update_ratings=update_ratings,
    )
    return inputs.season, inputs.week, results


def _none_if_nan(value) -> float | None:
    return None if pd.isna(value) else float(value)


def save_season_projections(db: Session, season: int, week: int, results: pd.DataFrame, n_simulations: int) -> int:
    """
    Write `results` (from simulate_season) to the season_projections table for the
    ratings snapshot (season, week), replacing any earlier run for that snapshot.
    This is what GET /api/rankings reads. Returns the number of rows written.
    The caller commits.
    """
    existing = {
        projection.team_id: projection
        for projection in db.query(SeasonProjection).filter_by(season=season, week=week)
    }
    now = datetime.utcnow()
    for row in results.itertuples(index=False):
        projection = existing.get(row.team_id)
        if projection is None:
            projection = SeasonProjection(team_id=int(row.team_id), season=season, week=week)
            db.add(projection)
        projection.n_simulations = n_simulations
        projection.avg_wins = float(row.avg_wins)
        projection.avg_losses = float(row.avg_losses)
        projection.bowl_pct = _none_if_nan(row.bowl_pct)
        projection.undefeated_pct = float(row.undefeated_pct)
        projection.title_game_pct = _none_if_nan(row.title_game_pct)
        projection.conf_champ_pct = _none_if_nan(row.conf_champ_pct)
        projection.playoff_pct = _none_if_nan(row.playoff_pct)
        projection.cfp_bye_pct = _none_if_nan(row.cfp_bye_pct)
        projection.cfp_quarterfinal_pct = _none_if_nan(row.cfp_quarterfinal_pct)
        projection.cfp_semifinal_pct = _none_if_nan(row.cfp_semifinal_pct)
        projection.cfp_final_pct = _none_if_nan(row.cfp_final_pct)
        projection.cfp_champion_pct = _none_if_nan(row.cfp_champion_pct)
        projection.computed_at = now
    return len(results)
