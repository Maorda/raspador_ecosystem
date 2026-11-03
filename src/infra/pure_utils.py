import re
import unicodedata
from typing import Any, Dict

PATRON_PARTIDA_REGISTRAL = re.compile(r"P?\d{8}")

def sanitizar_texto(texto: Any) -> str:
    """Limpia espacios en blanco de forma determinista."""
    if texto is None:
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip()

def normalizar_comparacion(texto: Any) -> str:
    """Normaliza texto removiendo acentos, espacios extra y convirtiendo a casefold."""
    txt = sanitizar_texto(texto)
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(caracter for caracter in txt if not unicodedata.combining(caracter))
    return txt.casefold()

def validar_partida_registral(valor: Any) -> bool:
    """Valida el formato de una partida registral obtenida de REMAJU."""
    if not isinstance(valor, str):
        return False
    return PATRON_PARTIDA_REGISTRAL.fullmatch(valor.strip()) is not None

def _clave_registro(expediente: str, convocatoria: str) -> tuple[str, str]:
    """Genera tupla única de expediente y convocatoria en mayúsculas."""
    return (str(expediente).strip().upper(), str(convocatoria).strip().upper())


def _obtener_titulo_tarjeta_locator(tarjeta):
        return tarjeta.locator(".label-danger, .h6").first

def _crear_execution_report() -> Dict[str, Any]:
        return {
            "estado": "en_ejecucion",
            "incidencias": [],
            "error": None,
            "motivo_finalizacion": None,
            "paginas_previstas": None,
            "paginas_intentadas": 0,
            "paginas_exitosas": 0,
            "paginas_fallidas": 0,
            "tarjetas_fallidas": 0,
            "documentos_emitidos": 0,
        }

def verificar_patron_partida(partida: str, patron: re.Pattern) -> bool:
    """Función pura para validar el formato estándar de una partida registral."""
    if not partida:
        return True
    return bool(patron.match(partida))