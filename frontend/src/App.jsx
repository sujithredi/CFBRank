import { useState } from 'react'
import RankingsTable from './components/RankingsTable'
import TeamDetails from './components/TeamDetails'
import WeeklyOdds from './components/WeeklyOdds'
import './App.css'

function App() {
  const [selectedTeamId, setSelectedTeamId] = useState(1)

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">College football power rankings</p>
          <h1>CFB Rank</h1>
        </div>
        <div className="header-badge">Live model</div>
      </header>

      <main className="main-grid">
        <section className="panel rankings-panel">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Power rankings</p>
              <h2>FBS team strength</h2>
            </div>
          </div>
          <RankingsTable
            selectedTeamId={selectedTeamId}
            onSelectTeam={setSelectedTeamId}
          />
        </section>

        <aside className="panel detail-panel">
          <div className="section-heading compact">
            <div>
              <p className="section-kicker">Team spotlight</p>
              <h2>Performance profile</h2>
            </div>
          </div>
          <TeamDetails teamId={selectedTeamId} />
        </aside>
      </main>

      <section className="panel odds-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Game projections</p>
            <h2>Upcoming games</h2>
          </div>
        </div>
        <WeeklyOdds />
      </section>
    </div>
  )
}

export default App
