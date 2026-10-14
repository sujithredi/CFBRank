"""
For each FBS conference with a title game, the two finalists are the top two
teams by conference winning percentage. Ties are broken by the
conference's tiebreakers, in order. The season simulation (season_simulation.py)
calls ConferenceModel.pick_finalists once per simulated season.

Conference            Tiebreakers (in order)                                  Title game site
SEC                   head-to-head; record vs common conference opponents     neutral
Big Ten               head-to-head; record vs common conference opponents     neutral
Big 12                head-to-head; record vs common conference opponents     neutral
ACC                   head-to-head; random (see disclaimer)                   neutral
Pac-12                head-to-head; win % vs the highest-placed common opp.   first-place team's home
American Athletic     head-to-head; model rating (see disclaimer)             first-place team's home
Conference USA        head-to-head; record vs common conference opponents     first-place team's home
Mountain West         head-to-head; model rating (see disclaimer)             first-place team's home
Mid-American          head-to-head; record vs common conference opponents     first-place team's home
Sun Belt              divisions: each division winner plays. Division ties:   first-place team's home
                      head-to-head; winning % within the division

DISCLAIMERS
    * ACC: the conference's real second tiebreaker uses non-public data, so
      any tie that reaches it is broken at random here.
    * American and Mountain West: their real second tiebreaker is the CFB
      Rankings, which this project doesn't have yet. Until it does, the team
      with the higher power rating from this project's model wins the tie.
    * Every conference: tie is broken at random if the listed tiebreakers don't settle a tie.

How a tie is broken
    Teams level on conference winning percentage form a tied group. Each
    tiebreaker is tried in order; the first one that separates the group splits
    it into smaller groups, and each smaller group *starts over from the first
    tiebreaker* (so a 3-way tie reduced to 2 teams goes back to head-to-head
    between just those two). Details of each tiebreaker:
      head-to-head      winning % in games among the tied teams only. A team
                        that played none of the other tied teams counts as .500.
      common opponents  winning % against the conference opponents that *every*
                        tied team played. Doesn't apply if there are none.
      next-highest common opponent (Pac-12)
                        take the common opponents in conference-standing order
                        (opponents level on winning % are one tier), and compare
                        winning % against the highest tier; if still level, the
                        next tier, and so on.
      division %        winning % in conference games against the team's own
                        division (Sun Belt only).
      model rating      the project's overall power rating, higher wins.

Home team: for conferences that play at a campus site, the first-place team
hosts. For the Sun Belt that's the division winner with the better conference
winning percentage.

Only games before CHAMPIONSHIP_WEEK count toward the standings. (Army-Navy, which is a conference game for
the American, does not count)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

CHAMPIONSHIP_WEEK = 14

STEP_NAMES = {
    "head_to_head",
    "common_opponents",
    "common_opponent_standing",
    "division_pct",
    "model_rating",
    "random",
}


@dataclass(frozen=True)
class ConferenceRules:
    neutral_site: bool  # True: title game at a neutral site; False: first-place team's home field
    tiebreakers: tuple[str, ...]  # in order; names from STEP_NAMES
    divisions: bool = False  # True: each division winner plays (tiebreakers then apply within a division)

    def __post_init__(self):
        unknown = set(self.tiebreakers) - STEP_NAMES
        if unknown:
            raise ValueError(f"Unknown tiebreaker(s): {sorted(unknown)}")
        if "division_pct" in self.tiebreakers and not self.divisions:
            raise ValueError("division_pct only makes sense for a conference with divisions")


H2H = "head_to_head"
COMMON = "common_opponents"

CONFERENCE_RULES: dict[str, ConferenceRules] = {
    "SEC": ConferenceRules(neutral_site=True, tiebreakers=(H2H, COMMON)),
    "Big Ten": ConferenceRules(neutral_site=True, tiebreakers=(H2H, COMMON)),
    "Big 12": ConferenceRules(neutral_site=True, tiebreakers=(H2H, COMMON)),
    "ACC": ConferenceRules(neutral_site=True, tiebreakers=(H2H, "random")),
    "Pac-12": ConferenceRules(neutral_site=False, tiebreakers=(H2H, "common_opponent_standing")),
    "American Athletic": ConferenceRules(neutral_site=False, tiebreakers=(H2H, "model_rating")),
    "Conference USA": ConferenceRules(neutral_site=False, tiebreakers=(H2H, COMMON)),
    "Mountain West": ConferenceRules(neutral_site=False, tiebreakers=(H2H, "model_rating")),
    "Mid-American": ConferenceRules(neutral_site=False, tiebreakers=(H2H, COMMON)),
    "Sun Belt": ConferenceRules(neutral_site=False, tiebreakers=(H2H, "division_pct"), divisions=True),
}

# Shown next to results so nobody mistakes the stand-ins for the real tiebreakers.
DISCLAIMERS = (
    "ACC: the conference's second tiebreaker uses non-public data, so ties that reach it are broken at random.",
    "American and Mountain West: the second tiebreaker is the CFB Rankings, which aren't incorporated yet; "
    "the higher-rated team by this project's model wins instead.",
    "Any tie the listed tiebreakers can't settle is broken at random.",
)


def _fraction(wins: int, losses: int, default: float) -> float:
    total = wins + losses
    return wins / total if total else default


def _tiers(members: list[int], pct: dict[int, float]) -> list[list[int]]:
    """Group teams level on winning percentage."""
    tiers: list[list[int]] = []
    for team in sorted(members, key=lambda t: -pct[t]):
        if tiers and pct[tiers[-1][0]] == pct[team]:
            tiers[-1].append(team)
        else:
            tiers.append([team])
    return tiers


@dataclass
class ConferenceModel:
    name: str
    rules: ConferenceRules
    members: list[int]
    schedule: list[tuple[int, int]]
    played: list[tuple[int, int]]
    division_of: dict[int, str] = field(default_factory=dict)
    rating: dict[int, float] = field(default_factory=dict)

    def __post_init__(self):
        if len(self.members) < 2:
            raise ValueError(f"{self.name} needs at least two teams for a championship game")

        self.opponents: dict[int, set[int]] = {team: set() for team in self.members}
        for a, b in self.schedule:
            self.opponents[a].add(b)
            self.opponents[b].add(a)

        # (winner, loser) -> number of wins in games already played.
        self.base_results: dict[tuple[int, int], int] = {}
        self.base_wins = {team: 0 for team in self.members}
        self.base_losses = {team: 0 for team in self.members}
        for winner, loser in self.played:
            self.base_results[(winner, loser)] = self.base_results.get((winner, loser), 0) + 1
            self.base_wins[winner] += 1
            self.base_losses[loser] += 1

        self.divisions: dict[str, list[int]] = {}
        if self.rules.divisions:
            missing = [team for team in self.members if not self.division_of.get(team)]
            if missing:
                raise ValueError(f"{self.name} uses divisions but {len(missing)} team(s) have none")
            for team in self.members:
                self.divisions.setdefault(self.division_of[team], []).append(team)
            if len(self.divisions) != 2:
                raise ValueError(f"{self.name} needs exactly two divisions, found {sorted(self.divisions)}")
            self.division_mates = {
                team: tuple(o for o in self.opponents[team] if self.division_of[o] == self.division_of[team])
                for team in self.members
            }

        self._steps = {
            "head_to_head": self._head_to_head,
            "common_opponents": self._common_opponents,
            "common_opponent_standing": self._common_opponent_standing,
            "division_pct": self._division_pct,
            "model_rating": self._model_rating,
            "random": self._random,
        }

    #tiebreakers: each returns {team: key} (higher is better), or None

    def _head_to_head(self, group, results, pct, rng):
        keys = {}
        for team in group:
            wins = losses = 0
            for other in group:
                if other != team:
                    wins += results.get((team, other), 0)
                    losses += results.get((other, team), 0)
            keys[team] = _fraction(wins, losses, 0.5)
        return keys

    def _common(self, group):
        common = set(self.opponents[group[0]])
        for team in group[1:]:
            common &= self.opponents[team]
        return common

    @staticmethod
    def _record_against(team, opponents, results):
        wins = sum(results.get((team, o), 0) for o in opponents)
        losses = sum(results.get((o, team), 0) for o in opponents)
        return _fraction(wins, losses, 0.5)

    def _common_opponents(self, group, results, pct, rng):
        common = self._common(group)
        if not common:
            return None
        return {team: self._record_against(team, common, results) for team in group}

    def _common_opponent_standing(self, group, results, pct, rng):
        common = self._common(group)
        if not common:
            return None
        for tier_pct in sorted({pct[o] for o in common}, reverse=True):
            tier = [o for o in common if pct[o] == tier_pct]
            keys = {team: self._record_against(team, tier, results) for team in group}
            if len(set(keys.values())) > 1:
                return keys
        return None

    def _division_pct(self, group, results, pct, rng):
        return {team: self._record_against(team, self.division_mates[team], results) for team in group}

    def _model_rating(self, group, results, pct, rng):
        return {team: self.rating.get(team, 0.0) for team in group}

    def _random(self, group, results, pct, rng):
        return {team: rng.random() for team in group}

    # ---- ordering ----

    def _order(self, group, steps, results, pct, rng) -> list[int]:
        """Order a group of teams level on winning percentage, best first."""
        if len(group) < 2:
            return list(group)
        for name in steps:
            keys = self._steps[name](group, results, pct, rng)
            if keys is None or len(set(keys.values())) == 1:
                continue
            ordered: list[int] = []
            for value in sorted(set(keys.values()), reverse=True):
                subgroup = [team for team in group if keys[team] == value]
                ordered.extend(self._order(subgroup, steps, results, pct, rng))  # start over from step 1
            return ordered
        shuffled = list(group)  # nothing separated them
        rng.shuffle(shuffled)
        return shuffled

    def _division_winner(self, members, pct, results, rng) -> int:
        top_tier = _tiers(members, pct)[0]
        return self._order(top_tier, self.rules.tiebreakers, results, pct, rng)[0]

    def pick_finalists(
        self,
        wins: list[int],
        losses: list[int],
        results: dict[tuple[int, int], int],
        rng: random.Random,
    ) -> tuple[int, int]:
        """
        The two teams that play for the title: (first place, second place). The
        first-place team is the home team when the game isn't at a neutral site.

        wins / losses  conference wins and losses, indexed by team index
        results        {(winner, loser): count} for every conference game this season
        """
        pct = {team: _fraction(wins[team], losses[team], 0.0) for team in self.members}
        steps = self.rules.tiebreakers

        if self.rules.divisions:
            first, second = (
                self._division_winner(members, pct, results, rng) for members in self.divisions.values()
            )
            if pct[second] > pct[first]:
                first, second = second, first
            elif pct[second] == pct[first]:
                first, second = self._order([first, second], (H2H,), results, pct, rng)
            return first, second

        ordered: list[int] = []
        for tier in _tiers(self.members, pct):
            ordered.extend(self._order(tier, steps, results, pct, rng))
            if len(ordered) >= 2:
                break
        return ordered[0], ordered[1]