import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { fetchRankings } from '../api'
import TeamDetails from '../components/TeamDetails'

// /team/:teamId shows that team; /team (reached from the top bar) shows a
// picker so the page is useful without first going through the rankings.
function TeamDetailsPage() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  // Set by the rankings table when a team is clicked, so going back keeps the sort.
  const rankingsSearch = location.state?.rankingsSearch ?? ''
  const [teams, setTeams] = useState([])
  const [teamsError, setTeamsError] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetchRankings()
      .then((result) => {
        if (cancelled) return
        const selectable = result.rankings
          .filter((team) => team.team_id != null)
          .sort((a, b) => a.team.localeCompare(b.team))
        setTeams(selectable)
      })
      .catch(() => {
        if (!cancelled) setTeamsError(true)
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="panel team-page">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Team details</p>
          <h2>Performance profile</h2>
        </div>
        <Link to={{ pathname: '/', search: rankingsSearch }} className="back-link">
          ← Back to rankings
        </Link>
      </div>

      <label className="team-picker">
        <span>Team</span>
        <select
          value={teamId ?? ''}
          disabled={teams.length === 0}
          onChange={(event) => navigate(`/team/${event.target.value}`)}
        >
          <option value="" disabled>
            {teamsError ? "Couldn't load teams" : teams.length === 0 ? 'Loading teams...' : 'Select a team...'}
          </option>
          {teams.map((team) => (
            <option key={team.team_id} value={team.team_id}>
              {team.team}
            </option>
          ))}
        </select>
      </label>

      {teamId ? (
        <TeamDetails teamId={teamId} />
      ) : (
        <p className="status-copy">
          Choose a team above, or <Link to="/">browse the rankings</Link> and click one.
        </p>
      )}
    </section>
  )
}

export default TeamDetailsPage
