import { useEffect, useState } from 'react'
import { fetchRankings } from '../api'

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

function RankingsTable({ selectedTeamId, onSelectTeam }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

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
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Team</th>
              <th>Conference</th>
              <th>W-L</th>
              <th>Power Rating</th>
            </tr>
          </thead>
          <tbody>
            {data.rankings.map((team) => (
              <tr key={team.rank} className={selectedTeamId === team.team_id ? 'selected-row' : ''}>
                <td>{team.rank}</td>
                <td>
                  <button
                    type="button"
                    className={`team-button ${selectedTeamId === team.team_id ? 'active' : ''}`}
                    disabled={team.team_id == null}
                    onClick={() => onSelectTeam?.(team.team_id)}
                  >
                    <TeamLogo url={team.logo_url} />
                    <span>{team.team}</span>
                  </button>
                </td>
                <td>{team.conference}</td>
                <td>{team.wins}-{team.losses}</td>
                <td>{team.power_score.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default RankingsTable
