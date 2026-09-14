import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()  # reads backend/.env when running locally

app = FastAPI(title="CFB Rank API", version="0.1.0")


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
