import { useEffect, useState } from 'react'
import { fetchWeeklyOdds } from '../api'

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

// US-03: this week's upcoming games with the model's projections next to the
// market spread/moneyline when a line has been ingested (scripts/ingest_lines.py).
// The backend simulates each game `num_simulations` (1,000) times: win % is the
// share of simulations each team won, and the points, margin and total are
// the averages over them.
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
    return <p className="status-copy">Loading weekly odds...</p>
  }

  if (error) {
    return (
      <p className="status-copy error-copy">
        Couldn't load weekly odds ({error}). Make sure the backend is running
        at the configured API URL.
      </p>
    )
  }

  if (!data || data.games.length === 0) {
    return <p className="status-copy">No upcoming games available yet.</p>
  }

  return (
    <div>
      <p className="meta-row">
        Season {data.season}, Week {data.week}
      </p>
      <p className="meta-row projection-note">
        Each game is simulated 10,000 times. Win % is the share of those simulations
        each team won; the points, margin and total are the averages across them.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Kickoff</th>
              <th>Home</th>
              <th>Away</th>
              <th title="Average points the home team scored across the simulations">Home Pts</th>
              <th title="Average points the away team scored across the simulations">Away Pts</th>
              <th title="Average home score minus away score across the simulations">Margin</th>
              <th title="Average combined score across the simulations">Total</th>
              <th>Home Win %</th>
              <th>Away Win %</th>
              <th>Spread</th>
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
                  <td>
                    <span className="team-link">
                      <TeamLogo url={game.home_logo_url} />
                      <span>{game.home_team}</span>
                    </span>
                  </td>
                  <td>
                    <span className="team-link">
                      <TeamLogo url={game.away_logo_url} />
                      <span>{game.away_team}</span>
                    </span>
                  </td>
                  <td>{game.model_home_points.toFixed(1)}</td>
                  <td>{game.model_away_points.toFixed(1)}</td>
                  <td>
                    <span className="pick-pill">{pick}</span>
                  </td>
                  <td>{game.model_total.toFixed(1)}</td>
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
    </div>
  )
}

export default WeeklyOdds
