import { useEffect, useState } from 'react'
import { fetchRankings } from '../api'

// US-01: ranked list of all FBS teams with a power score, conference, and
// record. No styling/logos yet -- plain markup so the data flow can be
// verified first (per Milestone 0 scope).
function RankingsTable() {
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
    return <p>Loading rankings...</p>
  }

  if (error) {
    return (
      <p>
        Couldn't load rankings ({error}). Make sure the backend is running at
        the configured API URL.
      </p>
    )
  }

  if (!data || data.rankings.length === 0) {
    return <p>No rankings available yet.</p>
  }

  return (
    <div>
      <p>
        Season {data.season}, Week {data.week} &middot; last updated{' '}
        {new Date(data.last_updated).toLocaleString()}
      </p>
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Team</th>
            <th>Conference</th>
            <th>W</th>
            <th>L</th>
            <th>Power Score</th>
          </tr>
        </thead>
        <tbody>
          {data.rankings.map((team) => (
            <tr key={team.rank}>
              <td>{team.rank}</td>
              <td>{team.team}</td>
              <td>{team.conference}</td>
              <td>{team.wins}</td>
              <td>{team.losses}</td>
              <td>{team.power_score}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default RankingsTable
