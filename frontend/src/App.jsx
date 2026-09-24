import RankingsTable from './components/RankingsTable'
import WeeklyOdds from './components/WeeklyOdds'

function App() {
  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>CFB Rank</h1>
      <p>CBF power rankings.</p>
      <RankingsTable />

      <h2>Upcoming Games</h2>
      <p>Model-predicted margin and win probability vs. the market line.</p>
      <WeeklyOdds />
    </div>
  )
}

export default App
