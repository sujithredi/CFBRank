import { Callout, Eq, Figure, Proof, Ref, Source, T } from './Tex'
import { TiltDensityFigure, WinProbabilityFigure } from './figures'

const r = String.raw

function Sub({ n, children }) {
  return (
    <h3>
      <span className="sec-num">{n}</span>
      {children}
    </h3>
  )
}

function Table({ head, children, className = '' }) {
  return (
    <div className="table-scroll">
      <table className={`method-table ${className}`}>
        <thead>
          <tr>
            {head.map((label) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 1. Notation
// ---------------------------------------------------------------------------

export function Notation() {
  return (
    <>
      <p>
        Symbols are the ones used in the code, so a formula below can be read against the function that implements
        it. Positive is good for every rating, and every rating is in points per game.
      </p>
      <Table head={['Symbol', 'Meaning']} className="notation">
        <tr>
          <td>{T`\mathcal T,\ n`}</td>
          <td>
            The rated teams (FBS and FCS together), indexed by {T`i,j`}; {T`n=|\mathcal T|`}.
          </td>
        </tr>
        <tr>
          <td>{T`p_{g,i},\ \ell_{g,i}`}</td>
          <td>
            Points scored by team {T`i`} in game {T`g`}, and its venue: {T`\ell_{g,i}=+1`} at home, {T`-1`} away, {T`0`}{' '}
            at a neutral site.
          </td>
        </tr>
        <tr>
          <td>{T`a_i,\ c_i,\ h`}</td>
          <td>Raw offense, raw defense and home-field coefficients of the regression in section 2.</td>
        </tr>
        <tr>
          <td>{T`o_i,\ d_i,\ r_i`}</td>
          <td>
            Centred offense and defense ratings, and the overall rating {T`r_i=o_i+d_i`}.
          </td>
        </tr>
        <tr>
          <td>{T`H`}</td>
          <td>
            Home-field edge in a game&apos;s <em>margin</em>, fixed at {T`2.5`} points in every prediction.
          </td>
        </tr>
        <tr>
          <td>{T`L,\ \sigma,\ \hat F`}</td>
          <td>
            Mean ({T`26.4`}) and standard deviation ({T`14.09`}) of points per team per game in the historical score
            table, and that table&apos;s empirical distribution; the table holds {T`M=3{,}150`} scores.
          </td>
        </tr>
        <tr>
          <td>{T`\Phi,\ \varphi,\ \Lambda`}</td>
          <td>
            Standard normal distribution function and density; logistic function {T`\Lambda(x)=1/(1+e^{-x})`}.
          </td>
        </tr>
        <tr>
          <td>{T`N,\ k`}</td>
          <td>
            Number of simulated seasons ({T`N=10{,}000`}) and the index of one of them, written as a superscript{' '}
            {T`(k)`}.
          </td>
        </tr>
        <tr>
          <td>{T`W_i,\ L_i`}</td>
          <td>Regular-season wins and losses of team {T`i`}; a conference title game is never counted.</td>
        </tr>
      </Table>
    </>
  )
}

// ---------------------------------------------------------------------------
// 2. Power ratings
// ---------------------------------------------------------------------------

export function PowerRatings() {
  return (
    <>
      <Sub n="2.1">A linear model for points scored</Sub>
      <p>
        Every completed game {T`g`} between teams {T`i`} and {T`j`} contributes two observations, one from each
        team&apos;s side. The points a team scores are modelled as a venue effect, plus the scoring team&apos;s
        offense, plus a coefficient for the opposing defense:
      </p>
      <Eq tag={1}>{r`p_{g,i} \;=\; h\,\ell_{g,i} \;+\; a_i \;+\; c_j \;+\; \varepsilon_{g,i}`}</Eq>
      <p>
        There is no intercept: the full set of team indicators already spans the constant. Stacking all{' '}
        {T`2|\mathcal G|`} observations gives {T`p = X\beta + \varepsilon`} with{' '}
        {T`\beta=(h,a_1,\dots,a_n,c_1,\dots,c_n)\T\in\R^{1+2n}`}. Each row of {T`X`} has exactly three non-zero
        entries: {T`\ell_{g,i}`} in column 0, a one in the column of {T`a_i`}, and a one in the column of {T`c_j`}.
        The coefficients are the minimum-norm least-squares solution
      </p>
      <Eq tag={2}>{r`\hat\beta \;=\; (X\T X)\pinv\, X\T p`}</Eq>
      <p>
        where {T`A\pinv`} is the Moore&ndash;Penrose pseudo-inverse. Read as a Bayesian model with Gaussian errors and
        a flat prior on {T`\beta`}, {T`\hat\beta`} is the posterior mean; the fit adds no shrinkage of its own.
      </p>

      <Sub n="2.2">The free constant and the reported ratings</Sub>
      <p>
        {T`X`} has a null direction. With {T`v=(0,\mathbf 1_n,-\mathbf 1_n)`}, each row of {T`X`} contributes{' '}
        {T`+1-1=0`} to {T`Xv`}, so raising every offense coefficient by {T`\kappa`} and lowering every defense
        coefficient by {T`\kappa`} leaves every fitted score unchanged. The reported ratings are defined after
        centring each side on zero over the rated teams, with defense sign-flipped so that a stingy defense is
        positive:
      </p>
      <Eq tag={3}>{r`o_i = a_i - \bar a, \qquad d_i = -(c_i - \bar c), \qquad r_i = o_i + d_i`}</Eq>

      <Callout kind="proposition" label="Proposition" n={1} title="What the ratings mean">
        <p>
          (i) {T`o_i`}, {T`d_i`} and {T`r_i`} are the same for every solution {T`\hat\beta+\kappa v`}. (ii) The fitted
          score is {T`\hat p_{g,i}=\bar\mu+h\,\ell_{g,i}+o_i-d_j`} with {T`\bar\mu=\bar a+\bar c`}. (iii) At a neutral
          site the fitted margin of {T`i`} over {T`j`} is {T`r_i-r_j`}.
        </p>
      </Callout>
      <Proof>
        (i) A common shift of every {T`a_i`} by {T`\kappa`} and of every {T`c_i`} by {T`-\kappa`} moves {T`\bar a`} and{' '}
        {T`\bar c`} by the same amounts, so {T`a_i-\bar a`} and {T`c_i-\bar c`} do not change. (ii) Substitute{' '}
        {T`a_i=o_i+\bar a`} and {T`c_j=\bar c-d_j`} into <Ref n={1} />. (iii) Subtract (ii) for {T`j`} from (ii) for{' '}
        {T`i`}: with {T`\ell=0`} the venue terms vanish, leaving {T`(o_i-d_j)-(o_j-d_i)=r_i-r_j`}.
      </Proof>

      <p>
        The null space of {T`X`} is exactly {T`\operatorname{span}(v)`} when the schedule graph is connected, contains
        an odd cycle, and the home/away pattern is not degenerate, all true of a real season after its first few
        weeks. Earlier, or with isolated groups of teams, there are further null directions and ratings in
        different components are not comparable. The code treats eigenvalues of {T`X\T X`} below {T`10^{-10}`} of the
        largest as zero when it forms the pseudo-inverse.
      </p>

      <Sub n="2.3">Home field</Sub>
      <p>
        The venue indicator enters the two rows of a game with opposite signs, so the fitted home edge in a{' '}
        <em>margin</em> is {T`2h`}. The coefficient is estimated so that venue does not leak into team ratings, but
        predictions do not use {T`\hat h`}. They use the fixed margin edge {T`H=2.5`} based on the 2025 season: half of it is added to the home
        team&apos;s expected score and half subtracted from the visitor&apos;s.
      </p>

      <Sub n="2.4">What the fit leaves out</Sub>
      <ul>
        <li>Only the current season&apos;s games are used; there is no preseason prior, so early-season ratings are noisy.</li>
        <li>Every game has equal weight: no recency decay, no cap on the margin, no discount for garbage time.</li>
        <li>Errors are treated as homoscedastic; injuries, weather and tempo are not modelled.</li>
      </ul>
    </>
  )
}

// ---------------------------------------------------------------------------
// 3. From ratings to a game
// ---------------------------------------------------------------------------

export function Games() {
  return (
    <>
      <Sub n="3.1">The odds page</Sub>
      <p>
        The Weekly Odds page simulates every scheduled game {T`N=1000`} times with the score simulator of section 3.2,
        using the home edge {T`H=2.5`} unless the game is at a neutral site, and reports averages. For home team{' '}
        {T`i`} and visitor {T`j`}, let {T`S_i^{(k)}`} and {T`S_j^{(k)}`} be the two scores in simulation {T`k`}. The
        page shows
      </p>
      <Eq tag={4}>
        {r`\begin{aligned} \hat p &= \frac1N\sum_{k=1}^{N}\mathbf 1\big[S_i^{(k)}>S_j^{(k)}\big] \\[4pt] \hat\mu_i &= \frac1N\sum_{k=1}^{N}S_i^{(k)}, \qquad \hat\mu_j = \frac1N\sum_{k=1}^{N}S_j^{(k)} \\[4pt] \hat m &= \hat\mu_i-\hat\mu_j, \qquad \hat T = \hat\mu_i+\hat\mu_j \end{aligned}`}
      </Eq>
      <p>
        the home win probability {T`\hat p`} (the away team&apos;s is {T`1-\hat p`}), each team&apos;s projected points{' '}
        {T`\hat\mu`}, the projected margin {T`\hat m`} and the projected total {T`\hat T`}. A win probability is
        therefore a count out of {T`1000`} and moves in steps of {T`0.1`} points; its sampling error is
      </p>
      <Eq tag={5}>{r`\operatorname{se}(\hat p) \;=\; \sqrt{\hat p\,(1-\hat p)/N} \;\le\; 0.016`}</Eq>
      <p>
        at most 1.6 points of probability, at {T`\hat p=\tfrac12`}. Each game&apos;s draws are seeded from the game&apos;s
        id, so a game shows the same numbers on every refresh until a team&apos;s ratings change. The margin and total
        are averages of simulated scores, not rating arithmetic: every simulated score is a score that has happened,
        so in a lopsided game the average margin comes out smaller than the rating gap plus {T`H`}.
      </p>

      <Sub n="3.2">The score simulator</Sub>
      <p>
        A simulated game draws each team&apos;s score separately. For team {T`A`} against{' '}
        {T`B`}, let {T`H_A\in\{H,0,-H\}`} be the home edge from {T`A`}&apos;s side (home, neutral, away). The expected
        points are
      </p>
      <Eq tag={6}>{r`\mu_A = L + o_A - d_B + \tfrac12 H_A, \qquad \mu_B = L + o_B - d_A - \tfrac12 H_A`}</Eq>
      <p>
        A score is then produced independently for each team in three steps: draw a noisy scoring level, convert it
        to the probability that a game at that level beats the league mean, and read that percentile off the sorted
        table of historical scores.
      </p>
      <Eq tag={7}>
        {r`\begin{aligned} Y &= \mu+\sigma Z, \qquad Z\sim\mathcal N(0,1), \qquad \delta=\frac{\mu-L}{\sigma}, \\[4pt] u &= \Pr\!\big[\mathcal N(Y,\sigma^2)>L\big]=\Phi\!\Big(\frac{Y-L}{\sigma}\Big)=\Phi(Z+\delta). \end{aligned}`}
      </Eq>
      <Eq tag={8}>{r`S \;=\; \hat F^{-1}(u) \;=\; q_{[\operatorname{round}(u\,(M-1))]}, \qquad q_{[0]}\le q_{[1]}\le\dots\le q_{[M-1]}`}</Eq>

      <Callout kind="proposition" label="Proposition" n={2} title="Percentile tilt">
        <p>
          If {T`Z\sim\mathcal N(0,1)`}, then {T`u=\Phi(Z+\delta)`} has density
        </p>
        <Eq tag={9}>{r`f_\delta(x) \;=\; \exp\!\big(\delta\,\Phi^{-1}(x) - \tfrac12\delta^2\big), \qquad 0<x<1.`}</Eq>
        <p>
          In particular {T`\delta=0`} gives a uniform {T`u`}, so {T`S`} then has exactly the historical score
          distribution, and {T`u`} increases stochastically with {T`\delta`}, so the expected score is increasing in{' '}
          {T`\mu`}.
        </p>
      </Callout>
      <Proof>
        {T`\Pr(u\le x)=\Pr\big(Z\le\Phi^{-1}(x)-\delta\big)=\Phi\big(\Phi^{-1}(x)-\delta\big)`}. Differentiating with{' '}
        {T`z=\Phi^{-1}(x)`} gives {T`\varphi(z-\delta)/\varphi(z)=\exp(\delta z-\delta^2/2)`}. For the last claim,{' '}
        {T`f_{\delta'}/f_\delta`} is increasing in {T`x`} whenever {T`\delta'>\delta`} (a monotone likelihood ratio),
        and {T`\hat F^{-1}`} is nondecreasing.
      </Proof>

      <Figure
        n={1}
        caption={
          <>
            The density <Ref n={9} /> of the percentile {T`u`} for three scoring levels. A below-average offense
            ({T`\delta=-1`}) samples low percentiles of the score table; an above-average one samples high ones.
          </>
        }
      >
        <TiltDensityFigure />
      </Figure>

      <p>
        Every simulated score is therefore a score that has actually happened (no negative scores, no 23.7), and the
        scoring level moves the whole distribution, not just its mean. Football has no ties: if the two scores are
        equal the game goes to overtime, which team {T`A`} wins with probability
      </p>
      <Eq tag={10}>{r`\Phi\!\Big(\frac{\mu_A-\mu_B}{\sqrt2\,\sigma}\Big)`}</Eq>
      <p>
        ({T`\sqrt2\,\sigma`} is the standard deviation of a difference of two independent scores), and the winner is
        given {T`3`} points.
      </p>

      <Callout kind="example" label="Example">
        <p>
          Team {T`A`} ({T`o=7,\ d=5`}, so {T`r=12`}) hosts team {T`B`} ({T`o=-1,\ d=2`}, so {T`r=1`}). By{' '}
          <Ref n={6} />, {T`\mu_A=26.4+7-2+1.25=32.65`} and {T`\mu_B=26.4-1-5-1.25=19.15`}, so{' '}
          {T`\delta_A=0.44`}, {T`\delta_B=-0.51`}, and the rating gap plus home edge is {T`13.5=r_A-r_B+H`}.
          Simulating the game 60,000 times with <Ref n={6} />&ndash;<Ref n={8} /> gives a win probability of{' '}
          {T`0.758`}, so the odds page, with {T`N=1000`}, would report about {T`0.76`} give or take {T`0.014`} (one
          standard error, <Ref n={5} />).
        </p>
      </Callout>
    </>
  )
}

// ---------------------------------------------------------------------------
// 4. Season simulation
// ---------------------------------------------------------------------------

export function SeasonSimulation() {
  return (
    <>
      <Sub n="4.1">Replicates and what is estimated</Sub>
      <p>
        Replicate {T`k`} replays every unplayed regular-season game and each conference&apos;s title game, starting from
        the same schedule and the same stored ratings, and yields a record plus a few events {T`E_i^{(k)}`} for each
        team. Every percentage on the site is a sample proportion:
      </p>
      <Eq tag={11}>
        {r`\hat p_i=\frac1N\sum_{k=1}^{N}\ind\{E_i^{(k)}\}, \qquad \operatorname{SE}(\hat p_i)=\sqrt{\frac{\hat p_i(1-\hat p_i)}{N}}\;\le\;\frac{1}{2\sqrt N}=0.005`}
      </Eq>
      <p>
        Monte Carlo error is at most half a percentage point, so
        differences between teams smaller than that are noise. The {T`N`} replicates are independent draws from one
        seeded random-number stream, which makes a run exactly reproducible. The playoff bracket draws from a second
        stream derived from the same seed, so playing it never changes any other number.
      </p>
      <Table head={['Column', 'Event or statistic per replicate']} className="events">
        <tr>
          <td>
            <code>avg_wins</code>, <code>avg_losses</code>
          </td>
          <td>
            Mean of {T`W_i^{(k)}`} and {T`L_i^{(k)}`}: games already played plus simulated, regular season only.
          </td>
        </tr>
        <tr>
          <td>
            <code>bowl_pct</code>
          </td>
          <td>
            {T`F_i+\min(C_i,1)\ge 6`}, FBS teams only, where {T`F_i`} and {T`C_i`} count wins over FBS and over FCS
            opponents. Eligibility, not bowl placement.
          </td>
        </tr>
        <tr>
          <td>
            <code>undefeated_pct</code>
          </td>
          <td>{T`L_i=0`}.</td>
        </tr>
        <tr>
          <td>
            <code>title_game_pct</code>
          </td>
          <td>Team {T`i`} is one of the two finalists of its conference (section 5).</td>
        </tr>
        <tr>
          <td>
            <code>conf_champ_pct</code>
          </td>
          <td>Team {T`i`} wins that game.</td>
        </tr>
        <tr>
          <td>
            <code>playoff_pct</code>
          </td>
          <td>
            Team {T`i`} is in the 12-team field {T`\mathcal F`} (section 6).
          </td>
        </tr>
        <tr>
          <td>
            <code>cfp_bye_pct</code>
          </td>
          <td>Team {T`i`} is one of the top four seeds of {T`\mathcal F`} (section 6.4).</td>
        </tr>
        <tr>
          <td>
            <code>cfp_quarterfinal_pct</code>
          </td>
          <td>Team {T`i`} plays in a quarterfinal: a top-four seed, or a first-round winner.</td>
        </tr>
        <tr>
          <td>
            <code>cfp_semifinal_pct</code>, <code>cfp_final_pct</code>
          </td>
          <td>Team {T`i`} plays in a semifinal, or in the national championship game.</td>
        </tr>
        <tr>
          <td>
            <code>cfp_champion_pct</code>
          </td>
          <td>Team {T`i`} wins the national championship.</td>
        </tr>
      </Table>

      <Sub n="4.2">Re-fitting the ratings after every simulated week</Sub>
      <p>
        Games are simulated one week at a time. After each week the ratings are refit on every game so far, the
        played ones and the simulated ones, and the next week is simulated with the updated ratings. A team that wins
        three games by wide margins in one replicate is therefore rated higher for what follows, as in the real
        rankings. Because the ratings depend on earlier simulated scores, outcomes within a replicate are dependent; with the
        ratings frozen they would be independent given the starting ratings.
      </p>
      <p>
        This is the model of section 2, refit, and it is cheap because of its structure. Let {T`X_w`} be the design
        matrix of every game scheduled through week {T`w`}, played or not (which games exist does not depend on any
        score), and let {T`G_w=X_w\T X_w`} and {T`b_w=X_w\T p_w`}. The Gram matrix {T`G_w`} depends only on the
        schedule. Scores enter only through {T`b_w`}, which is updated by adding each simulated game&apos;s
        contribution {T`X_g\T p_g`}, where {T`X_g`} is the game&apos;s two rows and {T`p_g`} its two scores:
      </p>
      <Eq tag={12}>{r`b_w \;=\; b_{w-1} + \sum_{g\,\in\,\text{week }w} X_g\T p_g, \qquad \hat\beta_w \;=\; G_w\pinv\, b_w`}</Eq>
      <Eq tag={13}>{r`\rho_w \;=\; \begin{pmatrix} o^{(w)} \\ d^{(w)} \end{pmatrix} \;=\; O_w\, b_w + \kappa_w`}</Eq>
      <p>
        Here {T`O_w`} is a fixed {T`2n\times(1+2n)`} matrix that composes {T`G_w\pinv`} with the sign flip and the
        centring of <Ref n={3} />, centring over the teams that have appeared in a game so far. {T`\kappa_w`} holds
        the stored ratings of teams that have not played yet, which keep them until their first game.
      </p>

      <Callout kind="proposition" label="Proposition" n={3} title="Exact, and cheap">
        <p>
          {T`\rho_w`} equals the offense and defense ratings obtained by fitting the model of section 2 from scratch
          to all games through week {T`w`}. The matrices {T`O_w`} are computed once per week and shared by all{' '}
          {T`N`} replicates; each replicate then costs one matrix&ndash;vector product per week.
        </p>
      </Callout>
      <Proof>
        {T`X_w`} does not depend on scores, so {T`G_w\pinv`} is the same in every replicate, and{' '}
        {T`\hat\beta_w=G_w\pinv b_w`} is <Ref n={2} /> applied to the stacked data. The sign flip and the centring are
        linear. The tests assert equality with <code>compute_power_ratings</code> on the same games.
      </Proof>
      <p>
        Each week costs one eigendecomposition of {T`G_w`}, about {T`O(n^3)`}, before any replicate starts. After
        that a replicate performs one {T`2n\times(1+2n)`} matrix&ndash;vector product per week: about{' '}
        {T`2.8\times10^{5}`} multiply&ndash;adds for the current {T`n=266`} teams.
      </p>

      <Callout kind="algorithm" label="Algorithm" n={1} title="One replicate">
        <ol>
          <li>
            Set {T`b\leftarrow b_0`} (from the games already played) and {T`\rho\leftarrow`} the stored ratings.
          </li>
          <li>
            For each remaining week {T`w`} in order:
            <ol type="a">
              <li>
                If {T`w`} is the first week numbered 14 or later (or, if there is none, once the last week is done),
                play each conference&apos;s title game with the current {T`\rho`} (section 5). Their scores are not
                added to {T`b`}.
              </li>
              <li>
                Simulate every game of week {T`w`} with <Ref n={6} />&ndash;<Ref n={8} />, using the current {T`\rho`}{' '}
                and the fixed {T`H`}.
              </li>
              <li>
                Add the games to {T`b`} by <Ref n={12} /> and set {T`\rho\leftarrow O_w b+\kappa_w`}.
              </li>
            </ol>
          </li>
          <li>
            Record each team&apos;s {T`W_i`}, {T`L_i`}, bowl eligibility and the title-game events.
          </li>
          <li>
            Select the playoff field (section 6) using the final {T`\rho`}.
          </li>
          <li>
            Seed the field, play the bracket with the same {T`\rho`} (section 6.4), and record how far each team got.
          </li>
        </ol>
      </Callout>

      <Sub n="4.3">Conventions</Sub>
      <ul>
        <li>
          Week 1 of the simulation uses the stored ratings, the same numbers the rankings page shows. Simulated games
          use the fixed {T`H`}; the refit&apos;s own {T`h`} only keeps venue out of the ratings.
        </li>
        <li>
          Real conference-championship rows already in the schedule are ignored for records, since the simulation
          plays its own. They remain in the rating fit as ordinary games.
        </li>
        <li>
          The starting ratings are treated as exact. Their sampling error is not propagated, so the probabilities
          describe a plug-in model, not a full posterior predictive, and are more confident than the data strictly
          justify.
        </li>
      </ul>
    </>
  )
}

// ---------------------------------------------------------------------------
// 5. Conference championships
// ---------------------------------------------------------------------------

export function Championships() {
  return (
    <>
      <Sub n="5.1">Finalists</Sub>
      <p>
        For each conference with a title game, let {T`w_i`} be a team&apos;s conference winning percentage over
        conference games before week 14, real and simulated. Teams are ranked by {T`w_i`} and not by wins, because
        conferences play unequal numbers of conference games. The top two meet. The Sun Belt differs: the winners of
        its two divisions meet.
      </p>

      <Sub n="5.2">Breaking ties</Sub>
      <p>
        Teams level on {T`w_i`} form a tied group {T`T`}. The conference&apos;s tiebreakers {T`\tau_1,\dots,\tau_K`}{' '}
        are tried in order, and a group that is only partly separated starts over from {T`\tau_1`}:
      </p>
      <Callout kind="algorithm" label="Algorithm" n={2} title={T`\operatorname{Order}(T)`}>
        <ol>
          <li>
            If {T`|T|=1`}, return {T`T`}.
          </li>
          <li>
            For {T`t=1,\dots,K`}: compute {T`\tau_t(i;T)`} for every {T`i\in T`}. If the values are not all equal,
            split {T`T`} into subgroups of equal value, best first, and return the concatenation of{' '}
            {T`\operatorname{Order}(T')`} over the subgroups {T`T'`} in that order.
          </li>
          <li>If no {T`\tau_t`} separates {T`T`}, order it at random.</li>
        </ol>
      </Callout>
      <p>
        So a three-way tie that one tiebreaker reduces to two teams goes back to head-to-head between just those two.
        The tiebreakers are
      </p>
      <Eq tag={14}>
        {r`\tau_{\mathrm{h2h}}(i;T)=\frac{\#\{\text{wins of } i \text{ over } T\setminus\{i\}\}}{\#\{\text{games of } i \text{ against } T\setminus\{i\}\}}\quad(\text{taken as }\tfrac12\text{ if there are none})`}
      </Eq>
      <p>
        and, for common opponents, {T`\tau_{\mathrm{co}}(i;T)`} is {T`i`}&apos;s winning percentage against the
        conference opponents that every member of {T`T`} played (not applicable if there are none). The Pac-12 instead
        compares winning percentage against the highest-placed common opponent, then the next, and so on; the Sun Belt
        applies head-to-head and then winning percentage within the division; and where a conference&apos;s real second
        step cannot be reproduced here, the model rating {T`r_i`} (American, Mountain West) or a coin flip (ACC)
        stands in, as in the table.
      </p>
      <Table head={['Conference', 'Tiebreakers, in order', 'Title game']} className="rules">
        <tr>
          <td>SEC, Big Ten, Big 12</td>
          <td>head-to-head; common opponents</td>
          <td>neutral</td>
        </tr>
        <tr>
          <td>ACC</td>
          <td>head-to-head; random</td>
          <td>neutral</td>
        </tr>
        <tr>
          <td>Pac-12</td>
          <td>head-to-head; highest-placed common opponent</td>
          <td>first place hosts</td>
        </tr>
        <tr>
          <td>American, Mountain West</td>
          <td>head-to-head; model rating {T`r_i`}</td>
          <td>first place hosts</td>
        </tr>
        <tr>
          <td>Conference USA, Mid-American</td>
          <td>head-to-head; common opponents</td>
          <td>first place hosts</td>
        </tr>
        <tr>
          <td>Sun Belt</td>
          <td>divisions: head-to-head; division winning percentage</td>
          <td>better division winner hosts</td>
        </tr>
      </Table>

      <Sub n="5.3">The title game</Sub>
      <p>
        The game is played with the simulator of section 3.2 using the ratings from after the last regular week before
        it. At a neutral site {T`H_A=0`}; where the first-place team hosts, {T`H_A=H`} from its side. The winner is the
        conference champion. A title game never counts toward {T`W_i`}, {T`L_i`}, bowl eligibility or the undefeated
        event, and its score is not fed back into the ratings.
      </p>
    </>
  )
}

// ---------------------------------------------------------------------------
// 6. Playoff field
// ---------------------------------------------------------------------------

export function Playoff() {
  return (
    <>
      <Sub n="6.1">Who is in the field</Sub>
      <p>
        Let {T`\mathcal C_4`} be the ACC, Big Ten, SEC and Big 12, let {T`\mathcal C_6`} be the American, Conference
        USA, Mid-American, Mountain West, Pac-12 and Sun Belt, and let {T`\pi_i`} be the network score of team {T`i`}{' '}
        (section 6.3). With {T`\operatorname{champ}(c)`} the title-game winner of conference {T`c`}, and {T`\mathcal N`}{' '}
        the set that holds Notre Dame if it is among the twelve FBS teams with the largest {T`\pi`} (and is empty
        otherwise), the 12-team field is
      </p>
      <Eq tag={15}>
        {r`\mathcal F \;=\; \underbrace{\{\operatorname{champ}(c):c\in\mathcal C_4\}}_{\text{4 automatic bids}} \;\cup\; \{g^{*}\} \;\cup\; \mathcal N \;\cup\; \mathcal B, \qquad g^{*}=\argmax_{c\in\mathcal C_6}\ \pi_{\operatorname{champ}(c)}`}
      </Eq>
      <p>
        where {T`\mathcal B`} is the {T`7-|\mathcal N|`} FBS teams with the largest {T`\pi`} among those not already
        chosen (ties go to the lower index). The four conference champions get in whatever their ranking. A Group of 6
        champion that loses out on {T`g^{*}`} can still enter through {T`\mathcal B`}. Notre Dame&apos;s bid only
        matters when the automatic bids would otherwise crowd it out of the at-large spots, and then it takes the last
        of them. The data has no committee ranking, so top 12 here means the network&apos;s own ordering. Other
        independents have no automatic bid and compete only for {T`\mathcal B`}. If a conference has no champion its
        spot goes to {T`\mathcal B`}, so the field always has 12 teams.
      </p>

      <Sub n="6.2">Inputs to the network</Sub>
      <p>
        Each team is described by {T`x_i=(\mathrm{SOS}_i,\,W_i,\,L_i)`}, all regular season. With {T`\Omega_i`} the
        multiset of its regular-season opponents, played or simulated, FCS teams included, and {T`r^{\mathrm{final}}`}{' '}
        the overall ratings after the last simulated week,
      </p>
      <Eq tag={16}>{r`\mathrm{SOS}_i \;=\; \frac{1}{|\Omega_i|}\sum_{j\in\Omega_i} r_j^{\mathrm{final}}`}</Eq>
      <p>
        The scales are comparable: in the current fit FBS ratings average about {T`17`} (FBS and FCS are centred
        together), close to the mean {T`\mathrm{SOS}`} of the training rows. Title games are not in {T`\Omega_i`} for now, just as they are not in{' '}
        {T`W_i`} and {T`L_i`}.
      </p>

      <Sub n="6.3">The network</Sub>
      <p>
        The network is a multilayer perceptron trained on
        historical team-seasons during the 12-team playoff era:
      </p>
      <Eq tag={17}>{r`z=\frac{x-\bar x}{s}, \qquad \pi \;=\; \Lambda\!\big(w_2\T \tanh(W_1 z + b_1) + b_2\big), \qquad W_1\in\R^{177\times 3}`}</Eq>
      <p>
        where {T`\bar x`} and {T`s`} are the componentwise mean and standard deviation of the training features (computed
        on all {T`136`} rows, before the split). It has {T`3\cdot177+177+177+1=886`} parameters {T`\theta`} and is
        fit on a random {T`80\%`} of the rows ({T`n=108`}) by L-BFGS, minimizing the regularized log-loss
      </p>
      <Eq tag={18}>
        {r`\begin{aligned} J(\theta) &= -\frac1n\sum_{t=1}^{n}\Big[y_t\log\pi_t+(1-y_t)\log(1-\pi_t)\Big] \\[4pt] &\quad+\; \frac{\alpha}{2n}\Big(\lVert W_1\rVert_F^2+\lVert w_2\rVert_2^2\Big), \qquad \alpha=0.228 \end{aligned}`}
      </Eq>
      <p>
        The optimizer is stopped before convergence, which acts as additional regularization. Only the ordering of the
        scores {T`\pi`} is used; they are not calibrated probabilities and are not displayed.
      </p>

      <Sub n="6.4">Seeding and the playoff games</Sub>
      <p>
        The committee&apos;s ranking is not in the data, so the field is seeded by overall rating. With{' '}
        {T`r^{\mathrm{final}}`} as in <Ref n={16} />, the seed of team {T`i\in\mathcal F`} is its place in{' '}
        {T`\mathcal F`} by rating, best first, ties going to the lower index:
      </p>
      <Eq tag={19}>{r`s(i) \;=\; 1+\bigl|\{\,j\in\mathcal F:\ r_j^{\mathrm{final}}>r_i^{\mathrm{final}}\,\}\bigr|`}</Eq>
      <p>
        The network score {T`\pi`} is not used for this: it answers whether a team makes the field, so it rates every
        strong team close to one and cannot order the top of the bracket. The bracket is fixed. The four best seeds skip
        the first round, and there is no re-seeding, so a low seed that wins keeps its path:
      </p>
      <Table head={['Round', 'Games', 'Site']}>
        <tr>
          <td>First round</td>
          <td>5 v 12, 6 v 11, 7 v 10, 8 v 9</td>
          <td>
            the better seed&apos;s campus, {T`H_A=H`}
          </td>
        </tr>
        <tr>
          <td>Quarterfinals</td>
          <td>1 v W(8/9), 4 v W(5/12), 2 v W(7/10), 3 v W(6/11)</td>
          <td>
            neutral, {T`H_A=0`}
          </td>
        </tr>
        <tr>
          <td>Semifinals</td>
          <td>W(1 and 8/9) v W(4 and 5/12), W(2 and 7/10) v W(3 and 6/11)</td>
          <td>neutral</td>
        </tr>
        <tr>
          <td>Championship</td>
          <td>the two semifinal winners</td>
          <td>neutral</td>
        </tr>
      </Table>
      <p>
        Every game is played with the simulator of section 3.2 and the ratings from after the last regular week, the
        same way as a title game. A tied score is sent to overtime, so every game has a winner. No playoff game is fed
        back into the ratings.
      </p>

      <Sub n="6.5">The estimators, and invariants</Sub>
      <p>
        <code>playoff_pct</code> is <Ref n={11} /> with {T`E_i=\{i\in\mathcal F\}`}. The playoff-game columns are the
        same estimator with the event that team {T`i`} reaches that stage, out of all {T`N`} replicates, so a team that
        misses the field counts as a miss, not as missing data. Every replicate selects exactly twelve teams and plays a
        bracket with four byes, eight quarterfinalists, four semifinalists, two finalists and one champion, so for every
        run
      </p>
      <Eq>
        {r`\begin{aligned} \sum_{i\,\in\,\text{FBS}} \hat p_i^{\,\text{playoff}} &= 1200\%, & \sum_{i} \hat p_i^{\,\text{bye}} &= 400\%, & \sum_{i} \hat p_i^{\,\text{QF}} &= 800\% \\[4pt] \sum_{i} \hat p_i^{\,\text{SF}} &= 400\%, & \sum_{i} \hat p_i^{\,\text{final}} &= 200\%, & \sum_{i} \hat p_i^{\,\text{champ}} &= 100\% \end{aligned}`}
      </Eq>
      <p>
        and, for every team, {T`\hat p^{\,\text{champ}}\le\hat p^{\,\text{final}}\le\hat p^{\,\text{SF}}\le\hat p^{\,\text{QF}}\le\hat p^{\,\text{playoff}}`}.
      </p>
      <p>
        Caveats: the training seasons are all 12 games long, so teams with 11 or 13 games are slightly outside what the
        network has seen; 136 rows with 19 positives is a small sample; and the network imitates past selections, it
        does not model the committee. Seeding by rating stands in for the committee&apos;s ranking and decides who gets
        a bye and who hosts, so the title odds are only as good as that stand-in.
      </p>
    </>
  )
}

// ---------------------------------------------------------------------------
// 7. Assumptions and limits
// ---------------------------------------------------------------------------

export function Limits() {
  return (
    <>
      <ul>
        <li>
          <strong>Plug-in uncertainty.</strong> The starting ratings are treated as known (section 4.3). The
          probabilities carry Monte Carlo error of at most half a point, but not the sampling error of the ratings
          themselves.
        </li>
        <li>
          <strong>A simple scoring model.</strong> Additive, equal-weight, constant variance, one season of data
          (section 2.4), and a home edge {T`H=2.5`} that is the same for every team and stadium.
        </li>
        <li>
          <strong>Two win-probability curves.</strong> The Weekly Odds page and the simulation use different spreads
          (section 3.3).
        </li>
        <li>
          <strong>Simplified tiebreakers.</strong> The real rulebooks have more steps than the ones listed in section 5.
          The ACC&apos;s second step is replaced by a coin flip, and the American and Mountain West use the model rating
          in place of the CFB Rankings.
        </li>
        <li>
          <strong>Seeding by rating.</strong> The committee&apos;s ranking is not in the data, so the playoff field is
          seeded by overall rating (section 6.4). That sets the byes and the first-round hosts, and the playoff games
          are played without refitting the ratings.
        </li>
        <li>
          <strong>Eligibility, not selection, for bowls.</strong> <code>bowl_pct</code> Is eligible for bowl but does not account for, 
          team opt-outs, 5-7 teams, or there being more bowl eligible teams then spots.
        </li>
        <li>
          <strong>Schedule strength includes FCS opponents</strong> at their (negative) ratings, so a team with an FCS
          game on its schedule is penalized relative to one without.
        </li>
      </ul>
    </>
  )
}