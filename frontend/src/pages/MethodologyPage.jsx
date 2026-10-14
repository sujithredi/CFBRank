import { useEffect, useState } from 'react'
import { Eq, T } from '../components/methodology/Tex'
import { SECTIONS } from '../components/methodology/sectionList'
import '../components/methodology/methodology.css'

// The six stages of a run, in order. Steps 2-3 repeat for every remaining week,
// and 2-6 for every one of the N replicates.
const PIPELINE = [
  { title: 'Fit ratings', text: 'Least squares on the games played so far' },
  { title: 'Simulate a week', text: 'Scores drawn by a quantile map of a normal' },
  { title: 'Refit', text: 'Update the sufficient statistic, recompute ratings' },
  { title: 'Title games', text: 'Tiebreakers choose two teams; one game decides' },
  { title: 'Playoff field', text: 'Champions, a Group of 6 bid, Notre Dame, the rest by network' },
  { title: 'Playoff games', text: 'Seed by rating, then play the 12-team bracket' },
]

// How far a section's top edge may sit below the top of the window before it
// counts as the one being read (clears the sticky top bar).
const READING_LINE = 130

function scrollToSection(id) {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(id)?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
}

function MethodologyPage() {
  const [activeId, setActiveId] = useState(SECTIONS[0].id)

  // Highlight the contents entry for the section being read: the last one whose
  // top has passed the reading line.
  useEffect(() => {
    let frame = 0

    const update = () => {
      frame = 0
      let current = SECTIONS[0].id
      for (const { id } of SECTIONS) {
        const element = document.getElementById(id)
        if (element && element.getBoundingClientRect().top <= READING_LINE) current = id
      }
      setActiveId(current)
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }

    schedule()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    return () => {
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <div className="panel method">
      <header className="method-header">
        <p className="section-kicker">Methodology</p>
        <h2>How the ratings, simulations and playoff odds are computed</h2>
        <p className="method-abstract">
          Team strength is a least-squares fit of points scored on offense, defense and venue. A scoring model turns two
          ratings into a simulated game; replaying the rest of the schedule thousands of times, with the ratings refit
          after every simulated week, gives each team a distribution over records, conference titles, playoff berths and national titles.
          This page states each model, constant and estimator the site uses, in the notation of the code, and names the
          file that implements it.
        </p>
        <Eq>{String.raw`p_{g,i} \;=\; \bar\mu \;+\; h\,\ell_{g,i} \;+\; o_i \;-\; d_j \;+\; \varepsilon_{g,i}`}</Eq>
        <p className="method-abstract">
          Every number on the site descends from this one equation: {T`p_{g,i}`} are the points team {T`i`} scores
          against team {T`j`} in game {T`g`}, {T`o`} and {T`d`} are the offense and defense ratings, and {T`h\,\ell`} the
          venue.
        </p>

        <ol className="pipeline" aria-label="Stages of a simulation run">
          {PIPELINE.map(({ title, text }, index) => (
            <li key={title}>
              <span className="step-n">{index + 1}</span>
              <strong>{title}</strong>
              <span className="step-text">{text}</span>
            </li>
          ))}
        </ol>
        <p className="pipeline-note">
          Step 1 happens once. Steps 2&ndash;3 repeat for each remaining week of the season, and steps 2&ndash;6 for each of
          the {T`N=10{,}000`} simulated seasons.
        </p>
      </header>

      <div className="method-body">
        <nav className="method-toc" aria-label="Sections of this page">
          <ol>
            {SECTIONS.map(({ id, title }, index) => (
              <li key={id}>
                <button
                  type="button"
                  className={id === activeId ? 'toc-link active' : 'toc-link'}
                  aria-current={id === activeId ? 'true' : undefined}
                  onClick={() => scrollToSection(id)}
                >
                  <span className="toc-num">{index + 1}</span>
                  {title}
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <article className="method-article">
          {SECTIONS.map(({ id, title, Body }, index) => (
            <section key={id} id={id} className="method-section">
              <h2>
                <span className="sec-num">{index + 1}</span>
                {title}
              </h2>
              <Body />
            </section>
          ))}
        </article>
      </div>
    </div>
  )
}

export default MethodologyPage
