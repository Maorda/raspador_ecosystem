from infra.captcha import CaptchaResolver
import os
from infra.logger import get_logger
from plugins.remaju.interceptors.factory import crear_motor_remaju
from interceptor_motor.interceptors.spinner import SpinnerTimeoutError
from interceptor_motor.contracts.base_modal import ModalCloseError
from typing import Any
from dotenv import load_dotenv
from core.result import Result
from strategies.base import BaseStrategy
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
import base64
from infra.screenshot import take_debug_screenshot
load_dotenv(r"D:\libs\scraper_ecosystem\.env")

logger = get_logger("remaju_plugin")

class AuthenticateStrategy(BaseStrategy):
    """Estrategia de autenticación ajustada a los IDs reales de JSF/PrimeFaces en REMAJU."""

    LOGIN_URL = "https://remaju.pj.gob.pe/remaju/pages/seguridad/login.xhtml"
    SUCCESS_URL = "https://remaju.pj.gob.pe/remaju/pages/inicio.xhtml"
    MAX_RETRIES = 5

    async def execute(self, tab: Any, context: dict[str, Any], **kwargs: Any) -> Result[bool]:
        page: Page = tab
        try:
            logger.info(f"Navegando a la URL de login de REMAJU: {self.LOGIN_URL}")
            await page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

            # 1. Ejecutar motor interceptor para manejar el spinner inicial y modales
            motor = crear_motor_remaju()
            logger.info("Ejecutando interceptores del motor para sincronizar spinner inicial...")
            await motor.execute_all(page)

            # Cerrar modal de aviso importante (#dlgPopUp) mediante #btnAceptarPopup si está visible
            btn_aceptar = page.locator("#btnAceptarPopup")
            if await btn_aceptar.is_visible(timeout=4000):
                logger.info("Cerrando modal de 'Aviso Importante' haciendo clic en #btnAceptarPopup...")
                await btn_aceptar.click()
                await page.wait_for_selector("#dlgPopUp", state="hidden", timeout=5000)
                logger.info("Modal cerrado y oculto correctamente.")

            # 2. Seleccionar la opción "Con Casilla"
            logger.info("Seleccionando la opción de login 'Con Casilla'...")
            try:
                casilla_elem = page.locator("text=Con Casilla").first
                if await casilla_elem.is_visible(timeout=4000):
                    await casilla_elem.click()
                else:
                    await page.click("[id*='casilla'], [value*='casilla']", timeout=3000)
                logger.info("Opción 'Con Casilla' seleccionada. Sincronizando el estado...")
                await motor.execute_all(page)
            except Exception as ex:
                logger.warning(f"Advertencia al seleccionar 'Con Casilla': {ex}. Intentando continuar...")

            # 3. Obtener credenciales del .env
            username = os.getenv("REMAJU_USER")
            password = os.getenv("REMAJU_PASSWORD")

            if not username or not password:
                logger.error("Credenciales REMAJU_USER o REMAJU_PASSWORD no encontradas en el .env.")
                await take_debug_screenshot(page, "auth_missing_credentials")
                return Result.fail("Credenciales de REMAJU no configuradas en el archivo .env.", "REMAJU_AUTH_FAILED")

            # SELECTORES REALES DEL DOM JSF/PRIMEFACES
            user_selector = "#frmLogin\\:usuario"
            pass_selector = "#frmLogin\\:claveConCasilla"
            captcha_img_selector = "#frmLogin\\:imgCaptcha"
            captcha_input_selector = "#frmLogin\\:captcha"
            submit_selector = "#frmLogin\\:btnLogin"

            # Esperar a que el campo de usuario real esté visible
            logger.info(f"Esperando selector de usuario real: {user_selector}...")
            await page.wait_for_selector(user_selector, state="visible", timeout=15000)
            await page.fill(user_selector, username)

            resolver = CaptchaResolver()

            # 4. Bucle de hasta 5 reintentos para contraseña y captcha
            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    logger.info(f"=== Intento de autenticación {attempt} de {self.MAX_RETRIES} ===")

                    # Rellenar contraseña en #frmLogin:claveConCasilla
                    await page.fill(pass_selector, password)

                    # Obtener imagen del captcha
                    await page.wait_for_selector(captcha_img_selector, state="visible", timeout=10000)
                    img_element = await page.query_selector(captcha_img_selector)

                    if not img_element:
                        logger.warning(f"Intento {attempt}: No se encontró la imagen del captcha.")
                        await take_debug_screenshot(page, f"auth_attempt_{attempt}_no_captcha_img")
                        if attempt == self.MAX_RETRIES:
                            return Result.fail("No se encontró la imagen del captcha en el DOM.", "REMAJU_CAPTCHA_NOT_FOUND")
                        continue

                    src = await img_element.get_attribute("src")
                    if not src:
                        logger.warning(f"Intento {attempt}: El atributo src del captcha está vacío.")
                        await take_debug_screenshot(page, f"auth_attempt_{attempt}_empty_src")
                        if attempt == self.MAX_RETRIES:
                            return Result.fail("El atributo src del captcha está vacío.", "REMAJU_CAPTCHA_EMPTY_SRC")
                        continue

                    if "base64," in src:
                        base64_data = src.split("base64,")[1]
                        captcha_bytes = base64.b64decode(base64_data)
                    else:
                        captcha_bytes = await img_element.screenshot()

                    captcha_text = resolver.resolver_bytes(captcha_bytes)
                    logger.info(f"Captcha resuelto (Intento {attempt}): {captcha_text}")

                    # Llenar campo del captcha
                    await page.fill(captcha_input_selector, "")
                    await page.fill(captcha_input_selector, captcha_text)

                    logger.info("Haciendo clic en 'Iniciar Sesión'...")
                    await page.click(submit_selector)

                    # =========================================================================
                    # ESCÁNER DIAGNÓSTICO DE ELEMENTOS VISIBLES TRAS EL CLIC DE LOGIN (F-STRING FIX)
                    # =========================================================================
                    try:
                        import asyncio
                        await asyncio.sleep(0.3)
                        html_detectado = await page.evaluate("""() => {
                            const candidatos = document.querySelectorAll('[id*="dlg"], [id*="block"], [id*="status"], [class*="block"], [class*="loading"], [class*="spinner"], img[src*="gif"]');
                            const visibles = [];
                            candidatos.forEach(el => {
                                const rect = el.getBoundingClientRect();
                                const styles = window.getComputedStyle(el);
                                if (styles.display !== 'none' && styles.visibility !== 'hidden' && styles.opacity !== '0' && (rect.width > 0 || rect.height > 0)) {
                                    visibles.push({
                                        id: el.id,
                                        className: el.className,
                                        tag: el.tagName,
                                        outerHTML: el.outerHTML.substring(0, 300)
                                    });
                                }
                            });
                            return visibles;
                        }""")
                        logger.warning(f"🔍 ELEMENTOS VISIBLES TRAS EL CLIC DE LOGIN: {html_detectado}")
                    except Exception as diag_err:
                        logger.error(f"Error en escáner diagnóstico: {diag_err}")
                    # =========================================================================

                    # Sincronizar el motor para que atrape el spinner posterior al envío
                    try:
                        await motor.execute_all(page)
                    except Exception as motor_err:
                        logger.warning(f"Aviso del motor durante la sincronización del login: {motor_err}")

                    # Sincronizar spinner post-click o evaluar redirección
                    try:
                        await page.wait_for_url(self.SUCCESS_URL, timeout=8000)
                        logger.info("¡Inicio de sesión exitoso! Redirección a inicio.xhtml confirmada.")

                        # Sincronizar el motor para atrapar el spinner de carga de datos del dashboard
                        logger.info("Sincronizando el spinner de carga de datos en el dashboard...")
                        try:
                            await motor.execute_all(page)
                            logger.info("Spinner del dashboard sincronizado correctamente.")
                        except Exception as dashboard_motor_err:
                            logger.warning(f"Aviso al sincronizar el spinner del dashboard: {dashboard_motor_err}")

                        return Result.ok(True)
                    except PlaywrightTimeoutError:
                        logger.warning(f"Intento {attempt}: No se redirigió a {self.SUCCESS_URL}. Captcha incorrecto.")
                        await take_debug_screenshot(page, f"auth_attempt_{attempt}_failed_login")
                        if attempt == self.MAX_RETRIES:
                            return Result.fail(f"Se agotaron los {self.MAX_RETRIES} intentos de autenticación.", "REMAJU_AUTH_FAILED")

                except (ModalCloseError, SpinnerTimeoutError) as err:
                    logger.error(f"Error de motor interceptor en intento {attempt}: {err}")
                    await take_debug_screenshot(page, f"auth_attempt_{attempt}_interceptor_error")
                    if attempt == self.MAX_RETRIES:
                        return Result.fail(str(err), "REMAJU_AUTH_FAILED")
                except Exception as ex:
                    logger.warning(f"Excepción en intento {attempt}: {ex}")
                    await take_debug_screenshot(page, f"auth_attempt_{attempt}_exception")
                    if attempt == self.MAX_RETRIES:
                        return Result.fail(str(ex), "REMAJU_AUTH_FAILED")

            logger.error("Se superó el límite máximo de 5 intentos de inicio de sesión.")
            await take_debug_screenshot(page, "auth_max_retries_exhausted")
            return Result.fail("Fallo en la autenticación tras agotar los 5 reintentos permitidos.", "REMAJU_AUTH_FAILED")

        except Exception as e:
            logger.exception("Excepción crítica inesperada en AuthenticateStrategy.")
            await take_debug_screenshot(page, "auth_critical_exception")
            return Result.fail(str(e), "REMAJU_AUTH_FAILED")