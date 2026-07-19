"""BIRD dataset loading and schema extraction.

Shared by generate.py, execute.py, judge.py and the annotation app — anything
that needs the DDL for a database or the dev-set records themselves.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIRD_ROOT = REPO_ROOT / "data" / "bird" / "dev_20240627"
DEV_JSON = BIRD_ROOT / "dev.json"
DB_ROOT = BIRD_ROOT / "dev_databases"


def db_path(db_id: str) -> Path:
    return DB_ROOT / db_id / f"{db_id}.sqlite"


@lru_cache(maxsize=1)
def load_dev() -> list[dict]:
    """The 1,534 dev question/gold-SQL records."""
    with DEV_JSON.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def schema_ddl(db_id: str) -> str:
    """CREATE statements for every table in a database, as stored by SQLite.

    Using the stored DDL rather than a reconstruction keeps the exact quoting
    and column names the gold queries rely on — BIRD schemas have columns like
    `Free Meal Count (K-12)` that only work backtick-quoted.
    """
    con = sqlite3.connect(f"file:{db_path(db_id)}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL "
            "ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    return "\n\n".join(sql.strip() for (sql,) in rows)
