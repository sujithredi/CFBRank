import WeeklyOdds from '../components/WeeklyOdds'

function WeeklyOddsPage() {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Game projections</p>
          <h2>Upcoming games</h2>
        </div>
      </div>
      <WeeklyOdds />
    </section>
  )
}

export default WeeklyOddsPage
