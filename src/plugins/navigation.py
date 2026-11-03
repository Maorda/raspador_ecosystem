import asyncio
import re
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from infra.logger import get_logger
from typing import Any, Callable, Awaitable

logger = get_logger("remaju_plugin")

# Constantes de selectores de navegación
SELECTOR_CONTENEDOR_LISTADO = '[id="formBuscarRematesPublicados:listaRemate_content"]'
SELECTOR_TARJETAS = '[id="formBuscarRematesPublicados:listaRemate_content"] .card.azul'
SELECTOR_PAGINADOR = '[id="formBuscarRematesPublicados:listaRemate_paginator_bottom"]'
SELECTOR_PAGINA_ACTIVA = SELECTOR_PAGINADOR + " .ui-paginator-page.ui-state-active"
SELECTOR_BOTON_REGRESAR = "button:has-text('Regresar'), a:has-text('Regresar')"


class RemajuNavigator:
    """Módulo agnóstico encargado exclusivamente de la navegación por paginación y retorno seguro a la bandeja."""

    def __init__(self, page: Page | None, pausa_entre_tarjetas: float = 1.0) -> None:
        self.page = page
        self.pausa_entre_tarjetas = pausa_entre_tarjetas

    def _require_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            raise RuntimeError("La página de Playwright não está disponible o se encuentra cerrada.")
        return self.page

    async def esperar_listado(self, timeout: int = 15000) -> bool:
        """Verifica que el contenedor de tarjetas y los ítems estén visibles en la bandeja."""
        page = self._require_page()
        if page.is_closed():
            raise RuntimeError("La página se cerró mientras se esperaba la bandeja.")
        
        contenedor = page.locator(SELECTOR_CONTENEDOR_LISTADO)
        await contenedor.wait_for(state="visible", timeout=timeout)
        
        tarjetas = page.locator(SELECTOR_TARJETAS)
        try:
            await tarjetas.first.wait_for(state="visible", timeout=timeout)
        except PlaywrightTimeoutError:
            if await tarjetas.count() == 0:
                logger.info("La bandeja no contiene tarjetas de remates.")
                return False
            raise
        return True

    async def _obtener_marca_pagina(self) -> str:
        """Obtiene la etiqueta o número de la página activa actual del paginador."""
        page = self._require_page()
        pagina_activa = page.locator(SELECTOR_PAGINA_ACTIVA)
        if await pagina_activa.count() == 0:
            return ""
        etiqueta = (await pagina_activa.first.get_attribute("aria-label") or "").strip()
        if etiqueta:
            return etiqueta
        return re.sub(r"\s+", " ", (await pagina_activa.first.inner_text()).strip())

    async def regresar_a_bandeja(self, motor_sincronizar_fn: Callable[[Page], Awaitable[Any]] | None = None) -> bool:
        page = self._require_page()
        if page.is_closed():
            logger.error("No se puede regresar a la bandeja: la página está cerrada.")
            return False

        try:
            listado = page.locator(SELECTOR_TARJETAS)

            if await listado.count() > 0 and await self.esperar_listado(timeout=2000):
                if motor_sincronizar_fn:
                    await motor_sincronizar_fn(page)
                return True

            btn_regresar = page.locator(SELECTOR_BOTON_REGRESAR).first
            await btn_regresar.wait_for(state="visible", timeout=10000)
            await btn_regresar.click()

            if not await self.esperar_listado(timeout=20000):
                logger.error("El retorno se ejecutó, pero no se confirmó el listado de tarjetas.")
                return False

            if motor_sincronizar_fn:
                await motor_sincronizar_fn(page)

            await asyncio.sleep(max(0.0, float(self.pausa_entre_tarjetas)))
            logger.debug("Regreso a la bandeja confirmado exitosamente.")
            return True

        except Exception:
            logger.exception("Error retornando a la bandeja general de remates.")
            return False

    async def avanzar_pagina(self, motor_sincronizar_fn: Callable[[Page], Awaitable[Any]] | None = None) -> bool:
        """Avanza a la siguiente página validando el estado del paginador y sincronizando el motor."""
        page = self._require_page()
        if motor_sincronizar_fn:
            await motor_sincronizar_fn(page)

        btn_siguiente_selector = SELECTOR_PAGINADOR + " a.ui-paginator-next"
        btn_siguiente = page.locator(btn_siguiente_selector).first

        for intento in range(3):
            if page.is_closed():
                return False
            if await btn_siguiente.count() > 0 and await btn_siguiente.is_visible():
                break
            if intento < 2:
                await asyncio.sleep(1.0)
                if motor_sincronizar_fn:
                    await motor_sincronizar_fn(page)

        if await btn_siguiente.count() == 0 or not await btn_siguiente.is_visible():
            logger.info("No hay una página siguiente disponible o se llegó al final del paginador.")
            return False

        clases_boton = (await btn_siguiente.get_attribute("class") or "").split()
        if "ui-state-disabled" in clases_boton:
            logger.info("Fin del listado confirmado: botón siguiente deshabilitado por PrimeFaces.")
            return False

        marca_anterior = await self._obtener_marca_pagina()
        if not marca_anterior:
            logger.warning("No se pudo identificar la página activa antes de avanzar.")
            return False

        try:
            await btn_siguiente.click()

            await page.wait_for_function(
                """
                ({ selector, anterior }) => {
                    const activo = document.querySelector(selector);
                    if (!activo) return false;
                    const actual = (activo.getAttribute('aria-label') || activo.innerText || '').trim();
                    return actual !== anterior;
                }
                """,
                arg={"selector": SELECTOR_PAGINA_ACTIVA, "anterior": marca_anterior},
                timeout=15000,
            )

            if motor_sincronizar_fn:
                await motor_sincronizar_fn(page)

            if not await self.esperar_listado(timeout=15000):
                logger.warning("El paginador cambió de estado, pero no se cargaron tarjetas en la nueva página.")
                return False

            marca_nueva = await self._obtener_marca_pagina()
            if not marca_nueva or marca_nueva == marca_anterior:
                logger.warning("El paginador no confirmó un cambio de página real.")
                return False

            logger.info("Paginación confirmada con éxito", anterior=marca_anterior, nueva=marca_nueva)
            return True

        except PlaywrightTimeoutError:
            logger.warning("El paginador no confirmó el cambio de página desde %s dentro del tiempo límite.", marca_anterior)
            return False