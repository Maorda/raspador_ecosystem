from __future__ import annotations

import os
import json
from typing import Optional
from plugins.remaju.strategies import AuthenticateStrategy, SearchExpedienteStrategy
from plugins.registry import BasePlugin, register_plugin
from core.blackboard import ScrapingBlackboard
from infra.database import DatabaseManager
from infra.logger import get_logger
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

logger = get_logger("remaju_plugin")

@register_plugin("remaju")
class RemajuPlugin(BasePlugin):
    """Plugin de integración REMAJU utilizando BaseStrategy y Playwright."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}
        self.headless: bool = self.config.get("headless", False)
        
        self.db_manager = DatabaseManager()
        self.auth_strategy = AuthenticateStrategy()
        self.search_strategy = SearchExpedienteStrategy()
        
        self._initialized: bool = False
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def initialize(self) -> None:
        """Inicializa Playwright, el navegador Chromium, contexto y pestaña."""
        try:
            logger.info("Iniciando recursos de Playwright para REMAJU...", extra={"headless": self.headless})
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-dev-shm-usage", "--no-sandbox"]
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True
            )
            self._page = await self._context.new_page()
            
            self._initialized = True
            logger.info("remaju_plugin_initialized", integration_ready=True)
        except Exception as e:
            logger.exception("Error crítico al inicializar RemajuPlugin.")
            await self.cleanup()
            raise RuntimeError(f"REMAJU_INIT_FAILED: {str(e)}")

    async def run(self, blackboard: ScrapingBlackboard) -> None:
        """Ejecuta autenticación y la estrategia de búsqueda incremental tarjeta por tarjeta."""
        if not self._initialized or not self._page:
            raise RuntimeError("RemajuPlugin debe inicializarse antes de run().")
        
        context_dict = getattr(blackboard, "context", {}) or {}
        params_dict = getattr(blackboard, "params", {}) or {}

        # 1. Autenticación
        auth = await self.auth_strategy.execute(self._page, context_dict, **params_dict)
        if not auth.is_success:
            raise RuntimeError(f"{auth.error_category}: {auth.error}")

        # 2. Búsqueda y procesamiento incremental tarjeta por tarjeta (Ruta Normal)
        search = await self.search_strategy.execute(self._page, context_dict, **params_dict)
        if not search.is_success:
            raise RuntimeError(f"{search.error_category}: {search.error}")

        # 3. FASE 2: Procesar automáticamente los pendientes del JSON usando búsqueda por número de expediente
        await self._procesar_pendientes_manuales(blackboard)

        logger.info("Flujo completo de REMAJU ejecutado exitosamente.")

    async def _procesar_pendientes_manuales(self, blackboard: ScrapingBlackboard) -> None:
        """Subrutina que lee el JSON de pendientes y reintenta la búsqueda por número de expediente."""
        ruta_json = self.config.get("ruta_pendientes_json", "revision_manual/errores_expedientes.json")
        if not os.path.exists(ruta_json):
            return

        try:
            with open(ruta_json, "r", encoding="utf-8") as f:
                pendientes = json.load(f)
        except Exception as e:
            logger.error("Error al leer el archivo JSON de pendientes: %s", e)
            return

        if not pendientes:
            logger.info("No hay pendientes en el archivo JSON de revisión manual.")
            return

        logger.info("Iniciando subrutina de resolución automática para registros pendientes...")
        pendientes_restantes = {}
        context_dict = getattr(blackboard, "context", {}) or {}
        params_dict = getattr(blackboard, "params", {}) or {}

        items_a_procesar = pendientes.items() if isinstance(pendientes, dict) else [(item.get("expediente_id"), item) for item in pendientes]

        for expediente_id, item in items_a_procesar:
            if not expediente_id:
                continue

            logger.info("Reintentando búsqueda directa para expediente pendiente: %s", expediente_id)
            try:
                params_busqueda = params_dict.copy()
                params_busqueda["expediente_id"] = expediente_id

                # Reintento usando la estrategia de búsqueda por expediente
                search_res = await self.search_strategy.execute(self._page, context_dict, **params_busqueda)
                if search_res.is_success:
                    logger.info("Expediente pendiente %s resuelto exitosamente en ruta manual.", expediente_id)
                else:
                    logger.warning("El expediente %s sigue sin resolverse en búsqueda manual.", expediente_id)
                    pendientes_restantes[expediente_id] = item
            except Exception as err:
                logger.error("Error procesando expediente pendiente %s en ruta manual: %s", expediente_id, err)
                pendientes_restantes[expediente_id] = item

        # Sincronizar archivo JSON con los pendientes restantes
        try:
            with open(ruta_json, "w", encoding="utf-8") as f:
                json.dump(pendientes_restantes, f, ensure_ascii=False, indent=4)
            logger.info("Archivo de pendientes sincronizado. Casos restantes para revisión humana: %s", len(pendientes_restantes))
        except Exception as e:
            logger.error("Error actualizando el archivo JSON de pendientes restantes: %s", e)

    async def cleanup(self) -> None:
        """Garantiza el cierre ordenado de recursos."""
        try:
            logger.info("Iniciando limpieza de recursos de RemajuPlugin...")
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as ex:
            logger.warning(f"Error durante la limpieza: {ex}")
        finally:
            self._initialized = False
            logger.info("remaju_plugin_cleanup_completed")