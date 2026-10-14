// Plain-SVG figures for the methodology page, drawn straight from the formulas
// (no charting library). Colors: blue = the old odds-page formula / the baseline,
// amber = the score simulator, teal = a below-average offense.

const W = 560
const H = 330
const PAD = { left: 58, right: 18, top: 14, bottom: 46 }

const BLUE = '#1d4ed8'
const AMBER = '#b45309'
const TEAL = '#0f766e'

// Standard normal CDF via the Abramowitz & Stegun 7.1.26 erf approximation
// (absolute error below 1.5e-7, far below what a plot can show).
function normalCdf(z) {
  const x = Math.abs(z) / Math.SQRT2
  const t = 1 / (1 + 0.3275911 * x)
  const poly = ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t
  const erf = 1 - poly * Math.exp(-x * x)
  return 0.5 * (1 + (z >= 0 ? erf : -erf))
}

const logistic = (x) => 1 / (1 + Math.exp(-x))

function scales(xMin, xMax, yMin, yMax) {
  const x = (v) => PAD.left + ((v - xMin) / (xMax - xMin)) * (W - PAD.left - PAD.right)
  const y = (v) => H - PAD.bottom - ((v - yMin) / (yMax - yMin)) * (H - PAD.top - PAD.bottom)
  return { x, y }
}

function path(points, { x, y }) {
  return points.map(([px, py], i) => `${i === 0 ? 'M' : 'L'}${x(px).toFixed(1)},${y(py).toFixed(1)}`).join(' ')
}

function Axes({ sx, xTicks, yTicks, xLabel, yLabel, yFormat = (v) => v }) {
  const { x, y } = sx
  const left = PAD.left
  const right = W - PAD.right
  const top = PAD.top
  const bottom = H - PAD.bottom
  return (
    <g className="fig-axes">
      {yTicks.map((v) => (
        <g key={`y${v}`}>
          <line className="fig-grid" x1={left} x2={right} y1={y(v)} y2={y(v)} />
          <text x={left - 8} y={y(v)} textAnchor="end" dominantBaseline="middle">
            {yFormat(v)}
          </text>
        </g>
      ))}
      {xTicks.map((v) => (
        <g key={`x${v}`}>
          <line className="fig-tick" x1={x(v)} x2={x(v)} y1={bottom} y2={bottom + 5} />
          <text x={x(v)} y={bottom + 20} textAnchor="middle">
            {v}
          </text>
        </g>
      ))}
      <line className="fig-frame" x1={left} x2={right} y1={bottom} y2={bottom} />
      <line className="fig-frame" x1={left} x2={left} y1={top} y2={bottom} />
      <text className="fig-label" x={(left + right) / 2} y={H - 6} textAnchor="middle">
        {xLabel}
      </text>
      <text
        className="fig-label"
        transform={`translate(14 ${(top + bottom) / 2}) rotate(-90)`}
        textAnchor="middle"
      >
        {yLabel}
      </text>
    </g>
  )
}

// Figure 2 -- the old odds-page logistic against what the score simulator actually does.
// The dots are a Monte Carlo of simulate_game at a neutral site: team A has offense and
// defense ratings of m/2 each (so a rating gap of m) against an average team B, 30,000
// games per gap. The curve through them is Phi(m / s) with s fitted by least squares.
const SIMULATOR_POINTS = [
  [0, 0.497], [2, 0.541], [4, 0.585], [6, 0.62], [8, 0.658], [10, 0.698], [12, 0.731],
  [14, 0.767], [16, 0.798], [18, 0.824], [20, 0.846], [24, 0.893], [28, 0.924],
]
const SIMULATOR_SD = 19.35

