// Columns the rankings table can be sorted by. `key` is the field on each
// ranking entry returned by GET /api/rankings.
//
// `description` (optional) is shown as the header tooltip. The last eleven come
// from the rest-of-season simulation and are null until it has been run.
export const SORT_COLUMNS = [
  { key: 'power_score', label: 'Overall' },
  { key: 'offense_rating', label: 'Offense' },
  { key: 'defense_rating', label: 'Defense' },
  {
    key: 'projected_wins',
    label: 'Proj. W-L',
    description: 'Average final regular-season record across the simulated seasons',
  },
  {
    key: 'bowl_pct',
    label: 'Bowl %',
    description: 'Chance of finishing with 6+ wins (bowl eligible). FBS teams only',
  },
  {
    key: 'undefeated_pct',
    label: 'Undefeated %',
    description: 'Chance of finishing the regular season with no losses',
  },
  {
    key: 'title_game_pct',
    label: 'Title Game %',
    description: 'Chance of playing in the conference championship game. FBS conferences with one only',
  },
  {
    key: 'conf_champ_pct',
    label: 'Conf. Champ %',
    description: 'Chance of winning the conference championship game. FBS conferences with one only',
  },
  {
    key: 'playoff_pct',
    label: 'Playoff %',
    description: 'Chance of being selected for the 12-team College Football Playoff field. FBS teams only',
  },
  {
    key: 'cfp_bye_pct',
    label: 'CFP Bye %',
    description: 'Chance of being a top-4 seed, with a first-round bye. FBS teams only',
  },
  {
    key: 'cfp_quarterfinal_pct',
    label: 'CFP Quarters %',
    description: 'Chance of playing in a playoff quarterfinal: a top-4 seed or a first-round winner. FBS teams only',
  },
  {
    key: 'cfp_semifinal_pct',
    label: 'CFP Semis %',
    description: 'Chance of playing in a playoff semifinal. FBS teams only',
  },
  {
    key: 'cfp_final_pct',
    label: 'CFP Final %',
    description: 'Chance of playing in the national championship game. FBS teams only',
  },
  {
    key: 'cfp_champion_pct',
    label: 'CFP Champ %',
    description: 'Chance of winning the national championship. FBS teams only',
  },
]

/**
 * Sort ranking entries by `sortKey`.
 *
 * direction 'desc' puts the best team first (every rating is "higher = better",
 * including defense); 'asc' puts the worst first. Teams with no value for the
 * column (offense/defense are null on snapshots computed before the split
 * existed, or before the season simulation was run; Bowl %, Title Game %, Conf. Champ %, Playoff % and the CFP columns for teams that don't have one) always go last, in either direction.
 *
 * Returns new objects with `displayRank` added: the team's position by that
 * column, best = 1, regardless of direction -- so sorting by Offense and
 * flipping to ascending shows ranks like 133, 132, ... rather than 1, 2, ...
 * `displayRank` is null for teams with no value.
 */
export function sortRankings(rankings, sortKey, direction = 'desc') {
  const withValue = rankings.filter((team) => team[sortKey] != null)
  const withoutValue = rankings.filter((team) => team[sortKey] == null)

  // Array.prototype.sort is stable, so ties keep the server's (overall) order.
  const bestFirst = [...withValue].sort((a, b) => b[sortKey] - a[sortKey])
  const ranked = bestFirst.map((team, index) => ({ ...team, displayRank: index + 1 }))

  const ordered = direction === 'asc' ? ranked.reverse() : ranked
  return [...ordered, ...withoutValue.map((team) => ({ ...team, displayRank: null }))]
}
