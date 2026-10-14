import { useEffect, useRef, useState } from 'react'
import { fetchRankings, simulateMatchup } from '../api'

// Mirrors MAX_SIMULATED_GAMES in backend/app/schemas.py.
const MAX_GAMES = 1000
// The game log shows only the first few games of a series; the summary covers all of them.
const GAME_LOG_LIMIT = 10

// Where the game is played, in words. Team names are filled in once picked.
function locationLabel(location, teamA, teamB) {
  if (location === 'team_a_home') return `${teamA || 'Team A'} home`
  if (location === 'team_b_home') return `${teamB || 'Team B'} home`
  return 'Neutral site'
}

function TeamLogo({ url }) {
  const [failed, setFailed] = useState(false)

  if (!url || failed) {
    return <span className="team-logo placeholder" aria-hidden="true" />
  }

  return (
    <img
      className="team-logo"
      src={url}
      alt=""
      width="28"
      height="28"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

function TeamSelect({ label, value, onChange, teams, disabledId, disabled, placeholder }) {
  return (
    <label className="team-picker matchup-picker">
      <span>{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        <option value="" disabled>
          {placeholder}
        </option>
        {teams.map((team) => (
          <option key={team.team_id} value={team.team_id} disabled={String(team.team_id) === disabledId}>
            {team.team}
          </option>
        ))}
      </select>
    </label>
  )
}

function ScoreSide({ team, isWinner }) {
  return (
    <div className={`scoreboard-side${isWinner ? ' winner' : ''}`}>
      <TeamLogo url={team.logo_url} />
      <span className="scoreboard-name">{team.team}</span>
      <strong className="scoreboard-score">{team.score}</strong>
      <small>Expected {team.expected_points.toFixed(1)} pts</small>
    </div>
  )
}

// One team's column in a multi-game result: wins, win rate, and average score.
function SeriesSide({ team, wins, winPct, avgScore, isLeader }) {
  return (
    <div className={`scoreboard-side${isLeader ? ' winner' : ''}`}>
      <TeamLogo url={team.logo_url} />
      <span className="scoreboard-name">{team.team}</span>
      <strong className="scoreboard-score">{wins}</strong>
      <small>
        {wins === 1 ? 'win' : 'wins'} · {winPct.toFixed(1)}%
      </small>
      <small>Avg {avgScore.toFixed(1)} pts</small>
      <small>Expected {team.expected_points.toFixed(1)} pts</small>
    </div>
  )
}

function GameLog({ result }) {
  const { team_a: teamA, team_b: teamB, games } = result
  const shown = games.slice(0, GAME_LOG_LIMIT)

  return (
    <div className="game-log">
      <ol>
        {shown.map((game, index) => {
          const aWon = game.winner_team_id === teamA.team_id
          return (
            <li key={index}>
              <span className="game-log-number">Game {index + 1}</span>
              <span className={aWon ? 'game-log-winner' : undefined}>
                {teamA.team} {game.score_a}
              </span>
              <span className={aWon ? undefined : 'game-log-winner'}>
                {teamB.team} {game.score_b}
              </span>
              {game.overtime && <span className="game-log-ot">OT</span>}
            </li>
          )
        })}
      </ol>
      {games.length > shown.length && (
        <p className="scoreboard-note">
          Showing the first {shown.length} of {games.length} games.
        </p>
      )}
    </div>
  )
}

// Pick two teams, then simulate a game between them.
function MatchupSimulator() {
  const [teams, setTeams] = useState([])
  const [teamsError, setTeamsError] = useState(false)
  const [teamAId, setTeamAId] = useState('')
  const [teamBId, setTeamBId] = useState('')
  const [location, setLocation] = useState('neutral')
  // Kept as the raw input string so the field can be cleared and retyped; parsed below.
  const [numGamesInput, setNumGamesInput] = useState('1')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [isSimulating, setIsSimulating] = useState(false)
  // Bumped whenever the picks or settings change or a new run starts, so a slow response for an old matchup can't overwrite what's on screen.
  const runId = useRef(0)

  useEffect(() => {
    let cancelled = false

    fetchRankings()
      .then((data) => {
        if (cancelled) return
        const selectable = data.rankings
          .filter((team) => team.team_id != null)
          .sort((a, b) => a.team.localeCompare(b.team))
        setTeams(selectable)
      })
      .catch(() => {
        if (!cancelled) setTeamsError(true)
      })

    return () => {
      cancelled = true
    }
  }, [])

  // Changing any input invalidates what's on screen, so clear it (and ignore any in-flight response).
  function resetOnChange(setter) {
    return (value) => {
      runId.current += 1
      setter(value)
      setResult(null)
      setError(null)
      setIsSimulating(false)
    }
  }

  const onTeamAChange = resetOnChange(setTeamAId)
  const onTeamBChange = resetOnChange(setTeamBId)
  const onLocationChange = resetOnChange(setLocation)
  const onNumGamesChange = resetOnChange(setNumGamesInput)

  async function handleSimulate() {
    const thisRun = ++runId.current
    setIsSimulating(true)
    setError(null)

    try {
      const game = await simulateMatchup(Number(teamAId), Number(teamBId), { location, numGames })
      if (runId.current === thisRun) setResult(game)
    } catch (err) {
      if (runId.current === thisRun) {
        setResult(null)
        setError(err.message)
      }
    } finally {
      if (runId.current === thisRun) setIsSimulating(false)
    }
  }

  const numGames = Number(numGamesInput)
  const gamesValid = numGamesInput.trim() !== '' && Number.isInteger(numGames) && numGames >= 1 && numGames <= MAX_GAMES
  const ready = teamAId !== '' && teamBId !== '' && gamesValid
  const teamAName = teams.find((team) => String(team.team_id) === teamAId)?.team
  const teamBName = teams.find((team) => String(team.team_id) === teamBId)?.team
  const placeholder = teamsError ? "Couldn't load teams" : teams.length === 0 ? 'Loading teams...' : 'Select a team...'

  return (
    <div className="matchup">
      <div className="matchup-pickers">
        <TeamSelect
          label="Team A"
          value={teamAId}
          onChange={onTeamAChange}
          teams={teams}
          disabledId={teamBId}
          disabled={teams.length === 0}
          placeholder={placeholder}
        />
        <span className="matchup-vs" aria-hidden="true">
          vs
        </span>
        <TeamSelect
          label="Team B"
          value={teamBId}
          onChange={onTeamBChange}
          teams={teams}
          disabledId={teamAId}
          disabled={teams.length === 0}
          placeholder={placeholder}
        />
      </div>

      <div className="matchup-settings">
        <label className="team-picker matchup-picker">
          <span>Location</span>
          <select value={location} onChange={(event) => onLocationChange(event.target.value)}>
            {['neutral', 'team_a_home', 'team_b_home'].map((option) => (
              <option key={option} value={option}>
                {locationLabel(option, teamAName, teamBName)}
              </option>
            ))}
          </select>
        </label>
        <label className="team-picker matchup-picker">
          <span>Number of games</span>
          <input
            type="number"
            inputMode="numeric"
            min="1"
            max={MAX_GAMES}
            step="1"
            value={numGamesInput}
            aria-invalid={!gamesValid}
            onChange={(event) => onNumGamesChange(event.target.value)}
          />
        </label>
      </div>
      {!gamesValid && (
        <p className="status-copy error-copy">Enter a whole number of games from 1 to {MAX_GAMES}.</p>
      )}

      <button type="button" className="primary-button" disabled={!ready || isSimulating} onClick={handleSimulate}>
        {isSimulating
          ? 'Simulating...'
          : result
            ? 'Simulate again'
            : gamesValid && numGames > 1
              ? `Simulate ${numGames} games`
              : 'Simulate game'}
      </button>

      {error && <p className="status-copy error-copy">Couldn't simulate this game ({error}).</p>}

      {result && result.num_games === 1 && (
        <div className="scoreboard" aria-live="polite">
          <p className="scoreboard-status">
            Final{result.overtime ? ' (OT)' : ''} · {locationLabel(result.location, result.team_a.team, result.team_b.team)}
          </p>
          <div className="scoreboard-row">
            <ScoreSide team={result.team_a} isWinner={result.winner_team_id === result.team_a.team_id} />
            <ScoreSide team={result.team_b} isWinner={result.winner_team_id === result.team_b.team_id} />
          </div>
          <p className="scoreboard-note">
            Based on {result.season}, Week {result.week} offense and defense ratings.
          </p>
        </div>
      )}

      {result && result.num_games > 1 && (
        <div className="scoreboard" aria-live="polite">
          <p className="scoreboard-status">
            {result.num_games} games · {locationLabel(result.location, result.team_a.team, result.team_b.team)}
          </p>
          <div className="scoreboard-row">
            <SeriesSide
              team={result.team_a}
              wins={result.summary.team_a_wins}
              winPct={result.summary.team_a_win_pct}
              avgScore={result.summary.avg_score_a}
              isLeader={result.summary.team_a_wins > result.summary.team_b_wins}
            />
            <SeriesSide
              team={result.team_b}
              wins={result.summary.team_b_wins}
              winPct={result.summary.team_b_win_pct}
              avgScore={result.summary.avg_score_b}
              isLeader={result.summary.team_b_wins > result.summary.team_a_wins}
            />
          </div>
          <p className="scoreboard-note">
            {result.summary.overtime_games} of {result.num_games} games went to overtime. Based on {result.season}, Week{' '}
            {result.week} offense and defense ratings.
          </p>
          <GameLog result={result} />
        </div>
      )}
    </div>
  )
}

export default MatchupSimulator
