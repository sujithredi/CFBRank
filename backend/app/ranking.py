"""
Power-rating model: margin-of-victory regression.

Every game contributes two rows -- one from each team's point of view --
and we fit

    margin ~ team_indicator - opponent_indicator + Location

with ordinary least squares and no intercept. Each team's fitted
"team_<name>" coefficient is its power rating: the number of points
it would be expected to beat an average team by on a neutral field.
"Location" gets its own coefficient too, so the model estimates a
home-field-advantage adjustment instead of baking it into every team's
number.

Input
--------------
    team            -- name of the first team
    opponent        -- name of the second team
    team_score      -- team's points
    opponent_score  -- opponent's points
    margin          -- team_score - opponent_score
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

REQUIRED_COLUMNS = ["team", "opponent", "team_score", "opponent_score", "margin", "Location"]


def _mirror_games(games: pd.DataFrame) -> pd.DataFrame:
    """Duplicate each game as the opponent's-perspective row (flipped sign)."""
    mirrored = games.copy()
    mirrored["margin"] = -mirrored["margin"]
    mirrored["Location"] = -mirrored["Location"]
    mirrored = mirrored.rename(
        columns={
            "team": "opponent",
            "opponent": "team",
            "team_score": "opponent_score",
            "opponent_score": "team_score",
        }
    )
    return pd.concat([games, mirrored], ignore_index=True)


def compute_power_ratings(games: pd.DataFrame) -> pd.DataFrame:
    """
    Fit the model and return a DataFrame with columns ["rank", "team", "rating"],
    sorted best-to-worst. Returns an empty (but correctly-shaped) DataFrame if
    there are no usable rows.
    """
    missing = set(REQUIRED_COLUMNS) - set(games.columns)
    if missing:
        raise ValueError(f"games is missing required column(s): {sorted(missing)}")

    games = games.dropna(subset=REQUIRED_COLUMNS).reset_index(drop=True)
    if games.empty:
        return pd.DataFrame(columns=["rank", "team", "rating"])

    doubled = _mirror_games(games)

    team_dummies = pd.get_dummies(doubled["team"], prefix="team")
    opponent_dummies = pd.get_dummies(doubled["opponent"], prefix="opponent")
    X = pd.concat([doubled[["Location"]], team_dummies, opponent_dummies], axis=1).astype(float)
    y = doubled["margin"].astype(float)

    model = LinearRegression(fit_intercept=False)
    model.fit(X, y)

    coefs = pd.Series(model.coef_, index=X.columns)
    team_ratings = coefs[coefs.index.str.startswith("team_")].copy()
    team_ratings.index = team_ratings.index.str.replace("team_", "", regex=False, n=1)

    ratings = (
        team_ratings.rename("rating")
        .reset_index()
        .rename(columns={"index": "team"})
        .sort_values("rating", ascending=False)
        .reset_index(drop=True)
    )
    ratings.insert(0, "rank", ratings.index + 1)
    return ratings


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