import { useMemo, useState } from 'react'
import { fetchWeeklyOdds } from '../api'
import { useFetch } from '../useFetch'
import {
  GAME_FILTERS,
  countByFilter,
  filterGames,
  formatKickoffTime,
  groupGamesByDay,
} from '../weeklyOddsUtils'
import TeamLogo from './TeamLogo'

// US-03: this week's upcoming games with the model's projections next to the
// market spread/moneyline when a line has been ingested (scripts/ingest_lines.py).
// The backend simulates each game `num_simulations` (1,000) times: win % is the
// share of simulations each team won, and the points, margin and total are
// the averages over them.
function WeeklyOdds() {
  const { data, error, isLoading } = useFetch(fetchWeeklyOdds)
  const [filterId, setFilterId] = useState('all')

  const games = data?.games
  const counts = useMemo(() => countByFilter(games ?? []), [games])
  const days = useMemo(() => groupGamesByDay(filterGames(games ?? [], filterId)), [games, filterId])

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

  const activeLabel = GAME_FILTERS.find((filter) => filter.id === filterId).label.toLowerCase()

  return (
    <div>
      <p className="odds-disclaimer" role="note">
        <strong>For educational purposes only.</strong> These odds come from a statistical
        model and are shown to teach how projections compare with market lines. They are not
        betting advice, and nothing here is a recommendation to place a wager.
      </p>

      <div className="odds-toolbar">
        <p className="meta-row">
          Season {data.season}, Week {data.week}
        </p>
        <div className="filter-group" role="group" aria-label="Filter games by division">
          {GAME_FILTERS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={`filter-button ${filterId === id ? 'active' : ''}`}
              aria-pressed={filterId === id}
              onClick={() => setFilterId(id)}
            >
              {label} <span className="filter-count">{counts[id]}</span>
            </button>
          ))}
        </div>
      </div>

      {days.length === 0 && (
        <p className="status-copy">No {activeLabel} this week.</p>
      )}

      {days.map((day) => (
        <section key={day.key} className="odds-day" aria-labelledby={`odds-day-${day.key}`}>
          <h3 id={`odds-day-${day.key}`} className="odds-day-heading">
            {day.heading}
          </h3>
          <div className="table-wrap">
            <table className="odds-table">
              <thead>
                <tr>
                  <th>Matchup</th>
                  <th>Time</th>
                  <th title="Average points the home team scored across the simulations">Home Pts</th>
                  <th title="Average points the away team scored across the simulations">Away Pts</th>
                  <th title="Average home score minus away score across the simulations">Margin</th>
                  <th title="Average combined score across the simulations">Total</th>
                  <th>Home Win %</th>
                  <th>Away Win %</th>
                  <th>Spread</th>
                  <th>Home ML</th>
                  <th>Away ML</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody>
                {day.games.map(({ game, kickoff }) => {
                  const margin = game.model_predicted_margin
                  const pick =
                    margin > 0
                      ? `${game.home_team} by ${margin.toFixed(1)}`
                      : margin < 0
                        ? `${game.away_team} by ${Math.abs(margin).toFixed(1)}`
                        : "Pick'em"

                  return (
                    <tr key={game.game_id}>
                      <td>
                        <span className="matchup">
                          <span className="team-link">
                            <TeamLogo url={game.away_logo_url} />
                            <span>{game.away_team}</span>
                          </span>
                          <span
                            className="matchup-sep"
                            title={game.neutral_site ? 'Neutral site' : 'Away team at home team'}
                          >
                            {game.neutral_site ? 'v' : '@'}
                          </span>
                          <span className="team-link">
                            <TeamLogo url={game.home_logo_url} />
                            <span>{game.home_team}</span>
                          </span>
                        </span>
                      </td>
                      <td className="odds-time">{formatKickoffTime(kickoff)}</td>
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
                      <td className="odds-location">{game.venue ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <p className="meta-row projection-note">
        Each game is simulated {data.num_simulations.toLocaleString()} times. Win % is the share
        of those simulations each team won; the points, margin and total are the averages across
        them. Times are shown in your local timezone.
      </p>
    </div>
  )
}

export default WeeklyOdds
