from __future__ import annotations
import re
from pathlib import Path
import fitz  # PyMuPDF para validar integridad del PDF
from typing import Any, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from infra.logger import get_logger

logger = get_logger("remaju_plugin")


class RemajuDownloader:
    """Módulo agnóstico y especializado para la gestión, descarga y validación de resoluciones PDF en REMAJU."""

    def __init__(self, page: Optional[Page], descargas_path: Path | str = "./descargas_resoluciones") -> None:
        self.page = page
        self.descargas_path = Path(descargas_path)

    def _require_page(self) -> Page:
        """Valida y retorna la instancia activa de Playwright Page."""
        if self.page is None or self.page.is_closed():
            raise RuntimeError("La página de Playwright no está disponible o se encuentra cerrada.")
        return self.page

    def sanitizar_texto(self, texto: Any) -> str:
        if texto is None:
            return ""
        return re.sub(r"\s+", " ", str(texto)).strip()

    async def download_resolucion_pdf(self, expediente_num: str, selector_panel: str = "") -> str:
        """Descarga, nombra limpiamente y valida el PDF de resolución basado en el número de expediente."""
        page = self._require_page()
        ruta_destino = self.descargas_path.expanduser()
        ruta_destino.mkdir(parents=True, exist_ok=True)
        
        nombre_seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.sanitizar_texto(expediente_num)).strip("._")
        if not nombre_seguro:
            nombre_seguro = "sin_expediente"
            
        nombre_archivo = f"resolucion_{nombre_seguro}.pdf"
        destino = ruta_destino / nombre_archivo
        
        try:
            # Selector flexible para capturar el botón o enlace de descarga de la resolución
            selector_enlace = 'button:has-text("Aviso"), a:has-text("Aviso"), [id*="j_idt238"], a.ui-commandlink[title="Descargar"]'
            if selector_panel:
                selector_enlace = f"{selector_panel} {selector_enlace}"
                
            enlace_pdf = page.locator(selector_enlace).first
            if await enlace_pdf.count() == 0:
                logger.warning("enlace_descarga_no_encontrado", expediente=expediente_num)
                return ""
                
            await enlace_pdf.wait_for(state="visible", timeout=10000)
            async with page.expect_download(timeout=15000) as descarga_info:
                await enlace_pdf.click()
                
            descarga = await descarga_info.value
            if await descarga.failure():
                logger.warning("fallo_descarga_archivo_fisico", expediente=expediente_num)
                return ""
                
            await descarga.save_as(str(destino))
            
            if not self._validar_pdf(destino, expediente_num):
                destino.unlink(missing_ok=True)
                return ""
                
            logger.info("resolucion_descargada_exitosamente", expediente=expediente_num, destino=str(destino))
            return nombre_archivo
            
        except PlaywrightTimeoutError:
            logger.warning("timeout_descarga_resolucion", expediente=expediente_num)
            return ""
        except Exception:
            logger.exception("error_completando_descarga_resolucion", expediente=expediente_num)
            return ""

    def _validar_pdf(self, destino: Path, expediente_num: str) -> bool:
        """Verifica que el archivo PDF exista, pueda abrirse y no esté vacío."""
        try:
            doc = fitz.open(str(destino))
            if len(doc) == 0:
                logger.warning("pdf_descargado_vacio", expediente=expediente_num)
                doc.close()
                return False
            doc.close()
            return True
        except Exception as ex:
            logger.warning("error_validando_estructura_pdf", expediente=expediente_num, error=str(ex))
            return False