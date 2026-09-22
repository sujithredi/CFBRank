## Run the backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/) to confirm the backend is running. It should show:

`{"message": "CFB Rank API is running"}`

Visit [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) to confirm the `.env` key is loaded. It should show:

`cfbd_api_key_configured: true`

The API key itself will not be printed.

Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the auto-generated FastAPI documentation.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Visit the local URL that Vite prints, typically [http://localhost:5173/](http://localhost:5173/). It should show a **CFB Rank** heading.

python -m scripts.compute_rankings --year 2026
python -m scripts.ingest_games --year 2026