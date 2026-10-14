import { Link, NavLink } from 'react-router'

const NAV_LINKS = [
  { to: '/', label: 'Rankings', end: true },
  { to: '/team', label: 'Team Details' },
  { to: '/odds', label: 'Weekly Odds' },
  { to: '/matchup', label: 'Matchup' },
  { to: '/methodology', label: 'Methodology' },
]

// Top bar shown on every page. NavLink marks the current page as active; the
// Team Details link also stays active on /team/:teamId.
function NavBar() {
  return (
    <header className="top-bar">
      <Link to="/" className="brand">
        CFB Rank
      </Link>
      <nav aria-label="Main">
        {NAV_LINKS.map(({ to, label, end }) => (
          <NavLink key={to} to={to} end={end} className="nav-link">
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}

export default NavBar
