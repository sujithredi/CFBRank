"""
Week-by-week rating updates for the season simulation.

The season simulation (season_simulation.py) plays the remaining schedule one
week at a time. After each simulated week the offense/defense ratings are
re-fit with that week's simulated scores added to the games already played, and
the next week is simulated with the updated ratings -- so a team that
(in a given simulation) blows out three opponents is rated higher for the games
that follow, exactly as the real rankings would move.

"Re-fit" means the same model as app/ranking.py, not an approximation of it:
ordinary least squares with no intercept,

    team_score ~ Location + offense[team] + defense_coef[opponent]

with two rows per game, offense and defense centered on zero afterwards, and
defense = -defense_coef. In Bayesian terms this is the posterior mean under a
flat prior with Gaussian noise (no extra shrinkage is added). Tests check that
the ratings produced here equal compute_power_ratings on the same games.

Why this is fast enough to do 10,000 seasons x ~9 weeks
    The least-squares solution is  coefficients = pinv(X'X) . X'y.
    X -- *who played whom, and where* -- is the same in every simulation (the
    schedule is fixed); only the simulated scores differ, and they only enter
    through the vector X'y. So the matrix is inverted ONCE per week, here,
    and each simulation just keeps a running X'y and multiplies by it.

Layout of the coefficient vector (length 1 + 2n, n = number of teams):
    [0]            Location
    [1 .. n]       offense, one per team
    [n+1 .. 2n]    defense coefficient (opponent dummy), one per team
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

# Eigenvalues of X'X below this fraction of the largest are treated as zero.
# The free offense/defense constant gives exactly one null direction (~1e-16);
# genuine directions are many orders of magnitude above this (see tests).
_NULL_EIGENVALUE_FRACTION = 1e-10


def _add_rows(
    gram: np.ndarray | None,
    b: list[float] | None,
    n: int,
    home: int,
    away: int,
    location: int,
    home_points: float | None = None,
    away_points: float | None = None,
) -> None:
    """
    Add one game's two rows (each team's point of view) to X'X (`gram`) and,
    when scores are given, to X'y (`b`). `location` is 1 for a home game, 0 for
    a neutral site; the away team's row gets its negative.
    """
    for me, opponent, loc, points in (
        (home, away, location, home_points),
        (away, home, -location, away_points),
    ):
        columns = (0, 1 + me, 1 + n + opponent)
        values = (loc, 1.0, 1.0)
        if gram is not None:
            for i in range(3):
                for j in range(3):
                    gram[columns[i], columns[j]] += values[i] * values[j]
        if b is not None and points is not None:
            for i in range(3):
                b[columns[i]] += values[i] * points


def _pseudo_inverse(gram: np.ndarray) -> np.ndarray:
    """Pseudo-inverse of a symmetric positive semi-definite matrix (X'X)."""
    values, vectors = np.linalg.eigh(gram)
    keep = values > values.max() * _NULL_EIGENVALUE_FRACTION
    return (vectors[:, keep] / values[keep]) @ vectors[:, keep].T


class RatingRefitter:
    """
    Re-fits offense/defense ratings after each simulated week.

    n_teams          number of teams; teams are identified by index 0..n-1
    played           (home, away, home_points, away_points, location) for every
                     game already played this season; location is 1 for a
                     home game and 0 for a neutral site
    weeks            the simulated weeks in order; each is a list of
                     (home, away, location) for that week's games
    base_offense /   each team's rating before any simulated week. A team that
    base_defense     hasn't played a game yet (in the real or simulated games so
                     far) keeps this rating until it does.

    Usage, per simulation:
        b = refitter.start_vector()
        ... after simulating each game of week `stage`:
        refitter.add_game(b, home, away, location, home_points, away_points)
        ... after the whole week:
        offense, defense = refitter.ratings(stage, b)   # for the next week
    """

    def __init__(
        self,
        n_teams: int,
        played: Iterable[tuple[int, int, float, float, int]],
        weeks: Sequence[Sequence[tuple[int, int, int]]],
        base_offense: Sequence[float],
        base_defense: Sequence[float],
    ):
        self.n = n_teams
        self.dim = 1 + 2 * n_teams
        gram = np.zeros((self.dim, self.dim))
        b = [0.0] * self.dim
        for home, away, home_points, away_points, location in played:
            _add_rows(gram, b, n_teams, home, away, location, home_points, away_points)
        self._start = b

        base = np.concatenate([np.asarray(base_offense, float), np.asarray(base_defense, float)])
        self._operators: list[np.ndarray] = []
        self._constants: list[np.ndarray] = []
        for week in weeks:
            for home, away, location in week:
                _add_rows(gram, None, n_teams, home, away, location)
            self._operators.append(self._rating_operator(gram))
            self._constants.append(self._inactive_ratings(gram, base))

    def _active(self, gram: np.ndarray) -> np.ndarray:
        """Teams that appear in at least one game so far (they have an offense row)."""
        return np.diag(gram)[1 : 1 + self.n] > 0

    def _rating_operator(self, gram: np.ndarray) -> np.ndarray:
        """
        Matrix O with  [offense; defense] = O . (X'y)  for the teams in play: the
        pseudo-inverse, followed by "defense = -coefficient" and centering each
        of offense and defense on zero across the teams in play.
        """
        n = self.n
        active = self._active(gram)
        count = int(active.sum())
        out = np.zeros((2 * n, self.dim))
        if count == 0:
            return out
        solve = _pseudo_inverse(gram)
        offense = solve[1 : 1 + n]
        defense_coef = solve[1 + n :]
        out[:n][active] = (offense - offense[active].mean(axis=0))[active]
        out[n:][active] = -(defense_coef - defense_coef[active].mean(axis=0))[active]
        return out

    def _inactive_ratings(self, gram: np.ndarray, base: np.ndarray) -> np.ndarray:
        inactive = ~self._active(gram)
        constants = np.zeros(2 * self.n)
        constants[: self.n][inactive] = base[: self.n][inactive]
        constants[self.n :][inactive] = base[self.n :][inactive]
        return constants

    # ---- per-simulation -----------------------------------------------------

    def start_vector(self) -> list[float]:
        """X'y for the games already played. Copy-on-use: every simulation starts from this."""
        return self._start[:]

    def add_game(
        self, b: list[float], home: int, away: int, location: int, home_points: float, away_points: float
    ) -> None:
        """Add one simulated game's scores to a simulation's running X'y."""
        n = self.n
        b[1 + home] += home_points
        b[1 + n + away] += home_points
        b[1 + away] += away_points
        b[1 + n + home] += away_points
        if location:
            b[0] += location * (home_points - away_points)

    def ratings(self, stage: int, b: list[float]) -> tuple[list[float], list[float]]:
        """
        Offense and defense ratings (one per team, same order as the team
        indexes) after simulated week number `stage` (0-based) has been added to `b`.
        """
        r = (self._operators[stage] @ np.asarray(b) + self._constants[stage]).tolist()
        return r[: self.n], r[self.n :]
