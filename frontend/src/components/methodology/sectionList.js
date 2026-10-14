import {
  Championships,
  Games,
  Limits,
  Notation,
  Playoff,
  PowerRatings,
  SeasonSimulation,
} from './sections'

// The order of the page and of its contents list.
export const SECTIONS = [
  { id: 'notation', title: 'Notation', Body: Notation },
  { id: 'ratings', title: 'Power ratings', Body: PowerRatings },
  { id: 'games', title: 'From ratings to a game', Body: Games },
  { id: 'season', title: 'Season simulation', Body: SeasonSimulation },
  { id: 'championships', title: 'Conference championships', Body: Championships },
  { id: 'playoff', title: 'Playoff field and games', Body: Playoff },
  { id: 'limits', title: 'Assumptions and limits', Body: Limits },
]
