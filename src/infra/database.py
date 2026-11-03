"""Persistencia SQLite con ruta estable y transacciones explícitas."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from infra.logger import get_logger

logger = get_logger("database_manager")


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DatabaseManager:
    def __init__(self, db_path: str | Path | None = None) -> None:
        configured = db_path or os.environ.get("SCRAPER_ECOSYSTEM_DB_PATH")
        path = Path(configured).expanduser() if configured else PROJECT_ROOT / "storage" / "blackboard.db"
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        self.db_path = path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level="DEFERRED")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def volcar_registros_finales(self, limite: int = 10) -> None:
        """Consulta y vuelca en el log los últimos expedientes registrados en la base de datos."""
        try:
            # Asegúrate de ajustar la ruta de tu archivo .db si es necesario
            db_path = getattr(self, "db_path", "database.db")
            if not os.path.exists(db_path):
                logger.warning("El archivo de base de datos no existe en la ruta: %s", db_path)
                return

            with sqlite3.connect(db_path) as conexion:
                conexion.row_factory = sqlite3.Row
                cursor = conexion.cursor()

                # Consulta los últimos registros insertados (ajusta el nombre de tu tabla si difiere)
                cursor.execute("""
                    SELECT numero_expediente, organo_jurisdiccional, status, created_at 
                    FROM expedientes 
                    ORDER BY id DESC 
                    LIMIT ?
                """, (limite,))
                
                filas = cursor.fetchall()
                
                if not filas:
                    logger.info("La base de datos no contiene registros de expedientes todavía.")
                    return

                logger.info("=== 📊 VOLCADO DE EXPEDIENTES REGISTRADOS (Últimos %s) ===", len(filas))
                for idx, fila in enumerate(filas, 1):
                    logger.info(
                        "[%s] Expediente: %s | Juzgado: %s | Estado: %s",
                        idx,
                        fila["numero_expediente"],
                        fila["organo_jurisdiccional"],
                        fila["status"]
                    )
                logger.info("==========================================================")

        except Exception as e:
            logger.error("Error al realizar el volcado de registros desde la base de datos: %s", e)

    def initialize_schema(self) -> None:
        with self.get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expedientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_expediente TEXT UNIQUE NOT NULL,
                    organo_jurisdiccional TEXT,
                    remate_info TEXT NOT NULL DEFAULT '{}',
                    inmueble_info TEXT NOT NULL DEFAULT '{}',
                    cronograma_info TEXT NOT NULL DEFAULT '{}',
                    pdf_path TEXT,
                    status TEXT NOT NULL DEFAULT 'COMPLETED',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_plugin TEXT NOT NULL,
                    target_plugin TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    available_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    lease_token TEXT,
                    lease_until TEXT,
                    last_error TEXT,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migración aditiva para bases creadas por la versión anterior del boilerplate.
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(task_queue)")}
            additions = {
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "max_attempts": "INTEGER NOT NULL DEFAULT 5",
                "available_at": "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'",
                "lease_token": "TEXT",
                "lease_until": "TEXT",
                "last_error": "TEXT",
                "idempotency_key": "TEXT",
                "updated_at": "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE task_queue ADD COLUMN {name} {declaration}")
            # Conserva el contador de reintentos del esquema anterior si existía.
            if "retry_count" in columns:
                conn.execute("UPDATE task_queue SET attempts=retry_count WHERE attempts=0 AND retry_count > 0")
            # Las tareas PROCESSING del esquema antiguo no tenían lease; recuperarlas.
            conn.execute(
                "UPDATE task_queue SET status='PENDING' WHERE status='PROCESSING' AND lease_until IS NULL"
            )
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_task_idempotency
                ON task_queue(target_plugin, idempotency_key)
                WHERE idempotency_key IS NOT NULL
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_task_claim ON task_queue(target_plugin, status, available_at, id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_task_lease ON task_queue(status, lease_until)")

            expediente_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(expedientes)")
            }
            if "updated_at" not in expediente_columns:
                conn.execute(
                    "ALTER TABLE expedientes ADD COLUMN updated_at TEXT NOT NULL "
                    "DEFAULT '1970-01-01T00:00:00+00:00'"
                )
                if "created_at" in expediente_columns:
                    conn.execute(
                        "UPDATE expedientes SET updated_at=created_at WHERE updated_at='1970-01-01T00:00:00+00:00'"
                    )
