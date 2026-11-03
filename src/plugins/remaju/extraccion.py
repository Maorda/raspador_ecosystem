from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple, Callable, Awaitable
from playwright.async_api import Page
from infra.logger import get_logger
from infra.pure_utils import sanitizar_texto, normalizar_comparacion, validar_partida_registral
from plugins.remaju.pre_extract import (
    SELECTOR_TABS,
    SELECTOR_PANEL_REMATE,
    SELECTOR_PANEL_INMUEBLES,
    SELECTOR_TABLA_INMUEBLES,
    SELECTOR_RESUMEN_UBICACION,
    SELECTOR_PANEL_CRONOGRAMA,
    SELECTOR_TABLA_CRONOGRAMA,
    PreExtractValidator
)

logger = get_logger("remaju_plugin")


class RemajuExtractor:
    """
    Módulo encargado del Momento 2: Extracción pura de datos,
    parseo de tablas, validación de partidas y estructuración de DTOs,
    utilizando navegación unificada con control estricto de spinners AJAX.
    """

    def __init__(self, page: Page | None, app_config: Dict[str, Any], pre_validator: PreExtractValidator) -> None:
        self.page = page
        self.app_config = app_config
        self.pre_validator = pre_validator

    def _require_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            raise RuntimeError("La página de Playwright no está disponible o se encuentra cerrada.")
        return self.page

    async def _extraer_campos_etiquetados(self, panel_selector: str, mapeo: Dict[str, str]) -> Dict[str, str]:
        """Extrae de forma genérica pares clave-valor basados en etiquetas estelares (PrimeFaces PanelGrid)."""
        page = self._require_page()
        panel = page.locator(panel_selector)
        await panel.wait_for(state="visible", timeout=10000)
        
        etiquetas_deseadas = {clave: normalizar_comparacion(etiqueta) for clave, etiqueta in mapeo.items()}
        resultado = {clave: "" for clave in mapeo}
        etiquetas = panel.locator(".ui-panelgrid-cell.text-bold")
        
        for indice in range(await etiquetas.count()):
            etiqueta = etiquetas.nth(indice)
            texto_etiqueta = normalizar_comparacion(await etiqueta.inner_text())
            claves = [clave for clave, texto_configurado in etiquetas_deseadas.items() if texto_configurado == texto_etiqueta]
            if not claves:
                continue
            
            valor_locator = etiqueta.locator("xpath=following-sibling::div[contains(concat(' ', normalize-space(@class), ' '), ' ui-panelgrid-cell ')][1]")
            if await valor_locator.count() == 0:
                continue
            
            valor = sanitizar_texto(await valor_locator.first.inner_text())
            for clave in claves:
                resultado[clave] = valor
        return resultado

    async def _extraer_datos_remate(self) -> Dict[str, Any]:
        """Extrae los campos de la pestaña principal de Remate."""
        page = self._require_page()
        panel = page.locator(SELECTOR_PANEL_REMATE)
        await panel.wait_for(state="visible", timeout=15000)
        
        datos = await self._extraer_campos_etiquetados(SELECTOR_PANEL_REMATE, self.app_config.get("mapeo_remate", {}))
        
        descripcion = panel.locator(".texto-info-scroll").first
        datos["descripcion"] = sanitizar_texto(await descripcion.inner_text()) if await descripcion.count() else ""
        
        # Dejamos inicializado o vacío para que la estrategia principal inyecte la ruta real del PDF descargado
        datos["archivoUrl"] = "" 
        
        if not datos.get("tipoCambio"):
            tipo_cambio = panel.locator("span.label-danger.text-bold")
            if await tipo_cambio.count():
                datos["tipoCambio"] = sanitizar_texto(await tipo_cambio.first.inner_text())
                
        return datos

    async def _extraer_datos_inmuebles(self) -> Tuple[Dict[str, str], List[Dict[str, str]], List[Dict[str, Any]]]:
        """Extrae la ubicación de forma determinista usando el HTML estructurado de celdas grid."""
        page = self._require_page()
        
        ubicacion = {}
        # Contenedor general donde residen las celdas de Departamento, Provincia y Distrito
        # Podemos buscar el contenedor raíz que posee la etiqueta "Departamento"
        
        keys_geograficas = {
            "departamento": "Departamento",
            "provincia": "Provincia",
            "distrito": "Distrito"
        }

        for clave_dto, etiqueta in keys_geograficas.items():
            try:
                # Buscamos el div que contiene exactamente el texto de la etiqueta y saltamos al div hermano contiguo
                xpath_expr = f"//div[text()='{etiqueta}']/following-sibling::div[1]"
                val_elem = page.locator(f"xpath={xpath_expr}").first
                
                if await val_elem.count() > 0:
                    ubicacion[clave_dto] = sanitizar_texto(await val_elem.inner_text())
            except Exception as ex:
                logger.debug("error_extrayendo_campo_ubicacion_grid", campo=clave_dto, error=str(ex))

        # Validación estricta por contrato (Fail-Fast)
        campos_faltantes = [clave for clave in keys_geograficas.keys() if not ubicacion.get(clave)]
        
        if campos_faltantes:
            logger.warning(
                "ubicacion_incompleta_grid",
                campos_faltantes=campos_faltantes,
                mensaje="No se pudieron extraer todos los campos geográficos del grid estructurado."
            )
            raise ValueError(
                f"Fallo de extracción crítica: Faltan los campos geográficos {campos_faltantes} "
                f"en el grid de ubicación. Expediente derivado a revisión manual."
            )
            
        # Extracción de la tabla de inmuebles...
        tbody = page.locator(SELECTOR_TABLA_INMUEBLES)
        await tbody.wait_for(state="visible", timeout=15000)
        filas = tbody.locator("tr[data-ri]")
        
        inmuebles: List[Dict[str, str]] = []
        partidas_invalidas: List[Dict[str, Any]] = []

        for indice in range(await filas.count()):
            fila = filas.nth(indice)
            celdas = fila.locator(":scope > td")
            if await celdas.count() < 5:
                continue

            partida = sanitizar_texto(await celdas.nth(0).inner_text())
            tipo_inm = sanitizar_texto(await celdas.nth(1).inner_text())
            direccion = sanitizar_texto(await celdas.nth(2).inner_text())
            gravamen = sanitizar_texto(await celdas.nth(3).inner_text())
            porcentaje = sanitizar_texto(await celdas.nth(4).inner_text())

            inmueble = {
                "partidaRegistral": partida,
                "tipoInmueble": tipo_inm,
                "direccion": direccion,
                "cargaYGravamen": gravamen,
                "porcentajeRematar": porcentaje,
            }

            inmueble.update(ubicacion)

            partida_limpia = partida.strip()
            if not validar_partida_registral(partida_limpia):
                partidas_invalidas.append({
                    "fila_remaju": indice,
                    "partida_original": partida,
                    "motivo": "partida_vacia" if not partida_limpia else "formato_partida_registral_invalido",
                    "inmueble": inmueble,
                })
                continue

            inmueble["partidaRegistral"] = partida_limpia
            inmuebles.append(inmueble)

        return ubicacion, inmuebles, partidas_invalidas

    async def _extraer_datos_cronograma(self) -> Dict[str, str]:
        """Extrae y mapea las fechas e hitos del cronograma de fases del remate."""
        page = self._require_page()
        tbody = page.locator(SELECTOR_TABLA_CRONOGRAMA)
        await tbody.wait_for(state="visible", timeout=15000)
        filas = tbody.locator("tr[data-ri]")
        fases: Dict[str, Dict[str, str]] = {}
        
        for indice in range(await filas.count()):
            celdas = filas.nth(indice).locator(":scope > td")
            if await celdas.count() < 4:
                continue
            fase = sanitizar_texto(await celdas.nth(1).inner_text())
            f_inicio = sanitizar_texto(await celdas.nth(2).inner_text())
            f_fin = sanitizar_texto(await celdas.nth(3).inner_text())
            clave_fase = normalizar_comparacion(fase)
            if clave_fase:
                fases[clave_fase] = {"inicio": f_inicio, "fin": f_fin}

        resultado: Dict[str, str] = {}
        mapeo = self.app_config.get("mapeo_cronograma", {})
        for clave_dto, nombre_fase in mapeo.items():
            fase = fases.get(normalizar_comparacion(nombre_fase), {})
            if "inicio" in clave_dto.casefold():
                resultado[clave_dto] = fase.get("inicio", "")
            elif "fin" in clave_dto.casefold():
                resultado[clave_dto] = fase.get("fin", "")
            else:
                resultado[clave_dto] = ""
        return resultado

    async def extract_tab_remate_completo(self, motor_sincronizar_fn = None) -> Dict[str, Any]:
        """Orquestador principal que utiliza directamente PreExtractValidator para la navegación."""
        page = self._require_page()
        
        await page.locator(SELECTOR_TABS).wait_for(state="visible", timeout=15000)
        if motor_sincronizar_fn:
            await motor_sincronizar_fn(page)

        await self.pre_validator.esperar_detalle_cargado(motor_sincronizar_fn=motor_sincronizar_fn)

        datos: Dict[str, Any] = {"remate": {}, "inmuebles": [], "cronograma": {}}

        # 1. Extracción de Remate (Pestaña por defecto)
        datos["remate"] = await self._extraer_datos_remate()

        # 2. Cambio a Inmuebles (Índice 1) directamente con el validador
        await self.pre_validator.activar_pestana(
            indice=1,
            selector_panel=SELECTOR_PANEL_INMUEBLES,
            selector_contenido=SELECTOR_TABLA_INMUEBLES,
            timeout=6000,
            motor_sincronizar_fn=motor_sincronizar_fn
        )
        ubicacion, inmuebles, partidas_invalidas = await self._extraer_datos_inmuebles()
        datos["remate"].update(ubicacion)
        datos["inmuebles"] = inmuebles
        datos["partidas_revision_manual"] = partidas_invalidas

        # 3. Cambio a Cronograma (Índice 2) directamente con el validador
        await self.pre_validator.activar_pestana(
            indice=2,
            selector_panel=SELECTOR_PANEL_CRONOGRAMA,
            selector_contenido=SELECTOR_TABLA_CRONOGRAMA,
            timeout=6000,
            motor_sincronizar_fn=motor_sincronizar_fn
        )
        datos["cronograma"] = await self._extraer_datos_cronograma()

        # 4. Retorno al tab inicial (Remates, índice 0)
        await self.pre_validator.activar_pestana(
            indice=0,
            selector_panel=SELECTOR_PANEL_REMATE,
            timeout=6000,
            motor_sincronizar_fn=motor_sincronizar_fn
        )

        return datos