## Run the backend

cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Visit http://127.0.0.1:8000/ should show `{"message": "CFB Rank API is running"}`.
Visit http://127.0.0.1:8000/health confirms `.env` key loaded (`cfbd_api_key_configured: true`) without printing the key itself.
Visit http://127.0.0.1:8000/docs for the auto-generated FastAPI docs.

## Run the frontend

cd frontend
npm install
npm run dev

Visit the local URL Vite prints (typically http://localhost:5173/) should show a "CFB Rank" heading.