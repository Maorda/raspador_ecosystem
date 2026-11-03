"""Configuración de selectores y tiempos para el motor de interceptores en REMAJU."""
from __future__ import annotations

SELECTOR_MODAL_BIENVENIDA = "#dlgPopUp"
SELECTOR_BOTON_ACEPTAR = "#btnAceptarPopup"
SELECTOR_MASCARA_MODAL = "#dlgPopUp_modal"
#SELECTOR_SPINNER_ESTADO = '#dlgEstado_content img[src*="loading-pj.gif"]' se encuentra en el motor

DEFAULT_TIMEOUT_DETECCION_MODAL = 1_000     # Reducido de 4s a 1s
DEFAULT_TIMEOUT_CIERRE_MODAL = 5_000        # Reducido de 10s a 5s
DEFAULT_TIMEOUT_APARICION_SPINNER = 100     # Reducido de 1.5s a 100ms (casi instantáneo)
DEFAULT_TIMEOUT_DESAPARICION_SPINNER = 8_000  # Reducido de 30s a 8s máximo