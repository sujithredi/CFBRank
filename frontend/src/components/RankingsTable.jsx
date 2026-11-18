import { useMemo, useRef } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { fetchRankings } from '../api'
import { ALL_CONFERENCES, filterByConference, hasConference, listConferences } from '../conferenceFilter'
import { formatPercent, formatProjectedRecord, formatRating } from '../format'
import { SORT_COLUMNS, sortRankings } from '../sortRankings'
import { useFetch } from '../useFetch'
import TeamLogo from './TeamLogo'

// How each sortable column's value is shown. Keys match SORT_COLUMNS, and the
// body cells are built by looping over SORT_COLUMNS, so a column's header and its
// cells can't drift out of order.
const CELL_FORMATTERS = {
  power_score: (team) => team.power_score.toFixed(1),
  offense_rating: (team) => formatRating(team.offense_rating),
  defense_rating: (team) => formatRating(team.defense_rating),
  projected_wins: (team) => formatProjectedRecord(team.projected_wins, team.projected_losses),
  bowl_pct: (team) => formatPercent(team.bowl_pct),
  undefeated_pct: (team) => formatPercent(team.undefeated_pct),
  title_game_pct: (team) => formatPercent(team.title_game_pct),
  conf_champ_pct: (team) => formatPercent(team.conf_champ_pct),
  playoff_pct: (team) => formatPercent(team.playoff_pct),
  cfp_bye_pct: (team) => formatPercent(team.cfp_bye_pct),
  cfp_quarterfinal_pct: (team) => formatPercent(team.cfp_quarterfinal_pct),
  cfp_semifinal_pct: (team) => formatPercent(team.cfp_semifinal_pct),
  cfp_final_pct: (team) => formatPercent(team.cfp_final_pct),
  cfp_champion_pct: (team) => formatPercent(team.cfp_champion_pct),
}

// Columns before the stats: Rank, Team, Conference, W-L. Hovering a column from
// here on highlights it (Rank and Team are pinned, so they never need it).
const FIRST_HIGHLIGHTABLE_COLUMN = 3

