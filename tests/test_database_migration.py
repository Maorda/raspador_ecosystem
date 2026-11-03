import sqlite3
from infra.database import DatabaseManager


def test_migrates_legacy_boilerplate_schema(tmp_path):
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE expedientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_expediente TEXT UNIQUE NOT NULL,
            organo_jurisdiccional TEXT,
            remate_info JSON,
            inmueble_info JSON,
            cronograma_info JSON,
            pdf_path TEXT,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO expedientes (numero_expediente, status) VALUES (?, ?)",
        ("EXP-LEGACY", "COMPLETED"),
    )
    conn.execute("""
        CREATE TABLE task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_plugin TEXT NOT NULL,
            target_plugin TEXT NOT NULL,
            payload JSON NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO task_queue (source_plugin, target_plugin, payload, retry_count) VALUES (?, ?, ?, ?)",
        ("REMAJU", "SUNARP", '{"partida":"123"}', 2),
    )
    conn.execute(
        "INSERT INTO task_queue (source_plugin, target_plugin, payload, status, retry_count) VALUES (?, ?, ?, 'PROCESSING', ?)",
        ("REMAJU", "CEJ", '{"expediente":"EXP-1"}', 1),
    )
    conn.commit()
    conn.close()

    manager = DatabaseManager(db_file)
    manager.initialize_schema()
    manager.initialize_schema()

    with manager.get_connection() as migrated:
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(task_queue)")}
        expediente_columns = {row["name"] for row in migrated.execute("PRAGMA table_info(expedientes)")}
        row = migrated.execute("SELECT * FROM task_queue WHERE id=1").fetchone()
        recovered = migrated.execute("SELECT * FROM task_queue WHERE id=2").fetchone()
        legacy_expediente = migrated.execute("SELECT * FROM expedientes WHERE numero_expediente='EXP-LEGACY'").fetchone()

    assert "updated_at" in expediente_columns
    assert legacy_expediente["updated_at"] == legacy_expediente["created_at"]
    assert {"attempts", "max_attempts", "available_at", "lease_token", "lease_until", "idempotency_key"} <= columns
    assert row["target_plugin"] == "SUNARP"
    assert row["payload"] == '{"partida":"123"}'
    assert row["attempts"] == 2
    assert recovered["status"] == "PENDING"
    assert recovered["attempts"] == 1

    from core.cqrs import CommandDispatcher, RegisterExpedienteCommand
    result = CommandDispatcher(manager).execute_register_expediente(
        RegisterExpedienteCommand(numero_expediente="EXP-LEGACY", status="COMPLETED")
    )
    assert result.is_success and result.value is True
