import json
from typing import Any
from pydantic import BaseModel, Field
from infra.database import DatabaseManager
from core.result import Result


class RegisterExpedienteCommand(BaseModel):
    numero_expediente: str
    organo_jurisdiccional: str | None = None
    remate_info: dict[str, Any] = Field(default_factory=dict)
    inmueble_info: dict[str, Any] = Field(default_factory=dict)
    cronograma_info: dict[str, Any] = Field(default_factory=dict)
    pdf_path: str | None = None
    status: str = "COMPLETED"


class CommandDispatcher:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def execute_register_expediente(self, cmd: RegisterExpedienteCommand) -> Result[bool]:
        expediente = cmd.numero_expediente.strip()
        if not expediente:
            return Result.fail("numero_expediente no puede estar vacío.", "VALIDATION_ERROR")
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    """INSERT INTO expedientes
                    (numero_expediente, organo_jurisdiccional, remate_info,
                     inmueble_info, cronograma_info, pdf_path, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(numero_expediente) DO UPDATE SET
                        organo_jurisdiccional=excluded.organo_jurisdiccional,
                        remate_info=excluded.remate_info,
                        inmueble_info=excluded.inmueble_info,
                        cronograma_info=excluded.cronograma_info,
                        pdf_path=excluded.pdf_path,
                        status=excluded.status,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (expediente, cmd.organo_jurisdiccional,
                     json.dumps(cmd.remate_info, ensure_ascii=False),
                     json.dumps(cmd.inmueble_info, ensure_ascii=False),
                     json.dumps(cmd.cronograma_info, ensure_ascii=False),
                     cmd.pdf_path, cmd.status),
                )
                return Result.ok(True)
        except Exception as exc:
            return Result.fail(str(exc), "COMMAND_ERROR")
