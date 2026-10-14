"""
College Football Playoff:

The field is FIELD_SIZE (12) teams (the 2026-27 rules):

    1. Conference champions of the ACC, Big Ten, SEC and Big 12 get in
       automatically, whatever their final ranking (AUTO_BID_CONFERENCES).
       "Champion" means the winner of the simulated conference title game.
    2. One more automatic bid goes to the best Group of 6 champion
       (GROUP_OF_6: American, Conference USA, Mid-American, Mountain West,
       Pac-12 and Sun Belt): the neural network rates the champion of each of
       those six conferences and the one with the highest playoff probability
       gets in.
    3. Notre Dame also gets in automatically if it is a top-12 team
       (RANKED_AUTO_BID_TEAMS). There is no committee ranking to read, so
       "top 12" is the network's own ordering: the twelve highest playoff
       probabilities among all eligible FBS teams. This only matters when the
       automatic bids above would otherwise crowd Notre Dame out of the
       at-large spots.
    4. The remaining spots (seven, or six when Notre Dame took an automatic
       bid) are at-large: the network rates every other FBS team and the
       highest probabilities fill the field. That pool includes independents
       and the Group of 6 champions that lost out on step 2.

Seeding and the playoff games themselves live in app/playoff_bracket.py.

The neural network
    A scikit-learn MLPClassifier trained on data/playoff_data.csv, one row per
    past team-season: did the team make the playoff (`playoffs`), given its
    strength of schedule (`sos`) and its regular-season record (`wins`,
    `loses`). Its output is P(makes the playoff) for a team, and the only thing
    that matters is how teams rank against each other -- the probabilities are
    not shown anywhere.

    The training recipe (features standardized, an 80/20 split with
    random_state=42, one 177-unit tanh layer, lbfgs for 21 iterations,
    alpha=0.228) is the one it was tuned with. Note that, as in that recipe,
    the scaler is fit on all the rows before the split, and the network itself
    is fit on the 80% training share only. Training takes about 10 ms, so it
    is done once per process (get_playoff_model) and never saved to disk.

Inputs the network is given (computed by the season simulation, per simulated season)
    sos      average overall power rating (offense + defense) of every regular-season
             opponent the team played -- games already played and simulated ones,
             FCS opponents included -- using the ratings as they stand after the
             last simulated week. The real or simulated conference title game is not
             a regular-season game, so it is left out here and out of wins/losses too.
    wins     regular-season wins (title game not included)
    loses    regular-season losses (title game not included)

Caveat: the training rows are all 12-game seasons (wins + loses = 12). A team
that plays 11 or 13 regular-season games is a little outside what the network
has seen; it is still scored, just less reliably.
"""

from __future__ import annotations

import heapq
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, NamedTuple, Sequence

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

PLAYOFF_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "playoff_data.csv"

# Column names in the CSV. The order here is the order the network is given its inputs in.
FEATURE_COLUMNS = ("sos", "wins", "loses")
LABEL_COLUMN = "playoffs"

FIELD_SIZE = 12

# Conference names exactly as stored in conferences.name (the keys of CONFERENCE_RULES).
AUTO_BID_CONFERENCES = ("ACC", "Big Ten", "SEC", "Big 12")
GROUP_OF_6 = ("American Athletic", "Conference USA", "Mid-American", "Mountain West", "Sun Belt", "Pac-12")
# Teams (by school name) that get an automatic bid if they rank in the top FIELD_SIZE.
RANKED_AUTO_BID_TEAMS = ("Notre Dame",)


class PlayoffModel:
    """A trained network plus the scaler its inputs need."""

    def __init__(self, scaler: StandardScaler, classifier: MLPClassifier, test_accuracy: float | None = None):
        classes = list(classifier.classes_)
        if 1 not in classes:
            raise ValueError("The playoff model has no 'made the playoff' class to predict")
        self.scaler = scaler
        self.classifier = classifier
        self.test_accuracy = test_accuracy  # share of the held-out 20% classified correctly
        self._positive = classes.index(1)

    def probability(self, sos, wins, losses) -> np.ndarray:
        """P(makes the playoff) for each team; the three arguments are equal-length sequences."""
        features = np.column_stack([sos, wins, losses]).astype(float)
        return self.classifier.predict_proba(self.scaler.transform(features))[:, self._positive]


