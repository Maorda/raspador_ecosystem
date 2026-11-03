from __future__ import annotations
import sqlite3
from pathlib import Path

# Ruta estándar de la base de datos del blackboard
DB_PATH = Path("storage/blackboard.db")

def purgar_base_datos(db_path: Path | str = DB_PATH) -> None:
    ruta = Path(db_path)
    if not ruta.exists():
        print(f"[ERROR] No se encontró la base de datos en: {ruta}")
        return

    print(f"[AVISO] Conectando a la base de datos Blackboard: {ruta}")
    conn = sqlite3.connect(ruta)
    cursor = conn.cursor()

    try:
        # Contar registros actuales antes de borrar
        cursor.execute("SELECT COUNT(*) FROM expedientes")
        total_registros = cursor.fetchone()[0]

        if total_registros == 0:
            print("[INFO] La base de datos ya está completamente vacía.")
            return

        print(f"[ALERTA] Se eliminarán permanentemente {total_registros} registros. No se creará ningún respaldo.")
        
        # Ejecutar vaciado de la tabla y reinicio de autoincrementables
        cursor.execute("DELETE FROM expedientes")
        
        # Opcional: reiniciar el contador autoincrement de la tabla si usas SQLite sequence
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='expedientes'")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        print(f"[ÉXITO] Base de datos purgada correctamente. Se han eliminado todos los registros.")

    except Exception as ex:
        conn.rollback()
        print(f"[CRÍTICO] Ocurrió un error durante la purga de la base de datos: {ex}")
    finally:
        conn.close()

if __name__ == "__main__":
    confirmacion = input("¿Estás completamente seguro de borrar TODOS los datos sin backup? (s/N): ").strip().lower()
    if confirmacion == 's':
        purgar_base_datos(DB_PATH)
    else:
        print("[CANCELADO] Operación abortada por el usuario.")