import sqlite3
from pathlib import Path
from typing import Optional, Any

from app.core.paths import DATA_DIR

DB_PATH = DATA_DIR / "app.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = _connect()
    cur = con.cursor()

    # New table: one row per upload/job (audio OR scene)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,            -- 'audio' or 'scene'
        language TEXT,                 -- only for audio jobs
        model_size TEXT,               -- only for audio jobs
        stage TEXT NOT NULL,
        progress INTEGER NOT NULL,
        error TEXT
    );
    """)

    con.commit()
    con.close()


def create_job(job_id: str, mode: str, language: Optional[str] = None, model_size: Optional[str] = None) -> None:
    if mode not in ("audio", "scene"):
        raise ValueError("mode must be 'audio' or 'scene'")

    con = _connect()
    cur = con.cursor()

    cur.execute("""
    INSERT INTO jobs (job_id, mode, language, model_size, stage, progress, error)
    VALUES (?, ?, ?, ?, ?, ?, NULL);
    """, (job_id, mode, language, model_size, "UPLOADED", 0))

    con.commit()
    con.close()


def update_status(job_id: str, stage: str, progress: int, error: Optional[str] = None) -> None:
    con = _connect()
    cur = con.cursor()

    cur.execute("""
    UPDATE jobs
    SET stage = ?, progress = ?, error = ?
    WHERE job_id = ?;
    """, (stage, int(progress), error, job_id))

    con.commit()
    con.close()


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    con = _connect()
    cur = con.cursor()

    cur.execute("SELECT * FROM jobs WHERE job_id = ?;", (job_id,))
    row = cur.fetchone()
    con.close()

    return dict(row) if row else None


def delete_job_row(job_id: str) -> None:
    con = _connect()
    cur = con.cursor()

    cur.execute("DELETE FROM jobs WHERE job_id = ?;", (job_id,))
    con.commit()
    con.close()