def train_playoff_model(path: Path | str = PLAYOFF_DATA_PATH) -> PlayoffModel:
    """Train the network on the CSV at `path` (columns: playoffs, sos, wins, loses)."""
    data = pd.read_csv(path).dropna(axis=0, how="any")
    missing = {LABEL_COLUMN, *FEATURE_COLUMNS} - set(data.columns)
    if missing:
        raise ValueError(f"{path} is missing column(s): {sorted(missing)}")

    labels = np.array(data[LABEL_COLUMN])
    if len(set(labels)) < 2:
        raise ValueError(f"{path} needs both playoff and non-playoff rows to train on")
    features = np.array(data[list(FEATURE_COLUMNS)], dtype=float)  # picked by name, so CSV column order doesn't matter

    scaler = StandardScaler().fit(features)
    train_features, test_features, train_labels, test_labels = train_test_split(
        scaler.transform(features), labels, test_size=0.2, random_state=42
    )
    classifier = MLPClassifier(
        hidden_layer_sizes=(177,),
        max_iter=21,
        activation="tanh",
        solver="lbfgs",
        early_stopping=False,
        alpha=0.228,
        random_state=42,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        classifier.fit(train_features, train_labels)

    return PlayoffModel(scaler, classifier, float(classifier.score(test_features, test_labels)))


@lru_cache(maxsize=1)
def get_playoff_model() -> PlayoffModel:
    """The network trained on the repository's playoff_data.csv, built on first use."""
    return train_playoff_model()


class PlayoffField(NamedTuple):
    """The selected teams, as the indexes the caller used for them."""

    conference_champions: list[int]  # automatic bids for AUTO_BID_CONFERENCES champions
    group_of_6: int | None  # the Group of 6 champion with the highest probability
    at_large: list[int]  # best remaining teams, highest probability first
    ranked_auto: Sequence[int] = ()  # RANKED_AUTO_BID_TEAMS that ranked in the top FIELD_SIZE

    @property
    def teams(self) -> list[int]:
        return [
            *self.conference_champions,
            *([] if self.group_of_6 is None else [self.group_of_6]),
            *self.ranked_auto,
            *self.at_large,
        ]


def select_playoff_field(
    probability: Sequence[float],
    champions: Mapping[str, int],
    eligible: Iterable[int],
    field_size: int = FIELD_SIZE,
    auto_conferences: Sequence[str] = AUTO_BID_CONFERENCES,
    group_of_6: Sequence[str] = GROUP_OF_6,
    ranked_auto_bid: Iterable[int] = (),
) -> PlayoffField:
    """
    Pick the playoff field.

    probability  each team's playoff probability, indexed by team (same indexes as `champions`)
    champions    {conference name: team that won its title game}; a conference with no
                 entry simply has no champion this season
    eligible     the teams that can be chosen at large (the FBS teams)
    field_size   total number of teams
    ranked_auto_bid
                 teams (e.g. Notre Dame) that get an automatic bid if they are among the
                 `field_size` highest-probability eligible teams

    Ties in probability go to the team with the lower index, so the choice is
    deterministic. If a conference has no champion, its automatic spot is not
    held open: it goes to the at-large pool, so the field is always full while
    enough eligible teams exist.
    """
    eligible = list(eligible)
    automatic = [champions[name] for name in auto_conferences if name in champions]

    group_champions = [champions[name] for name in group_of_6 if name in champions]
    best_group_champion = max(group_champions, key=lambda team: (probability[team], -team), default=None)

    chosen = set(automatic)
    if best_group_champion is not None:
        chosen.add(best_group_champion)

    # A ranked-auto-bid team (Notre Dame) is in if it is a top-`field_size` team, even when the
    # automatic bids above would otherwise have crowded it out of the at-large spots.
    top_teams = set(heapq.nlargest(field_size, eligible, key=lambda team: (probability[team], -team)))
    ranked_auto = []
    for team in ranked_auto_bid:
        if team in top_teams and team not in chosen:
            ranked_auto.append(team)
            chosen.add(team)

    open_spots = max(field_size - len(chosen), 0)
    at_large = heapq.nlargest(
        open_spots,
        (team for team in eligible if team not in chosen),
        key=lambda team: (probability[team], -team),
    )
    return PlayoffField(automatic, best_group_champion, at_large, ranked_auto)