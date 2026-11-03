"""Cola SQLite con reclamación atómica y arrendamientos."""
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from infra.database import DatabaseManager
from core.result import Result


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


class ScrapingBlackboard:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def enqueue_task(
        self,
        source_plugin: str,
        target_plugin: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> Result[int]:
        if not source_plugin.strip() or not target_plugin.strip():
            return Result.fail("source_plugin y target_plugin son obligatorios.", "VALIDATION_ERROR")
        if max_attempts < 1:
            return Result.fail("max_attempts debe ser mayor que cero.", "VALIDATION_ERROR")
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            with self.db.get_connection() as conn:
                if idempotency_key is not None:
                    existing = conn.execute(
                        "SELECT id FROM task_queue WHERE target_plugin=? AND idempotency_key=?",
                        (target_plugin, idempotency_key),
                    ).fetchone()
                    if existing:
                        return Result.ok(int(existing["id"]))
                cursor = conn.execute(
                    """INSERT INTO task_queue
                    (source_plugin, target_plugin, payload, idempotency_key, max_attempts, available_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (source_plugin, target_plugin, payload_json, idempotency_key, max_attempts,
                     _stamp(available_at or _utc_now())),
                )
                return Result.ok(int(cursor.lastrowid))
        except sqlite3.IntegrityError as exc:
            # La restricción única resuelve también la carrera de idempotencia.
            if idempotency_key is not None:
                with self.db.get_connection() as conn:
                    row = conn.execute(
                        "SELECT id FROM task_queue WHERE target_plugin=? AND idempotency_key=?",
                        (target_plugin, idempotency_key),
                    ).fetchone()
                    if row:
                        return Result.ok(int(row["id"]))
            return Result.fail(str(exc), "DB_CONSTRAINT_ERROR")
        except Exception as exc:
            return Result.fail(str(exc), "DB_ERROR")

    def fetch_pending_task(self, target_plugin: str) -> Result[dict[str, Any] | None]:
        """Consulta de solo lectura; no debe usarse como mecanismo de consumo concurrente."""
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    """SELECT * FROM task_queue WHERE target_plugin=? AND status='PENDING'
                    AND available_at <= ? ORDER BY id LIMIT 1""",
                    (target_plugin, _stamp(_utc_now())),
                ).fetchone()
                return Result.ok(self._decode_task(row) if row else None)
        except Exception as exc:
            return Result.fail(str(exc), "DB_ERROR")

    def claim_pending_task(self, target_plugin: str, lease_seconds: int = 300) -> Result[dict[str, Any] | None]:
        if lease_seconds < 1:
            return Result.fail("lease_seconds debe ser mayor que cero.", "VALIDATION_ERROR")
        token = str(uuid.uuid4())
        now = _utc_now()
        now_text = _stamp(now)
        lease_until = _stamp(now + timedelta(seconds=lease_seconds))
        try:
            with self.db.get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT id FROM task_queue
                    WHERE target_plugin=? AND status='PENDING' AND available_at <= ?
                    ORDER BY id LIMIT 1""",
                    (target_plugin, now_text),
                ).fetchone()
                if row is None:
                    return Result.ok(None)
                task_id = int(row["id"])
                updated = conn.execute(
                    """UPDATE task_queue SET status='PROCESSING', attempts=attempts+1,
                    lease_token=?, lease_until=?, updated_at=?
                    WHERE id=? AND status='PENDING'""",
                    (token, lease_until, now_text, task_id),
                )
                if updated.rowcount != 1:
                    return Result.ok(None)
                claimed = conn.execute("SELECT * FROM task_queue WHERE id=?", (task_id,)).fetchone()
                return Result.ok(self._decode_task(claimed))
        except Exception as exc:
            return Result.fail(str(exc), "DB_ERROR")

    def complete_task(self, task_id: int, lease_token: str) -> Result[bool]:
        now = _stamp(_utc_now())
        try:
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    """UPDATE task_queue SET status='COMPLETED', lease_token=NULL, lease_until=NULL,
                    last_error=NULL, updated_at=?
                    WHERE id=? AND status='PROCESSING' AND lease_token=? AND lease_until > ?""",
                    (now, task_id, lease_token, now),
                )
                return Result.ok(cur.rowcount == 1)
        except Exception as exc:
            return Result.fail(str(exc), "DB_ERROR")

    def fail_task(
        self,
        task_id: int,
        lease_token: str,
        error: str,
        *,
        retryable: bool = True,
        retry_delay_seconds: int = 30,
    ) -> Result[bool]:
        now_dt = _utc_now()
        now = _stamp(now_dt)
        try:
            with self.db.get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT attempts, max_attempts FROM task_queue
                    WHERE id=? AND status='PROCESSING' AND lease_token=? AND lease_until > ?""",
                    (task_id, lease_token, now),
                ).fetchone()
                if row is None:
                    return Result.ok(False)
                retry = retryable and int(row["attempts"]) < int(row["max_attempts"])
                status = "PENDING" if retry else "FAILED"
                available = _stamp(now_dt + timedelta(seconds=max(0, retry_delay_seconds))) if retry else now
                cur = conn.execute(
                    """UPDATE task_queue SET status=?, available_at=?, lease_token=NULL,
                    lease_until=NULL, last_error=?, updated_at=?
                    WHERE id=? AND status='PROCESSING' AND lease_token=? AND lease_until > ?""",
                    (status, available, error[:4000], now, task_id, lease_token, now),
                )
                return Result.ok(cur.rowcount == 1)
        except Exception as exc:
            return Result.fail(str(exc), "DB_ERROR")

    def recover_expired_tasks(self) -> Result[int]:
        now = _stamp(_utc_now())
        try:
            with self.db.get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute(
                    "SELECT id, attempts, max_attempts FROM task_queue WHERE status='PROCESSING' AND lease_until <= ?",
                    (now,),
                ).fetchall()
                recovered = 0
                for row in rows:
                    status = "PENDING" if int(row["attempts"]) < int(row["max_attempts"]) else "FAILED"
                    cur = conn.execute(
                        """UPDATE task_queue SET status=?, lease_token=NULL, lease_until=NULL,
                        last_error=COALESCE(last_error, 'Lease expirado'), updated_at=?
                        WHERE id=? AND status='PROCESSING'""",
                        (status, now, int(row["id"])),
                    )
                    recovered += cur.rowcount
                return Result.ok(recovered)
        except Exception as exc:
            return Result.fail(str(exc), "DB_ERROR")

    @staticmethod
    def _decode_task(row: sqlite3.Row) -> dict[str, Any]:
        task = dict(row)
        task["payload"] = json.loads(task["payload"])
        return task
