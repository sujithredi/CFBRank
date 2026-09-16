"""
Power-rating model: margin-of-victory regression (SRS/Massey-style).

Every game contributes two rows -- one from each team's point of view --
and we fit

    margin ~ team_indicator - opponent_indicator + Location

with ordinary least squares and no intercept. Each team's fitted
"team_<name>" coefficient is its power rating: the number of points
it would be expected to beat an average team by on a neutral field.
"Location" gets its own coefficient too, so the model estimates a
home-field-advantage adjustment instead of baking it into every team's
number.

This is the same design as the standalone lin_rank.py prototype, cleaned
up into a function that takes a DataFrame (from the CFBD-backed games
table, a CSV, or a unit test) instead of a hardcoded local file path.

Input contract
--------------
`games` needs one row per game with these columns:
    team            -- name of the first team
    opponent        -- name of the second team
    team_score      -- team's points
    opponent_score  -- opponent's points
    margin          -- team_score - opponent_score
    Location        -- 1 if `team` was at home, -1 if `team` was away,
                        0 if neutral site

Only ONE row per game is expected here (not already mirrored) -- e.g. for
a CFBD game, put the home team in `team` and use Location=1 (or 0 for a
neutral site). `compute_power_ratings` generates the opponent's-eye-view
row itself.

Known limitation
-----------------
Like any schedule-strength regression (SRS, Massey, Colley, etc.), this
needs the games graph to be reasonably well-connected -- if two groups of
teams haven't played anyone in common yet (common early in a season, or
in a toy/filtered dataset), the least-squares solution can't tell the
groups' overall strength apart and the resulting ratings for one group
can be arbitrarily shifted relative to the other. Sanity-check early
-season output against a human poll before trusting it, and consider
requiring a minimum number of weeks/games before publishing rankings.
"""

from __future__ import annotations

import pandas as pd
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
