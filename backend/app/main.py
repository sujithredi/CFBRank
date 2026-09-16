import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import rankings
from app.database import init_db
from app.routers import odds, teams

load_dotenv()  # reads backend/.env when running locally


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="CFB Rank API", version="0.1.0", lifespan=lifespan)

# Allow the Vite dev server (and any other localhost port during dev) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rankings.router)
app.include_router(teams.router)
app.include_router(odds.router)


@app.get("/")
def read_root():
    return {"message": "CFB Rank API is running"}


@app.get("/health")
def health_check():
    """
    Quick check that the app booted and picked up its environment.
    Does NOT return the key itself -- only whether it's set.
    """
    return {
        "status": "ok",
        "cfbd_api_key_configured": bool(os.getenv("CFBD_API_KEY")),
    }