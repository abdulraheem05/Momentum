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