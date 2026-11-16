export const ALL_CONFERENCES = 'all'

const GROUPS = [
  { id: 'fbs', label: 'FBS' },
  { id: 'fcs', label: 'FCS' },
  { id: 'other', label: 'Other' },
]

/**
 * Build the filter's options from the rankings themselves, so a conference only
 * appears if it has at least one team in the current snapshot.
 *
 * Returns [{ id, label, conferences: [{ name, count }] }], FBS first, then FCS,
 * then anything without a classification. Conferences are alphabetical within a
 * group; empty groups are left out.
 */
export function listConferences(rankings) {
  const byGroup = new Map(GROUPS.map(({ id }) => [id, new Map()]))

  for (const team of rankings) {
    const groupId = byGroup.has(team.conference_classification) ? team.conference_classification : 'other'
    const counts = byGroup.get(groupId)
    counts.set(team.conference, (counts.get(team.conference) ?? 0) + 1)
  }

  return GROUPS.map(({ id, label }) => ({
    id,
    label,
    conferences: [...byGroup.get(id)]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => a.name.localeCompare(b.name)),
  })).filter((group) => group.conferences.length > 0)
}

/** True if `name` is a conference present in `groups` (the output of listConferences). */
export function hasConference(groups, name) {
  return groups.some((group) => group.conferences.some((conference) => conference.name === name))
}

/** Keep only the teams in `conference` (or everyone when it is ALL_CONFERENCES). */
export function filterByConference(rows, conference) {
  return conference === ALL_CONFERENCES ? rows : rows.filter((team) => team.conference === conference)
}