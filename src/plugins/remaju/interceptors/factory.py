"""Fábrica para instanciar y configurar el MotorInterceptor con los interceptores de REMAJU."""
from __future__ import annotations

from interceptor_motor import MotorInterceptor, ModalInterceptor, SpinnerInterceptor
from interceptor_motor.strategies import ClickStrategy
from interceptor_motor.selectors.spinner_selectors import SELECTOR_SPINNER_ESTADO
from .config import (
    SELECTOR_MODAL_BIENVENIDA,
    SELECTOR_BOTON_ACEPTAR,
    SELECTOR_MASCARA_MODAL,
    
    DEFAULT_TIMEOUT_DETECCION_MODAL,
    DEFAULT_TIMEOUT_CIERRE_MODAL,
    DEFAULT_TIMEOUT_APARICION_SPINNER,
    DEFAULT_TIMEOUT_DESAPARICION_SPINNER,
)


def crear_motor_remaju() -> MotorInterceptor:
    motor = MotorInterceptor()
    motor.register(
        ModalInterceptor(
            name="modal_bienvenida",
            selector_modal=SELECTOR_MODAL_BIENVENIDA,
            selector_mascara=SELECTOR_MASCARA_MODAL,
            close_strategy=ClickStrategy(SELECTOR_BOTON_ACEPTAR),
            timeout_deteccion=DEFAULT_TIMEOUT_DETECCION_MODAL,
            timeout_cierre=DEFAULT_TIMEOUT_CIERRE_MODAL,
        )
    )
    motor.register(
        SpinnerInterceptor(
            selector=SELECTOR_SPINNER_ESTADO,
            timeout_aparicion=DEFAULT_TIMEOUT_APARICION_SPINNER,
            timeout_desaparicion=DEFAULT_TIMEOUT_DESAPARICION_SPINNER,
        )
    )
    return motor