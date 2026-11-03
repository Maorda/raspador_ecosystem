from __future__ import annotations

import os
import re
from typing import Any, Dict, List
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from core.result import Result
from strategies.base import BaseStrategy
from strategies.mixins import JSCapableMixin
from infra.database import DatabaseManager
from infra.logger import get_logger
from infra.screenshot import take_debug_screenshot
from plugins.remaju.interceptors.factory import crear_motor_remaju
from interceptor_motor import ModalCloseError, SpinnerTimeoutError

# Módulos especializados inyectados
from plugins.remaju.pre_extract import PreExtractValidator
from plugins.extraccion import RemajuExtractor
from plugins.navigation import RemajuNavigator
from plugins.downloads import RemajuDownloader
from core.blackboard import ScrapingBlackboard

# Utilidades desacopladas y constantes
from plugins.remaju.persistence import StatePersistenceManager
from infra.pure_utils import sanitizar_texto, verificar_patron_partida
from plugins.remaju.schema_map import SCHEMA_MAP
from core.cqrs import CommandDispatcher, RegisterExpedienteCommand

logger = get_logger("remaju_plugin")


class SearchExpedienteStrategy(BaseStrategy, JSCapableMixin):
    """Estrategia orquestadora limpia, sin redundancias de PDF y apoyada en módulos puros."""

    SELECTOR_TARJETAS = '[id="formBuscarRematesPublicados:listaRemate_content"] .card.azul'
    SELECTOR_BOTON_DETALLE = 'button:has-text("Detalle"), a:has-text("Detalle")'

    PATRON_PARTIDA_REGISTRAL = re.compile(r"P?\d{8}")
    PDF_DOWNLOAD_DIR = "downloads_pdf"
    MATERIA_EXCLUIDA = "obligacion de dar suma por alimentos"

    def __init__(self, blackboard: ScrapingBlackboard | None = None) -> None:
        self.db_manager = DatabaseManager()
        self.dispatcher = CommandDispatcher(self.db_manager)
        self.blackboard = blackboard or ScrapingBlackboard(self.db_manager)
        self.state_manager = StatePersistenceManager(
            procesados_file="estado_procesamiento/remates_procesados.json",
            manual_file="revision_manual/errores_expedientes.json"
        )

    async def execute(self, tab: Any, context: dict[str, Any], **kwargs: Any) -> Result[List[Dict[str, Any]]]:
        page: Page = tab
        motor = crear_motor_remaju()
        extracted_records = []

        try:
            logger.info("syncing_initial_state_post_login")
            await motor.execute_all(page)

            logger.info("navigating_to_judicial_auctions_search")
            await page.click("#linkRemateJudicial a", timeout=10000)
            await page.click("#menuForm\\:j_idt76", timeout=10000)
            await motor.execute_all(page)

            pre_validator = PreExtractValidator(page)
            extractor = RemajuExtractor(page, SCHEMA_MAP, pre_validator)
            downloader = RemajuDownloader(page, descargas_path=self.PDF_DOWNLOAD_DIR)
            navigator = RemajuNavigator(page)

            has_next_page = True
            page_number = 1

            while has_next_page:
                logger.info("processing_results_page", page_number=page_number)
                await navigator.esperar_listado(timeout=15000)

                count_cards = await page.locator(self.SELECTOR_TARJETAS).count()
                logger.info("cards_detected_on_page", count=count_cards, page_number=page_number)

                for index in range(count_cards):
                    expediente_id = f"EXP-P{page_number}-C{index+1}"
                    num_expediente = expediente_id  
                    
                    try:
                        logger.info("processing_card_item", current=index + 1, total=count_cards, page=page_number)

                        card = page.locator(self.SELECTOR_TARJETAS).nth(index)
                        
                        # (Opcional avanzado): Si el texto de la tarjeta contiene el número de remate/convocatoria, 
                        # podrías validarlo aquí mismo antes de hacer clic en "Detalle" para ahorrar tiempo de navegación.

                        btn_detalle = card.locator(self.SELECTOR_BOTON_DETALLE).first
                        await btn_detalle.wait_for(state="visible", timeout=5000)
                        await btn_detalle.click()
                        await motor.execute_all(page)

                        await pre_validator.esperar_detalle_cargado(motor_sincronizar_fn=motor.execute_all)

                        # 🌟 USO DEL EXTRACTOR CONFIGURADO CON SCHEMA_MAP
                        # Esto garantiza que remate, inmuebles (con departamento) y cronograma se mapeen correctamente
                        datos_completos = await extractor.extract_tab_remate_completo(motor_sincronizar_fn=motor.execute_all)
                        
                        remate_info = datos_completos.get("remate", {})
                        inmuebles_lista = datos_completos.get("inmuebles", [])
                        inmueble_info = inmuebles_lista[0] if inmuebles_lista else {}
                        cronograma_info = datos_completos.get("cronograma", {})

                        # Rescate seguro del departamento utilizando SCHEMA_MAP / inmueble_info
                        departamento = (
                            inmueble_info.get("departamento") or 
                            remate_info.get("departamento") or 
                            "NO ESPECIFICADO"
                        )
                        inmueble_info["departamento"] = departamento

                        num_remate = sanitizar_texto(remate_info.get("resolucion", "")) or expediente_id
                        convocatoria = sanitizar_texto(remate_info.get("convocatoria", ""))
                        num_expediente = sanitizar_texto(remate_info.get("expediente", "")) or expediente_id
                        
                        datos_completos["expediente_id"] = num_expediente

                        # 🛑 VALIDACIÓN TEMPRANA DE IDEMPOTENCIA
                        if self.state_manager.esta_procesado(num_remate, convocatoria):
                            print(f"\n[SALTANDO REPETIDO] Remate ya procesado anteriormente: {num_remate} ({convocatoria})")
                            await navigator.regresar_a_bandeja(motor_sincronizar_fn=motor.execute_all)
                            continue

                        # Descarga de PDF y registro inmediato en Base de Datos
                        nombre_pdf = await downloader.download_resolucion_pdf(expediente_num=num_expediente)
                        datos_completos["pdf_path"] = nombre_pdf

                        materia = sanitizar_texto(remate_info.get("materia", "")).lower()
                        if self.MATERIA_EXCLUIDA in materia:
                            logger.info("expediente_excluded_by_subject", materia=materia)
                        else:
                            cmd = RegisterExpedienteCommand(
                                numero_expediente=num_expediente,
                                organo_jurisdiccional=remate_info.get("distritoJudicial"),
                                remate_info=remate_info, 
                                inmueble_info=inmueble_info,
                                cronograma_info=cronograma_info,
                                pdf_path=datos_completos.get("pdf_path"), 
                                status="COMPLETED"
                            )
                            cmd_result = self.dispatcher.execute_register_expediente(cmd)
                            if not cmd_result.is_success:
                                logger.error("database_registration_failed", error=cmd_result.error)

                            extracted_records.append(datos_completos)
                            
                            self.state_manager.guardar_procesado(num_remate, convocatoria, datos_completos)
                            self.state_manager.limpiar_error_manual(num_expediente)

                            print(f"\n[GUARDADO EXITOSO EN BD] Pág: {page_number} | Tarjeta: {index+1}/{count_cards}")
                            print(f" -> Expediente: {num_expediente} | Remate: {num_remate} ({convocatoria})")
                            print(f" -> Departamento: {departamento} | Fases de Cronograma: {len(cronograma_info)}\n")

                        await navigator.regresar_a_bandeja(motor_sincronizar_fn=motor.execute_all)

                    except Exception as card_err:
                        logger.error("card_processing_failed", expediente=num_expediente, error=str(card_err), exc_info=True)
                        await take_debug_screenshot(page, f"error_tarjeta_p{page_number}_c{index+1}")
                        
                        # 📝 REGISTRO EN REVISIÓN MANUAL CON EL NÚMERO DE EXPEDIENTE REAL
                        self.state_manager.registrar_error_manual(num_expediente, str(card_err))

                        print(f"\n[ERROR EN TARJETA -> DERIVADO A MANUAL] Expediente: {num_expediente}")
                        print(f" -> Motivo: {card_err}\n")

                        try:
                            await navigator.regresar_a_bandeja(motor_sincronizar_fn=motor.execute_all)
                        except Exception:
                            pass

                avanzo = await navigator.avanzar_pagina(motor_sincronizar_fn=motor.execute_all)
                if avanzo:
                    page_number += 1
                else:
                    has_next_page = False
                    logger.info("pagination_completed_successfully")

            return Result.ok(extracted_records)

        except (ModalCloseError, SpinnerTimeoutError, PlaywrightTimeoutError) as err:
            logger.error("critical_error_in_search_strategy", error=str(err))
            await take_debug_screenshot(page, "search_strategy_error")
            return Result.fail(str(err), "REMAJU_SEARCH_FAILED")
        except Exception as e:
            logger.exception("unexpected_exception_in_search_strategy")
            await take_debug_screenshot(page, "search_strategy_critical_exception")
            return Result.fail(str(e), "REMAJU_SEARCH_FAILED")