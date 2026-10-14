import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { fetchRankings } from '../api'
import { formatPercent, formatProjectedRecord, formatRating } from '../format'
import { SORT_COLUMNS, sortRankings } from '../sortRankings'

// Team logo with a fixed-size slot
function TeamLogo({ url }) {
  const [failed, setFailed] = useState(false)

  if (!url || failed) {
    return <span className="team-logo placeholder" aria-hidden="true" />
  }

  return (
    <img
      className="team-logo"
      src={url}
      alt=""
      width="28"
      height="28"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

function RankingsTable() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  // The sort lives in the URL (?sort=offense_rating&dir=asc) rather than in
  // component state, so going to a team's page and pressing Back returns to the
  // same sorted view. Unknown/missing values fall back to Overall, best first.
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const requestedSort = searchParams.get('sort')
  const sortKey = SORT_COLUMNS.some(({ key }) => key === requestedSort) ? requestedSort : 'power_score'
  const sortDirection = searchParams.get('dir') === 'asc' ? 'asc' : 'desc'

  useEffect(() => {
    let cancelled = false

    setIsLoading(true)
    setError(null)

    fetchRankings()
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const rows = useMemo(
    () => (data ? sortRankings(data.rankings, sortKey, sortDirection) : []),
    [data, sortKey, sortDirection],
  )

  // Clicking the active column flips the direction; a new column starts best-first.
  function handleSort(key) {
    const direction = key === sortKey && sortDirection === 'desc' ? 'asc' : 'desc'
    // replace: re-sorting shouldn't add a history entry per click.
    setSearchParams({ sort: key, dir: direction }, { replace: true })
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
      <div className="table-wrap">
        <table className="rankings-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Team</th>
              <th>Conference</th>
              <th>W-L</th>
              {SORT_COLUMNS.map(({ key, label, description }) => {
                const active = key === sortKey
                const ariaSort = active ? (sortDirection === 'desc' ? 'descending' : 'ascending') : 'none'
                return (
                  <th key={key} aria-sort={ariaSort}>
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
                <td>{team.displayRank ?? '—'}</td>
                <td>
                  {team.team_id == null ? (
                    // Fallback rows (no database team behind them) have no detail page.
                    <span className="team-link">
                      <TeamLogo url={team.logo_url} />
                      <span>{team.team}</span>
                    </span>
                  ) : (
                    // `state` lets the team page's "Back to rankings" link restore this sort.
                    <Link
                      to={`/team/${team.team_id}`}
                      state={{ rankingsSearch: location.search }}
                      className="team-link"
                    >
                      <TeamLogo url={team.logo_url} />
                      <span>{team.team}</span>
                    </Link>
                  )}
                </td>
                <td>{team.conference}</td>
                <td>{team.wins}-{team.losses}</td>
                <td>{team.power_score.toFixed(1)}</td>
                <td>{formatRating(team.offense_rating)}</td>
                <td>{formatRating(team.defense_rating)}</td>
                <td>{formatProjectedRecord(team.projected_wins, team.projected_losses)}</td>
                <td>{formatPercent(team.bowl_pct)}</td>
                <td>{formatPercent(team.undefeated_pct)}</td>
                <td>{formatPercent(team.title_game_pct)}</td>
                <td>{formatPercent(team.conf_champ_pct)}</td>
                <td>{formatPercent(team.playoff_pct)}</td>
                <td>{formatPercent(team.cfp_bye_pct)}</td>
                <td>{formatPercent(team.cfp_quarterfinal_pct)}</td>
                <td>{formatPercent(team.cfp_semifinal_pct)}</td>
                <td>{formatPercent(team.cfp_final_pct)}</td>
                <td>{formatPercent(team.cfp_champion_pct)}</td>
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
