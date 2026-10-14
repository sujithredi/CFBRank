"""
College Football Playoff bracket: seeding the field and playing the games.

app/playoff.py decides *who* is in the field. This module takes those teams and
plays the bracket out, one simulated game at a time, with app.simulation.simulate_game.

Format (the 2026-27 CFP, 12 teams)
    * The field is seeded 1-12 straight down the ranking. The four best seeds get a
      first-round bye, whether or not they won their conference.
    * Round 1 is 5v12, 6v11, 7v10 and 8v9, on the higher seed's campus.
    * Quarterfinals: 1 vs the 8/9 winner, 4 vs the 5/12 winner, 2 vs the 7/10 winner,
      3 vs the 6/11 winner. Semifinals: the 1 and 4 quarterfinal winners meet, as do the
      2 and 3 winners. Then the final. All of these are at neutral sites.
    * There is no re-seeding after a round, and the bracket is never adjusted to avoid
      rematches or same-conference games.

The bracket is data (TWELVE_TEAM_BRACKET), not code: each game names what fills its
two slots, either "seed n" or "the winner of game g". A different format (14 or 16
teams, other byes) is another tuple of BracketGame, and nothing else here changes.

Seeding
    The CFP committee's ranking isn't something this project has, so `seed_field` orders
    the twelve teams by overall rating (offense + defense) as it stands after the last
    simulated week -- the same ratings the playoff games are played with. The network in
    playoff.py is not used for this: it answers "does this team make the field?", so it
    rates every strong team near 1 and can't order the top of the bracket. If you later get
    committee rankings, replace `seed_field`; `simulate_bracket` takes the seeds as given.

Assumptions
    * Ratings are not re-fit between playoff rounds, the same way a conference title game
      doesn't feed back into the ratings.
    * The home team in round 1 gets app.ranking.DEFAULT_HOME_FIELD_ADVANTAGE, the same
      margin as every other home game in the simulation. Every other round is neutral.
    * Football has no ties; simulate_game sends a tied score to overtime.
    * A field with fewer teams than the bracket has seeds is still played: an empty seed
      slot is a walkover for its opponent (a team with no opponent just advances). The real
      field is always full, so this only matters for tiny test leagues.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, NamedTuple, Sequence

from app.ranking import DEFAULT_HOME_FIELD_ADVANTAGE
from app.simulation import load_sorted_scores, simulate_game

FIRST_ROUND = 1
QUARTERFINAL = 2
SEMIFINAL = 3
FINAL = 4

ROUND_NAMES = {
    FIRST_ROUND: "First round",
    QUARTERFINAL: "Quarterfinal",
    SEMIFINAL: "Semifinal",
    FINAL: "National championship",
}


@dataclass(frozen=True)
class Seed:
    """A bracket slot filled by the team with this seed (1 = best)."""

    number: int


@dataclass(frozen=True)
class Winner:
    """A bracket slot filled by whoever wins the game with this id."""

    game: str


@dataclass(frozen=True)
class BracketGame:
    id: str
    round: int
    slot_a: Seed | Winner
    slot_b: Seed | Winner
    # True if team A (the better seed) hosts and gets the home-field edge; False is a neutral site.
    hosted: bool = False


# Games are listed in the order they're played: a game always comes after the games feeding it.
TWELVE_TEAM_BRACKET: tuple[BracketGame, ...] = (
    BracketGame("R1-5v12", FIRST_ROUND, Seed(5), Seed(12), hosted=True),
    BracketGame("R1-6v11", FIRST_ROUND, Seed(6), Seed(11), hosted=True),
    BracketGame("R1-7v10", FIRST_ROUND, Seed(7), Seed(10), hosted=True),
    BracketGame("R1-8v9", FIRST_ROUND, Seed(8), Seed(9), hosted=True),
    BracketGame("QF-1", QUARTERFINAL, Seed(1), Winner("R1-8v9")),
    BracketGame("QF-4", QUARTERFINAL, Seed(4), Winner("R1-5v12")),
    BracketGame("QF-2", QUARTERFINAL, Seed(2), Winner("R1-7v10")),
    BracketGame("QF-3", QUARTERFINAL, Seed(3), Winner("R1-6v11")),
    BracketGame("SF-1/4", SEMIFINAL, Winner("QF-1"), Winner("QF-4")),
    BracketGame("SF-2/3", SEMIFINAL, Winner("QF-2"), Winner("QF-3")),
    BracketGame("FINAL", FINAL, Winner("SF-1/4"), Winner("SF-2/3")),
)


def validate_bracket(bracket: Sequence[BracketGame]) -> None:
    """Raise ValueError unless every seed is used once and every game follows the games feeding it."""
    seen_games: set[str] = set()
    seeds: list[int] = []
    for game in bracket:
        if game.id in seen_games:
            raise ValueError(f"Duplicate game id {game.id!r}")
        for slot in (game.slot_a, game.slot_b):
            if isinstance(slot, Seed):
                seeds.append(slot.number)
            elif slot.game not in seen_games:
                raise ValueError(f"{game.id} needs the winner of {slot.game!r}, which isn't played before it")
        seen_games.add(game.id)
    if sorted(seeds) != list(range(1, len(seeds) + 1)):
        raise ValueError(f"Seeds must be 1..n, each used once; got {sorted(seeds)}")


def bracket_size(bracket: Sequence[BracketGame] = TWELVE_TEAM_BRACKET) -> int:
    """Number of teams the bracket holds (its highest seed)."""
    return max(slot.number for game in bracket for slot in (game.slot_a, game.slot_b) if isinstance(slot, Seed))


def bye_seeds(bracket: Sequence[BracketGame] = TWELVE_TEAM_BRACKET) -> list[int]:
    """The seeds that skip the first round: placed straight into a later-round game."""
    first_round = min(game.round for game in bracket)
    return sorted(
        slot.number
        for game in bracket
        if game.round > first_round
        for slot in (game.slot_a, game.slot_b)
        if isinstance(slot, Seed)
    )


validate_bracket(TWELVE_TEAM_BRACKET)


def seed_field(teams: Iterable[int], rating: Sequence[float]) -> list[int]:
    """
    Order the field best first: the first team in the list is the 1 seed.

    `rating` is indexed the same way as `teams` (overall rating, higher = better). Ties go to
    the lower index, so the seeding is deterministic.
    """
    return sorted(teams, key=lambda team: (-rating[team], team))


class BracketGameResult(NamedTuple):
    game: str
    round: int
    team_a: int | None
    team_b: int | None
    score_a: int | None  # None, with score_b, when the game was a walkover
    score_b: int | None
    winner: int | None


class BracketResult(NamedTuple):
    seeds: list[int]
    games: list[BracketGameResult]  # in the order they were played
    champion: int | None
    # Team -> the latest round it was placed into. A bye team starts in the quarterfinal; a
    # team that wins the title is in FINAL.
    furthest_round: dict[int, int]
    bye_teams: list[int]


def simulate_bracket(
    seeds: Sequence[int],
    offense: Sequence[float],
    defense: Sequence[float],
    rng: random.Random,
    sorted_scores=None,
    home_field_advantage: float = DEFAULT_HOME_FIELD_ADVANTAGE,
    bracket: Sequence[BracketGame] = TWELVE_TEAM_BRACKET,
) -> BracketResult:
    """
    Play the bracket once.

    seeds     team indexes, best seed first (see `seed_field`); `seeds[0]` is the 1 seed
    offense, defense
              each team's ratings, indexed by team (the ratings after the last regular week)
    rng       the source of randomness; pass a seeded Random for a reproducible bracket
    home_field_advantage
              the host's margin edge in a `hosted` game; every other game is neutral
    """
    size = bracket_size(bracket)
    if len(seeds) > size:
        raise ValueError(f"This bracket holds {size} teams, but {len(seeds)} were given")
    if len(set(seeds)) != len(seeds):
        raise ValueError("A team can only be in the field once")
    if sorted_scores is None:
        sorted_scores = load_sorted_scores()

    team_at_seed = {number: team for number, team in enumerate(seeds, start=1)}
    winners: dict[str, int | None] = {}
    furthest: dict[int, int] = {}
    played: list[BracketGameResult] = []

    for game in bracket:
        a, b = (
            team_at_seed.get(slot.number) if isinstance(slot, Seed) else winners[slot.game]
            for slot in (game.slot_a, game.slot_b)
        )
        for team in (a, b):
            if team is not None:
                furthest[team] = max(furthest.get(team, 0), game.round)

        if a is None or b is None:  # an empty slot: the other team (if any) just advances
            winner = a if a is not None else b
            played.append(BracketGameResult(game.id, game.round, a, b, None, None, winner))
        else:
            sim = simulate_game(
                offense[a], defense[a], offense[b], defense[b],
                sorted_scores=sorted_scores, rng=rng,
                home_field_advantage=home_field_advantage if game.hosted else 0.0,
            )
            winner = a if sim["score_a"] > sim["score_b"] else b
            played.append(BracketGameResult(game.id, game.round, a, b, sim["score_a"], sim["score_b"], winner))
        winners[game.id] = winner

    byes = set(bye_seeds(bracket))
    return BracketResult(
        seeds=list(seeds),
        games=played,
        champion=winners[bracket[-1].id],
        furthest_round=furthest,
        bye_teams=[team for number, team in team_at_seed.items() if number in byes],
    )
