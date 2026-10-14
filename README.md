# CFB Rank

CFB Rank is a college football ranking and odds dashboard built with a FastAPI backend and a React + Vite frontend. It provides team data, rankings, and weekly odds in a single app for exploring season trends and power ratings.

## Overview

- Backend: Python, FastAPI, SQLAlchemy, SQLite
- Frontend: React, Vite, JavaScript
- Data pipeline: scripts for ingesting conference/team data and computing ratings
- Primary data model: teams, conferences, rankings, and odds

## Project structure

```text
CFBRank/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── rankings.py
│   │   ├── routers/
│   │   ├── database.py
│   │   └── schemas.py
│   ├── scripts/
│   ├── data/
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── docs/
└── README.md
```

## Features

- Season and weekly ranking snapshots
- Team detail and conference information
- Weekly odds and matchup data
- Responsive frontend for browsing rankings and team pages
- SQLite-backed local development database with easy local setup

## Local development

### 1) Set up the backend

From the repository root:

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
```

If you are using external game or odds data, create a local `.env` file in the `backend` folder and set any required environment variables, such as `CFBD_API_KEY`.

Start the API:

```bash
cd backend
uvicorn app.main:app --reload
```

The API will be available at:

- http://localhost:8000
- Health check: http://localhost:8000/health

### 2) Set up the frontend

From the repository root:

```bash
cd frontend
npm install
npm run dev
```

The app will be served by Vite, typically at:

- http://localhost:5173

## API highlights

The backend exposes ranking and team data via FastAPI routers, including:

- `/api/rankings`
- `/api/teams`
- `/api/odds`

## Ratings

Each team gets three numbers, all in points per game relative to an average team (0 = league average, positive = better):

- **Offense** -- points the team scores above an average offense.
- **Defense** -- points the team holds opponents below an average defense (positive = good defense).
- **Overall** -- offense + defense. This is the number the rankings sort on; the gap between two teams' overall ratings is the expected margin of victory on a neutral field. The weekly odds and the matchup simulator use the offense and defense ratings separately.

The model (`backend/app/ranking.py`) regresses points scored on the offense, the opposing defense, and game location. After pulling in this version, run `python -m scripts.compute_rankings --year <year> [--through-week N]` to fill in offense/defense for snapshots computed earlier -- until then they show as `null` / a dash. The new `power_ratings` columns are added to an existing `cfbrank.db` automatically on startup.

## Weekly odds

`GET /api/odds/weekly` simulates every upcoming game of the week **1,000 times** (`backend/app/routers/odds.py`). It uses the same score simulator as the matchup page, each team's offense and defense ratings going into the week, and the usual home-field edge unless the game is at a neutral site. For each game the page shows, next to the market spread and moneylines:

- **Win %** -- the share of the 1,000 simulations each team won.
- **Home Pts / Away Pts** -- the average points each team scored (the projected score).
- **Margin** -- the average of home score minus away score.
- **Total** -- the average combined score.

Each game's simulations are seeded from its game id, so the numbers don't change on refresh until a team's ratings do. A game is skipped when a team has no offense/defense rating yet (re-run `scripts.compute_rankings`). Team logos come from `teams.logo_url`; a team without one gets a blank placeholder.

The simulator's win probabilities are flatter than the logistic formula the page used before (a 14-point rating gap went from 90% to 77%): see section 3 of the Methodology page.

## Playoff projection

`python -m scripts.simulate_season` replays the rest of the regular season and each conference's title game thousands of times (`backend/app/season_simulation.py`). After every simulated season it picks the 12-team College Football Playoff field (`backend/app/playoff.py`), seeds it, and plays the bracket (`backend/app/playoff_bracket.py`). The rankings table shows how often each team makes the field (**Playoff %**) and how far it gets (**CFP Bye %**, **Quarters %**, **Semis %**, **Final %** and **Champ %**).

**Who is in the field** (the 2026-27 rules):

1. The **ACC, Big Ten, SEC and Big 12 champions** get in automatically, whatever their ranking.
2. The **best Group of 6 champion** (American, Conference USA, Mid-American, Mountain West, Pac-12, Sun Belt) gets one more automatic spot: the neural network rates each of those champions and the highest probability wins.
3. **Notre Dame** gets in automatically if it is a top-12 team. There is no committee ranking in the data, so "top 12" is the network's own ordering of all eligible FBS teams. This only matters when the automatic bids would otherwise crowd Notre Dame out of the at-large spots.
4. The **remaining spots are at large** (seven, or six when Notre Dame took an automatic bid): the network rates every other FBS team (independents and Group of 6 champions that lost out on step 2 included) and the highest probabilities get in.

The network is a scikit-learn `MLPClassifier` trained on `backend/data/playoff_data.csv` (columns `playoffs`, `sos`, `wins`, `loses`; one row per past team-season) and is rebuilt in a few milliseconds each time the simulation starts. A team's `sos` is the average overall rating of every regular-season opponent it played (FCS opponents included), using the ratings as they stand after the last simulated week; `wins` and `loses` are regular-season only, so a conference title game never counts toward them.

**The bracket:**

- The field is **seeded 1-12 by overall rating** (offense + defense) after the last simulated week. That stands in for the committee's ranking, which this project doesn't have; `seed_field` in `playoff_bracket.py` is the one place to change if you get one. The network is not used for seeding, because it answers "does this team make the field?" and rates every strong team near 1.
- The top four seeds get a **first-round bye**. Round 1 is 5v12, 6v11, 7v10 and 8v9 on the higher seed's campus (the usual home-field edge). The quarterfinals (1 vs the 8/9 winner, 4 vs 5/12, 2 vs 7/10, 3 vs 6/11), the semifinals and the final are at neutral sites, and there is **no re-seeding**.
- Games use the same game simulator as everything else, with the ratings from after the last regular-season week; playoff results are not fed back into the ratings.
- The bracket draws from its own random stream (derived from `--seed`), so adding it changed none of the other columns for a given seed.
- The bracket is data (`TWELVE_TEAM_BRACKET`): a different format is another tuple of `BracketGame`s. The field size, the Group of 6 and the Notre Dame rule are constants at the top of `playoff.py`.

Each odds column is a share of *all* simulated seasons, so a team that misses the field counts as a 0 in the bracket columns, not as missing data. With the full field the columns add up exactly: 1200% for the field, 400% for byes, 800% for the quarterfinals, 400% semifinals, 200% final and 100% champion. The new `season_projections` columns are added to an existing `cfbrank.db` automatically on startup; rerun `scripts.simulate_season` to fill them.

## Data and scripts

The backend includes ingestion and ranking scripts under `backend/scripts` for populating data sources and generating ranking snapshots. These are useful when you want to seed teams, conferences, and computed rating data for local testing.

## Notes

- The project uses SQLite by default for local development.
- The frontend is configured to call the backend from the local Vite development server.
- The app is designed to support an iterative sports data pipeline without requiring a production database during early development.

## License

This project is currently maintained as a local application and does not include a separate licensing file in the repository yet.