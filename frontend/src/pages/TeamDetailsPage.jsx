import { useMemo, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { fetchRankings } from '../api'
import TeamDetails from '../components/TeamDetails'
import TeamLogo from '../components/TeamLogo'
import { useFetch } from '../useFetch'

// FBS conferences first, then FCS, each alphabetical. Anything without a known
// classification (e.g. teams with no conference) goes last.
const CLASSIFICATION_ORDER = { fbs: 0, fcs: 1 }

function classificationRank(classification) {
  return CLASSIFICATION_ORDER[classification?.toLowerCase()] ?? 2
}

function compareGroups(a, b) {
  return (
    classificationRank(a.classification) - classificationRank(b.classification) ||
    a.conference.localeCompare(b.conference)
  )
}

// /team/:teamId shows that team; /team (reached from the top bar) shows every
// team grouped by conference, each one a single link to its page.
function TeamDetailsPage() {
  const { teamId } = useParams()
  const location = useLocation()
  // Set by the rankings table when a team is clicked, so going back keeps the sort.
  const rankingsSearch = location.state?.rankingsSearch ?? ''
  const [conferenceFilter, setConferenceFilter] = useState('all')

  // The team list is only needed on the /team overview, so no request is made on a team's page.
  const { data: rankings, error: teamsFetchError } = useFetch(teamId ? null : fetchRankings)
  const teams = useMemo(
    () => (rankings ? rankings.rankings.filter((team) => team.team_id != null) : []),
    [rankings],
  )
  const teamsError = teamsFetchError != null

  // [{ conference, classification, teams: [...] }, ...] in display order, teams alphabetized.
  const groups = useMemo(() => {
    const byConference = new Map()
    for (const team of teams) {
      if (!byConference.has(team.conference)) {
        byConference.set(team.conference, {
          conference: team.conference,
          classification: team.conference_classification,
          teams: [],
        })
      }
      byConference.get(team.conference).teams.push(team)
    }
    return [...byConference.values()]
      .map((group) => ({ ...group, teams: group.teams.sort((a, b) => a.team.localeCompare(b.team)) }))
      .sort(compareGroups)
  }, [teams])

  if (teamId) {
    return (
      <section className="panel team-page">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Team details</p>
            <h2>Performance profile</h2>
          </div>
          <div className="team-page-links">
            <Link to="/team" className="back-link">
              ← All teams
            </Link>
            <Link to={{ pathname: '/', search: rankingsSearch }} className="back-link">
              Back to rankings
            </Link>
          </div>
        </div>

        <TeamDetails teamId={teamId} />
      </section>
    )
  }

  // If the chosen conference disappears (e.g. after a reload), show everything.
  const isLoading = teams.length === 0 && !teamsError
  const activeFilter = groups.some((group) => group.conference === conferenceFilter) ? conferenceFilter : 'all'
  const visibleGroups = activeFilter === 'all' ? groups : groups.filter((group) => group.conference === activeFilter)

  return (
    <section className="panel team-directory">
      <div className="team-directory-header">
        <h2>College Football Teams</h2>
        <select
          className="conference-filter"
          aria-label="Filter by conference"
          value={activeFilter}
          disabled={groups.length === 0}
          onChange={(event) => setConferenceFilter(event.target.value)}
        >
          <option value="all">All Conferences</option>
          {groups.map((group) => (
            <option key={group.conference} value={group.conference}>
              {group.conference}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="status-copy">Loading teams...</p>}
      {teamsError && <p className="status-copy error-copy">Couldn't load teams.</p>}

      <div className="conference-grid">
        {visibleGroups.map((group) => (
          <section key={group.conference} className="conference-section">
            <h3>{group.conference}</h3>
            <ul className="team-tile-list">
              {group.teams.map((team) => (
                <li key={team.team_id}>
                  <Link to={`/team/${team.team_id}`} className="team-tile">
                    <TeamLogo url={team.logo_url} variant="tile" />
                    <span className="team-tile-name">{team.team}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </section>
  )
}

export default TeamDetailsPage
