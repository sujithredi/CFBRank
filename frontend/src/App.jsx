import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'
import NavBar from './components/NavBar'
import MatchupPage from './pages/MatchupPage'
import MethodologyPage from './pages/MethodologyPage'
import RankingsPage from './pages/RankingsPage'
import TeamDetailsPage from './pages/TeamDetailsPage'
import WeeklyOddsPage from './pages/WeeklyOddsPage'
import './App.css'

// A new page should start at the top -- otherwise clicking a team near the
// bottom of the long rankings table would open its page scrolled halfway down.
function ScrollToTop() {
  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return null
}

function App() {
  return (
    <div className="app-shell">
      <ScrollToTop />
      <NavBar />

      <main>
        <Routes>
          <Route path="/" element={<RankingsPage />} />
          <Route path="/team" element={<TeamDetailsPage />} />
          <Route path="/team/:teamId" element={<TeamDetailsPage />} />
          <Route path="/odds" element={<WeeklyOddsPage />} />
          <Route path="/matchup" element={<MatchupPage />} />
          <Route path="/methodology" element={<MethodologyPage />} />
          {/* Unknown URL -> back to the rankings, the home page. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