function RankingsTable() {
  const { data, error, isLoading } = useFetch(fetchRankings)
  const tableRef = useRef(null)

  // The sort and conference filter live in the URL
  // (?sort=offense_rating&dir=asc&conf=SEC) rather than in component state, so
  // going to a team's page and pressing Back returns to the same view.
  // Unknown/missing values fall back to Overall, best first, all conferences.
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const requestedSort = searchParams.get('sort')
  const sortKey = SORT_COLUMNS.some(({ key }) => key === requestedSort) ? requestedSort : 'power_score'
  const sortDirection = searchParams.get('dir') === 'asc' ? 'asc' : 'desc'

  const conferenceGroups = useMemo(() => (data ? listConferences(data.rankings) : []), [data])
  const requestedConference = searchParams.get('conf')
  const conference =
    requestedConference && hasConference(conferenceGroups, requestedConference)
      ? requestedConference
      : ALL_CONFERENCES

  // Sort first, then filter: each team's displayRank stays its position among
  // *all* teams, so filtering to a conference doesn't renumber it.
  const sortedRows = useMemo(
    () => (data ? sortRankings(data.rankings, sortKey, sortDirection) : []),
    [data, sortKey, sortDirection],
  )
  const rows = useMemo(() => filterByConference(sortedRows, conference), [sortedRows, conference])

  // Updates one or more URL params while keeping the rest (sort/dir/conf).
  // replace: sorting and filtering shouldn't add a history entry per click.
  function updateParams(changes) {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        for (const [name, value] of Object.entries(changes)) {
          if (value == null) next.delete(name)
          else next.set(name, value)
        }
        return next
      },
      { replace: true },
    )
  }

  // Clicking the active column flips the direction; a new column starts best-first.
  function handleSort(key) {
    const direction = key === sortKey && sortDirection === 'desc' ? 'asc' : 'desc'
    updateParams({ sort: key, dir: direction })
  }

  function handleConferenceChange(event) {
    const value = event.target.value
    updateParams({ conf: value === ALL_CONFERENCES ? null : value })
  }

  // Crosshair highlight: the row under the pointer is highlighted by CSS (:hover),
  // and the column is marked with data-hover-col on the table. This is set
  // directly on the element, not in React state, so moving the mouse across the
  // table never re-renders its hundreds of cells.
  function handlePointerOver(event) {
    const cell = event.target.closest('td, th')
    const column = cell ? cell.cellIndex + 1 : 0
    if (column >= FIRST_HIGHLIGHTABLE_COLUMN) tableRef.current?.setAttribute('data-hover-col', String(column))
    else tableRef.current?.removeAttribute('data-hover-col')
  }

  function handlePointerLeave() {
    tableRef.current?.removeAttribute('data-hover-col')
  }

  if (isLoading) {
    return <p className="status-copy">Loading rankings...</p>
  }

  if (error) {
    return (
      <p className="status-copy error-copy">
        Couldn't load rankings ({error}). Make sure the backend is running at
        the configured API URL.
      </p>
    )
  }

  if (!data || data.rankings.length === 0) {
    return <p className="status-copy">No rankings available yet.</p>
  }

  return (
    <div>
      <div className="rankings-toolbar">
        <p className="meta-row">
          Season {data.season}, Week {data.week} &middot; updated{' '}
          {new Date(data.last_updated).toLocaleString()}
          {data.simulations != null && (
            <>
              {' '}
              &middot; projections from {data.simulations.toLocaleString()} simulated seasons
            </>
          )}
        </p>
        <div className="rankings-conference">
          <label htmlFor="rankings-conference-select">Conference</label>
          <select id="rankings-conference-select" value={conference} onChange={handleConferenceChange}>
            <option value={ALL_CONFERENCES}>All conferences ({data.rankings.length})</option>
            {conferenceGroups.map((group) =>
              // With only one group there's nothing to separate, so skip the group label.
              conferenceGroups.length === 1 ? (
                group.conferences.map(({ name, count }) => (
                  <option key={name} value={name}>
                    {name} ({count})
                  </option>
                ))
              ) : (
                <optgroup key={group.id} label={group.label}>
                  {group.conferences.map(({ name, count }) => (
                    <option key={name} value={name}>
                      {name} ({count})
                    </option>
                  ))}
                </optgroup>
              ),
            )}
          </select>
        </div>
      </div>
      <p className="meta-row filter-summary" role="status">
        {conference === ALL_CONFERENCES
          ? `Showing all ${rows.length} teams`
          : `Showing ${rows.length} ${conference} ${rows.length === 1 ? 'team' : 'teams'}. Ranks are among all teams.`}
      </p>
      {/* The table scrolls inside this box (both ways) so the header row and the
          Rank/Team columns can stay pinned while you move around a wide table. */}
      <div className="table-wrap rankings-scroll">
        <table
          ref={tableRef}
          className="rankings-table"
          onMouseOver={handlePointerOver}
          onMouseLeave={handlePointerLeave}
        >
          <thead>
            <tr>
              <th scope="col" className="col-rank">Rank</th>
              <th scope="col" className="col-team">Team</th>
              <th scope="col">Conference</th>
              <th scope="col">W-L</th>
              {SORT_COLUMNS.map(({ key, label, description }) => {
                const active = key === sortKey
                const ariaSort = active ? (sortDirection === 'desc' ? 'descending' : 'ascending') : 'none'
                return (
                  <th key={key} scope="col" aria-sort={ariaSort} className={active ? 'sorted-col' : undefined}>
                    <button
                      type="button"
                      className={`sort-button ${active ? 'active' : ''}`}
                      onClick={() => handleSort(key)}
                      title={description ? `${description} (click to sort)` : `Sort by ${label.toLowerCase()}`}
                    >
                      {label}
                      <span className="sort-arrow" aria-hidden="true">
                        {active ? (sortDirection === 'desc' ? '▼' : '▲') : '↕'}
                      </span>
                    </button>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((team) => (
              <tr key={team.team_id ?? team.rank}>
                <td className="col-rank">{team.displayRank ?? '—'}</td>
                {/* A row header, so assistive tech announces the team name with every cell. */}
                <th scope="row" className="col-team">
                  {team.team_id == null ? (
                    // Fallback rows (no database team behind them) have no detail page.
                    <span className="team-link">
                      <TeamLogo url={team.logo_url} />
                      <span>{team.team}</span>
                    </span>
                  ) : (
                    // `state` lets the team page's "Back to rankings" link restore this view.
                    <Link
                      to={`/team/${team.team_id}`}
                      state={{ rankingsSearch: location.search }}
                      className="team-link"
                    >
                      <TeamLogo url={team.logo_url} />
                      <span>{team.team}</span>
                    </Link>
                  )}
                </th>
                <td>{team.conference}</td>
                <td>{team.wins}-{team.losses}</td>
                {SORT_COLUMNS.map(({ key }) => (
                  <td key={key} className={key === sortKey ? 'sorted-col' : undefined}>
                    {CELL_FORMATTERS[key](team)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.simulations != null && (
        <p className="meta-row projection-note">
          Each simulated week re-fits the ratings with that week&apos;s simulated results before the
          next week is played. Proj. W-L, Bowl % and Undefeated % cover the regular season only; a
          conference championship game never counts toward them. Title Game % and Conf. Champ % come from
          simulating each conference's title game with its own tiebreakers. Playoff % is the chance of
          making the 12-team playoff field: the ACC, Big Ten, SEC and Big 12 champions get in, the
          best Group of 6 champion gets one more spot, Notre Dame gets in if it&apos;s a top-12 team,
          and the rest are picked at large by a neural network from each team&apos;s strength of
          schedule and record. The field is then seeded by overall rating and the bracket is
          played out: the CFP columns are the chance of a top-4 seed (a first-round bye), of playing
          in the quarterfinals, semifinals and national championship game, and of winning it. They
          are out of all simulated seasons, so a team that misses the field counts as a 0. Tiebreaker notes:
          the ACC's second tiebreaker uses non-public data, so ties it would decide are broken
          at random; the American and Mountain West's second tiebreaker is the CFB Rankings,
          which aren't included yet, so the higher-rated team by this model wins instead.
        </p>
      )}
    </div>
  )
}

export default RankingsTable
