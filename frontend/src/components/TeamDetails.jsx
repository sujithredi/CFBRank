import { useCallback } from 'react'
import { fetchTeamDetail } from '../api'
import { formatRating } from '../format'
import { useFetch } from '../useFetch'
import TeamLogo from './TeamLogo'

// Upcoming games only show the date, e.g. "10/24", in the viewer's timezone.
function formatGameDate(isoDate) {
  if (!isoDate) return 'TBD'
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) return 'TBD'
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function ScheduleRow({ game }) {
  return (
    <li className="schedule-row">
      <span className="schedule-location">{game.location === 'away' ? '@' : 'vs'}</span>
      <TeamLogo url={game.opponent_logo_url} />
      <span className="schedule-opponent">{game.opponent}</span>
      {game.completed ? (
        <>
          <span className={`schedule-outcome outcome-${game.outcome}`}>{game.outcome}</span>
          <span className="schedule-score">{game.score}</span>
        </>
      ) : (
        <span className="schedule-date">{formatGameDate(game.start_date)}</span>
      )}
    </li>
  )
}

function TeamDetails({ teamId = null }) {
  // A new function per team id, so useFetch reloads when the id changes. No id, no request.
  const loadTeam = useCallback(() => fetchTeamDetail(teamId), [teamId])
  const { data, error, isLoading } = useFetch(teamId ? loadTeam : null)

  if (isLoading) {
    return <p className="status-copy">Loading team profile...</p>
  }

  if (error) {
    return <p className="status-copy error-copy">Couldn't load team details ({error}).</p>
  }

  if (!data) {
    return <p className="status-copy">Select a team from the rankings to inspect its trend.</p>
  }

  // Older backends don't send a schedule; treat that as empty rather than crashing.
  const schedule = data.schedule ?? []
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
        <h4>Rating breakdown</h4>
        <div className="split-ratings">
          <div className="split-rating">
            <small>Offense</small>
            <strong>{formatRating(data.offense_rating)}</strong>
          </div>
          <div className="split-rating">
            <small>Defense</small>
            <strong>{formatRating(data.defense_rating)}</strong>
          </div>
        </div>
      </div>

      <div className="detail-block">
        <h4>Schedule</h4>
        {schedule.length === 0 ? (
          <p className="status-copy">No games on the schedule yet.</p>
        ) : (
          <ul className="schedule-list">
            {schedule.map((game) => (
              <ScheduleRow key={`${game.week}-${game.opponent}`} game={game} />
            ))}
          </ul>
        )}
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
