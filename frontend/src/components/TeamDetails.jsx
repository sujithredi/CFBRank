import { useEffect, useState } from 'react'
import { fetchTeamDetail } from '../api'

function TeamDetails({ teamId = 1 }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (!teamId) {
      setData(null)
      setError(null)
      setIsLoading(false)
      return undefined
    }

    let cancelled = false

    setIsLoading(true)
    setError(null)

    fetchTeamDetail(teamId)
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
  }, [teamId])

  if (isLoading) {
    return <p className="status-copy">Loading team profile...</p>
  }

  if (error) {
    return <p className="status-copy error-copy">Couldn't load team details ({error}).</p>
  }

  if (!data) {
    return <p className="status-copy">Select a team from the rankings to inspect its trend.</p>
  }

  const trendValues = data.rating_trend.map((point) => point.rating)
  const minRating = Math.min(...trendValues)
  const maxRating = Math.max(...trendValues)

  return (
    <div className="team-detail-card">
      <div className="team-header-row">
        <div>
          <p className="section-kicker muted">#{data.rank}</p>
          <h3>{data.team}</h3>
        </div>
        <span className="score-pill">{data.power_score.toFixed(1)}</span>
      </div>

      <div className="meta-list">
        <span>{data.conference}</span>
        <span>
          {data.wins}-{data.losses}
        </span>
      </div>

      <div className="detail-block">
        <h4>Recent results</h4>
        <ul className="results-list">
          {data.recent_results.map((result) => (
            <li key={`${result.week}-${result.opponent}`}>
              <span>Week {result.week}</span>
              <span>{result.opponent}</span>
              <strong>{result.result}</strong>
            </li>
          ))}
        </ul>
      </div>

      <div className="detail-block">
        <h4>Rating trend</h4>
        <div className="trend-chart" aria-label="team rating trend">
          {data.rating_trend.map((point) => {
            const height = maxRating === minRating ? 100 : ((point.rating - minRating) / (maxRating - minRating)) * 100
            return (
              <div key={point.week} className="trend-column" title={`${point.week}: ${point.rating}`}>
                <span className="trend-bar" style={{ height: `${Math.max(height, 12)}%` }} />
                <small>W{point.week}</small>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default TeamDetails
