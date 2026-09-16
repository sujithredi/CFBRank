import RankingsTable from './components/RankingsTable'

function App() {
  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>CFB Rank</h1>
      <p>FBS power rankings, computed from live game data.</p>
      <RankingsTable />
    </div>
  )
}

export default App
