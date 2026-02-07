import sqlite3
from pathlib import Path
from typing import Optional

from app.core.paths import DATA_DIR

DB_PATH = DATA_DIR/"app.db"

def _connect() -> sqlite3.Connection :
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con 

def _init() -> None:
    con = _connect()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos(
                video_id TEXT PRIMARY KEY,
                language TEXT NOT NULL,
                model_size TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress TEXT NOT NULL,
                error TEXT
            )
    """)

    con.commit()
    con.close()

def create_video(video_id: str, language: str, model_size: str) -> None:
    con = _connect()
    cur = con.cursor()

    cur.execute("""
    INSERT INTO videos (video_id, language, model_size, stage, progress, error)
    VALUES (?, ?, ?, ?, ?, NULL);
    """, (video_id, language, model_size, "UPLOADED", 0))

    con.commit()
    con.close()


def update_status(video_id: str, stage: str, progress: int, error: Optional[str] = None) -> None:
    con = _connect()
    cur = con.cursor()

    cur.execute("""
    UPDATE videos
    SET stage = ?, progress = ?, error = ?
    WHERE video_id = ?;
    """, (stage, progress, error, video_id))

    con.commit()
    con.close()

def get_video(video_id: str) -> Optional[dict]:
    con = _connect()
    cur = con.cursor()

    cur.execute("SELECT * FROM videos WHERE video_id = ?;", (video_id,))
    row = cur.fetchone()
    con.close()

    return dict(row) if row else None

def delete_video_row(video_id: str) -> None:
    con = _connect()
    cur = con.cursor()
    cur.execute("DELETE FROM videos WHERE video_id = ?;", (video_id,))
    con.commit()
    con.close()