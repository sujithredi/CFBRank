// Offense/defense ratings are null for snapshots computed before the split
// existed (and for the backend's hardcoded fallback rows), so show a dash
// rather than crashing on null.toFixed().
export function formatRating(value, digits = 1) {
  return value == null ? '—' : value.toFixed(digits)
}

// Season-projection percentages (0-100). Null when the simulation hasn't run for
// this snapshot, and for Bowl % on FCS teams. A real-but-tiny or near-certain
// chance is shown as <0.1% / >99.9% so it never rounds to a flat 0% or 100%
// that would read as "impossible" or "guaranteed".
export function formatPercent(value) {
  if (value == null) return '—'
  if (value > 0 && value < 0.1) return '<0.1%'
  if (value < 100 && value > 99.9) return '>99.9%'
  return `${value.toFixed(1)}%`
}

// Average simulated final record, e.g. "10.4-1.6". Null until the simulation has run.
export function formatProjectedRecord(wins, losses) {
  return wins == null || losses == null ? '—' : `${wins.toFixed(1)}-${losses.toFixed(1)}`
}
