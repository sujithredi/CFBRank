import { useState } from 'react'

// The two logo sizes the app uses. `inline` sits next to a team name in tables
// and lists; `tile` is the larger logo on the team directory's tiles.
const VARIANTS = {
  inline: { className: 'team-logo', size: 28 },
  tile: { className: 'team-tile-logo', size: 48 },
}

// Team logo with a fixed-size slot. When the logo is missing or fails to load it
// falls back to an empty placeholder of the same size, so team names stay aligned.
function TeamLogo({ url, variant = 'inline' }) {
  const [failed, setFailed] = useState(false)
  const { className, size } = VARIANTS[variant]

  if (!url || failed) {
    return <span className={`${className} placeholder`} aria-hidden="true" />
  }

  return (
    <img
      className={className}
      src={url}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

export default TeamLogo