export function WinProbabilityFigure() {
  const sx = scales(0, 28, 0.5, 1)
  const grid = Array.from({ length: 57 }, (_, i) => i * 0.5)
  const odds = grid.map((m) => [m, logistic(0.1533 * m + 0.0533)])
  const normal = grid.map((m) => [m, normalCdf(m / SIMULATOR_SD)])
  const { x, y } = sx
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="fig-win-title fig-win-desc">
      <title id="fig-win-title">Win probability against rating gap: old odds formula versus simulator</title>
      <desc id="fig-win-desc">
        The old odds-page logistic curve rises faster than the simulator&apos;s win probability. At a 14 point rating
        gap the logistic gives 90 percent and the simulator 77 percent.
      </desc>
      <Axes
        sx={sx}
        xTicks={[0, 4, 8, 12, 16, 20, 24, 28]}
        yTicks={[0.5, 0.6, 0.7, 0.8, 0.9, 1]}
        xLabel={
          <>
            Rating gap <tspan fontStyle="italic">r</tspan>
            <tspan dy="3" fontSize="9">A</tspan>
            <tspan dy="-3"> − </tspan>
            <tspan fontStyle="italic">r</tspan>
            <tspan dy="3" fontSize="9">B</tspan>
            <tspan dy="-3"> at a neutral site (points)</tspan>
          </>
        }
        yLabel="P(A wins)"
        yFormat={(v) => v.toFixed(1)}
      />
      <path d={path(odds, sx)} fill="none" stroke={BLUE} strokeWidth="2.2" />
      <path d={path(normal, sx)} fill="none" stroke={AMBER} strokeWidth="1.6" strokeDasharray="5 4" />
      {SIMULATOR_POINTS.map(([m, p]) => (
        <circle key={m} cx={x(m)} cy={y(p)} r="3.4" fill="#fff" stroke={AMBER} strokeWidth="1.8" />
      ))}
      <g className="fig-legend">
        <line x1={x(13.5)} x2={x(16)} y1={y(0.625)} y2={y(0.625)} stroke={BLUE} strokeWidth="2.2" />
        <text x={x(16.4)} y={y(0.625)} dominantBaseline="middle">
          Old odds: Λ(0.1533 m + 0.0533)
        </text>
        <circle cx={x(14.75)} cy={y(0.58)} r="3.4" fill="#fff" stroke={AMBER} strokeWidth="1.8" />
        <text x={x(16.4)} y={y(0.58)} dominantBaseline="middle">
          Simulator, Monte Carlo
        </text>
        <line x1={x(13.5)} x2={x(16)} y1={y(0.54)} y2={y(0.54)} stroke={AMBER} strokeWidth="1.6" strokeDasharray="5 4" />
        <text x={x(16.4)} y={y(0.54)} dominantBaseline="middle">
          Φ(m / 19.35), least-squares fit
        </text>
      </g>
    </svg>
  )
}

// Figure 1 -- Proposition 2: the density of u = Phi(Z + delta) is exp(delta * z - delta^2 / 2)
// at x = Phi(z). Drawn by walking z and plotting (Phi(z), density), so no inverse CDF is needed.
export function TiltDensityFigure() {
  const sx = scales(0, 1, 0, 4)
  const zs = Array.from({ length: 161 }, (_, i) => -4 + i * 0.05)
  const curve = (delta) =>
    zs
      .map((z) => [normalCdf(z), Math.exp(delta * z - (delta * delta) / 2)])
      .filter(([, density]) => density <= 4.05)
  const { x, y } = sx
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="fig-tilt-title fig-tilt-desc">
      <title id="fig-tilt-title">Density of the score percentile for three values of delta</title>
      <desc id="fig-tilt-desc">
        With delta equal to zero the percentile is uniform, a flat line at one. Positive delta tilts the density
        toward high percentiles, negative delta toward low ones, exponentially in the probit of the percentile.
      </desc>
      <Axes
        sx={sx}
        xTicks={[0, 0.25, 0.5, 0.75, 1]}
        yTicks={[0, 1, 2, 3, 4]}
        xLabel="Percentile u of the historical score table"
        yLabel="Density of u"
      />
      <path d={path(curve(-1), sx)} fill="none" stroke={TEAL} strokeWidth="2.2" />
      <path d={path(curve(0), sx)} fill="none" stroke="#475569" strokeWidth="2.2" />
      <path d={path(curve(1), sx)} fill="none" stroke={BLUE} strokeWidth="2.2" />
      <g className="fig-legend">
        <text x={x(0.07)} y={y(3.35)} style={{ fill: TEAL }}>
          δ = −1
        </text>
        <text x={x(0.52)} y={y(1.22)} style={{ fill: '#475569' }}>
          δ = 0
        </text>
        <text x={x(0.8)} y={y(3.35)} style={{ fill: BLUE }}>
          δ = +1
        </text>
      </g>
    </svg>
  )
}
