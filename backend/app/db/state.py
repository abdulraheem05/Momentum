import psycopg2
from psycopg2 import extras
import os
from dotenv import load_dotenv
from typing import Optional, Any

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def _connect():
    # We use extras.RealDictCursor so the data comes back as a dictionary automatically
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=extras.RealDictCursor)
    return conn

def init_db() -> None:
    conn = _connect()
    cur = conn.cursor()

    # Postgres syntax for CREATE TABLE
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,             -- 'audio' or 'scene'
        language TEXT,                  -- only for audio jobs
        model_size TEXT,                -- only for audio jobs
        stage TEXT NOT NULL,
        progress INTEGER NOT NULL,
        error TEXT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

def create_job(job_id: str, mode: str, language: Optional[str] = None, model_size: Optional[str] = None) -> None:
    if mode not in ("audio", "scene"):
        raise ValueError("mode must be 'audio' or 'scene'")

    conn = _connect()
    cur = conn.cursor()

    # Note: Changed ? to %s for PostgreSQL
    cur.execute("""
    INSERT INTO jobs (job_id, mode, language, model_size, stage, progress, error)
    VALUES (%s, %s, %s, %s, %s, %s, NULL);
    """, (job_id, mode, language, model_size, "UPLOADED", 0))

    conn.commit()
    cur.close()
    conn.close()

def update_status(job_id: str, stage: str, progress: int, error: Optional[str] = None) -> None:
    conn = _connect()
    cur = conn.cursor()

    # Note: Changed ? to %s
    cur.execute("""
    UPDATE jobs
    SET stage = %s, progress = %s, error = %s
    WHERE job_id = %s;
    """, (stage, int(progress), error, job_id))

    conn.commit()
    cur.close()
    conn.close()

def get_job(job_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("SELECT * FROM jobs WHERE job_id = %s;", (job_id,))
    row = cur.fetchone()
    
    cur.close()
    conn.close()

    # RealDictCursor returns a dictionary already, so we just return the row
    return row

def delete_job_row(job_id: str) -> None:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("DELETE FROM jobs WHERE job_id = %s;", (job_id,))
    conn.commit()
    cur.close()
    conn.close()