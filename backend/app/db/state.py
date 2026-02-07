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

