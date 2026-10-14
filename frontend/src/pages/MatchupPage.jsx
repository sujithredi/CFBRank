import MatchupSimulator from '../components/MatchupSimulator'

function MatchupPage() {
  return (
    <section className="panel team-page">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Team matchup</p>
          <h2>Simulate a game</h2>
        </div>
      </div>
      <MatchupSimulator />
    </section>
  )
}

export default MatchupPage
