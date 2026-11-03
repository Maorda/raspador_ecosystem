from __future__ import annotations
import sqlite3
import json
from pathlib import Path

# Ruta estándar de la base de datos del blackboard
DB_PATH = Path("storage/blackboard.db")

def conectar_db(db_path: Path | str) -> sqlite3.Connection | None:
    ruta = Path(db_path)
    if not ruta.exists():
        return None
    return sqlite3.connect(ruta)

def obtener_resumen_expedientes_json(db_path: Path | str = DB_PATH, custom_query: str | None = None) -> str:
    """
    Devuelve los registros en formato JSON estructurado adaptándose 
    dinámicamente a los campos especificados en el SELECT.
    """
    conn = conectar_db(db_path)
    if not conn:
        return json.dumps({"error": f"No se encontró la base de datos en: {db_path}"}, ensure_ascii=False)

    cursor = conn.cursor()
    try:
        # Si pasas una consulta personalizada la usa, de lo contrario usa una por defecto
        query = custom_query or """
            SELECT id, numero_expediente, organo_jurisdiccional, status, created_at
            FROM expedientes 
            ORDER BY id DESC
        """
        cursor.execute(query)
        filas = cursor.fetchall()

        if not filas:
            return json.dumps({"mensaje": "No se encontraron registros en la consulta."}, ensure_ascii=False)

        # 1. Obtenemos los nombres de las columnas directamente desde la consulta SQL
        columnas = [col[0] for col in cursor.description]

        resultado = []
        for row in filas:
            fila_dict = {}
            for i, col_name in enumerate(columnas):
                valor = row[i]
                # Si el campo es uno de los JSONs internos y viene como string, lo parseamos
                if col_name in ("remate_info", "inmueble_info", "cronograma_info") and isinstance(valor, str):
                    try:
                        valor = json.loads(valor)
                    except json.JSONDecodeError:
                        pass # Si falla el parseo, se mantiene tal cual o se maneja
                
                fila_dict[col_name] = valor if valor is not None else "N/D"
                
            resultado.append(fila_dict)

        return json.dumps(resultado, indent=4, ensure_ascii=False)

    except Exception as ex:
        return json.dumps({"error": f"Ocurrió un error al ejecutar la consulta: {str(ex)}"}, ensure_ascii=False)
    finally:
        conn.close()


def consultar_detalle_por_expediente_json(numero_expediente: str, db_path: Path | str = DB_PATH, custom_query: str | None = None) -> str:
    """
    Devuelve los detalles de un expediente adaptándose dinámicamente a los campos del SELECT,
    parseando automáticamente las columnas de tipo JSON.
    """
    conn = conectar_db(db_path)
    if not conn:
        return json.dumps({"error": f"No se encontró la base de datos en: {db_path}"}, ensure_ascii=False)

    cursor = conn.cursor()
    try:
        # Consulta por defecto o personalizada permitiendo filtrar por LIKE
        query = custom_query or """
            SELECT numero_expediente, organo_jurisdiccional, remate_info, inmueble_info, cronograma_info, pdf_path, status
            FROM expedientes 
            WHERE numero_expediente LIKE ?
        """
        
        # Si usan una consulta personalizada, evaluamos si lleva parámetros o no
        if custom_query:
            cursor.execute(query)
        else:
            cursor.execute(query, (f"%{numero_expediente}%",))
        
        filas = cursor.fetchall()
        if not filas:
            return json.dumps({"error": f"No se encontró ningún expediente que coincida con: {numero_expediente}"}, ensure_ascii=False)

        columnas = [col[0] for col in cursor.description]
        detalles = []

        for row in filas:
            fila_dict = {}
            for i, col_name in enumerate(columnas):
                valor = row[i]
                
                # Auto-parseo si la columna seleccionada corresponde a un JSON interno
                if col_name in ("remate_info", "inmueble_info", "cronograma_info") and isinstance(valor, str):
                    try:
                        valor = json.loads(valor)
                    except json.JSONDecodeError:
                        pass
                
                fila_dict[col_name] = valor if valor is not None else "N/D"
                
            detalles.append(fila_dict)

        # Si hay un único resultado, lo retornamos como objeto directo; si hay varios, como lista
        payload = detalles[0] if len(detalles) == 1 else detalles
        return json.dumps(payload, indent=4, ensure_ascii=False)

    except Exception as ex:
        return json.dumps({"error": f"Error al parsear los registros: {str(ex)}"}, ensure_ascii=False)
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        termino_busqueda = sys.argv[1]
        print(consultar_detalle_por_expediente_json(termino_busqueda))
    else:
        print(obtener_resumen_expedientes_json())