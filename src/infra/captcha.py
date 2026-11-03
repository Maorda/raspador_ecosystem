import ddddocr
from infra.logger import get_logger

logger = get_logger("captcha_resolver")


class CaptchaResolver:
    """Resuelve el captcha visual de REMAJU utilizando ddddocr."""

    def __init__(self) -> None:
        self.ocr_engine = ddddocr.DdddOcr(show_ad=False)

    def resolver_bytes(self, image_bytes: bytes) -> str:
        """Recibe los bytes de una imagen de captcha y retorna el texto limpio en mayúsculas."""
        texto_extraido = self.ocr_engine.classification(image_bytes)
        return texto_extraido.upper().strip()