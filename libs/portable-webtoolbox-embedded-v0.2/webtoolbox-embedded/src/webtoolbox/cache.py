"""SQLite response cache, keyed by normalized URL, query and extraction recipe."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                saved_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )""")

    def _connect(self) -> sqlite3.Connection:
        # Short-lived connections permit calls from threads and separate apps/processes.
        con = sqlite3.connect(self.path, timeout=15)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=15000")
        return con

    def get(self, key: str, *, allow_stale: bool = False) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT value, saved_at, expires_at FROM cache WHERE cache_key=?", (key,)).fetchone()
        if row is None:
            return None
        if not allow_stale and row[2] <= time.time():
            return None
        obj = json.loads(row[0])
        obj["cached"] = True
        obj["stale"] = row[2] <= time.time()
        return obj

    def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        now = time.time()
        # INSERT...ON CONFLICT prevents duplicate entries when two agents query together.
        with self._connect() as con:
            con.execute("""INSERT INTO cache(cache_key, value, saved_at, expires_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                value=excluded.value, saved_at=excluded.saved_at, expires_at=excluded.expires_at""",
                (key, json.dumps(value, ensure_ascii=False), now, now + max(0, ttl)))

    def stats(self) -> dict[str, int]:
        with self._connect() as con:
            total, fresh = con.execute("SELECT COUNT(*), SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) FROM cache", (time.time(),)).fetchone()
        return {"entries": total, "fresh_entries": fresh or 0}

    def prune(self) -> int:
        # Expired entries can be cleared without touching application-owned contacts.
        with self._connect() as con:
            cur = con.execute("DELETE FROM cache WHERE expires_at <= ?", (time.time(),))
            return cur.rowcount
