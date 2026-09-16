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
