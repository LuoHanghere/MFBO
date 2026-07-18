"""SQLite experiment ledger with resumable trial and event state."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ExperimentStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS trials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    design_json TEXT NOT NULL,
                    fidelity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    objective REAL,
                    constraints_json TEXT,
                    metrics_json TEXT,
                    predicted_json TEXT,
                    relative_cost REAL NOT NULL,
                    run_dir TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    trial_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(trial_id) REFERENCES trials(id)
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def set_metadata(self, key: str, value: Any) -> None:
        text = json.dumps(value, ensure_ascii=False)
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO metadata(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, text),
            )

    def metadata(self) -> dict[str, Any]:
        with self._connect() as db:
            return {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM metadata")}

    def add_event(self, message: str, *, level: str = "info", trial_id: int | None = None) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO events(level,message,trial_id,created_at) VALUES(?,?,?,?)",
                (level, message, trial_id, _now()),
            )

    def create_trial(
        self,
        design: dict[str, Any],
        fidelity: str,
        source: str,
        relative_cost: float,
        predicted: dict[str, Any] | None = None,
    ) -> int:
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """INSERT INTO trials(
                    design_json,fidelity,status,source,predicted_json,relative_cost,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    json.dumps(design, sort_keys=True), fidelity, "pending", source,
                    json.dumps(predicted or {}), relative_cost, _now(),
                ),
            )
            return int(cursor.lastrowid)

    def mark_running(self, trial_id: int, run_dir: str | Path) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE trials SET status='running',run_dir=?,started_at=? WHERE id=?",
                (str(run_dir), _now(), trial_id),
            )

    def complete(
        self,
        trial_id: int,
        objective: float,
        constraints: dict[str, float],
        metrics: dict[str, Any],
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """UPDATE trials SET status='completed',objective=?,constraints_json=?,
                   metrics_json=?,finished_at=? WHERE id=?""",
                (objective, json.dumps(constraints), json.dumps(metrics), _now(), trial_id),
            )

    def fail(self, trial_id: int, error: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE trials SET status='failed',error=?,finished_at=? WHERE id=?",
                (error[-12000:], _now(), trial_id),
            )

    def recover_interrupted(self) -> int:
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """UPDATE trials SET status='failed',error=?,finished_at=?
                   WHERE status='running'""",
                ("controller interrupted before trial completion", _now()),
            )
            return int(cursor.rowcount)

    def trials(self, statuses: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM trials"
        params: tuple[Any, ...] = ()
        if statuses:
            query += " WHERE status IN (" + ",".join("?" for _ in statuses) + ")"
            params = statuses
        query += " ORDER BY id"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self._decode(row) for row in rows]

    def events(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def cost_used(self) -> float:
        with self._connect() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(relative_cost),0) AS cost FROM trials WHERE status='completed'"
            ).fetchone()
        return float(row["cost"])

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("design_json", "constraints_json", "metrics_json", "predicted_json"):
            target = key.removesuffix("_json")
            item[target] = json.loads(item.pop(key) or "{}")
        return item
