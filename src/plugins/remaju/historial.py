import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

def _load_data(self, target_path: Path) -> List[Any]:
    if not target_path.exists():
        return []
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_data_atomically(self, target_path: Path, data: List[Any]) -> None:
    dir_name = target_path.parent
    dir_name.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=4, ensure_ascii=False)
            temp_name = tf.name
        os.replace(temp_name, target_path)
    except Exception as e:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except Exception:
                pass
        raise e

def _cargar_json_registros(self, ruta: Path) -> Dict[str, Any]:
    ruta = Path(ruta)
    if not ruta.exists():
        return {"version": 1, "fuente": "remaju", "registros": []}
    with ruta.open("r", encoding="utf-8") as archivo:
        contenido = json.load(archivo)
    if not isinstance(contenido, dict) or not isinstance(contenido.get("registros"), list):
        return {"version": 1, "fuente": "remaju", "registros": []}
    return contenido

def _guardar_json_atomico(self, ruta: Path, contenido: Dict[str, Any]) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=str(ruta.parent), suffix=".tmp", delete=False, encoding="utf-8") as archivo:
            json.dump(contenido, archivo, ensure_ascii=False, indent=2)
            temp_name = archivo.name
        os.replace(temp_name, ruta)
    except Exception:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except Exception:
                pass
        raise

def is_processed(self, numero_expediente: str, numero_convocatoria: str, filepath: Path) -> bool:
    records = self._load_data(filepath)
    exp, conv = self._clave_registro(numero_expediente, numero_convocatoria)
    for record in records:
        r_exp, r_conv = self._clave_registro(record.get("expediente", ""), record.get("convocatoria", ""))
        if r_exp == exp and r_conv == conv:
            return True
    return False

def save_processed(self, numero_expediente: str, numero_convocatoria: str, filepath: Path) -> None:
    exp, conv = self._clave_registro(numero_expediente, numero_convocatoria)
    if not exp or not conv:
        return
    records = self._load_data(filepath)
    if not any(self._clave_registro(r.get("expediente", ""), r.get("convocatoria", "")) == (exp, conv) for r in records):
        records.append({"expediente": exp, "convocatoria": conv})
        self._save_data_atomically(filepath, records)

def _guardar_datos_extraidos(self, expediente: str, convocatoria: str, datos: Dict[str, Any], pdf_estado: str) -> None:
    ruta = self.descargas_path / "datos_extraidos.json"
    contenido = self._cargar_json_registros(ruta)
    clave = self._clave_registro(expediente, convocatoria)
    registros = contenido["registros"]

    registro = {
        "expediente": str(expediente).strip(),
        "convocatoria": str(convocatoria).strip(),
        "datos": datos,
        "pdf_estado": pdf_estado,
        "actualizado_en": datetime.now(timezone.utc).isoformat(),
    }

    for indice, existente in enumerate(registros):
        if isinstance(existente, dict) and self._clave_registro(existente.get("expediente", ""), existente.get("convocatoria", "")) == clave:
            registros[indice] = registro
            break
    else:
        registros.append(registro)

    self._guardar_json_atomico(ruta, contenido)

def _registrar_partida_revision_manual(self, expediente: str, convocatoria: str, incidencia: Dict[str, Any]) -> None:
    ruta = self.descargas_path / "revision_manual" / "partidas_invalidas.json"
    contenido = self._cargar_json_registros(ruta)
    inmueble = incidencia.get("inmueble", {}) if isinstance(incidencia.get("inmueble"), dict) else {}
    partida_original = incidencia.get("partida_original", "")
    
    registro = {
        "expediente": str(expediente).strip(),
        "convocatoria": str(convocatoria).strip(),
        "partida_original": partida_original,
        "motivo": incidencia.get("motivo", "formato_partida_registral_invalido"),
        "fila_remaju": incidencia.get("fila_remaju"),
        "inmueble": inmueble,
        "estado": "pendiente_revision",
        "registrado_en": datetime.now(timezone.utc).isoformat(),
    }
    contenido["registros"].append(registro)
    self._guardar_json_atomico(ruta, contenido)

def _registrar_pdf_revision_manual(self, expediente: str, convocatoria: str, motivo: str) -> None:
    ruta = self.descargas_path / "revision_manual" / "descargas_fallidas.json"
    contenido = self._cargar_json_registros(ruta)
    registro = {
        "expediente": str(expediente).strip(),
        "convocatoria": str(convocatoria).strip(),
        "motivo": motivo,
        "registrado_en": datetime.now(timezone.utc).isoformat(),
        "estado": "pendiente_revision",
    }
    contenido["registros"].append(registro)
    self._guardar_json_atomico(ruta, contenido)