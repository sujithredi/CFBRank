import { useEffect, useState } from 'react'
import { fetchWeeklyOdds } from '../api'

// US-03: this week's upcoming games with the model's predicted margin and
// win probability, next to the market spread/moneyline when a line has
// been ingested (scripts/ingest_lines.py)
function WeeklyOdds() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    setIsLoading(true)
    setError(null)

    fetchWeeklyOdds()
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
    return <p>Loading weekly odds...</p>
  }

  if (error) {
    return (
      <p>
        Couldn't load weekly odds ({error}). Make sure the backend is running
        at the configured API URL.
      </p>
    )
  }

  if (!data || data.games.length === 0) {
    return <p>No upcoming games available yet.</p>
  }

  return (
    <div>
      <p>
        Season {data.season}, Week {data.week}
      </p>
      <table>
        <thead>
          <tr>
            <th>Kickoff</th>
            <th>Away</th>
            <th>Home</th>
            <th>Margin</th>
            <th>Home Win %</th>
            <th>Away Win %</th>
            <th>Market Spread</th>
            <th>Home ML</th>
            <th>Away ML</th>
          </tr>
        </thead>
        <tbody>
          {data.games.map((game) => {
            const margin = game.model_predicted_margin
            const pick =
              margin > 0
                ? `${game.home_team} by ${margin.toFixed(1)}`
                : margin < 0
                  ? `${game.away_team} by ${Math.abs(margin).toFixed(1)}`
                  : "Pick'em"

            return (
              <tr key={game.game_id}>
                <td>{new Date(game.start_date).toLocaleString()}</td>
                <td>{game.away_team}</td>
                <td>{game.home_team}</td>
                <td>{game.model_predicted_margin}</td>
                <td>{(game.model_home_win_prob * 100).toFixed(1)}%</td>
                <td>{((1 - game.model_home_win_prob) * 100).toFixed(1)}%</td>
                <td>{game.market_spread ?? '—'}</td>
                <td>{game.market_home_moneyline ?? '—'}</td>
                <td>{game.market_away_moneyline ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default WeeklyOdds
