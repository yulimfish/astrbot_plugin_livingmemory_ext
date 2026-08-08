#!/usr/bin/env python3
"""Diagnose the upstream LivingMemory database for the diary_digest scope bug.

Read-only (URI mode=ro). Prints the schema version, session_id distribution,
and recent rows so a group-scoped diary rule returning 0 memories can be
root-caused from a single run.

Usage:
    python3 scripts/diagnose_memories.py [path/to/livingmemory.db]

Default path matches the AstrBot working-directory layout:
    data/plugin_data/astrbot_plugin_livingmemory/livingmemory.db
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = "data/plugin_data/astrbot_plugin_livingmemory/livingmemory.db"

_ACTIVE_SQL = "WHERE COALESCE(json_extract(metadata, '$.status'), 'active') = 'active'"


def _ts(iso: str) -> str:
    return f"{datetime.fromtimestamp(float(iso)).isoformat()}"


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB)
    if not path.exists():
        print(f"DB not found: {path}")
        return 1

    try:
        db = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        # WAL databases copied without their -wal/-shm files can reject a
        # read-only URI connection; fall back to a normal read-only session.
        db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    print(f"== db: {path}")
    print(f"user_version: {db.execute('PRAGMA user_version').fetchone()[0]}")

    tables = [
        r["name"]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ]
    print(f"tables: {tables}")
    if "documents" not in tables:
        print("no 'documents' table; nothing to diagnose")
        return 1

    total = db.execute("SELECT count(*) FROM documents").fetchone()[0]
    active = db.execute(f"SELECT count(*) FROM documents {_ACTIVE_SQL}").fetchone()[0]
    print(f"documents: total={total} active={active}")

    print("== distinct session_id (top 30) ==")
    for r in db.execute(
        "SELECT json_extract(metadata, '$.session_id') s, count(*) c "
        "FROM documents GROUP BY s ORDER BY c DESC LIMIT 30"
    ):
        print(f"  {r['c']:6d}  {r['s']!r}")

    print("== latest 5 raw metadata ==")
    for r in db.execute(
        "SELECT metadata FROM documents "
        "ORDER BY CAST(json_extract(metadata, '$.create_time') AS REAL) DESC "
        "LIMIT 5"
    ):
        print("  " + str(r["metadata"]))

    print("== time boundaries ==")
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"  now          = {now.isoformat()}")
    print(f"  today  start = {_ts(today.timestamp())}")
    print(f"  yesterday st = {_ts((today - timedelta(days=1)).timestamp())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
