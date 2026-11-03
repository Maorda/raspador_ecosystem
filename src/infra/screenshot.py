import os
from datetime import datetime
from playwright.async_api import Page

from infra.logger import get_logger

logger = get_logger("screenshot_util")


async def take_debug_screenshot(page: Page, prefix: str) -> None:
    """Toma una captura de pantalla de depuración y la guarda en ./debug_screenshots/"""
    try:
        os.makedirs("debug_screenshots", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filepath = os.path.join("debug_screenshots", f"{prefix}_{timestamp}.png")
        await page.screenshot(path=filepath, full_page=True)
        logger.info(f"Captura de pantalla de depuración guardada en: {filepath}")
    except Exception as ex:
        logger.warning(f"No se pudo guardar la captura de pantalla de depuración: {ex}")