import RankingsTable from '../components/RankingsTable'

// Home page. Clicking a team in the table opens its Team Details page.
function RankingsPage() {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Power rankings</p>
          <h2>Team strength</h2>
        </div>
        <p className="section-hint">Click a team to see its details</p>
      </div>
      <RankingsTable />
    </section>
  )
}

export default RankingsPage
