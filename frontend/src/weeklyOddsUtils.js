// Helpers for the weekly odds page: kickoff times, the All / FBS / FCS filter, and
// grouping games by the day they are played.

export const GAME_FILTERS = [
  { id: 'all', label: 'All games' },
  { id: 'fbs', label: 'FBS games' },
  { id: 'fcs', label: 'FCS games' },
]

// The API sends kickoff times as UTC without a timezone suffix (e.g. "2026-10-31T15:00:00"),
// which `new Date()` would read as the viewer's local time and shift every game by their
// UTC offset. Add the "Z" so the browser converts from UTC to the viewer's timezone.
export function parseKickoff(startDate) {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(startDate)
  return new Date(hasTimezone ? startDate : `${startDate}Z`)
}

// "11:00 AM" -- just the time, because the day is shown in the heading above the games.
export function formatKickoffTime(date) {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

// "Saturday, October 31, 2026"
export function formatDayHeading(date) {
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

// A game belongs to a filter when either team is in that classification, so an FBS team
// playing an FCS team appears under both FBS games and FCS games.
export function matchesFilter(game, filterId) {
  if (filterId === 'all') return true
  return game.home_classification === filterId || game.away_classification === filterId
}

export function filterGames(games, filterId) {
  return games.filter((game) => matchesFilter(game, filterId))
}

// How many games each filter would show, for the counts on the filter buttons.
export function countByFilter(games) {
  return Object.fromEntries(GAME_FILTERS.map(({ id }) => [id, filterGames(games, id).length]))
}

// Groups games by the viewer's local calendar day, earliest day first and earliest kickoff
// first within a day. Returns [{ key, heading, games: [{ game, kickoff }] }].
export function groupGamesByDay(games) {
  const dated = games
    .map((game) => ({ game, kickoff: parseKickoff(game.start_date) }))
    .sort((a, b) => a.kickoff - b.kickoff)

  const days = []
  for (const entry of dated) {
    const { kickoff } = entry
    const key = `${kickoff.getFullYear()}-${kickoff.getMonth() + 1}-${kickoff.getDate()}`
    let day = days[days.length - 1]
    if (!day || day.key !== key) {
      day = { key, heading: formatDayHeading(kickoff), games: [] }
      days.push(day)
    }
    day.games.push(entry)
  }
  return days
}
