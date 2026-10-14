"""
Power-rating model: separate offense and defense ratings, plus an overall.

Every game contributes two rows -- one from each team's point of view --
and we regress the points a team scored on who was on offense, who was on
defense, and where the game was played:

    team_score ~ Location + offense[team] + defense_coef[opponent]

fit with ordinary least squares and no intercept.

    offense  -- points per game a team scores above an average offense,
                against an average defense, on a neutral field.
    defense  -- points per game a team *prevents* relative to an average
                defense (positive = good defense). This is the negated
                opponent coefficient, so a defense that holds opponents
                below the norm comes out positive.
    rating   -- overall = offense + defense. The difference between two
                teams' overall ratings is the model's expected margin of
                victory between them, so this stays on the same
                "points better than an average team" scale the app has
                always used (`expected_margin`, the odds endpoint, etc.).

The offense/defense split has one free constant: adding c to every offense
coefficient and subtracting c from every defense coefficient gives the
exact same predictions. We pin it down by centering offense and defense on
zero, so 0 means "league average" for each. Centering does not change the
overall rating or the ranking.

"Location" gets its own coefficient, so the model estimates a home-field
adjustment instead of baking it into every team's number. Note that it is
applied to the points *scored*, so the home-field edge in a game's margin
is twice this coefficient.

Input
--------------
    team            -- name of the first team
    opponent        -- name of the second team
    team_score      -- team's points
    opponent_score  -- opponent's points
    Location        -- 1 if `team` was at home, -1 if `team` was away, 0 if neutral site

Only ONE row per game is expected here (not already mirrored) -- e.g. for
a CFBD game, put the home team in `team` and use Location=1 (or 0 for a
neutral site). `compute_power_ratings` generates the opponent's-eye-view
row itself.
"""

from __future__ import annotations

import pandas as pd
import math
from sklearn.linear_model import LinearRegression

REQUIRED_COLUMNS = ["team", "opponent", "team_score", "opponent_score", "Location"]
RATING_COLUMNS = ["rank", "team", "offense", "defense", "rating"]


def _mirror_games(games: pd.DataFrame) -> pd.DataFrame:
    """Duplicate each game as the opponent's-perspective row (teams, scores and location flipped)."""
    games_a = games[["Location", "team", "opponent", "team_score", "opponent_score"]].copy()
    games_b = games_a.rename(
        columns={
            "team": "opponent",
            "opponent": "team",
            "team_score": "opponent_score",
            "opponent_score": "team_score",
        }
    )
    games_b["Location"] *= -1
    return pd.concat([games_a, games_b], ignore_index=True)


def compute_power_ratings(games: pd.DataFrame) -> pd.DataFrame:
    """
    Fit the model and return a DataFrame with columns
    ["rank", "team", "offense", "defense", "rating"], sorted best-to-worst by
    `rating` (the overall rating, offense + defense). Positive offense and
    defense are both good. Returns an empty (but correctly-shaped) DataFrame
    if there are no usable rows.
    """
    missing = set(REQUIRED_COLUMNS) - set(games.columns)
    if missing:
        raise ValueError(f"games is missing required column(s): {sorted(missing)}")

    games = games.dropna(subset=REQUIRED_COLUMNS).reset_index(drop=True)
    if games.empty:
        return pd.DataFrame(columns=RATING_COLUMNS)

    doubled = _mirror_games(games)

    # Features: location + offense dummies (team) + defense dummies (opponent)
    off_dummies = pd.get_dummies(doubled["team"], prefix="off", dtype=float)
    def_dummies = pd.get_dummies(doubled["opponent"], prefix="def", dtype=float)
    X = pd.concat([doubled[["Location"]].astype(float), off_dummies, def_dummies], axis=1)
    y = doubled["team_score"].astype(float)

    model = LinearRegression(fit_intercept=False)
    model.fit(X, y)

    coefs = pd.Series(model.coef_, index=X.columns)

    offense = coefs[coefs.index.str.startswith("off_")]
    offense.index = offense.index.str[len("off_"):]

    defense = coefs[coefs.index.str.startswith("def_")]
    defense.index = defense.index.str[len("def_"):]

    ratings = pd.DataFrame(
        {
            "offense": offense,
            "defense": -defense,  # flipped so positive = good defense
        }
    )
    # Pin the free offense/defense constant: 0 = league average for each.
    ratings["offense"] -= ratings["offense"].mean()
    ratings["defense"] -= ratings["defense"].mean()
    ratings["rating"] = ratings["offense"] + ratings["defense"]

    ratings = (
        ratings.sort_values("rating", ascending=False)
        .rename_axis("team")
        .reset_index()
    )
    ratings.insert(0, "rank", ratings.index + 1)
    return ratings[RATING_COLUMNS]


def record_from_games(games: pd.DataFrame) -> pd.DataFrame:
    """
    Wins/losses per team from the same one-row-per-game shape used above
    (ties count as neither). Returned as columns ["team", "wins", "losses"].
    """
    if games.empty:
        return pd.DataFrame(columns=["team", "wins", "losses"])

    team_win = (games["team_score"] > games["opponent_score"]).astype(int)
    team_loss = (games["team_score"] < games["opponent_score"]).astype(int)
    opp_win = team_loss
    opp_loss = team_win

    team_records = pd.DataFrame({"team": games["team"], "win": team_win, "loss": team_loss})
    opp_records = pd.DataFrame({"team": games["opponent"], "win": opp_win, "loss": opp_loss})
    all_records = pd.concat([team_records, opp_records], ignore_index=True)

    summary = all_records.groupby("team", as_index=False).sum()
    summary = summary.rename(columns={"win": "wins", "loss": "losses"})
    return summary

DEFAULT_HOME_FIELD_ADVANTAGE = 2.5
DEFAULT_MARGIN_SCALE = 9.0

def expected_margin(
    home_rating: float,
    away_rating: float,
    home_field_advantage: float = DEFAULT_HOME_FIELD_ADVANTAGE,
) -> float:
    """
    Expected home-team margin of victory, in points: positive means the
    home team is favored, negative means the away team is. `home_rating`/
    `away_rating` are each team's fitted coefficient from
    `compute_power_ratings` -- expected points better than an average team
    on a neutral field. Pass `home_field_advantage=0` for a neutral site.
    """
    return (home_rating - away_rating) + home_field_advantage

def win_probability_from_margin(margin: float) -> float:
    """
    Logistic squash of an expected point margin into a win probability in
    (0, 1). See `predict_win_probability` for how the default `scale` was
    chosen and what it implies at a few sample margins.
    """
    return 1.0 / (1.0 + math.exp(-((margin * 0.1533) + 0.0533)))

def predict_win_probability(
    home_rating: float,
    away_rating: float,
    home_field_advantage: float = DEFAULT_HOME_FIELD_ADVANTAGE,
    scale: float = DEFAULT_MARGIN_SCALE,
) -> float:
    """
    Turn a matchup between two power ratings into a home-team win
    probability (US-03: "the model's win probability" for the weekly odds
    view). Equivalent to `win_probability_from_margin(expected_margin(...))`
    """
    margin = expected_margin(home_rating, away_rating, home_field_advantage)
    return win_probability_from_margin(margin)