// Base URL for the FastAPI backend. Override by setting VITE_API_BASE_URL
// in a frontend/.env file (see .env.example) -- useful once the backend is
// deployed somewhere other than http://127.0.0.1:8000.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

/**
 * GET /api/rankings
 * Returns { season, week, last_updated, rankings: [...] }
 */
export async function fetchRankings() {
  const response = await fetch(`${API_BASE_URL}/api/rankings`)

  if (!response.ok) {
    throw new Error(`Rankings request failed with status ${response.status}`)
  }

  return response.json()
}

/**
 * GET /api/teams/{team_id}
 * Returns team detail metadata such as the recent results and rating trend.
 */
export async function fetchTeamDetail(teamId) {
  const response = await fetch(`${API_BASE_URL}/api/teams/${teamId}`)

  if (!response.ok) {
    throw new Error(`Team detail request failed with status ${response.status}`)
  }

  return response.json()
}

/**
 * GET /api/odds/weekly
 * Returns { season, week, games: [...] }, one entry per upcoming game with
 * the model's predicted margin/win probability and (when ingested) the
 * market spread/moneyline (US-03).
 */
export async function fetchWeeklyOdds() {
  const response = await fetch(`${API_BASE_URL}/api/odds/weekly`)

  if (!response.ok) {
    throw new Error(`Weekly odds request failed with status ${response.status}`)
  }

  return response.json()
}

/**
 * POST /api/matchup/simulate
 * Simulates games between two teams (by teams.id) and returns both teams'
 * expected points, every simulated game, and a summary across them. Each call
 * is a fresh set of random games.
 *
 * options.location: 'neutral' (default), 'team_a_home' or 'team_b_home'.
 * options.numGames: how many games to simulate (the backend allows 1-1000).
 */
export async function simulateMatchup(teamAId, teamBId, { location = 'neutral', numGames = 1 } = {}) {
  const response = await fetch(`${API_BASE_URL}/api/matchup/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      team_a_id: teamAId,
      team_b_id: teamBId,
      location,
      num_games: numGames,
    }),
  })

  if (!response.ok) {
    // FastAPI sends { detail: "..." } for errors we raise on purpose; show that.
    let detail = null
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Body wasn't JSON -- fall through to the generic message.
    }
    throw new Error(detail ?? `Matchup request failed with status ${response.status}`)
  }

  return response.json()
}
