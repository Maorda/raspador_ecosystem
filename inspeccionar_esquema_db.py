from __future__ import annotations
import sqlite3
from pathlib import Path

# Ruta estándar de la base de datos del blackboard
DB_PATH = Path("storage/blackboard.db")

def inspeccionar_esquema(db_path: Path | str = DB_PATH) -> None:
    ruta = Path(db_path)
    if not ruta.exists():
        print(f"[ERROR] No se encontró la base de datos en: {ruta}")
        return

    print(f"[INFO] Conectando a la base de datos Blackboard: {ruta}")
    conn = sqlite3.connect(ruta)
    cursor = conn.cursor()

    try:
        # 1. Obtener todas las tablas creadas en la base de datos
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tablas = cursor.fetchall()

        if not tablas:
            print("[INFO] La base de datos no contiene tablas creadas.")
            return

        print(f"\n[ESTRUCTURA] Se encontraron {len(tablas)} tabla(s) en la base de datos:\n")

        for (nombre_tabla,) in tablas:
            print(f"==================================================")
            print(f"📋 TABLA: {nombre_tabla.upper()}")
            print(f"==================================================")

            # 2. Consultar la estructura (columnas) de cada tabla mediante PRAGMA
            cursor.execute(f"PRAGMA table_info('{nombre_tabla}')")
            columnas = cursor.fetchall()

            # Formato de salida tabular para las columnas
            print(f" {'Cid':<4} | {'Columna':<25} | {'Tipo de Dato':<18} | {'NotNull':<8} | {'Default':<10} | {'PK':<3}")
            print("-" * 78)
            
            for col in columnas:
                cid, name, tipo, notnull, dflt_value, pk = col
                notnull_str = "Sí" if notnull else "No"
                dflt_str = str(dflt_value) if dflt_value is not None else "NULL"
                pk_str = "Sí" if pk else "-"
                print(f" {cid:<4} | {name:<25} | {tipo:<18} | {notnull_str:<8} | {dflt_str:<10} | {pk_str:<3}")
            
            print("\n")

    except Exception as ex:
        print(f"[ERROR] Ocurrió un error al inspeccionar la base de datos: {ex}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspeccionar_esquema(DB_PATH)