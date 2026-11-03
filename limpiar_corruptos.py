from __future__ import annotations
import sqlite3
import json
import os
from pathlib import Path

# Ruta estándar de la base de datos del blackboard (ajustable según tu entorno)
DB_PATH = Path("storage/blackboard.db")

def limpiar_expedientes_corruptos(db_path: Path | str) -> None:
    ruta = Path(db_path)
    if not ruta.exists():
        print(f"[ERROR] No se encontró la base de datos en: {ruta}")
        return

    print(f"[INFO] Conectando a la base de datos Blackboard: {ruta}")
    conn = sqlite3.connect(ruta)
    cursor = conn.cursor()

    ids_a_eliminar: list[int] = []

    try:
        # Extraer registros para auditar su integridad en memoria
        cursor.execute("SELECT id, numero_expediente, inmueble_info FROM expedientes")
        registros = cursor.fetchall()

        print(f"[INFO] Auditando {len(registros)} registros en busca de corrupción o datos incompletos...")

        for row in registros:
            db_id, num_exp, inmueble_json = row
            corrupto = False
            motivo = ""

            if not inmueble_json:
                corrupto = True
                motivo = "JSON de inmueble vacío o nulo"
            else:
                try:
                    inmuebles = json.loads(inmueble_json)
                    
                    # Validar si es una lista de inmuebles o un diccionario individual
                    if isinstance(inmuebles, list):
                        if not inmuebles:
                            corrupto = True
                            motivo = "Lista de inmuebles vacía"
                        else:
                            for item in inmuebles:
                                depto = item.get("departamento", "").strip().upper()
                                if not depto or depto == "NO ESPECIFICADO":
                                    corrupto = True
                                    motivo = f"Departamento inválido o ausente: {depto!r}"
                                    break
                    elif isinstance(inmuebles, dict):
                        depto = inmuebles.get("departamento", "").strip().upper()
                        if not depto or depto == "NO ESPECIFICADO":
                            corrupto = True
                            motivo = f"Departamento inválido o ausente en diccionario: {depto!r}"
                    else:
                        corrupto = True
                        motivo = "Estructura JSON no reconocida"

                except json.JSONDecodeError:
                    corrupto = True
                    motivo = "Error de sintaxis en la serialización JSON"

            if corrupto:
                ids_a_eliminar.append(db_id)
                print(f"  -> [DETECTADO CORRUPTO] ID: {db_id} | Expediente: {num_exp} | Motivo: {motivo}")

        if ids_a_eliminar:
            print(f"\n[ACCIÓN] Procediendo a eliminar {len(ids_a_eliminar)} registros corruptos del Blackboard...")
            
            # Ejecutar eliminación masiva bajo transacción segura
            cursor.executemany("DELETE FROM expedientes WHERE id = ?", [(id_val,) for id_val in ids_a_eliminar])
            conn.commit()
            
            print(f"[ÉXITO] Limpieza completada. Se eliminaron {len(ids_a_eliminar)} expedientes corruptos.")
        else:
            print("\n[INFO] ¡Excelente! No se encontraron expedientes corruptos en el Blackboard. Todos los datos cumplen con el contrato.")

    except Exception as ex:
        conn.rollback()
        print(f"[CRítico] Ocurrió un error durante la ejecución de la limpieza: {ex}")
    finally:
        conn.close()

if __name__ == "__main__":
    limpiar_expedientes_corruptos(DB_PATH)