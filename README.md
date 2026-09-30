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

## Data and scripts

The backend includes ingestion and ranking scripts under `backend/scripts` for populating data sources and generating ranking snapshots. These are useful when you want to seed teams, conferences, and computed rating data for local testing.

## Notes

- The project uses SQLite by default for local development.
- The frontend is configured to call the backend from the local Vite development server.
- The app is designed to support an iterative sports data pipeline without requiring a production database during early development.

## License

This project is currently maintained as a local application and does not include a separate licensing file in the repository yet.
