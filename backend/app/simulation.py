"""
Single-game simulation for the team matchup page.

This is the script from the feature request, turned into functions:

    1. Expected points for a team = league average + its offense rating
       - the opponent's defense rating. Both ratings come from the latest
       PowerRating snapshot (see app/ranking.py: offense and defense are
       centered on 0 = league average, positive = better, so a good opposing
       defense is *subtracted*).
    2. Add game-to-game noise: draw S ~ Normal(expected, SCORE_STD).
    3. Turn S into a percentile: P(Normal(S, SCORE_STD) > LEAGUE_AVG_POINTS).
    4. Look that percentile up in the sorted historical team scores
       (data/game_scores.csv), so the final score is always a score that has
       really happened (no 23.7-point games, no negative scores).

Differences from the original script, none of which change the method:
    * scipy.stats.norm.cdf is replaced by statistics.NormalDist (same math,
      one less dependency -- scipy isn't in requirements.txt).
    * The CSV is read once and cached instead of on every simulation.
    * The path is relative to this file instead of a Windows Downloads folder.
    * Football has no ties, so if both teams land on the same score the game
      goes to overtime (see `_break_tie`).
"""

from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

LEAGUE_AVG_POINTS = 26.4  # mean points per team per game in game_scores.csv
SCORE_STD = 14.09  # std dev of points per team per game in game_scores.csv
OVERTIME_POINTS = 3  # a tie is broken by giving the overtime winner a field goal

GAME_SCORES_PATH = Path(__file__).resolve().parent.parent / "data" / "game_scores.csv"


@lru_cache(maxsize=1)
def load_sorted_scores() -> np.ndarray:
    """Historical single-team game scores, sorted ascending (read once, then cached)."""
    df = pd.read_csv(GAME_SCORES_PATH)
    scores = np.sort(df["game_scores"].dropna().to_numpy())
    if scores.size == 0:
        raise RuntimeError(f"{GAME_SCORES_PATH} has no scores to sample from")
    return scores


def expected_points(offense: float, opponent_defense: float) -> float:
    """Points a team is expected to score against this opponent (neutral site)."""
    return LEAGUE_AVG_POINTS + offense - opponent_defense


def simulate_team_score(expected: float, sorted_scores: np.ndarray, rng: random.Random) -> int:
    """One simulated score for a team whose expected points are `expected`."""
    # Random score based on predicted points.
    noisy_points = rng.gauss(expected, SCORE_STD)

    # Probability: how likely a Normal(noisy_points, SCORE_STD) game beats the league average.
    percentile = 1 - NormalDist(mu=noisy_points, sigma=SCORE_STD).cdf(LEAGUE_AVG_POINTS)

    # Nearest actual score at that percentile of the historical scores.
    position = percentile * (len(sorted_scores) - 1)
    return int(sorted_scores[int(round(position))])


def _break_tie(
    score_a: int, score_b: int, expected_a: float, expected_b: float, rng: random.Random
) -> tuple[int, int]:
    """
    Overtime: the winner is drawn from the two teams' expected-points gap and
    gets OVERTIME_POINTS added. The sd of a score *difference* is
    SCORE_STD * sqrt(2) because the two scores are independent.
    """
    a_win_prob = NormalDist().cdf((expected_a - expected_b) / (SCORE_STD * math.sqrt(2)))
    if rng.random() < a_win_prob:
        return score_a + OVERTIME_POINTS, score_b
    return score_a, score_b + OVERTIME_POINTS


def simulate_game(
    offense_a: float,
    defense_a: float,
    offense_b: float,
    defense_b: float,
    sorted_scores: np.ndarray | None = None,
    rng: random.Random | None = None,
    home_field_advantage: float = 0.0,
) -> dict:
    """
    Simulate team A vs team B. Neutral site unless `home_field_advantage` is set.

    `home_field_advantage` is the home team's edge in the *margin*, in points
    (the same convention as app.ranking.DEFAULT_HOME_FIELD_ADVANTAGE), and
    team A is treated as the home team. Half of it is added to A's expected
    points and half subtracted from B's, which is how the rating model's
    Location coefficient works. Pass a negative value if A is the road team.
    The default of 0 is a neutral site.

    Returns {"expected_a", "expected_b", "score_a", "score_b", "overtime"}.
    """
    if sorted_scores is None:
        sorted_scores = load_sorted_scores()
    if rng is None:
        rng = random.Random()

    expected_a = expected_points(offense_a, defense_b) + home_field_advantage / 2
    expected_b = expected_points(offense_b, defense_a) - home_field_advantage / 2

    score_a = simulate_team_score(expected_a, sorted_scores, rng)
    score_b = simulate_team_score(expected_b, sorted_scores, rng)

    overtime = score_a == score_b
    if overtime:
        score_a, score_b = _break_tie(score_a, score_b, expected_a, expected_b, rng)

    return {
        "expected_a": expected_a,
        "expected_b": expected_b,
        "score_a": score_a,
        "score_b": score_b,
        "overtime": overtime,
    }