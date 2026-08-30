from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import AttemptRecord, BenchmarkCondition, BenchmarkTask, ExperimentStatus

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class BenchmarkStore(AbstractContextManager["BenchmarkStore"]):
    """Per-experiment durable state with append-only attempt records."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        self._lock = threading.RLock()
        if read_only:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            uri = f"file:{self.path.as_posix()}?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True, timeout=30)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=30)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if not read_only:
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._migrate()

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_info "
                "(version INTEGER NOT NULL, created_at TEXT NOT NULL)"
            )
            row = self._connection.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO schema_info(version, created_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported benchmark schema {row['version']}; expected {SCHEMA_VERSION}"
                )
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    heartbeat_at TEXT,
                    worker_pid INTEGER,
                    manifest_path TEXT NOT NULL,
                    private_directory TEXT NOT NULL,
                    publishable_directory TEXT NOT NULL,
                    stop_requested INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_identity TEXT PRIMARY KEY,
                    benchmark TEXT NOT NULL,
                    benchmark_version TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    entry_point TEXT NOT NULL,
                    reference_input_tokens INTEGER NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    order_index INTEGER NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS task_cells (
                    task_identity TEXT NOT NULL REFERENCES tasks(task_identity),
                    condition TEXT NOT NULL,
                    schedule_index INTEGER NOT NULL UNIQUE,
                    completed INTEGER NOT NULL DEFAULT 0,
                    final_status TEXT,
                    completed_at TEXT,
                    PRIMARY KEY(task_identity, condition)
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_identity TEXT NOT NULL REFERENCES tasks(task_identity),
                    condition TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    selected_tier TEXT NOT NULL,
                    selected_model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(task_identity, condition, attempt_number)
                );
                CREATE TABLE IF NOT EXISTS resource_samples (
                    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_identity TEXT,
                    condition TEXT,
                    attempt_number INTEGER,
                    sampled_at TEXT NOT NULL,
                    cpu_percent REAL,
                    ram_bytes INTEGER,
                    ram_percent REAL,
                    source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    task_identity TEXT,
                    condition TEXT,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def create_experiment(
        self,
        *,
        experiment_id: str,
        manifest_path: Path,
        private_directory: Path,
        publishable_directory: Path,
        tasks: Iterable[BenchmarkTask],
        schedule: Iterable[tuple[str, BenchmarkCondition]],
    ) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        task_list = tuple(tasks)
        schedule_list = tuple(schedule)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO experiments(
                    experiment_id, status, created_at, manifest_path,
                    private_directory, publishable_directory
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    ExperimentStatus.PREPARED.value,
                    utc_now(),
                    str(manifest_path),
                    str(private_directory),
                    str(publishable_directory),
                ),
            )
            self._connection.executemany(
                """
                INSERT INTO tasks(
                    task_identity, benchmark, benchmark_version, task_id, prompt,
                    entry_point, reference_input_tokens, source_sha256, order_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        task.identity(),
                        task.benchmark,
                        task.benchmark_version,
                        task.task_id,
                        task.prompt,
                        task.entry_point,
                        task.reference_input_tokens,
                        task.source_sha256,
                        index,
                    )
                    for index, task in enumerate(task_list)
                ],
            )
            self._connection.executemany(
                """
                INSERT INTO task_cells(task_identity, condition, schedule_index)
                VALUES (?, ?, ?)
                """,
                [
                    (task_identity, condition.value, index)
                    for index, (task_identity, condition) in enumerate(schedule_list)
                ],
            )

    def set_status(
        self,
        experiment_id: str,
        status: ExperimentStatus,
        *,
        worker_pid: int | None = None,
        error: str | None = None,
    ) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        now = utc_now()
        assignments = ["status = ?", "heartbeat_at = ?"]
        values: list[Any] = [status.value, now]
        if worker_pid is not None:
            assignments.append("worker_pid = ?")
            values.append(worker_pid)
        if status == ExperimentStatus.RUNNING:
            assignments.append("started_at = COALESCE(started_at, ?)")
            values.append(now)
        if status in {
            ExperimentStatus.STOPPED,
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.RESOURCE_VIOLATION,
        }:
            assignments.append("ended_at = ?")
            values.append(now)
        if error is not None:
            assignments.append("error = ?")
            values.append(error[:4000])
        values.append(experiment_id)
        with self._lock, self._connection:
            updated = self._connection.execute(
                f"UPDATE experiments SET {', '.join(assignments)} WHERE experiment_id = ?",
                values,
            ).rowcount
        if updated != 1:
            raise KeyError(experiment_id)

    def heartbeat(self, experiment_id: str, worker_pid: int) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE experiments SET heartbeat_at = ?, worker_pid = ? WHERE experiment_id = ?",
                (utc_now(), worker_pid, experiment_id),
            )

    def request_stop(self, experiment_id: str) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        with self._lock, self._connection:
            updated = self._connection.execute(
                """
                UPDATE experiments
                SET stop_requested = 1, status = ?, heartbeat_at = ?
                WHERE experiment_id = ?
                """,
                (ExperimentStatus.STOP_REQUESTED.value, utc_now(), experiment_id),
            ).rowcount
        if updated != 1:
            raise KeyError(experiment_id)

    def stop_requested(self, experiment_id: str) -> bool:
        row = self._connection.execute(
            "SELECT stop_requested FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return bool(row["stop_requested"])

    def clear_stop_request(self, experiment_id: str) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        with self._connection:
            self._connection.execute(
                "UPDATE experiments SET stop_requested = 0 WHERE experiment_id = ?",
                (experiment_id,),
            )

    def next_cell(self) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT c.task_identity, c.condition, c.schedule_index, t.*
            FROM task_cells AS c
            JOIN tasks AS t ON t.task_identity = c.task_identity
            WHERE c.completed = 0
            ORDER BY c.schedule_index
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row is not None else None

    def attempts_for_cell(self, task_identity: str, condition: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT payload_json FROM attempts
            WHERE task_identity = ? AND condition = ?
            ORDER BY attempt_number
            """,
            (task_identity, condition),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def record_attempt(self, attempt: AttemptRecord, raw_results_path: Path) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        payload = attempt.as_dict()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        task_identity = f"{attempt.benchmark}:{attempt.task_id}"
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """
                    INSERT INTO attempts(
                        task_identity, condition, attempt_number, selected_tier,
                        selected_model, status, started_at, ended_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_identity,
                        attempt.condition.value,
                        attempt.attempt_number,
                        attempt.selected_tier.value,
                        attempt.selected_model,
                        attempt.status.value,
                        attempt.start_time,
                        attempt.end_time,
                        encoded,
                    ),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
            raw_results_path.parent.mkdir(parents=True, exist_ok=True)
            with raw_results_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")
                stream.flush()
                os.fsync(stream.fileno())

    def synchronize_raw_results(self, raw_results_path: Path) -> int:
        """Append SQLite-authoritative attempts missing after an interrupted file append."""

        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        existing: set[tuple[str, str, str, int]] = set()
        needs_separator = False
        if raw_results_path.is_file():
            raw = raw_results_path.read_bytes()
            needs_separator = bool(raw and not raw.endswith(b"\n"))
            for line in raw.splitlines():
                try:
                    payload = json.loads(line)
                    existing.add(_attempt_key(payload))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
        missing = [
            payload for payload in self.all_attempts() if _attempt_key(payload) not in existing
        ]
        if not missing:
            return 0
        raw_results_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_results_path.open("ab") as stream:
            if needs_separator:
                stream.write(b"\n")
            for payload in missing:
                stream.write(
                    json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
                        "utf-8"
                    )
                    + b"\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        return len(missing)

    def complete_cell(self, task_identity: str, condition: str, final_status: str) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        with self._lock, self._connection:
            updated = self._connection.execute(
                """
                UPDATE task_cells
                SET completed = 1, final_status = ?, completed_at = ?
                WHERE task_identity = ? AND condition = ?
                """,
                (final_status, utc_now(), task_identity, condition),
            ).rowcount
        if updated != 1:
            raise KeyError(f"{task_identity}:{condition}")

    def record_resource_sample(
        self,
        *,
        task_identity: str | None,
        condition: str | None,
        attempt_number: int | None,
        cpu_percent: float | None,
        ram_bytes: int | None,
        ram_percent: float | None,
        source: str,
    ) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO resource_samples(
                    task_identity, condition, attempt_number, sampled_at,
                    cpu_percent, ram_bytes, ram_percent, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_identity,
                    condition,
                    attempt_number,
                    utc_now(),
                    cpu_percent,
                    ram_bytes,
                    ram_percent,
                    source,
                ),
            )

    def record_event(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        task_identity: str | None = None,
        condition: str | None = None,
    ) -> None:
        if self.read_only:
            raise RuntimeError("read-only benchmark store")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO events(recorded_at, kind, task_identity, condition, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    kind,
                    task_identity,
                    condition,
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )

    def status(self) -> dict[str, Any]:
        experiment = self._connection.execute("SELECT * FROM experiments LIMIT 1").fetchone()
        if experiment is None:
            raise RuntimeError("benchmark database does not contain an experiment")
        counts = self._connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS completed
            FROM task_cells
            """
        ).fetchone()
        current = self._connection.execute(
            """
            SELECT t.benchmark, t.task_id, c.condition, c.schedule_index
            FROM task_cells AS c JOIN tasks AS t ON t.task_identity = c.task_identity
            WHERE c.completed = 0 ORDER BY c.schedule_index LIMIT 1
            """
        ).fetchone()
        result = dict(experiment)
        result.update(
            {
                "total_cells": int(counts["total"] or 0),
                "completed_cells": int(counts["completed"] or 0),
                "remaining_cells": int(counts["total"] or 0) - int(counts["completed"] or 0),
                "current": dict(current) if current is not None else None,
            }
        )
        return result

    def all_attempts(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT payload_json FROM attempts ORDER BY attempt_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def resource_extrema(self) -> dict[str, Any]:
        row = self._connection.execute(
            """
            SELECT MAX(cpu_percent) AS peak_cpu_percent,
                   MAX(ram_bytes) AS peak_ram_bytes,
                   MAX(ram_percent) AS peak_ram_percent
            FROM resource_samples
            """
        ).fetchone()
        return dict(row) if row is not None else {}

    def tasks(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self._connection.execute("SELECT * FROM tasks ORDER BY order_index")
        ]


def _attempt_key(payload: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(payload["benchmark"]),
        str(payload["task_id"]),
        str(payload["condition"]),
        int(payload["attempt_number"]),
    )
