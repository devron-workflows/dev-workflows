import os

from fastapi import FastAPI
from dotenv import load_dotenv
import psycopg

# Load environment variables from .env
load_dotenv(dotenv_path=".env")

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(
    title="Dev Workflows",
    description="Weekly planning & execution platform for field reps",
    version="0.1.0",
)

@app.get("/")
def root():
    return {"status": "ok", "message": "Dev Workflows API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/db-check")
def db_check():
    if not DATABASE_URL:
        return {"ok": False, "error": "DATABASE_URL not set"}

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return {"ok": True, "database": "connected"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

