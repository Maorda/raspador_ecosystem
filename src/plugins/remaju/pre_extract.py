from typing import Any, Dict, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from infra.logger import get_logger

logger = get_logger("remaju_plugin")

# ==========================================
# CONSTANTES DE SELECTORES DE PRE-EXTRACCIÓN
# ==========================================

SELECTOR_TABS = '[id="formDetalleRemate:tvResumen"]'
SELECTOR_TAB_NAV = '[id="formDetalleRemate:tvResumen"] ul.ui-tabs-nav'

# Paneles de las pestañas basados en los IDs de los contenedores rol="tabpanel"
SELECTOR_PANEL_REMATE = '[id="formDetalleRemate:tvResumen:tbRemate"]'
SELECTOR_PANEL_INMUEBLES = '[id="formDetalleRemate:tvResumen:tbInmuebles"]'
SELECTOR_PANEL_CRONOGRAMA = '[id="formDetalleRemate:tvResumen:tbCronograma"]'

# Tablas y contenedores internos de datos
SELECTOR_TABLA_INMUEBLES = '[id="formDetalleRemate:tvResumen:dtResumenInmueble_data"]'
SELECTOR_RESUMEN_UBICACION = '[id="formDetalleRemate:tvResumen:panelUbicacion"]' # (Si aplica en el panel de inmuebles)
SELECTOR_TABLA_CRONOGRAMA = '[id="formDetalleRemate:tvResumen:dtCronograma_data"]'

SELECTOR_BOTON_REGRESAR = "button:has-text('Regresar'), a:has-text('Regresar')"


class PreExtractValidator:
    """
    Módulo agnóstico encargado del Momento 1: Validaciones previas, Readiness Guards,
    sincronización de widgets PrimeFaces (TabView) y control de estados AJAX.
    """

    def __init__(self, page: Optional[Page]) -> None:
        self.page = page

    def _require_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            raise RuntimeError("La página de Playwright no está disponible o se encuentra cerrada.")
        return self.page

    async def esperar_sincronizacion_primefaces(self, timeout: int = 10000) -> None:
        """Espera a que las peticiones activas de jQuery/PrimeFaces terminen (active === 0)."""
        page = self._require_page()
        try:
            await page.wait_for_function(
                "() => { if (!window.jQuery) { return true; } return window.jQuery.active === 0; }",
                timeout=timeout
            )
        except PlaywrightTimeoutError:
            logger.warning("PrimeFaces no confirmó el fin de las peticiones jQuery en %s ms.", timeout)

    async def esperar_inicializacion_tabview(self, timeout: int = 15000) -> None:
        """Verifica el estado del documento y la disponibilidad del widget TabView de REMAJU."""
        page = self._require_page()
        await page.wait_for_function("() => document.readyState === 'complete'", timeout=timeout)
        await page.wait_for_function(
            """() => {
                const pf = window.PrimeFaces;
                if (!pf || !pf.widgets) return false;
                return Object.values(pf.widgets).some(widget => widget && widget.id === "formDetalleRemate:tvResumen");
            }""",
            timeout=timeout,
        )

    async def esperar_detalle_cargado(self, motor_sincronizar_fn = None, timeout: int = 15000) -> None:
        """Valida que los paneles de pestañas, el panel de remate y el botón de retorno estén completamente visibles."""
        page = self._require_page()
        if page.is_closed():
            raise RuntimeError("La página se cerró al abrir el detalle del remate.")
        
        panel_tabs = page.locator(SELECTOR_TABS)
        panel_remate = page.locator(SELECTOR_PANEL_REMATE)
        btn_regresar = page.locator(SELECTOR_BOTON_REGRESAR).first

        try:
            await panel_tabs.wait_for(state="visible", timeout=timeout)
            await panel_remate.wait_for(state="visible", timeout=timeout)
            await btn_regresar.wait_for(state="visible", timeout=timeout)
            
            # CORRECCIÓN: Pasar siempre la página al motor de interceptores si existe
            if motor_sincronizar_fn:
                await motor_sincronizar_fn(page)
            else:
                await self.esperar_sincronizacion_primefaces()

        except PlaywrightTimeoutError as exc:
            raise RuntimeError("REMAJU no confirmó la apertura completa del detalle de la tarjeta.") from exc

    async def activar_pestana(self, indice: int, selector_panel: str, selector_contenido: str = "", timeout: int = 15000, motor_sincronizar_fn = None) -> None:
        """Activa una pestaña mediante el widget PrimeFaces (con fallback a clic forzado) y valida la visibilidad del panel."""
        page = self._require_page()
        await self.esperar_inicializacion_tabview(timeout=timeout)

        navegacion = page.locator(SELECTOR_TAB_NAV)
        pestana = navegacion.locator(f'li[data-index="{indice}"]')
        panel = page.locator(selector_panel)

        await pestana.wait_for(state="visible", timeout=timeout)
        seleccionada = await pestana.get_attribute("aria-selected")

        if seleccionada != "true":
            # Intento de activación por API de widget PrimeFaces
            activacion = await page.evaluate(
                """(indice) => {
                    const id = "formDetalleRemate:tvResumen";
                    const widgets = window.PrimeFaces?.widgets ?? {};
                    const widget = Object.values(widgets).find(item => item?.id === id);
                    if (!widget || typeof widget.select !== "function") return { activado: false };
                    try {
                        widget.select(indice);
                        return { activado: true };
                    } catch (error) {
                        return { activado: false, error: String(error) };
                    }
                }""",
                arg=indice,
            )

            # Fallback a clic físico si el widget no está disponible
            if not activacion.get("activado"):
                await pestana.click(force=True)

            # Confirmación de selección en el DOM
            await page.wait_for_function(
                """(indice) => {
                    const root = document.querySelector('[id="formDetalleRemate:tvResumen"]');
                    const tab = root?.querySelector(`ul.ui-tabs-nav li[data-index="${indice}"]`);
                    return tab?.getAttribute("aria-selected") === "true";
                }""",
                arg=indice,
                timeout=timeout,
            )

        await panel.wait_for(state="visible", timeout=timeout)
        
        # CORRECCIÓN: Ejecutar el motor de interceptores pasando obligatoriamente `page` para limpiar spinners
        if motor_sincronizar_fn:
            await motor_sincronizar_fn(page)
        else:
            await self.esperar_sincronizacion_primefaces(timeout=timeout)

        if selector_contenido:
            await page.locator(selector_contenido).wait_for(state="attached", timeout=timeout)