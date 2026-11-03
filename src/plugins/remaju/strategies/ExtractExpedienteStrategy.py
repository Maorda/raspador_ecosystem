
import os
from infra.logger import get_logger
from plugins.remaju.interceptors.factory import crear_motor_remaju
from plugins.remaju.pre_extract import PreExtractValidator
from plugins.remaju.extraccion import RemajuExtractor
from interceptor_motor.interceptors.spinner import SpinnerTimeoutError
from interceptor_motor.contracts.base_modal import ModalCloseError
from typing import Any
from dotenv import load_dotenv
from core.result import Result
from strategies.base import BaseStrategy
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from infra.screenshot import take_debug_screenshot

load_dotenv(r"D:\libs\scraper_ecosystem\.env")

logger = get_logger("remaju_plugin")

class ExtractExpedienteStrategy(BaseStrategy):
    """Estrategia de extracción sincronizada para obtener el detalle completo del expediente, 
    incluyendo múltiples inmuebles, partidas registrales y cronograma."""

    async def execute(self, tab: Any, context: dict[str, Any], **kwargs: Any) -> Result[dict[str, Any]]:
        page: Page = tab
        motor = crear_motor_remaju()
        
        try:
            logger.info("Sincronizando estado mediante motor interceptor antes de extraer...")
            await motor.execute_all(page)

            results_selector = "#tblResultadosExpediente"
            logger.info("Esperando tabla de resultados de expedientes...")
            await page.wait_for_selector(results_selector, state="visible", timeout=15000)

            # TODO: Aquí asumimos que ya estás haciendo clic en el expediente específico de la tabla 
            # para abrir la vista de detalle (formDetalleRemate). Si la estrategia de búsqueda ya te deja 
            # dentro del detalle, pasamos directo a la extracción.

            # Definir configuración de mapeo (puedes cargarla desde tu archivo de config del plugin)
            app_config = kwargs.get("app_config") or context.get("app_config") or {}

            # Instanciar validador previo y extractor optimizado
            pre_validator = PreExtractValidator(page)
            extractor = RemajuExtractor(page, app_config, pre_validator)

            # Definir función de sincronización para pasar al extractor
            async def motor_sincronizar(p: Page):
                await motor.execute_all(p)

            logger.info("Iniciando extracción completa de pestañas (Remate, Inmuebles, Cronograma)...")
            datos_completos = await extractor.extract_tab_remate_completo(motor_sincronizar_fn=motor_sincronizar)

            extracted_data = {
                "expediente_id": kwargs.get("expediente_id") or context.get("expediente_id"),
                "status": "extracted",
                "detalle": datos_completos
            }

            logger.info("Extracción completa de expediente finalizada correctamente.")
            return Result.ok(extracted_data)

        except (ModalCloseError, SpinnerTimeoutError, PlaywrightTimeoutError) as err:
            logger.error(f"Error durante la extracción de expediente: {err}")
            await take_debug_screenshot(page, "extract_expediente_error")
            return Result.fail(str(err), "REMAJU_EXTRACTION_FAILED")
        except Exception as e:
            logger.exception("Error inesperado en ExtractExpedienteStrategy.")
            await take_debug_screenshot(page, "extract_expediente_critical_exception")
            return Result.fail(str(e), "REMAJU_EXTRACTION_FAILED")