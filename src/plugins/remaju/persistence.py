from __future__ import annotations
import os
import json
from typing import Any, Dict
class StatePersistenceManager:
    """Gestor agnóstico para la persistencia de archivos locales (procesados y revisión manual)."""

    def __init__(self, procesados_file: str, manual_file: str):
        self.procesados_file = procesados_file
        self.manual_file = manual_file

    def esta_procesado(self, numero_remate: str, convocatoria: str) -> bool:
        if not os.path.exists(self.procesados_file):
            return False
        try:
            with open(self.procesados_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return f"{numero_remate.strip()}_{convocatoria.strip()}" in data
        except Exception:
            return False

    def guardar_procesado(self, numero_remate: str, convocatoria: str, datos: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.procesados_file), exist_ok=True)
        data = {}
        if os.path.exists(self.procesados_file):
            try:
                with open(self.procesados_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        clave = f"{numero_remate.strip()}_{convocatoria.strip()}"
        data[clave] = {
            "numero_remate": numero_remate,
            "convocatoria": convocatoria,
            "expediente": datos.get("remate", {}).get("expediente", "")
        }
        with open(self.procesados_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def registrar_error_manual(self, expediente: str, error_msg: str) -> None:
        os.makedirs(os.path.dirname(self.manual_file), exist_ok=True)
        data = {}
        if os.path.exists(self.manual_file):
            try:
                with open(self.manual_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data[expediente] = {"estado": "error", "motivo": error_msg}
        with open(self.manual_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def limpiar_error_manual(self, expediente: str) -> None:
        if os.path.exists(self.manual_file):
            try:
                with open(self.manual_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if expediente in data:
                    del data[expediente]
                    with open(self.manual_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass